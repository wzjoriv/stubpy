"""
stubpy.emitter
==============

Stub text generation — converts live objects and module-level symbols
into ``.pyi`` source text.

Formatting modes
----------------
Two formatting modes are chosen automatically:

- **Inline** — used when a function / method has **≤ 2** non-self/cls
  parameters; the entire signature fits on one line.
- **Multi-line** — used for larger signatures; each parameter gets its
  own indented line with a trailing comma.

Special-class handling
----------------------
:func:`generate_class_stub` applies dedicated logic for common Python
patterns before falling back to the general reflection path:

- **NamedTuple subclasses** — emits ``class Name(NamedTuple):`` with
  per-field annotations and default values.
- **@dataclass classes** — emits the ``@dataclass`` decorator and
  synthesises an ``__init__`` stub from ``__dataclass_fields__``,
  correctly handling ``default_factory``, ``init=False``, and
  ``ClassVar`` fields.
- **Abstract methods** — emits ``@abstractmethod`` for any callable
  whose ``__isabstractmethod__`` attribute is set.
- **Generic base classes** — reads ``__orig_bases__`` (PEP 560) to emit
  ``class Foo(Generic[T]):`` correctly, preserving subscripted type
  parameters that ``__bases__`` erases.

Alias and overload stubs
------------------------
- :func:`generate_alias_stub` re-emits TypeVar, TypeAlias, NewType,
  ParamSpec, and TypeVarTuple declarations from the AST pre-pass, with
  support for the ``alias_style`` configuration option (compatible
  ``Name: TypeAlias = ...``, or Python 3.12+ ``type Name = ...`` form).
- :func:`generate_overload_group_stub` emits one ``@overload`` stub per
  variant, suppressing the concrete implementation per PEP 484.

Parameter separators
--------------------
- :func:`insert_kw_separator` inserts a bare ``*`` before the first
  keyword-only parameter when no ``*args`` is present.
- :func:`insert_pos_separator` inserts a bare ``/`` after the last
  ``POSITIONAL_ONLY`` parameter (PEP 570).

All methods emit ``async def`` when :func:`inspect.iscoroutinefunction`
or :func:`inspect.isasyncgenfunction` returns ``True``.
"""
from __future__ import annotations

import dataclasses as _dc
import inspect
import typing
from typing import TYPE_CHECKING

from .annotations import annotation_to_str, default_to_str, format_param, get_hints_for_method
from .context import StubContext
from .diagnostics import DiagnosticStage
from .resolver import ParamWithHints, _KW_ONLY, _VAR_POS, resolve_params, resolve_function_params

if TYPE_CHECKING:
    from .symbols import AliasSymbol, FunctionSymbol, OverloadGroup, VariableSymbol

#: Sentinel parameter name representing a bare ``*`` keyword-only separator.
_KW_SEP_NAME: str = "__kw_sep__"

#: Sentinel parameter name representing a bare ``/`` positional-only separator.
_POS_SEP_NAME: str = "__pos_sep__"

_POS_ONLY = inspect.Parameter.POSITIONAL_ONLY

#: Dunder names that belong in stubs. All other ``__dunder__`` names are omitted.
_PUBLIC_DUNDERS: frozenset[str] = frozenset({
    "__init__", "__new__", "__call__",
    "__repr__", "__str__", "__bytes__",
    "__len__", "__bool__",
    "__getitem__", "__setitem__", "__delitem__",
    "__contains__", "__iter__", "__next__",
    "__enter__", "__exit__",
    "__eq__", "__ne__", "__lt__", "__le__", "__gt__", "__ge__", "__hash__",
    "__add__", "__radd__", "__sub__", "__rsub__",
    "__mul__", "__rmul__", "__truediv__", "__rtruediv__",
    "__floordiv__", "__mod__", "__pow__",
    "__and__", "__or__", "__xor__",
    "__neg__", "__pos__", "__abs__",
    "__deepcopy__", "__copy__",
    "__post_init__",
})


# ---------------------------------------------------------------------------
# Descriptor introspection helpers
# ---------------------------------------------------------------------------

def _unwrap_descriptor(raw: object) -> object:
    """Return the underlying function from a descriptor wrapper."""
    if isinstance(raw, (classmethod, staticmethod)):
        return raw.__func__
    if isinstance(raw, property):
        return raw.fget
    return raw


def _is_async_callable(raw: object) -> bool:
    """Return ``True`` if *raw* is an async function or async generator."""
    fn = _unwrap_descriptor(raw)
    if fn is None:
        return False
    return inspect.iscoroutinefunction(fn) or inspect.isasyncgenfunction(fn)


def _is_abstract_method(raw: object) -> bool:
    """Return ``True`` if *raw* has ``__isabstractmethod__ = True``."""
    fn = _unwrap_descriptor(raw)
    if fn is None:
        return False
    return bool(getattr(fn, "__isabstractmethod__", False))


# ---------------------------------------------------------------------------
# Class-kind detection
# ---------------------------------------------------------------------------

def _is_dataclass(cls: type) -> bool:
    """Return ``True`` when *cls* was decorated with ``@dataclass``."""
    return hasattr(cls, "__dataclass_fields__")


def _is_namedtuple(cls: type) -> bool:
    """Return ``True`` when *cls* is a NamedTuple subclass."""
    return (
        isinstance(cls, type)
        and issubclass(cls, tuple)
        and hasattr(cls, "_fields")
        and hasattr(cls, "_asdict")
    )


