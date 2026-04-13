"""
stubpy.resolver
===============

Parameter resolution — the core ``**kwargs`` / ``*args`` backtracing logic.

Two public entry points cover every resolution scenario:

* :func:`resolve_params` — resolves a **method** on a class using the
  class MRO.  Three strategies are applied in priority order:

  1. *No variadics* — own parameters returned unchanged.
  2. *cls()-call detection* — a ``@classmethod`` body contains
     ``cls(..., **kwargs)``; resolve against ``cls.__init__``.
  3. *MRO walk* — iterate ancestors that define the same method,
     collecting concrete parameters until all variadics are resolved.
     If variadics remain after the MRO is exhausted, module-level
     function targets (from *ast_info*) are resolved via *namespace*.

* :func:`resolve_function_params` — resolves a **module-level function**
  using AST-detected forwarding targets and a runtime namespace lookup.
  When a target is a class constructor (a ``type``), resolution
  delegates to :func:`resolve_params` so the chain continues correctly.

Both entry points call each other when mixed chains are encountered
(method → function → method, function → class → method, etc.).
Cycle detection via a *_seen* frozenset prevents infinite recursion.

Shared low-level helpers
------------------------
* :func:`_normalise_kind` — promotes ``POSITIONAL_ONLY`` to
  ``POSITIONAL_OR_KEYWORD`` when a param is absorbed by ``**kwargs``.
* :func:`_merge_concrete_params` — deduplicates and normalises params
  from a source list into an accumulated output list.
* :func:`_finalise_variadics` — re-inserts ``*args`` and residual
  ``**kwargs`` in the correct position after merging.

Architecture note
-----------------
AST *scanning* (detecting where ``**kwargs`` / ``*args`` is forwarded)
lives exclusively in :mod:`stubpy.ast_pass` — specifically in
:meth:`~stubpy.ast_pass.ASTHarvester._harvest_function`, which populates
:attr:`~stubpy.ast_pass.FunctionInfo.kwargs_forwarded_to` and
:attr:`~stubpy.ast_pass.FunctionInfo.args_forwarded_to` for every
function and method definition.

This module handles *resolution only* — it reads pre-scanned metadata
and performs runtime lookups, never re-parsing source code except in the
``_detect_cls_call`` fallback path (backward compat for callers that
omit ``ast_info``).
"""
from __future__ import annotations

import ast
import inspect
import textwrap
import typing
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .ast_pass import FunctionInfo

_VAR_POS  = inspect.Parameter.VAR_POSITIONAL
_VAR_KW   = inspect.Parameter.VAR_KEYWORD
_KW_ONLY  = inspect.Parameter.KEYWORD_ONLY
_POS_ONLY = inspect.Parameter.POSITIONAL_ONLY
_POS_KW   = inspect.Parameter.POSITIONAL_OR_KEYWORD

#: A ``(parameter, hints-dict)`` pair produced by the resolver entry points.
ParamWithHints = tuple[inspect.Parameter, dict[str, Any]]


# ---------------------------------------------------------------------------
# Low-level introspection helpers
# ---------------------------------------------------------------------------

def _get_hints(fn: Any) -> dict[str, Any]:
    """Safely retrieve resolved type hints, unwrapping descriptors.

    Parameters
    ----------
    fn : Any
        A callable, classmethod, staticmethod, or property.

    Returns
    -------
    dict
        ``{name: annotation}`` or ``{}`` on failure.
    """
    if fn is None:
        return {}
    raw: Any = fn
    if isinstance(raw, (classmethod, staticmethod)):
        raw = raw.__func__
    elif isinstance(raw, property):
        raw = raw.fget
    try:
        return typing.get_type_hints(raw)
    except Exception:
        return getattr(raw, "__annotations__", {})


