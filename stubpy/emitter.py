"""
stubpy.emitter
==============

Stub text generation — converts live class objects into ``.pyi`` source.

Two formatting modes are chosen automatically:

- **Inline** for methods with **≤ 2** non-self/cls parameters.
- **Multi-line** for methods with **> 2** parameters, each on its own
  indented line with a trailing comma for clean diffs.
"""
from __future__ import annotations

import inspect

from .annotations import annotation_to_str, format_param, get_hints_for_method
from .context import StubContext
from .resolver import ParamWithHints, _KW_ONLY, _VAR_POS, resolve_params

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
})


def _raw_key(param: inspect.Parameter) -> str:
    """Return the key used in :attr:`~stubpy.ast_pass.FunctionInfo.raw_arg_annotations`.

    The AST harvester prefixes variadic parameter names with ``*`` or ``**``
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
    """Return raw AST annotation strings for *method_name* on *cls*, or ``{}``.

    Looks up the :class:`~stubpy.symbols.ClassSymbol` for *cls* in
    ``ctx.symbol_table``, then finds the matching
    :class:`~stubpy.ast_pass.FunctionInfo` among its methods and returns
    its :attr:`~stubpy.ast_pass.FunctionInfo.raw_arg_annotations` dict.

    Returns an empty dict when the symbol table is absent or when no AST
    info is available for this method (e.g. dynamically generated methods).
    """
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

    lines: list[str] = []

    if isinstance(raw, property):
        hints    = get_hints_for_method(raw.fget)
        ret_ann  = hints.get("return", inspect.Parameter.empty)
        ret_str  = annotation_to_str(ret_ann, ctx)
        ret_part = f" -> {ret_str}" if ret_str else ""

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

    is_cls = isinstance(raw, classmethod)
    is_sta = isinstance(raw, staticmethod)

    if is_cls:
        lines.append(f"{indent}@classmethod")
    elif is_sta:
        lines.append(f"{indent}@staticmethod")

    params_with_hints = resolve_params(cls, method_name)
    params_with_hints = insert_kw_separator(params_with_hints)

    own_hints = get_hints_for_method(raw)
    ret_ann   = own_hints.get("return", inspect.Parameter.empty)
    ret_str   = annotation_to_str(ret_ann, ctx)

    if not ret_str and method_name in ("__init__", "__new__"):
        ret_str = "None"

    # Look up raw AST annotation strings from the symbol table.
    # These preserve alias names (e.g. "Union[types.Color, int]") that
    # Python's typing.Union flattens away at evaluation time.
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
        lines.append(f"{indent}def {method_name}({', '.join(param_strs)}){ret_part}: ...")
    else:
        inner  = indent + "    "
        joined = f",\n{inner}".join(param_strs)
        lines.append(f"{indent}def {method_name}(")
        lines.append(f"{inner}{joined},")
        lines.append(f"{indent}){ret_part}: ...")

    return "\n".join(lines)


def generate_class_stub(cls: type, ctx: StubContext) -> str:
    """Generate the full ``.pyi`` block for *cls*.

    Emits in order:

    1. ``class Name(Base, ...):`` line.
    2. Class-level annotations from ``cls.__dict__["__annotations__"]``.
    3. A blank line after annotations when present.
    4. One stub per public method defined directly on *cls*.
    5. ``...`` when the class has neither annotations nor methods.

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
    bases    = [b.__name__ for b in cls.__bases__ if b is not object]
    base_str = f"({', '.join(bases)})" if bases else ""
    lines: list[str] = [f"class {cls.__name__}{base_str}:"]

    own_annotations = cls.__dict__.get("__annotations__", {})
    for attr_name, ann in own_annotations.items():
        lines.append(f"    {attr_name}: {annotation_to_str(ann, ctx)}")

    if own_annotations:
        lines.append("")

    method_names = methods_defined_on(cls)

    if not method_names and not own_annotations:
        lines.append("    ...")
    else:
        for method_name in method_names:
            stub = generate_method_stub(cls, method_name, ctx)
            if stub:
                lines.append(stub)

    return "\n".join(lines)