def _is_typeddict(cls: type) -> bool:
    """Return ``True`` when *cls* was created via ``TypedDict``."""
    return (
        isinstance(cls, type)
        and hasattr(cls, "__total__")
        and hasattr(cls, "__required_keys__")
        and hasattr(cls, "__optional_keys__")
    )


def _is_enum(cls: type) -> bool:
    """Return ``True`` when *cls* is an :class:`~enum.Enum` subclass."""
    import enum
    return isinstance(cls, type) and issubclass(cls, enum.Enum)


# Enum member names to suppress (internal Python implementation detail)
_ENUM_PRIVATE_METHODS: frozenset[str] = frozenset({
    "_generate_next_value_", "_missing_", "_new_member_",
    "_member_type_", "_value_repr_", "_iter_member_",
    "_check_value_",
})


# ---------------------------------------------------------------------------
# Dataclass helpers
# ---------------------------------------------------------------------------

def _synthesize_dataclass_init(
    cls: type,
    ctx: StubContext,
    indent: str = "    ",
) -> str:
    """Build a synthesised ``__init__`` stub from ``__dataclass_fields__``.

    - ``default_factory`` fields are shown as ``field: Type = ...`` to avoid
      exposing the internal sentinel object.
    - ``ClassVar`` and ``init=False`` fields are excluded from the signature.
    - Annotations are resolved through the MRO so inherited fields retain
      their type string from the defining parent class.
    """
    fields = cls.__dataclass_fields__

    def _find_annotation(fname: str) -> object:
        for klass in cls.__mro__:
            ann = klass.__dict__.get("__annotations__", {})
            if fname in ann:
                return ann[fname]
        return None

    params: list[str] = ["self"]
    for fname, f in fields.items():
        if f._field_type is _dc._FIELD_CLASSVAR:  # type: ignore[attr-defined]
            continue
        if not f.init:
            continue

        type_ann = _find_annotation(fname)
        type_str = annotation_to_str(type_ann, ctx) if type_ann is not None else ""

        if f.default is not _dc.MISSING:
            p = (f"{fname}: {type_str} = {repr(f.default)}"
                 if type_str else f"{fname} = {repr(f.default)}")
        elif f.default_factory is not _dc.MISSING:  # type: ignore[misc]
            p = f"{fname}: {type_str} = ..." if type_str else f"{fname} = ..."
        else:
            p = f"{fname}: {type_str}" if type_str else fname
        params.append(p)

    body_params = params[1:]
    if len(body_params) <= 2:
        return f"{indent}def __init__({', '.join(params)}) -> None: ..."
    inner = indent + "    "
    joined = f",\n{inner}".join(params)
    return f"{indent}def __init__(\n{inner}{joined},\n{indent}) -> None: ..."


def _emit_dataclass_annotations(
    cls: type,
    own_annotations: dict,
    ctx: StubContext,
    lines: list[str],
    indent: str = "    ",
) -> None:
    """Append per-field annotation lines for a dataclass class body."""
    for attr_name, ann in own_annotations.items():
        ann_str = annotation_to_str(ann, ctx)
        lines.append(f"{indent}{attr_name}: {ann_str}")


# ---------------------------------------------------------------------------
# NamedTuple helper
# ---------------------------------------------------------------------------

def _emit_typeddict_stub(cls: type, ctx: "StubContext") -> str:
    """Generate a clean ``TypedDict`` stub for *cls*.

    TypedDict classes are emitted as::

        class Name(TypedDict):           # total=True (default)
            field: Type

        class Name(TypedDict, total=False):   # optional fields
            field: Type

    Parameters
    ----------
    cls : type
        The TypedDict class.
    ctx : StubContext
        Current stub context.

    Returns
    -------
    str
        The complete class stub text.
    """
    total = getattr(cls, "__total__", True)
    suffix = ", total=False" if not total else ""
    lines = [f"class {cls.__name__}(TypedDict{suffix}):"]

    ann = cls.__dict__.get("__annotations__", {})
    if not ann:
        lines.append("    ...")
    else:
        for field_name, field_type in ann.items():
            type_str = annotation_to_str(field_type, ctx)
            lines.append(f"    {field_name}: {type_str}")

    return "\n".join(lines)


def _generate_namedtuple_stub(cls: type, ctx: StubContext) -> str:
    """Generate the complete ``.pyi`` block for a NamedTuple subclass.

    Emits field annotations first (in ``_fields`` order), then any
    additional methods defined directly on the class — including
    ``@property`` descriptors and ordinary methods.  The standard
    NamedTuple auto-generated methods (``_make``, ``_asdict``,
    ``_replace``, ``__getnewargs__``, ``__new__``) are suppressed.
    """
    lines: list[str] = [f"class {cls.__name__}(NamedTuple):"]

    field_names: tuple[str, ...] = cls._fields  # type: ignore[attr-defined]
    ann = getattr(cls, "__annotations__", {})
    defaults: dict = getattr(cls, "_field_defaults", {})

    if not field_names:
        lines.append("    ...")
        return "\n".join(lines)

    for name in field_names:
        type_ann = ann.get(name, inspect.Parameter.empty)
        type_str = (
            annotation_to_str(type_ann, ctx)
            if type_ann is not inspect.Parameter.empty
            else ""
        )
        if name in defaults:
            default_s = default_to_str(defaults[name])
            lines.append(
                f"    {name}: {type_str} = {default_s}" if type_str
                else f"    {name} = {default_s}"
            )
        else:
            lines.append(f"    {name}: {type_str}" if type_str else f"    {name}: ...")

    # Emit extra methods defined on the class (properties, helpers, etc.)
    # Suppress NamedTuple-generated internals.
    _NT_GENERATED: frozenset[str] = frozenset({
        "_make", "_asdict", "_replace", "_fields", "_field_defaults",
        "__getnewargs__", "__getnewargs_ex__", "__new__",
    })
    extra_method_names = [
        m for m in methods_defined_on(cls)
        if m not in _NT_GENERATED
    ]
    if extra_method_names:
        lines.append("")
        for mn in extra_method_names:
            stub = generate_method_stub(cls, mn, ctx)
            if stub:
                lines.append(stub)

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Parameter formatting helpers
# ---------------------------------------------------------------------------