def _get_raw_params(
    cls: type, method_name: str
) -> tuple[list[inspect.Parameter] | None, dict[str, Any]]:
    """Return own parameters and hints for a method defined directly on *cls*.

    Parameters
    ----------
    cls : type
        The class to inspect.
    method_name : str
        Name of the method.

    Returns
    -------
    params : list of inspect.Parameter or None
        Parameter list with ``self``/``cls`` excluded, or ``None`` if
        the method is not in ``cls.__dict__``.
    hints : dict
        Resolved type hints, or ``{}`` on failure.
    """
    raw = cls.__dict__.get(method_name)
    if raw is None:
        return None, {}

    unwrapped: Any = raw
    if isinstance(unwrapped, (classmethod, staticmethod)):
        unwrapped = unwrapped.__func__
    elif isinstance(unwrapped, property):
        unwrapped = unwrapped.fget

    try:
        sig = inspect.signature(unwrapped)
    except (ValueError, TypeError):
        return None, {}

    params = [
        p for name, p in sig.parameters.items()
        if name not in ("self", "cls")
    ]
    hints = _get_hints(raw)
    return params, hints


# ---------------------------------------------------------------------------
# Shared transformation helpers  (used by both public entry points)
# ---------------------------------------------------------------------------

def _normalise_kind(p: inspect.Parameter) -> inspect.Parameter:
    """Promote ``POSITIONAL_ONLY`` to ``POSITIONAL_OR_KEYWORD``.

    When a positional-only parameter from a parent is absorbed by a
    child's ``**kwargs``, callers pass it by keyword through the child
    interface.  Keeping it ``POSITIONAL_ONLY`` would emit a misplaced
    ``/`` separator.  This helper corrects that.
    """
    if p.kind == _POS_ONLY:
        return p.replace(kind=_POS_KW)
    return p


def _merge_concrete_params(
    base: list[ParamWithHints],
    seen: set[str],
    source: list[ParamWithHints],
) -> None:
    """Merge non-variadic params from *source* into *base*, deduplicating by name.

    ``VAR_POSITIONAL`` and ``VAR_KEYWORD`` entries in *source* are skipped
    — those are handled separately by :func:`_finalise_variadics`.
    ``POSITIONAL_ONLY`` parameters are promoted via :func:`_normalise_kind`.

    Parameters
    ----------
    base : list of ParamWithHints
        Accumulated output — modified in place.
    seen : set of str
        Names already present in *base* — modified in place.
    source : list of ParamWithHints
        Resolved parameter list to merge from.
    """
    for p, h in source:
        if p.kind in (_VAR_POS, _VAR_KW):
            continue
        if p.name in seen:
            continue
        base.append((_normalise_kind(p), h))
        seen.add(p.name)


def _finalise_variadics(
    merged: list[ParamWithHints],
    own_params: list[inspect.Parameter],
    own_hints: dict[str, Any],
    still_var_pos: bool,
    still_var_kw: bool,
) -> list[ParamWithHints]:
    """Re-insert ``*args`` and residual ``**kwargs`` at correct positions.

    Called after all concrete parameters have been merged.

    * ``*args`` is inserted before the first ``KEYWORD_ONLY`` or
      ``VAR_KEYWORD`` parameter, if still unresolved *or* if the original
      ``*args`` carried an explicit type annotation.
    * ``**kwargs`` is appended last, only when still unresolved.

    Parameters
    ----------
    merged : list of ParamWithHints
        Merged concrete-param list.  Modified in place.
    own_params : list of inspect.Parameter
        Original parameter list — source of the ``*args`` / ``**kwargs``
        objects (with their annotations and defaults).
    own_hints : dict
        Type hints for *own_params*.
    still_var_pos : bool
        ``True`` when ``*args`` was not fully resolved.
    still_var_kw : bool
        ``True`` when ``**kwargs`` was not fully resolved.

    Returns
    -------
    list of ParamWithHints
        *merged* with variadics inserted / appended.
    """
    pos_param = next((p for p in own_params if p.kind == _VAR_POS), None)
    if pos_param is not None:
        is_typed = pos_param.annotation is not inspect.Parameter.empty
        if still_var_pos or is_typed:
            insert_at = next(
                (i for i, (p, _) in enumerate(merged) if p.kind in (_KW_ONLY, _VAR_KW)),
                len(merged),
            )
            merged.insert(insert_at, (pos_param, own_hints))

    if still_var_kw:
        kw_param = next((p for p in own_params if p.kind == _VAR_KW), None)
        if kw_param:
            merged.append((kw_param, own_hints))

    return merged


