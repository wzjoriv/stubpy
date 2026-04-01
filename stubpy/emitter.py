"""
stubpy.emitter
==============

Stub text generation — converts live objects and module-level symbols
into ``.pyi`` source text.

Two formatting modes are chosen automatically:

- **Inline** — used when a function / method has **≤ 2** non-self/cls
  parameters; the entire signature fits on one line.
- **Multi-line** — used for larger signatures; each parameter gets its
  own indented line with a trailing comma.

Special-class handling
----------------------
:func:`generate_class_stub` applies dedicated logic for three common
Python patterns before falling back to the general reflection path:

- **NamedTuple subclasses** — emits ``class Name(NamedTuple):`` with
  per-field annotations and default values.
- **@dataclass classes** — emits the ``@dataclass`` decorator and
  synthesises an ``__init__`` stub from ``__dataclass_fields__``,
  correctly handling ``default_factory``, ``init=False``, and
  ``ClassVar`` fields.
- **Abstract methods** — emits ``@abstractmethod`` for any callable
  whose ``__isabstractmethod__`` attribute is set.

All methods, including classmethods and staticmethods, emit ``async def``
when :func:`inspect.iscoroutinefunction` or
:func:`inspect.isasyncgenfunction` returns ``True``.
"""
from __future__ import annotations

import dataclasses as _dc
import inspect
from typing import TYPE_CHECKING

from .annotations import annotation_to_str, format_param, get_hints_for_method
from .context import StubContext
from .diagnostics import DiagnosticStage
from .resolver import ParamWithHints, _KW_ONLY, _VAR_POS, resolve_params

if TYPE_CHECKING:
    from .symbols import FunctionSymbol, VariableSymbol

#: Sentinel parameter name representing a bare ``*`` keyword-only separator.
_KW_SEP_NAME: str = "__kw_sep__"

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

def _generate_namedtuple_stub(cls: type, ctx: StubContext) -> str:
    """Generate the complete ``.pyi`` block for a NamedTuple subclass."""
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
            default_s = repr(defaults[name])
            lines.append(
                f"    {name}: {type_str} = {default_s}" if type_str
                else f"    {name} = {default_s}"
            )
        else:
            lines.append(f"    {name}: {type_str}" if type_str else f"    {name}: ...")

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
        else format_param(p, h, ctx, raw_ann_override=raw_anns.get(_raw_key(p)))
        for p, h in params_with_hints
    ]
    ret_part = f" -> {ret_str}" if ret_str else ""

    body_params = [s for s in param_strs if s not in ("self", "cls")]
    if len(body_params) <= 2:
        lines.append(
            f"{indent}{keyword} {method_name}({', '.join(param_strs)}){ret_part}: ..."
        )
    else:
        inner  = indent + "    "
        joined = f",\n{inner}".join(param_strs)
        lines.append(f"{indent}{keyword} {method_name}(")
        lines.append(f"{inner}{joined},")
        lines.append(f"{indent}){ret_part}: ...")

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
    if _is_namedtuple(cls):
        return _generate_namedtuple_stub(cls, ctx)

    is_dc = _is_dataclass(cls)

    prefix_lines: list[str] = []
    if is_dc:
        prefix_lines.append("@dataclass")

    bases: list[str] = []
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

    if not method_stubs and not own_annotations:
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
    if live_fn is not None:
        try:
            params = list(inspect.signature(live_fn).parameters.values())
        except (ValueError, TypeError):
            params = []
        hints   = get_hints_for_method(live_fn)
        ret_ann = hints.get("return", inspect.Parameter.empty)
        ret_str = annotation_to_str(ret_ann, ctx)
    else:
        params  = []
        hints   = {}
        ret_str = ""

    if not ret_str and sym.ast_info and sym.ast_info.raw_return_annotation:
        ret_str = sym.ast_info.raw_return_annotation

    raw_anns: dict[str, str] = {}
    if sym.ast_info is not None:
        raw_anns = sym.ast_info.raw_arg_annotations

    params_with_hints: list[ParamWithHints] = [(p, hints) for p in params]
    params_with_hints = insert_kw_separator(params_with_hints)

    param_strs = [
        "*" if p.name == _KW_SEP_NAME
        else format_param(p, h, ctx, raw_ann_override=raw_anns.get(_raw_key(p)))
        for p, h in params_with_hints
    ]

    ret_part = f" -> {ret_str}" if ret_str else ""

    if len(param_strs) <= 2:
        return f"{keyword} {sym.name}({', '.join(param_strs)}){ret_part}: ..."

    inner  = "    "
    joined = f",\n{inner}".join(param_strs)
    return "\n".join([
        f"{keyword} {sym.name}(",
        f"{inner}{joined},",
        f"){ret_part}: ...",
    ])


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