def _raw_key(param: inspect.Parameter) -> str:
    """Return the key used in ``FunctionInfo.raw_arg_annotations``.

    Variadic parameter names are prefixed with ``*`` or ``**``
    to distinguish them from regular parameters of the same name.
    """
    if param.kind == inspect.Parameter.VAR_POSITIONAL:
        return f"*{param.name}"
    if param.kind == inspect.Parameter.VAR_KEYWORD:
        return f"**{param.name}"
    return param.name


def _get_raw_ast_annotations(
    cls: type,
    method_name: str,
    ctx: StubContext,
) -> "dict[str, str]":
    """Return raw AST annotation strings for *method_name* on *cls*, or ``{}``."""
    if ctx.symbol_table is None:
        return {}
    try:
        cls_sym = ctx.symbol_table.get_class(cls.__name__)
        if cls_sym is None or cls_sym.ast_info is None:
            return {}
        for method_info in cls_sym.ast_info.methods:
            if method_info.name == method_name:
                return method_info.raw_arg_annotations
    except Exception:
        pass
    return {}


def insert_kw_separator(
    params_with_hints: list[ParamWithHints],
) -> list[ParamWithHints]:
    """Insert a bare ``*`` sentinel before the first keyword-only parameter.

    Python requires a bare ``*`` (or a ``*args``) before any keyword-only
    parameters in a function signature. When no ``*args`` is present but
    keyword-only parameters exist, this function inserts a sentinel
    :class:`inspect.Parameter` named :data:`_KW_SEP_NAME` that
    :func:`generate_method_stub` emits as a literal ``*``.

    If a ``VAR_POSITIONAL`` (``*args``) parameter is already present no
    sentinel is needed and the list is returned unchanged.

    Parameters
    ----------
    params_with_hints : list of ParamWithHints
        The parameter list from :func:`~stubpy.resolver.resolve_params`.

    Returns
    -------
    list of ParamWithHints
        The same list with the sentinel inserted at the correct position,
        or the original list unchanged if no insertion is needed.

    Examples
    --------
    >>> import inspect
    >>> kw = inspect.Parameter("b", inspect.Parameter.KEYWORD_ONLY)
    >>> pos = inspect.Parameter("a", inspect.Parameter.POSITIONAL_OR_KEYWORD)
    >>> result = insert_kw_separator([(pos, {}), (kw, {})])
    >>> result[1][0].name   # sentinel is between a and b
    '__kw_sep__'
    """
    if any(p.kind == _VAR_POS for p, _ in params_with_hints):
        return params_with_hints

    kw_indices = [
        i for i, (p, _) in enumerate(params_with_hints)
        if p.kind == _KW_ONLY
    ]
    if not kw_indices:
        return params_with_hints

    result = list(params_with_hints)
    sentinel = inspect.Parameter(_KW_SEP_NAME, _VAR_POS)
    result.insert(kw_indices[0], (sentinel, {}))
    return result


def insert_pos_separator(
    params_with_hints: list[ParamWithHints],
) -> list[ParamWithHints]:
    """Insert a bare ``/`` sentinel after the last positional-only parameter.

    Python 3.8+ allows ``def foo(a, b, /, c)`` to declare *a* and *b* as
    positional-only.  Stub files must preserve this with a ``/`` separator
    (PEP 570).  This function inserts a sentinel
    :class:`inspect.Parameter` named :data:`_POS_SEP_NAME` immediately
    after the last ``POSITIONAL_ONLY`` parameter so that
    :func:`generate_method_stub` and :func:`generate_function_stub` can
    emit it as a literal ``/``.

    If no ``POSITIONAL_ONLY`` parameters are present, the list is returned
    unchanged.

    Parameters
    ----------
    params_with_hints : list of ParamWithHints
        The parameter list, usually from :func:`~stubpy.resolver.resolve_params`
        or from :func:`inspect.signature`.

    Returns
    -------
    list of ParamWithHints
        The same list with the ``/`` sentinel inserted after the last
        positional-only parameter, or the original list unchanged.

    Examples
    --------
    >>> import inspect
    >>> a = inspect.Parameter("a", inspect.Parameter.POSITIONAL_ONLY)
    >>> b = inspect.Parameter("b", inspect.Parameter.POSITIONAL_OR_KEYWORD)
    >>> result = insert_pos_separator([(a, {}), (b, {})])
    >>> result[1][0].name  # sentinel between a and b
    '__pos_sep__'
    """
    last_pos_only = -1
    for i, (p, _) in enumerate(params_with_hints):
        if p.kind == _POS_ONLY:
            last_pos_only = i

    if last_pos_only < 0:
        return params_with_hints

    result = list(params_with_hints)
    sentinel = inspect.Parameter(_POS_SEP_NAME, inspect.Parameter.POSITIONAL_OR_KEYWORD)
    result.insert(last_pos_only + 1, (sentinel, {}))
    return result