def _enforce_signature_validity(
    merged: list[ParamWithHints],
) -> list[ParamWithHints]:
    """Promote non-default params to KEYWORD_ONLY when they follow a default param.

    Python requires that a parameter without a default value never follows a
    parameter that has one (outside of ``/`` or ``*`` separation).  This
    situation arises when params are *absorbed* from a forwarding target:

    .. code-block:: python

        def make_color(r, g, b, a=1.0): ...
        def make_red(r=1.0, **kwargs): make_color(r=r, **kwargs)
        #  → merges to: make_red(r=1.0, g, b, a=1.0)  ← invalid!
        #  → fixed to:  make_red(r=1.0, *, g, b, a=1.0)  ← valid

    The fix is correct semantically: absorbed params came in via ``**kwargs``,
    so callers must supply them by keyword anyway.  Promoting them to
    ``KEYWORD_ONLY`` makes that contract explicit in the stub.

    ``VAR_POSITIONAL`` and ``VAR_KEYWORD`` sentinels are left untouched.

    Parameters
    ----------
    merged : list of ParamWithHints
        The fully-merged list (before adding ``*`` / ``/`` sentinels).

    Returns
    -------
    list of ParamWithHints
        Same list with any offending parameters promoted to ``KEYWORD_ONLY``.
    """
    # Find the index of the first parameter that has a default value.
    first_default_idx: int | None = None
    for i, (p, _) in enumerate(merged):
        if p.kind in (_VAR_POS, _VAR_KW):
            continue
        if p.default is not inspect.Parameter.empty:
            first_default_idx = i
            break

    if first_default_idx is None:
        return merged  # no defaults → nothing to fix

    # Any non-variadic, non-KEYWORD_ONLY param without a default that appears
    # after first_default_idx must be promoted.
    result: list[ParamWithHints] = []
    for i, (p, h) in enumerate(merged):
        if (
            i > first_default_idx
            and p.kind not in (_VAR_POS, _VAR_KW, _KW_ONLY)
            and p.default is inspect.Parameter.empty
        ):
            p = p.replace(kind=_KW_ONLY)
        result.append((p, h))
    return result


# ---------------------------------------------------------------------------
# Class-method resolution helpers
# ---------------------------------------------------------------------------

def _scan_cls_call_inline(
    cls: type, method_name: str
) -> tuple[bool, set[str]]:
    """Inline AST scan for ``cls(...)`` — used when no FunctionInfo is available."""
    raw = cls.__dict__.get(method_name)
    if raw is None:
        return False, set()

    fn = raw.__func__ if isinstance(raw, classmethod) else raw

    try:
        src = textwrap.dedent(inspect.getsource(fn))
        tree = ast.parse(src)
    except Exception:
        return False, set()

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        is_cls_call = (
            (isinstance(func, ast.Name) and func.id == "cls")
            or (
                isinstance(func, ast.Attribute)
                and func.attr == "__init__"
                and isinstance(func.value, ast.Name)
                and func.value.id == "cls"
            )
        )
        if not is_cls_call:
            continue
        if any(kw.arg is None for kw in node.keywords):
            explicit = {kw.arg for kw in node.keywords if kw.arg is not None}
            return True, explicit

    return False, set()


def _detect_cls_call(
    cls: type,
    method_name: str,
    ast_info: "FunctionInfo | None" = None,
) -> tuple[bool, set[str]]:
    """Detect the ``cls(..., **kwargs)`` pattern inside a classmethod.

    When a ``@classmethod`` body contains ``cls(**kwargs)`` or
    ``cls.__init__(..., **kwargs)``, the ``**kwargs`` should resolve
    against ``cls.__init__`` rather than MRO siblings.

    Uses pre-scanned *ast_info* when available (avoids a redundant
    source parse); falls back to :func:`_scan_cls_call_inline` otherwise.

    Parameters
    ----------
    cls : type
        The class that owns the method.
    method_name : str
        Name of the classmethod.
    ast_info : FunctionInfo, optional
        Pre-scanned metadata from the AST pre-pass stage.

    Returns
    -------
    detected : bool
        ``True`` if the ``cls(..., **kwargs)`` pattern was found.
    explicitly_passed : set of str
        Hardcoded keyword names in the call (e.g. ``{\"r\"}`` for
        ``cls(r=1, **kwargs)``).  Excluded from the resolved stub.
    """
    # Fast path: pre-scanned data already tells us about cls-forwarding
    if ast_info is not None:
        if "cls" in ast_info.kwargs_forwarded_to:
            # Confirmed cls() call — now recover explicit kw names
            _, explicit = _scan_cls_call_inline(cls, method_name)
            return True, explicit
        return False, set()

    # Fallback: no pre-scanned data
    return _scan_cls_call_inline(cls, method_name)


