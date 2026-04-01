"""
stubpy.resolver
===============

Parameter resolution — the core ``**kwargs`` / ``*args`` backtracing logic.

:func:`resolve_params` returns the fully-merged parameter list for any
method, expanding variadic arguments into the concrete named parameters
they absorb by walking the class MRO or detecting ``cls(**kwargs)``
patterns via AST analysis.
"""
from __future__ import annotations

import ast
import inspect
import textwrap
import typing
from typing import Any

_VAR_POS = inspect.Parameter.VAR_POSITIONAL
_VAR_KW  = inspect.Parameter.VAR_KEYWORD
_KW_ONLY = inspect.Parameter.KEYWORD_ONLY

#: A ``(parameter, hints-dict)`` pair produced by :func:`resolve_params`.
ParamWithHints = tuple[inspect.Parameter, dict[str, Any]]


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


def _detect_cls_call(cls: type, method_name: str) -> tuple[bool, set[str]]:
    """Detect the ``cls(..., **kwargs)`` pattern inside a classmethod via AST.

    When a ``@classmethod`` contains ``cls(**kwargs)`` or
    ``cls.__init__(..., **kwargs)``, the ``**kwargs`` should be resolved
    against ``cls.__init__`` rather than MRO siblings of the same method.

    Parameters
    ----------
    cls : type
        The class that owns the method.
    method_name : str
        Name of the classmethod to inspect.

    Returns
    -------
    detected : bool
        ``True`` if the ``cls(..., **kwargs)`` pattern was found.
    explicitly_passed : set of str
        Keyword argument names already hardcoded in the call — e.g.
        ``cls(r=1, **kwargs)`` yields ``{"r"}``. These are excluded from
        the resolved stub to avoid duplicates.
    """
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
        has_kwargs = any(kw.arg is None for kw in node.keywords)
        if has_kwargs:
            explicit = {kw.arg for kw in node.keywords if kw.arg is not None}
            return True, explicit

    return False, set()


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


def _normalise_kind(p: inspect.Parameter) -> inspect.Parameter:
    """Return *p* with ``POSITIONAL_ONLY`` kind promoted to ``POSITIONAL_OR_KEYWORD``.

    When a parent method's positional-only parameters are absorbed into a
    child's ``**kwargs``, callers can pass those arguments by keyword
    through the child's interface.  Emitting them as ``POSITIONAL_ONLY``
    would produce an invalid stub (``/`` appearing in the wrong place).
    Promoting them to ``POSITIONAL_OR_KEYWORD`` correctly reflects what
    the child's ``**kwargs`` accepts.
    """
    if p.kind == inspect.Parameter.POSITIONAL_ONLY:
        return p.replace(kind=inspect.Parameter.POSITIONAL_OR_KEYWORD)
    return p


def _resolve_via_cls_call(
    cls: type,
    method_name: str,
    own_params: list[inspect.Parameter],
    own_hints: dict[str, Any],
) -> list[ParamWithHints] | None:
    """Resolve ``**kwargs`` against ``cls.__init__`` when a cls-call is detected.

    If *method_name* body contains ``cls(..., **kwargs)``, the ``**kwargs``
    is resolved against the fully-resolved ``__init__`` of *cls*.

    Parameters
    ----------
    cls : type
        The class owning the classmethod.
    method_name : str
        Name of the classmethod.
    own_params : list of inspect.Parameter
        The classmethod's own parameters (``self``/``cls`` excluded).
    own_hints : dict
        Resolved type hints for the classmethod.

    Returns
    -------
    list of ParamWithHints or None
        Merged list on success, or ``None`` if no cls-call was detected
        (allowing the caller to fall back to the MRO walk).
    """
    cls_call, explicit_kw = _detect_cls_call(cls, method_name)
    if not cls_call:
        return None

    init_params = resolve_params(cls, "__init__")

    merged: list[ParamWithHints] = [
        (p, own_hints)
        for p in own_params
        if p.kind not in (_VAR_POS, _VAR_KW)
    ]
    seen = {p.name for p, _ in merged} | explicit_kw

    for p, h in init_params:
        if p.kind in (_VAR_POS, _VAR_KW):
            continue
        if p.name in seen:
            continue
        merged.append((_normalise_kind(p), h))
        seen.add(p.name)

    if any(p.kind == _VAR_KW for p, _ in init_params):
        kw_param = next((p for p in own_params if p.kind == _VAR_KW), None)
        if kw_param:
            merged.append((kw_param, own_hints))

    return merged