def methods_defined_on(cls: type) -> list[str]:
    """Return names of callable members defined directly on *cls*.

    Only inspects ``cls.__dict__`` — inherited members are excluded.
    Dunder names not in :data:`_PUBLIC_DUNDERS` are silently skipped.
    Insertion order is preserved.

    Parameters
    ----------
    cls : type
        The class to inspect.

    Returns
    -------
    list of str
        Method names (including classmethods, staticmethods, properties)
        defined on *cls* that should appear in a stub.

    Examples
    --------
    >>> class Parent:
    ...     def parent_method(self) -> None: ...
    >>> class Child(Parent):
    ...     def child_method(self) -> None: ...
    >>> methods_defined_on(Child)
    ['child_method']
    """
    names: list[str] = []
    for name, obj in cls.__dict__.items():
        if (
            name.startswith("__")
            and name.endswith("__")
            and name not in _PUBLIC_DUNDERS
        ):
            continue
        if callable(obj) or isinstance(obj, (classmethod, staticmethod, property)):
            names.append(name)
    return names


# ---------------------------------------------------------------------------
# Core stub generators
# ---------------------------------------------------------------------------

def generate_method_stub(
    cls: type,
    method_name: str,
    ctx: StubContext,
    indent: str = "    ",
) -> str:
    """Generate the ``.pyi`` stub line(s) for a single method on *cls*.

    Dispatches on the descriptor type in ``cls.__dict__``:

    - :class:`property` — ``@property`` with optional ``@name.setter``.
    - :class:`classmethod` — ``@classmethod`` with ``cls`` first.
    - :class:`staticmethod` — ``@staticmethod`` with no implicit first parameter.
    - Regular method — ``self`` as first parameter.

    Emits ``async def`` when the underlying callable is a coroutine or
    async generator function, and ``@abstractmethod`` when
    ``__isabstractmethod__`` is set.

    Methods with ≤ 2 non-self params are formatted inline; larger
    signatures are split across lines with a trailing comma on each
    parameter.

    Parameters
    ----------
    cls : type
        The class that owns the method.
    method_name : str
        Name of the method as it appears in ``cls.__dict__``.
    ctx : StubContext
        The current :class:`~stubpy.context.StubContext`.
    indent : str, optional
        Indentation string prepended to each line. Default is four spaces.

    Returns
    -------
    str
        One or more stub lines, or ``""`` if *method_name* is not in
        ``cls.__dict__``.

    Examples
    --------
    >>> from stubpy.context import StubContext
    >>> class A:
    ...     def move(self, x: float, y: float) -> None: ...
    >>> stub = generate_method_stub(A, "move", StubContext())
    >>> stub
    '    def move(self, x: float, y: float) -> None: ...'
    """
    raw = cls.__dict__.get(method_name)
    if raw is None:
        return ""

    is_abstract = _is_abstract_method(raw)
    is_async    = _is_async_callable(raw)
    lines: list[str] = []

    # ── Property ──────────────────────────────────────────────────────
    if isinstance(raw, property):
        hints    = get_hints_for_method(raw.fget)
        ret_ann  = hints.get("return", inspect.Parameter.empty)
        ret_str  = annotation_to_str(ret_ann, ctx)
        ret_part = f" -> {ret_str}" if ret_str else ""

        if is_abstract:
            lines.append(f"{indent}@abstractmethod")
        lines.append(f"{indent}@property")
        lines.append(f"{indent}def {method_name}(self){ret_part}: ...")

        if raw.fset is not None:
            setter_hints = get_hints_for_method(raw.fset)
            try:
                val_params = [
                    p for n, p in inspect.signature(raw.fset).parameters.items()
                    if n not in ("self", "cls")
                ]
            except (ValueError, TypeError):
                val_params = []

            val_name    = val_params[0].name if val_params else "value"
            val_ann     = setter_hints.get(
                val_name,
                val_params[0].annotation if val_params else inspect.Parameter.empty,
            )
            val_ann_str = annotation_to_str(val_ann, ctx)
            val_sig     = f"{val_name}: {val_ann_str}" if val_ann_str else val_name

            lines.append(f"{indent}@{method_name}.setter")
            lines.append(f"{indent}def {method_name}(self, {val_sig}) -> None: ...")

        return "\n".join(lines)

    # ── Regular / classmethod / staticmethod ──────────────────────────
    is_cls = isinstance(raw, classmethod)
    is_sta = isinstance(raw, staticmethod)

    if is_cls:
        lines.append(f"{indent}@classmethod")
    elif is_sta:
        lines.append(f"{indent}@staticmethod")

    if is_abstract:
        lines.append(f"{indent}@abstractmethod")

    keyword = "async def" if is_async else "def"

    params_with_hints = resolve_params(cls, method_name)
    params_with_hints = insert_pos_separator(params_with_hints)
    params_with_hints = insert_kw_separator(params_with_hints)

    own_hints = get_hints_for_method(raw)
    ret_ann   = own_hints.get("return", inspect.Parameter.empty)
    ret_str   = annotation_to_str(ret_ann, ctx)

    if not ret_str and method_name in ("__init__", "__new__"):
        ret_str = "None"

    raw_anns = _get_raw_ast_annotations(cls, method_name, ctx)

    self_prefix = [] if is_sta else (["cls"] if is_cls else ["self"])
    param_strs  = self_prefix + [
        "*" if p.name == _KW_SEP_NAME
        else "/" if p.name == _POS_SEP_NAME
        else format_param(p, h, ctx, raw_ann_override=raw_anns.get(_raw_key(p)))
        for p, h in params_with_hints
    ]
    ret_part = f" -> {ret_str}" if ret_str else ""

    include_doc_m = getattr(ctx.config, "include_docstrings", False)
    _mraw = cls.__dict__.get(method_name)
    _mfn = _mraw.__func__ if isinstance(_mraw, (classmethod, staticmethod)) else _mraw
    _mbody = _make_docstring_body(_mfn, indent + "    ") if include_doc_m else "..."

    body_params = [s for s in param_strs if s not in ("self", "cls")]
    if len(body_params) <= 2:
        sig = f"{indent}{keyword} {method_name}({', '.join(param_strs)}){ret_part}"
        if _mbody == "...":
            lines.append(f"{sig}: ...")
        else:
            lines.append(f"{sig}:")
            lines.append(f"{indent}    {_mbody}")
    else:
        inner  = indent + "    "
        joined = f",\n{inner}".join(param_strs)
        lines.append(f"{indent}{keyword} {method_name}(")
        lines.append(f"{inner}{joined},")
        if _mbody == "...":
            lines.append(f"{indent}){ret_part}: ...")
        else:
            lines.append(f"{indent}){ret_part}:")
            lines.append(f"{indent}    {_mbody}")

    return "\n".join(lines)