def _resolve_via_cls_call(
    cls: type,
    method_name: str,
    own_params: list[inspect.Parameter],
    own_hints: dict[str, Any],
    ast_info: "FunctionInfo | None" = None,
) -> list[ParamWithHints] | None:
    """Resolve ``**kwargs`` against ``cls.__init__`` when a cls-call is detected.

    Returns ``None`` when no cls-call was found so the caller can fall
    through to the MRO walk.
    """
    cls_call, explicit_kw = _detect_cls_call(cls, method_name, ast_info)
    if not cls_call:
        return None

    init_params = resolve_params(cls, "__init__")

    merged: list[ParamWithHints] = [
        (p, own_hints) for p in own_params if p.kind not in (_VAR_POS, _VAR_KW)
    ]
    seen = {p.name for p, _ in merged} | explicit_kw

    for p, h in init_params:
        if p.kind in (_VAR_POS, _VAR_KW):
            continue
        if p.name in seen:
            continue
        merged.append((_normalise_kind(p), h))
        seen.add(p.name)

    # Preserve residual **kwargs if __init__ itself is still open
    if any(p.kind == _VAR_KW for p, _ in init_params):
        kw_param = next((p for p in own_params if p.kind == _VAR_KW), None)
        if kw_param:
            merged.append((kw_param, own_hints))

    return merged


def _resolve_via_namespace(
    still_var_kw: bool,
    still_var_pos: bool,
    own_params: list[inspect.Parameter],
    own_hints: dict[str, Any],
    merged: list[ParamWithHints],
    seen_names: set[str],
    ast_info: "FunctionInfo | None",
    namespace: dict[str, Any],
    ast_info_by_name: "dict[str, FunctionInfo] | None",
    _seen: frozenset[str],
) -> tuple[bool, bool]:
    """Attempt to resolve remaining variadics via module-level namespace lookup.

    Called after the MRO walk (or any other strategy) when variadics are
    still unresolved.  This enables **method → function** chains: a method
    that forwards ``**kwargs`` to a standalone module function.

    Parameters
    ----------
    still_var_kw, still_var_pos : bool
        Which variadics remain unresolved.
    own_params : list
        Own parameter list (to find varidic param objects).
    own_hints : dict
        Own type hints.
    merged : list
        Accumulated output — modified in place.
    seen_names : set
        Names already in merged — modified in place.
    ast_info : FunctionInfo or None
        Pre-scanned metadata with ``kwargs_forwarded_to`` / ``args_forwarded_to``.
    namespace : dict
        The module ``__dict__`` for looking up callable targets.
    ast_info_by_name : dict or None
        Maps function name → FunctionInfo for recursive resolution.
    _seen : frozenset
        Cycle-detection set of names already being resolved.

    Returns
    -------
    still_var_kw, still_var_pos : bool
        Updated flags after namespace resolution.
    """
    if ast_info is None:
        return still_var_kw, still_var_pos

    kw_targets  = ast_info.kwargs_forwarded_to if still_var_kw  else []
    pos_targets = ast_info.args_forwarded_to   if still_var_pos else []

    # Deduplicate while preserving order; skip already-in-MRO targets
    visited: list[str] = []
    for t in kw_targets + pos_targets:
        if t not in visited and t not in ("cls", "self"):
            visited.append(t)

    for target_name in visited:
        if target_name in _seen:
            continue

        target_obj = namespace.get(target_name)
        if target_obj is None:
            continue

        # --- class constructor: delegate to resolve_params(__init__) ---
        if isinstance(target_obj, type):
            inner_seen = _seen | {target_name}
            resolved = resolve_params(
                target_obj, "__init__",
                namespace=namespace,
                ast_info_by_name=ast_info_by_name,
                _seen=inner_seen,
            )
            _merge_concrete_params(merged, seen_names, resolved)
            final_var_kw  = any(p.kind == _VAR_KW  for p, _ in resolved)
            final_var_pos = any(p.kind == _VAR_POS for p, _ in resolved)
            if target_name in kw_targets  and not final_var_kw:
                still_var_kw = False
            if target_name in pos_targets and not final_var_pos:
                still_var_pos = False
            continue

        if not callable(target_obj):
            continue

        # --- callable (function): delegate to resolve_function_params ---
        try:
            target_params = list(inspect.signature(target_obj).parameters.values())
        except (ValueError, TypeError):
            continue

        t_has_var_kw  = any(p.kind == _VAR_KW  for p in target_params)
        t_has_var_pos = any(p.kind == _VAR_POS for p in target_params)

        inner_seen = _seen | {target_name}
        if t_has_var_kw or t_has_var_pos:
            target_ast = (ast_info_by_name or {}).get(target_name)
            resolved = resolve_function_params(
                target_obj, target_ast, namespace,
                ast_info_by_name=ast_info_by_name,
                _seen=inner_seen,
            )
        else:
            t_hints  = _get_hints(target_obj)
            resolved = [(p, t_hints) for p in target_params]

        _merge_concrete_params(merged, seen_names, resolved)
        final_var_kw  = any(p.kind == _VAR_KW  for p, _ in resolved)
        final_var_pos = any(p.kind == _VAR_POS for p, _ in resolved)
        if target_name in kw_targets  and not final_var_kw:
            still_var_kw = False
        if target_name in pos_targets and not final_var_pos:
            still_var_pos = False

    return still_var_kw, still_var_pos