def _resolve_via_mro(
    cls: type,
    method_name: str,
    own_params: list[inspect.Parameter],
    own_hints: dict[str, Any],
) -> list[ParamWithHints]:
    """Resolve ``**kwargs`` / ``*args`` by walking the MRO.

    Iterates ``cls.__mro__[1:]``, collecting concrete parameters from each
    ancestor that defines *method_name*, until both variadics are resolved
    or the MRO is exhausted.

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

    Returns
    -------
    list of ParamWithHints
        Own parameters first, then ancestor parameters in MRO order.
        Residual ``**kwargs`` and explicitly-typed ``*args`` appended last.
    """
    merged: list[ParamWithHints] = [
        (p, own_hints)
        for p in own_params
        if p.kind not in (_VAR_POS, _VAR_KW)
    ]
    seen_names = {p.name for p, _ in merged}

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

        for p in parent_params:
            if p.kind in (_VAR_POS, _VAR_KW):
                continue
            if p.name in seen_names:
                continue
            # Positional-only params from a parent that are absorbed by a
            # child's **kwargs must be promoted to POSITIONAL_OR_KEYWORD —
            # callers pass them by keyword through the child interface.
            merged.append((_normalise_kind(p), parent_hints))
            seen_names.add(p.name)

        if not p_has_var_kw:
            still_var_kw = False
        if not p_has_var_pos:
            still_var_pos = False

        if not still_var_kw and not still_var_pos:
            break

    # ── Insert *args before keyword-only params and before **kwargs ────────
    # Must happen BEFORE appending **kwargs so we can find the right
    # insertion point regardless of resolution state.
    pos_param = next((p for p in own_params if p.kind == _VAR_POS), None)
    if pos_param is not None:
        is_explicitly_typed = pos_param.annotation is not inspect.Parameter.empty
        if still_var_pos or is_explicitly_typed:
            # Insert just before the first KEYWORD_ONLY param OR before
            # any trailing **kwargs already in merged — whichever is first.
            insert_at = next(
                (
                    i for i, (p, _) in enumerate(merged)
                    if p.kind in (_KW_ONLY, _VAR_KW)
                ),
                len(merged),
            )
            merged.insert(insert_at, (pos_param, own_hints))

    # ── Append residual **kwargs after *args is placed ───────────────────
    if still_var_kw:
        kw_param = next((p for p in own_params if p.kind == _VAR_KW), None)
        if kw_param:
            merged.append((kw_param, own_hints))

    return merged


def resolve_params(cls: type, method_name: str) -> list[ParamWithHints]:
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

    ``self`` and ``cls`` are always excluded from the result.

    Parameters
    ----------
    cls : type
        The class owning (or inheriting) the method.
    method_name : str
        Name of the method to resolve.

    Returns
    -------
    list of ParamWithHints
        Ordered ``(Parameter, hints_dict)`` tuples. Own parameters come
        first, then ancestor parameters in MRO order. Unresolvable
        ``**kwargs`` and explicitly-typed ``*args`` are appended last.

    See Also
    --------
    stubpy.emitter.generate_method_stub : Consumes the output of this function.

    Examples
    --------
    >>> class Base:
    ...     def __init__(self, color: str, opacity: float = 1.0) -> None: ...
    >>> class Child(Base):
    ...     def __init__(self, label: str, **kwargs) -> None: ...
    >>> params = resolve_params(Child, "__init__")
    >>> [p.name for p, _ in params]
    ['label', 'color', 'opacity']
    """
    own_params, own_hints = _get_raw_params(cls, method_name)

    if own_params is None:
        for parent in cls.__mro__[1:]:
            if method_name in parent.__dict__:
                return resolve_params(parent, method_name)
        return []

    has_var_kw  = any(p.kind == _VAR_KW  for p in own_params)
    has_var_pos = any(p.kind == _VAR_POS for p in own_params)

    if not has_var_kw and not has_var_pos:
        return [(p, own_hints) for p in own_params]

    raw = cls.__dict__.get(method_name)
    if isinstance(raw, classmethod) and has_var_kw:
        result = _resolve_via_cls_call(cls, method_name, own_params, own_hints)
        if result is not None:
            return result

    return _resolve_via_mro(cls, method_name, own_params, own_hints)