def generate_class_stub(cls: type, ctx: StubContext) -> str:
    """Generate the full ``.pyi`` block for *cls*.

    Dispatches to specialised generators for NamedTuple subclasses and
    dataclasses before falling back to standard reflection.  Abstract
    methods receive ``@abstractmethod``; async methods receive ``async def``.

    Parameters
    ----------
    cls : type
        The class to stub.
    ctx : StubContext
        The current :class:`~stubpy.context.StubContext`.

    Returns
    -------
    str
        Complete class stub as a multi-line string without a trailing newline.

    Examples
    --------
    >>> from stubpy.context import StubContext
    >>> class Point:
    ...     x: float
    ...     y: float
    ...     def __init__(self, x: float, y: float) -> None: ...
    >>> stub = generate_class_stub(Point, StubContext())
    >>> "class Point:" in stub
    True
    >>> "x: float" in stub
    True
    """
    if _is_typeddict(cls):
        return _emit_typeddict_stub(cls, ctx)
    if _is_namedtuple(cls):
        return _generate_namedtuple_stub(cls, ctx)

    is_dc = _is_dataclass(cls)

    prefix_lines: list[str] = []
    if is_dc:
        prefix_lines.append("@dataclass")

    # ── Base class resolution ─────────────────────────────────────────────
    # Prefer __orig_bases__ (PEP 560, Python 3.7+) over __bases__ because
    # __bases__ erases subscript information: Generic[T] → Generic.
    # We render each orig-base using annotation_to_str so alias names and
    # subscripts are preserved correctly.
    orig_bases = getattr(cls, "__orig_bases__", None)
    if orig_bases:
        bases: list[str] = []
        import typing as _typing_mod
        _tdict = getattr(_typing_mod, "TypedDict", None)
        for b in orig_bases:
            if b is object:
                continue
            # TypedDict appears as the TypedDict function in __orig_bases__
            if b is _tdict:
                bases.append("TypedDict")
                continue
            b_str = annotation_to_str(b, ctx)
            if b_str and b_str not in ("object", ""):
                bases.append(b_str)
    else:
        bases = []
        for b in cls.__bases__:
            if b is object:
                continue
            if b is tuple and _is_namedtuple(cls):
                bases.append("NamedTuple")
            else:
                bases.append(b.__name__)
    base_str = f"({', '.join(bases)})" if bases else ""

    lines: list[str] = prefix_lines + [f"class {cls.__name__}{base_str}:"]

    own_annotations: dict = cls.__dict__.get("__annotations__", {})
    if is_dc:
        _emit_dataclass_annotations(cls, own_annotations, ctx, lines)
    else:
        for attr_name, ann in own_annotations.items():
            lines.append(f"    {attr_name}: {annotation_to_str(ann, ctx)}")

    if own_annotations:
        lines.append("")

    method_names = methods_defined_on(cls)
    if _is_enum(cls):
        method_names = [m for m in method_names if m not in _ENUM_PRIVATE_METHODS]

    if is_dc:
        non_init = [m for m in method_names if m != "__init__"]
        init_stub = _synthesize_dataclass_init(cls, ctx)
        method_stubs: list[str] = [init_stub] if init_stub else []
        for mn in non_init:
            stub = generate_method_stub(cls, mn, ctx)
            if stub:
                method_stubs.append(stub)
    else:
        method_stubs = []
        for mn in method_names:
            stub = generate_method_stub(cls, mn, ctx)
            if stub:
                method_stubs.append(stub)

    # Inject class docstring as first body statement
    if getattr(ctx.config, "include_docstrings", False):
        cls_doc_body = _make_docstring_body(cls, "    ")
        if cls_doc_body != "...":
            lines.insert(len(lines), f"    {cls_doc_body}")

    if not method_stubs and not own_annotations and not getattr(ctx.config, "include_docstrings", False):
        lines.append("    ...")
    elif not method_stubs and not own_annotations:
        if not getattr(cls, "__doc__", None) or not cls.__doc__.strip():
            lines.append("    ...")
    else:
        lines.extend(method_stubs)

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Module-level symbol stubs
# ---------------------------------------------------------------------------