def _resolve_via_mro(
    cls: type,
    method_name: str,
    own_params: list[inspect.Parameter],
    own_hints: dict[str, Any],
    ast_info: "FunctionInfo | None" = None,
    namespace: "dict[str, Any] | None" = None,
    ast_info_by_name: "dict[str, FunctionInfo] | None" = None,
    _seen: "frozenset[str] | None" = None,
) -> list[ParamWithHints]:
    """Resolve ``**kwargs`` / ``*args`` by walking the MRO.

    Iterates ``cls.__mro__[1:]``, collecting concrete parameters from each
    ancestor that defines *method_name*, until both variadics are resolved
    or the MRO is exhausted.

    If variadics remain after the MRO is exhausted AND *namespace* is
    provided, a secondary namespace-based lookup is attempted for any
    module-level function targets found in *ast_info*.  This handles
    **method → function** forwarding chains.

    Parameters
    ----------
    cls : type
        The class owning the method.
    method_name : str
        Name of the method to resolve.
    own_params : list of inspect.Parameter
        The method's own parameters (``self``/``cls`` excluded).
    own_hints : dict
        Resolved type hints for the method.
    ast_info : FunctionInfo, optional
        Pre-scanned metadata — used for post-MRO namespace fallback.
    namespace : dict, optional
        Module ``__dict__`` for looking up function targets that are not
        in the class hierarchy (method → function chains).
    ast_info_by_name : dict, optional
        Maps function name → FunctionInfo for recursive resolution.
    _seen : frozenset, optional
        Cycle-detection set passed through from the public entry point.

    Returns
    -------
    list of ParamWithHints
        Own parameters first, then ancestor parameters in MRO order.
        Residual ``**kwargs`` and explicitly-typed ``*args`` appended last.
    """
    merged: list[ParamWithHints] = [
        (p, own_hints) for p in own_params if p.kind not in (_VAR_POS, _VAR_KW)
    ]
    seen_names: set[str] = {p.name for p, _ in merged}

    still_var_kw  = any(p.kind == _VAR_KW  for p in own_params)
    still_var_pos = any(p.kind == _VAR_POS for p in own_params)

    for parent in cls.__mro__[1:]:
        if parent is object:
            break
        if method_name not in parent.__dict__:
            continue

        parent_params, parent_hints = _get_raw_params(parent, method_name)
        if parent_params is None:
            continue

        p_has_var_kw  = any(p.kind == _VAR_KW  for p in parent_params)
        p_has_var_pos = any(p.kind == _VAR_POS for p in parent_params)

        _merge_concrete_params(
            merged, seen_names,
            [(p, parent_hints) for p in parent_params],
        )

        if not p_has_var_kw:
            still_var_kw = False
        if not p_has_var_pos:
            still_var_pos = False

        if not still_var_kw and not still_var_pos:
            break

    # Post-MRO: try namespace lookup for method → function chains
    if (still_var_kw or still_var_pos) and namespace and ast_info is not None:
        if _seen is None:
            fn_qname = f"{cls.__name__}.{method_name}"
            _seen = frozenset({fn_qname})
        still_var_kw, still_var_pos = _resolve_via_namespace(
            still_var_kw, still_var_pos,
            own_params, own_hints,
            merged, seen_names,
            ast_info, namespace,
            ast_info_by_name,
            _seen,
        )

    # Enforce valid signature ordering (no non-default param after default param).
    # This can arise when namespace-resolved params absorbed from a forwarding
    # target have default values while the target's non-default params don't.
    merged = _enforce_signature_validity(merged)

    return _finalise_variadics(merged, own_params, own_hints, still_var_pos, still_var_kw)