def generate_function_stub(
    sym: "FunctionSymbol",
    ctx: StubContext,
) -> str:
    """Generate the ``.pyi`` stub line(s) for a module-level function.

    Handles both synchronous and asynchronous functions.  The ``async``
    keyword is emitted when :attr:`~stubpy.symbols.FunctionSymbol.is_async`
    is ``True`` or :func:`inspect.iscoroutinefunction` confirms it at
    runtime.

    Parameter formatting follows the same inline / multi-line rules as
    :func:`generate_method_stub`: inline when ≤ 2 parameters, multi-line
    otherwise.  Raw AST annotation strings are used where they preserve
    type-alias information that runtime evaluation would destroy.

    Parameters
    ----------
    sym : FunctionSymbol
        The function symbol from the :class:`~stubpy.symbols.SymbolTable`.
    ctx : StubContext
        The current :class:`~stubpy.context.StubContext`.

    Returns
    -------
    str
        One or more stub lines.

    Examples
    --------
    >>> from stubpy.context import StubContext
    >>> from stubpy.symbols import FunctionSymbol
    >>> from stubpy.ast_pass import FunctionInfo
    >>> fi = FunctionInfo(name="greet", lineno=1, raw_return_annotation="str")
    >>> def greet(name: str) -> str: return name
    >>> sym = FunctionSymbol("greet", 1, live_func=greet, ast_info=fi)
    >>> "def greet" in generate_function_stub(sym, StubContext())
    True
    """
    is_async = sym.is_async
    if not is_async and sym.live_func is not None:
        is_async = (
            inspect.iscoroutinefunction(sym.live_func)
            or inspect.isasyncgenfunction(sym.live_func)
        )

    keyword = "async def" if is_async else "def"

    live_fn = sym.live_func

    # Build raw_anns early — needed for both resolved and fallback paths
    raw_anns: dict[str, str] = {}
    if sym.ast_info is not None:
        raw_anns = sym.ast_info.raw_arg_annotations

    if live_fn is not None:
        hints   = get_hints_for_method(live_fn)
        ret_ann = hints.get("return", inspect.Parameter.empty)
        ret_str = annotation_to_str(ret_ann, ctx)

        # ── kwargs / *args backtracing for standalone functions ────────────
        # Build ast_info_by_name once so recursive targets can resolve too.
        ast_info_by_name: dict = {}
        if ctx.symbol_table is not None:
            from .symbols import FunctionSymbol as _FS
            for _s in ctx.symbol_table:
                if isinstance(_s, _FS) and _s.ast_info is not None:
                    ast_info_by_name[_s.name] = _s.ast_info

        params_with_hints = resolve_function_params(
            live_fn,
            sym.ast_info,
            ctx.module_namespace,
            ast_info_by_name=ast_info_by_name,
        )
    else:
        hints   = {}
        ret_str = ""
        params_with_hints = []

    if not ret_str and sym.ast_info and sym.ast_info.raw_return_annotation:
        ret_str = sym.ast_info.raw_return_annotation

    params_with_hints = insert_pos_separator(params_with_hints)
    params_with_hints = insert_kw_separator(params_with_hints)

    param_strs = [
        "*" if p.name == _KW_SEP_NAME
        else "/" if p.name == _POS_SEP_NAME
        else format_param(p, h, ctx, raw_ann_override=raw_anns.get(_raw_key(p)))
        for p, h in params_with_hints
    ]

    ret_part = f" -> {ret_str}" if ret_str else ""
    include_doc = getattr(ctx.config, "include_docstrings", False)
    doc_body = (
        _make_docstring_body(live_fn, "    ")
        if include_doc and live_fn is not None
        else "..."
    )

    if len(param_strs) <= 2:
        sig = f"{keyword} {sym.name}({', '.join(param_strs)}){ret_part}"
        if doc_body == "...":
            return f"{sig}: ..."
        return f"{sig}:\n    {doc_body}"

    inner  = "    "
    joined = f",\n{inner}".join(param_strs)
    sig_lines = [
        f"{keyword} {sym.name}(",
        f"{inner}{joined},",
        f"){ret_part}:",
    ]
    if doc_body == "...":
        sig_lines[-1] = sig_lines[-1][:-1] + ": ..."  # put ... on same line
        return "\n".join(sig_lines[:-1] + [sig_lines[-1]])
    return "\n".join(sig_lines + [f"{inner}{doc_body}"])


def generate_variable_stub(
    sym: "VariableSymbol",
    ctx: StubContext,
) -> str:
    """Generate a ``name: Type`` line for a module-level variable.

    Resolution order for the type string:

    1. **AST annotation string** — the annotation as written in source.
    2. **Inferred type** — ``type(live_value).__name__`` when the variable
       has no annotation.  A ``WARNING`` diagnostic is recorded because the
       inferred type may be imprecise.
    3. **Skip** — returns ``""`` if neither source is available.

    Parameters
    ----------
    sym : VariableSymbol
        The variable symbol from the :class:`~stubpy.symbols.SymbolTable`.
    ctx : StubContext
        The current :class:`~stubpy.context.StubContext`.

    Returns
    -------
    str
        A single ``name: Type`` line, or ``""`` when the type cannot be
        determined.

    Examples
    --------
    >>> from stubpy.context import StubContext
    >>> from stubpy.symbols import VariableSymbol
    >>> sym = VariableSymbol("MAX", 1, annotation_str="int", live_value=100)
    >>> generate_variable_stub(sym, StubContext())
    'MAX: int'
    >>> sym2 = VariableSymbol("FLAG", 2, live_value=True, inferred_type_str="bool")
    >>> generate_variable_stub(sym2, StubContext())
    'FLAG: bool'
    """
    type_str = sym.annotation_str

    if type_str is None:
        if sym.inferred_type_str:
            type_str = sym.inferred_type_str
            ctx.diagnostics.warning(
                DiagnosticStage.EMIT,
                sym.name,
                f"No annotation on {sym.name!r}; using inferred type"
                f" {type_str!r} from runtime value",
            )
        else:
            return ""

    return f"{sym.name}: {type_str}"


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Alias and overload stubs
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------

def generate_alias_stub(
    sym: "AliasSymbol",
    ctx: StubContext,
) -> str:
    """Re-emit a TypeVar, TypeAlias, NewType, ParamSpec, or TypeVarTuple declaration.

    The source text is taken verbatim from the AST pre-pass
    (:attr:`~stubpy.symbols.AliasSymbol.ast_info`) so that constraints,
    bounds, and alias expansions are preserved exactly as written.

    Emission format per kind is controlled by
    :attr:`~stubpy.context.StubConfig.alias_style`:

    **TypeAlias declarations** (annotated, implicit bare, or PEP 695):

    - ``"compatible"`` (default) — ``Name: TypeAlias = <rhs>``
      Works on all Python 3.10+ versions.
    - ``"pep695"`` — ``type Name = <rhs>``
      Python 3.12+ only.
    - ``"auto"`` — uses ``pep695`` when running on Python 3.12+,
      otherwise falls back to ``compatible``.

    **TypeVar / ParamSpec / TypeVarTuple / NewType** always emit as
    ``Name = Kind(...)`` regardless of ``alias_style``.

    Parameters
    ----------
    sym : AliasSymbol
        The alias symbol from the :class:`~stubpy.symbols.SymbolTable`.
    ctx : StubContext
        The current :class:`~stubpy.context.StubContext`.

    Returns
    -------
    str
        One declaration line, or ``""`` when insufficient AST data
        is available.

    Examples
    --------
    >>> from stubpy.context import StubContext
    >>> from stubpy.symbols import AliasSymbol
    >>> from stubpy.ast_pass import TypeVarInfo
    >>> tv = TypeVarInfo(name="T", lineno=1, kind="TypeVar", source_str="TypeVar('T')")
    >>> sym = AliasSymbol("T", lineno=1, ast_info=tv)
    >>> generate_alias_stub(sym, StubContext())
    "T = TypeVar('T')"
    """
    ai = sym.ast_info
    if ai is None:
        return ""

    if ai.kind == "TypeAlias":
        style = _resolve_alias_style(ctx)
        if style == "pep695":
            # Python 3.12+ ``type Name = <rhs>`` form
            return f"type {sym.name} = {ai.source_str}" if ai.source_str else f"type {sym.name}"
        # compatible: ``Name: TypeAlias = <rhs>`` — works on all supported versions
        if ai.source_str:
            return f"{sym.name}: TypeAlias = {ai.source_str}"
        return f"{sym.name}: TypeAlias"

    # TypeVar / ParamSpec / TypeVarTuple / NewType — call-expression form
    if ai.source_str:
        return f"{sym.name} = {ai.source_str}"
    return ""


def _resolve_alias_style(ctx: StubContext) -> str:
    """Resolve the effective type-alias style from the context config.

    Returns ``"pep695"`` or ``"compatible"``.  The ``"auto"`` setting
    selects ``"pep695"`` on Python 3.12+ and ``"compatible"`` otherwise.
    """
    import sys
    style = getattr(ctx.config, "alias_style", "compatible")
    if style == "auto":
        return "pep695" if sys.version_info >= (3, 12) else "compatible"
    return style if style in ("pep695", "compatible") else "compatible"