# ---------------------------------------------------------------------------
# Public entry point: class method resolution
# ---------------------------------------------------------------------------

def resolve_params(
    cls: type,
    method_name: str,
    ast_info: "FunctionInfo | None" = None,
    namespace: "dict[str, Any] | None" = None,
    ast_info_by_name: "dict[str, FunctionInfo] | None" = None,
    _seen: "frozenset[str] | None" = None,
) -> list[ParamWithHints]:
    """Return the fully-merged parameter list for *method_name* on *cls*.

    Expands ``**kwargs`` and ``*args`` into the concrete parameters they
    absorb using one of three strategies applied in order:

    1. **No variadics** — if the method has neither ``*args`` nor
       ``**kwargs``, return its own parameters unchanged.
    2. **cls()-call detection** — if the method is a ``@classmethod``
       whose body contains ``cls(..., **kwargs)``, resolve against
       ``cls.__init__``. Parameters hardcoded in the call are excluded.
    3. **MRO walk** — iterate ancestors that define the same method,
       collecting concrete parameters until all variadics are resolved.
       If variadics remain after MRO exhaustion and *namespace* is
       provided, falls back to module-level function lookup (handles
       **method → function** forwarding chains).

    ``self`` and ``cls`` are always excluded from the result.

    Parameters
    ----------
    cls : type
        The class owning (or inheriting) the method.
    method_name : str
        Name of the method to resolve.
    ast_info : FunctionInfo, optional
        Pre-scanned metadata from :class:`~stubpy.ast_pass.ASTHarvester`.
        When provided, avoids a redundant inline AST parse inside
        :func:`_detect_cls_call` and enables post-MRO namespace fallback.
    namespace : dict, optional
        Module ``__dict__`` — used for **method → function** chain
        resolution.  Pass ``ctx.module_namespace`` from the emitter.
    ast_info_by_name : dict, optional
        Maps function name → FunctionInfo — enables recursive resolution
        when a namespace target also has variadics.
    _seen : frozenset, optional
        Cycle-detection set.  Do not pass manually.

    Returns
    -------
    list of ParamWithHints
        Ordered ``(Parameter, hints_dict)`` tuples. Own parameters come
        first, then ancestor parameters in MRO order. Unresolvable
        ``**kwargs`` and explicitly-typed ``*args`` are appended last.

    See Also
    --------
    resolve_function_params : Entry point for standalone module-level functions.
    stubpy.emitter.generate_method_stub : Consumes the output of this function.

    Examples
    --------
    >>> class Base:
    ...     def __init__(self, color: str, opacity: float = 1.0) -> None: ...
    >>> class Child(Base):
    ...     def __init__(self, label: str, **kwargs) -> None: ...
    >>> params = resolve_params(Child, \"__init__\")
    >>> [p.name for p, _ in params]
    ['label', 'color', 'opacity']
    """
    own_params, own_hints = _get_raw_params(cls, method_name)

    if own_params is None:
        for parent in cls.__mro__[1:]:
            if method_name in parent.__dict__:
                return resolve_params(
                    parent, method_name,
                    namespace=namespace,
                    ast_info_by_name=ast_info_by_name,
                    _seen=_seen,
                )
        return []

    has_var_kw  = any(p.kind == _VAR_KW  for p in own_params)
    has_var_pos = any(p.kind == _VAR_POS for p in own_params)

    if not has_var_kw and not has_var_pos:
        return [(p, own_hints) for p in own_params]

    raw = cls.__dict__.get(method_name)
    if isinstance(raw, classmethod) and has_var_kw:
        result = _resolve_via_cls_call(cls, method_name, own_params, own_hints, ast_info)
        if result is not None:
            return result

    if _seen is None:
        _seen = frozenset({f"{cls.__name__}.{method_name}"})

    return _resolve_via_mro(
        cls, method_name, own_params, own_hints,
        ast_info=ast_info,
        namespace=namespace,
        ast_info_by_name=ast_info_by_name,
        _seen=_seen,
    )


# ---------------------------------------------------------------------------
# Public entry point: module-level function resolution
# ---------------------------------------------------------------------------

def resolve_function_params(
    live_fn: Any,
    ast_info: "FunctionInfo | None",
    namespace: dict[str, Any],
    *,
    ast_info_by_name: "dict[str, FunctionInfo] | None" = None,
    _seen: frozenset[str] | None = None,
) -> list[ParamWithHints]:
    """Return the fully-merged parameter list for a module-level function.

    Expands ``**kwargs`` and ``*args`` into concrete parameters by
    following AST-detected forwarding targets looked up in *namespace*.

    Unlike :func:`resolve_params` (which walks the class MRO), this
    handles **standalone functions** where there is no class hierarchy.
    It relies on :attr:`~stubpy.ast_pass.FunctionInfo.kwargs_forwarded_to`
    and :attr:`~stubpy.ast_pass.FunctionInfo.args_forwarded_to` —
    pre-populated by :meth:`~stubpy.ast_pass.ASTHarvester._harvest_function`.

    When a forwarding target is a **class** (type), resolution delegates
    to :func:`resolve_params` on that class's ``__init__``.  This handles
    **function → class constructor** chains.  Similarly, :func:`resolve_params`
    falls back to this function when a method forwards to a standalone
    function — enabling arbitrarily deep mixed chains.

    All parameter *kinds* are handled correctly:

    * ``POSITIONAL_ONLY`` (``/``) — promoted to ``POSITIONAL_OR_KEYWORD``
      when absorbed through ``**kwargs`` (callers use keyword form).
    * ``POSITIONAL_OR_KEYWORD`` — merged as-is.
    * ``VAR_POSITIONAL`` (``*args``) — resolved via ``args_forwarded_to``;
      kept if still unresolved or explicitly typed.
    * ``KEYWORD_ONLY`` (after ``*`` / ``*args``) — merged as-is; the
      emitter inserts the bare ``*`` separator automatically.
    * ``VAR_KEYWORD`` (``**kwargs``) — resolved via ``kwargs_forwarded_to``;
      kept as residual only when no target fully resolved it.

    Strategy (in order)
    -------------------
    1. **No variadics** — own parameters returned unchanged.
    2. **No targets** — own parameters returned unchanged (variadics
       preserved; no information to expand them).
    3. **Target resolution** — look each name up in *namespace*, merge
       its concrete params (recursively for chained forwarding), with
       cycle detection via *_seen*.  Class targets are handled via
       :func:`resolve_params` on their ``__init__``.
    4. **Finalise** — re-insert ``*args`` and residual ``**kwargs``.

    Parameters
    ----------
    live_fn : callable
        The live function object from the loaded module.
    ast_info : FunctionInfo or None
        Pre-scanned metadata from :class:`~stubpy.ast_pass.ASTHarvester`.
    namespace : dict
        The module's ``__dict__`` — used to look up live callable targets.
    ast_info_by_name : dict, optional
        Maps function name → :class:`~stubpy.ast_pass.FunctionInfo` for
        functions in the same module.  Enables recursive resolution when a
        forwarding target also has variadics.
    _seen : frozenset, optional
        Names already on the call stack — prevents infinite recursion in
        mutually-recursive forwarding patterns.  Do not pass manually.

    Returns
    -------
    list of ParamWithHints
        Ordered ``(Parameter, hints_dict)`` tuples, variadics expanded
        as far as possible.

    See Also
    --------
    resolve_params : Entry point for class method resolution via MRO.

    Examples
    --------
    >>> def make_color(r: float, g: float, b: float, a: float = 1.0): ...
    >>> def make_red(r: float = 1.0, **kwargs): make_color(r=r, **kwargs)
    """
    if live_fn is None:
        return []

    try:
        sig = inspect.signature(live_fn)
        own_params = list(sig.parameters.values())
    except (ValueError, TypeError):
        return []

    own_hints = _get_hints(live_fn)
    has_var_kw  = any(p.kind == _VAR_KW  for p in own_params)
    has_var_pos = any(p.kind == _VAR_POS for p in own_params)

    # Strategy 1: no variadics
    if not has_var_kw and not has_var_pos:
        return [(p, own_hints) for p in own_params]

    # Strategy 2: no AST data or no forwarding targets
    if ast_info is None:
        return [(p, own_hints) for p in own_params]

    kw_targets  = ast_info.kwargs_forwarded_to if has_var_kw  else []
    pos_targets = ast_info.args_forwarded_to   if has_var_pos else []

    if not kw_targets and not pos_targets:
        return [(p, own_hints) for p in own_params]

    # Strategy 3: resolve forwarding targets
    fn_name = getattr(live_fn, "__name__", None) or getattr(live_fn, "__qualname__", None)
    if _seen is None:
        _seen = frozenset()
    _seen = _seen | {fn_name} if fn_name else _seen

    merged: list[ParamWithHints] = [
        (p, own_hints) for p in own_params if p.kind not in (_VAR_POS, _VAR_KW)
    ]
    seen_names: set[str] = {p.name for p, _ in merged}

    still_var_kw  = has_var_kw
    still_var_pos = has_var_pos

    # Deduplicate target list while preserving order
    visited: list[str] = []
    for t in kw_targets + pos_targets:
        if t not in visited:
            visited.append(t)

    for target_name in visited:
        if target_name in _seen:
            continue  # cycle guard

        target_fn = namespace.get(target_name)
        if target_fn is None:
            continue

        # --- class constructor: delegate to resolve_params(__init__) ---
        if isinstance(target_fn, type):
            inner_seen = _seen | {target_name}
            resolved = resolve_params(
                target_fn, "__init__",
                namespace=namespace,
                ast_info_by_name=ast_info_by_name,
                _seen=inner_seen,
            )
            _merge_concrete_params(merged, seen_names, resolved)
            final_var_kw  = any(p.kind == _VAR_KW  for p, _ in resolved)
            final_var_pos = any(p.kind == _VAR_POS for p, _ in resolved)
            if target_name in kw_targets  and not final_var_kw:
                still_var_kw = False
            if target_name in pos_targets and not final_var_pos:
                still_var_pos = False
            continue

        if not callable(target_fn):
            continue

        try:
            target_params = list(inspect.signature(target_fn).parameters.values())
        except (ValueError, TypeError):
            continue

        t_has_var_kw  = any(p.kind == _VAR_KW  for p in target_params)
        t_has_var_pos = any(p.kind == _VAR_POS for p in target_params)

        # Recurse when the target also has variadics
        inner_seen = _seen | {target_name}
        if t_has_var_kw or t_has_var_pos:
            target_ast = (ast_info_by_name or {}).get(target_name)
            resolved = resolve_function_params(
                target_fn, target_ast, namespace,
                ast_info_by_name=ast_info_by_name,
                _seen=inner_seen,
            )
        else:
            t_hints  = _get_hints(target_fn)
            resolved = [(p, t_hints) for p in target_params]

        _merge_concrete_params(merged, seen_names, resolved)

        # Variadics are resolved when the target has none remaining
        final_var_kw  = any(p.kind == _VAR_KW  for p, _ in resolved)
        final_var_pos = any(p.kind == _VAR_POS for p, _ in resolved)

        if target_name in kw_targets  and not final_var_kw:
            still_var_kw = False
        if target_name in pos_targets and not final_var_pos:
            still_var_pos = False

    # Strategy 4: enforce default-ordering rule (absorbed params may need
    # KEYWORD_ONLY promotion to produce valid syntax — see docstring).
    merged = _enforce_signature_validity(merged)

    # Strategy 5: re-insert variadics
    return _finalise_variadics(merged, own_params, own_hints, still_var_pos, still_var_kw)