def generate_overload_group_stub(
    group: "OverloadGroup",
    ctx: StubContext,
) -> str:
    """Emit one ``@overload``-decorated stub per variant in *group*.

    PEP 484 mandates that stub files contain *one decorated stub per
    overload variant* and that the concrete implementation (the
    non-``@overload`` def) is **absent** from the stub.  This function
    produces the former; suppression of the latter is handled by the
    caller (:func:`~stubpy.generator.generate_stub`).

    Each variant in :attr:`~stubpy.symbols.OverloadGroup.variants` maps to
    a :class:`~stubpy.symbols.FunctionSymbol` whose
    :attr:`~stubpy.symbols.FunctionSymbol.ast_info` holds the raw
    parameter annotations from the AST pre-pass.

    Parameters
    ----------
    group : OverloadGroup
        The overload group from the :class:`~stubpy.symbols.SymbolTable`.
    ctx : StubContext
        The current :class:`~stubpy.context.StubContext`.

    Returns
    -------
    str
        All overload stubs joined by ``"\\n\\n"``, or ``""`` if the group
        has no variants.

    Examples
    --------
    >>> from stubpy.context import StubContext
    >>> from stubpy.symbols import OverloadGroup, FunctionSymbol
    >>> from stubpy.ast_pass import FunctionInfo
    >>> fi1 = FunctionInfo("parse", 1, raw_return_annotation="int",
    ...                    raw_arg_annotations={"x": "int"})
    >>> fi2 = FunctionInfo("parse", 3, raw_return_annotation="str",
    ...                    raw_arg_annotations={"x": "str"})
    >>> sym1 = FunctionSymbol("parse", 1, ast_info=fi1)
    >>> sym2 = FunctionSymbol("parse", 3, ast_info=fi2)
    >>> g = OverloadGroup("parse", 1, variants=[sym1, sym2])
    >>> stub = generate_overload_group_stub(g, StubContext())
    >>> stub.count("@overload")
    2
    >>> "@overload" in stub
    True
    """
    if not group.variants:
        return ""

    variant_stubs: list[str] = []
    for variant_sym in group.variants:
        inner = _generate_overload_variant(variant_sym, group, ctx)
        if inner:
            variant_stubs.append(inner)

    return "\n\n".join(variant_stubs)


def _generate_overload_variant(
    sym: "FunctionSymbol",
    group: "OverloadGroup",
    ctx: StubContext,
) -> str:
    """Emit one ``@overload`` stub for a single overload variant.

    Uses AST annotation strings from *sym.ast_info* as the primary
    annotation source.  Falls back to runtime introspection of
    *group.live_func* when AST data is incomplete.
    """
    is_async = sym.is_async
    if not is_async and group.live_func is not None:
        is_async = (
            inspect.iscoroutinefunction(group.live_func)
            or inspect.isasyncgenfunction(group.live_func)
        )

    keyword = "async def" if is_async else "def"
    name = sym.name

    # ── Build parameter list ──────────────────────────────────────────
    # Prefer AST-derived raw annotations for this specific variant.
    raw_anns: dict[str, str] = {}
    if sym.ast_info is not None:
        raw_anns = sym.ast_info.raw_arg_annotations

    # Build params from live function if available, else synthesise from AST.
    params: list[inspect.Parameter] = []
    hints: dict = {}
    if group.live_func is not None:
        try:
            params = list(inspect.signature(group.live_func).parameters.values())
            hints  = get_hints_for_method(group.live_func)
        except (ValueError, TypeError):
            params = []

    params_with_hints: list[ParamWithHints] = [(p, hints) for p in params]
    params_with_hints = insert_pos_separator(params_with_hints)
    params_with_hints = insert_kw_separator(params_with_hints)

    param_strs = [
        "*" if p.name == _KW_SEP_NAME
        else "/" if p.name == _POS_SEP_NAME
        else format_param(p, h, ctx, raw_ann_override=raw_anns.get(_raw_key(p)))
        for p, h in params_with_hints
    ]

    # ── Return type ──────────────────────────────────────────────────
    ret_str = ""
    if sym.ast_info and sym.ast_info.raw_return_annotation:
        ret_str = sym.ast_info.raw_return_annotation
    elif hints:
        ret_ann = hints.get("return", inspect.Parameter.empty)
        ret_str = annotation_to_str(ret_ann, ctx)

    ret_part = f" -> {ret_str}" if ret_str else ""

    # ── Format ──────────────────────────────────────────────────────
    lines = ["@overload"]
    if len(param_strs) <= 2:
        lines.append(f"{keyword} {name}({', '.join(param_strs)}){ret_part}: ...")
    else:
        inner  = "    "
        joined = f",\n{inner}".join(param_strs)
        lines.append(f"{keyword} {name}(")
        lines.append(f"{inner}{joined},")
        lines.append(f"){ret_part}: ...")

    return "\n".join(lines)



# ---------------------------------------------------------------------------
# Docstring embedding helper
# ---------------------------------------------------------------------------

def _make_docstring_body(obj: object, indent: str) -> str:
    """Return a triple-quoted docstring block for *obj*, or ``...``.

    Called by emitters when :attr:`~stubpy.context.StubConfig.include_docstrings`
    is ``True``.  Falls back to ``...`` if *obj* has no useful docstring.

    Parameters
    ----------
    obj : object
        The live callable, class, or other object whose ``__doc__`` to embed.
    indent : str
        Indentation prefix (e.g. ``"    "`` for method bodies).

    Returns
    -------
    str
        Either a triple-quoted literal block or the string ``"..."``.
    """
    import textwrap
    doc = getattr(obj, "__doc__", None)
    if not doc or not doc.strip():
        return "..."
    cleaned = textwrap.dedent(doc).strip()
    # Escape any triple-quote sequences
    cleaned = cleaned.replace('"""', r'\"\"\"')
    lines = cleaned.splitlines()
    if len(lines) == 1 and len(cleaned) < 72:
        return f'"""{cleaned}"""'
    inner = ("\n" + indent).join(lines)
    return f'"""\n{indent}{inner}\n{indent}"""'
