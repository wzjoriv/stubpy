"""
stubpy.ast_pass
===============

AST pre-pass — harvests structural metadata from source *without executing*
the module.

This module runs a read-only walk over the source file's AST before (or
instead of) importing the module.  Because no code is executed, this pass
is free from import-time side effects.

The harvested data is stored in :class:`ASTSymbols` and fed into
:func:`~stubpy.symbols.build_symbol_table` to construct the
:class:`~stubpy.symbols.SymbolTable`.

What is harvested
-----------------

* **Classes** — name, source line, base class expressions (as strings),
  decorator names, and directly-defined methods.
* **Module-level functions** — name, line, ``async`` flag, decorator names,
  and a flag for ``@overload``-decorated variants.
* **Annotated variables** — ``name: Type = value`` at module scope.
* **``__all__``** — the explicit public API list, when present.
* **Type alias declarations** (all forms):

  - ``Name: TypeAlias = <rhs>``  — explicit PEP 613 annotation
  - ``Name = int | float``        — bare PEP 604 union
  - ``Name = Union[str, int]``    — subscripted generic
  - ``Name = int``                — known built-in or typing type name
  - ``type Name = <rhs>``         — Python 3.12+ PEP 695 soft keyword
  - ``type Stack[T] = list[T]``   — generic alias (PEP 695)

* **TypeVar / ParamSpec / TypeVarTuple / NewType** call-expression declarations.

Ignore directive
----------------

If the source file begins (before any code) with a comment containing
``# stubpy: ignore`` (case-insensitive), the harvester returns an empty
:class:`ASTSymbols` and the caller should skip stub generation for that
file.  Check :attr:`ASTSymbols.skip_file` to detect this.

What is *not* harvested
-----------------------

* Nested functions or classes inside other functions.
* Import statements (handled by :mod:`stubpy.imports`).
* Runtime values — those require the module to be executed.

Examples
--------
>>> from stubpy.ast_pass import ast_harvest
>>> syms = ast_harvest("x: int = 1\\nclass Foo: pass\\n")
>>> syms.variables[0].name
'x'
>>> syms.classes[0].name
'Foo'
"""
from __future__ import annotations

import ast
from dataclasses import dataclass, field

def _iter_body_calls(fn_node: "ast.FunctionDef | ast.AsyncFunctionDef") -> "Iterator[ast.Call]":
    """Yield all :class:`ast.Call` nodes in *fn_node*'s body.

    Unlike :func:`ast.walk`, this traversal **stops at nested function and
    class definitions** so that calls inside inner scopes are not attributed
    to the outer function's forwarding analysis.

    Parameters
    ----------
    fn_node : FunctionDef or AsyncFunctionDef
        The function whose body to traverse.

    Yields
    ------
    ast.Call
        Each call expression reachable from *fn_node*'s body, excluding
        those inside nested ``def``/``async def``/``class`` definitions.
    """
    def _walk(node: ast.AST) -> "Iterator[ast.Call]":
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue  # do not enter nested scopes
            if isinstance(child, ast.Call):
                yield child
            yield from _walk(child)

    yield from _walk(fn_node)




# ---------------------------------------------------------------------------
# Data containers for harvested metadata
# ---------------------------------------------------------------------------


@dataclass
class RawParam:
    """Structured parameter metadata extracted from an AST function definition.

    Represents a single parameter without requiring module execution,
    providing enough information to synthesize an :class:`inspect.Parameter`
    in AST-only mode.

    Attributes
    ----------
    name : str
        Parameter name (without ``*`` or ``**`` prefix).
    kind : str
        One of ``"POSITIONAL_ONLY"``, ``"POSITIONAL_OR_KEYWORD"``,
        ``"VAR_POSITIONAL"``, ``"KEYWORD_ONLY"``, ``"VAR_KEYWORD"``.
    annotation_str : str or None
        Unparsed annotation expression from the source, or ``None``.
    inferred_type_str : str or None
        Type inferred from the literal default value via
        :func:`infer_type_from_literal`, or ``None``.
    default_repr : str or None
        Unparsed default value expression string, or ``None`` when the
        parameter is required.
    """
    name:              str
    kind:              str
    annotation_str:    str | None = None
    inferred_type_str: str | None = None
    default_repr:      str | None = None

@dataclass
class FunctionInfo:
    """
    Metadata for a single function or method definition from the AST.

    Parameters
    ----------
    name : str
    lineno : int
    is_async : bool
        ``True`` for ``async def`` definitions.
    decorators : list of str
        Plain names of all decorators (e.g. ``["classmethod"]``).
    is_overload : bool
        ``True`` when ``overload`` appears in *decorators*.
    raw_arg_annotations : dict
        Maps parameter name → unparsed annotation string for every annotated
        parameter.  Variadic names are prefixed: ``"*args"``, ``"**kwargs"``.
    raw_return_annotation : str or None
        Unparsed return-annotation string, or ``None`` when absent.
    kwargs_forwarded_to : list of str
        Names of callables to which ``**kwargs`` is forwarded in the body.
    kwargs_positional_skips : dict of str → int
        Number of positional args pre-bound at each call site.  The resolver
        skips the first N non-variadic parameters of the target to avoid
        including already-bound params in the expanded stub.
    kwargs_explicit_names : dict of str → set of str
        Keyword arg names explicitly passed in each call (e.g. ``fmt=fmt``).
        Excluded from the expansion since they are already satisfied.
        Populated by the body scanner in
        :meth:`ASTHarvester._harvest_function`.  Used by
        :func:`~stubpy.resolver.resolve_function_params` to expand variadic
        parameters into their concrete counterparts.
    args_forwarded_to : list of str
        Names of callables to which ``*args`` is forwarded in the body.
        Same purpose as *kwargs_forwarded_to* for positional variadics.

    Examples
    --------
    >>> info = FunctionInfo(name="greet", lineno=5, is_async=False)
    >>> info.is_overload
    False
    >>> info.kwargs_forwarded_to
    []
    """
    name:                  str
    lineno:                int
    is_async:              bool                  = False
    decorators:            list[str]             = field(default_factory=list)
    is_overload:           bool                  = False
    raw_arg_annotations:   dict[str, str]        = field(default_factory=dict)
    # Maps parameter name → inferred type string from its literal default value.
    # Only populated for params that lack explicit annotations.
    # Used in AST-only mode to improve stubs without executing the module.
    raw_arg_inferred_types: dict[str, str]       = field(default_factory=dict)
    # Inferred return type from simple ``return <literal>`` statements.
    raw_inferred_return:    str | None            = None
    # Ordered list of all parameters with kind, annotation, default, and inferred type.
    raw_params:             list["RawParam"]      = field(default_factory=list)
    raw_return_annotation: str | None            = None
    kwargs_forwarded_to:   list[str]             = field(default_factory=list)
    args_forwarded_to:     list[str]             = field(default_factory=list)
    # Positional args pre-bound in each **kwargs forwarding call.
    # Maps target_name → number of positional arguments in the call.
    # Used by the resolver to skip positionally-bound parameters so they
    # don't appear in the expanded stub (e.g. ``save_svg(self.x, path, **kw)``
    # pre-binds ``element`` and ``path`` positionally — skip them).
    kwargs_positional_skips:  dict[str, int]       = field(default_factory=dict)
    # Keyword args explicitly passed in the forwarding call (by name).
    # These are already satisfied and should not appear in the expansion.
    kwargs_explicit_names:    dict[str, set[str]]  = field(default_factory=dict)
    # Method names called via self.X(**kwargs) or cls.X(**kwargs) inside the body.
    # Resolved against the class MRO, not the module namespace.
    kwargs_method_targets:    list[str]             = field(default_factory=list)
    args_method_targets:      list[str]             = field(default_factory=list)


@dataclass
class ClassInfo:
    """
    Metadata for a single class definition from the AST.

    Parameters
    ----------
    name : str
    lineno : int
    bases : list of str
        Base class expressions as unparsed strings (e.g. ``["Element"]``).
    decorators : list of str
        Plain decorator names.
    methods : list of FunctionInfo
        Methods defined directly in the class body.

    Examples
    --------
    >>> info = ClassInfo(name="Widget", lineno=10, bases=["Element"])
    >>> info.decorators
    []
    """
    name:       str
    lineno:     int
    bases:      list[str]         = field(default_factory=list)
    decorators: list[str]         = field(default_factory=list)
    methods:    list[FunctionInfo] = field(default_factory=list)


@dataclass
class VariableInfo:
    """
    Metadata for a module-level variable assignment.

    Covers both annotated assignments (``name: Type = value``) and
    plain assignments without annotations (``name = value``).

    Parameters
    ----------
    name : str
    lineno : int
    annotation_str : str or None
        Unparsed annotation expression, or ``None`` for unannotated assignments.
    value_repr : str or None
        Unparsed right-hand side expression, or ``None`` when absent.
    """
    name:           str
    lineno:         int
    annotation_str:    str | None  = None
    value_repr:        str | None  = None
    # Type inferred from the literal right-hand side when no annotation exists.
    # Set by :func:`infer_type_from_literal` during AST harvest.
    inferred_type_str: str | None  = None


@dataclass
class TypeVarInfo:
    """
    Metadata for a ``TypeVar``, ``ParamSpec``, ``TypeVarTuple``,
    ``TypeAlias``, or ``NewType`` declaration.

    Parameters
    ----------
    name : str
    lineno : int
    kind : str
        One of ``"TypeVar"``, ``"ParamSpec"``, ``"TypeVarTuple"``,
        ``"TypeAlias"``, ``"NewType"``.
    source_str : str
        Unparsed right-hand side expression (for TypeVar/NewType) or the
        aliased type expression (for TypeAlias).
    """
    name:       str
    lineno:     int
    kind:       str   # "TypeVar" | "ParamSpec" | "TypeVarTuple" | "TypeAlias" | "NewType"
    source_str: str


@dataclass
class ASTSymbols:
    """
    Container for all metadata harvested from a single source file's AST.

    Created by :func:`ast_harvest` and consumed by
    :func:`~stubpy.symbols.build_symbol_table`.

    Attributes
    ----------
    classes : list of ClassInfo
        All top-level class definitions, in source order.
    functions : list of FunctionInfo
        All top-level function definitions, in source order.
    variables : list of VariableInfo
        All top-level annotated (and plain) variable assignments.
    typevar_decls : list of TypeVarInfo
        TypeVar / ParamSpec / TypeVarTuple / TypeAlias / NewType declarations.
    all_exports : list of str or None
        Contents of ``__all__``, or ``None`` when the module has no
        ``__all__`` declaration.
    """
    classes:       list[ClassInfo]     = field(default_factory=list)
    functions:     list[FunctionInfo]  = field(default_factory=list)
    variables:     list[VariableInfo]  = field(default_factory=list)
    typevar_decls: list[TypeVarInfo]   = field(default_factory=list)
    all_exports:   list[str] | None   = None   # None = no __all__ found
    skip_file:     bool                = False  # True when # stubpy: ignore found


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

_TYPEVAR_CALL_NAMES: frozenset[str] = frozenset(
    {"TypeVar", "ParamSpec", "TypeVarTuple", "NewType"}
)
_OVERLOAD_NAMES: frozenset[str] = frozenset({"overload"})

# Known built-in type names that are always types, never plain values.
# Used to recognise implicit type-alias assignments like ``Color = str``.
_BUILTIN_TYPE_NAMES: frozenset[str] = frozenset({
    "int", "float", "complex", "bool", "str", "bytes", "bytearray",
    "list", "tuple", "set", "frozenset", "dict", "type", "object",
    "memoryview", "range", "slice",
})

# typing.__all__ names that function as types (not values or decorators).
# Populated once at import time; conservative — only the names that would
# never be used as plain variable values.
try:
    import typing as _typing_mod
    _TYPING_TYPE_NAMES: frozenset[str] = frozenset(
        n for n in _typing_mod.__all__
        if not n.startswith("_") and n[0].isupper()
    )
except Exception:
    _TYPING_TYPE_NAMES = frozenset({
        "Any", "Callable", "ClassVar", "Dict", "Final", "FrozenSet",
        "Generic", "Iterator", "List", "Literal", "Optional", "Protocol",
        "Sequence", "Set", "Tuple", "Type", "Union",
    })

# Combined set of names that are "always a type" and therefore safe to
# treat as implicit type aliases when they appear as a bare assignment RHS.
_KNOWN_TYPE_NAMES: frozenset[str] = _BUILTIN_TYPE_NAMES | _TYPING_TYPE_NAMES


def _is_implicit_alias(node: ast.expr | None) -> bool:
    """Return ``True`` when *node* looks like an implicit type alias RHS.

    Three patterns are recognised as unambiguous type alias expressions:

    1. **PEP 604 union** — ``int | float`` (``ast.BinOp`` with ``BitOr``).
    2. **Subscripted generic** — ``Union[str, int]``, ``list[int]``,
       ``Literal["a"]``, etc. (any ``ast.Subscript``).
    3. **Known-type bare name** — ``int``, ``str``, ``list``, ``Any``, etc.
       Only names in :data:`_KNOWN_TYPE_NAMES` qualify; arbitrary names such
       as ``SomeClass`` or ``logger`` do not, to avoid false positives.

    ``ast.Constant`` (numbers, strings), ``ast.Call`` (function calls), and
    unrecognised ``ast.Name`` nodes are intentionally excluded.

    .. note::
        ``Name = SomeArbitraryName`` is NOT treated as a TypeAlias because
        we cannot determine at parse time whether ``SomeArbitraryName`` is
        a type or a value without executing the module.  Use
        ``Name: TypeAlias = SomeArbitraryName`` or the Python 3.12+
        ``type Name = SomeArbitraryName`` form for unambiguous declaration.
    """
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        return True
    if isinstance(node, ast.Subscript):
        return True
    if isinstance(node, ast.Name) and node.id in _KNOWN_TYPE_NAMES:
        return True
    return False


def _decorator_name(node: ast.expr) -> str:
    """
    Return the simple name of a decorator node.

    Handles both ``@name`` (:class:`ast.Name`) and ``@module.name``
    (:class:`ast.Attribute`) forms.  Returns ``""`` for arbitrary
    expressions.
    """
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""


def _unparse(node: ast.expr | None) -> str | None:
    """Safely unparse an AST expression to its source string, or ``None``."""
    if node is None:
        return None
    try:
        return ast.unparse(node)
    except Exception:
        return None


def _extract_all_list(node: ast.Assign) -> list[str] | None:
    """
    Return the string elements of ``__all__ = [...]`` / ``__all__ = (...)``.

    Returns ``None`` if *node* is not an ``__all__`` assignment or the
    right-hand side is not a literal list/tuple of strings.
    """
    for target in node.targets:
        if isinstance(target, ast.Name) and target.id == "__all__":
            if isinstance(node.value, (ast.List, ast.Tuple)):
                result: list[str] = []
                for elt in node.value.elts:
                    if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                        result.append(elt.value)
                return result
    return None



def infer_type_from_literal(node: ast.expr) -> "str | None":
    """Infer a Python type name string from an AST literal expression.

    Used in AST-only mode to improve type coverage for variables and
    parameters that lack explicit annotations but have literal defaults.

    Supports: ``bool``, ``int``, ``float``, ``str``, ``bytes``,
    ``complex``, ``None``, homogeneous ``list``/``tuple``/``set``/``dict``
    literals, unary negation of numeric literals, and ``...`` (``Ellipsis``).

    Returns ``None`` when no type can be confidently inferred — e.g. for
    complex expressions, variables, or heterogeneous collections.

    Parameters
    ----------
    node : ast.expr
        An AST expression node, typically the right-hand side of an
        assignment or a parameter default.

    Returns
    -------
    str or None
        A type string such as ``"int"``, ``"str"``, ``"list[float]"``, or
        ``None`` when inference is not possible.

    Examples
    --------
    >>> import ast
    >>> infer_type_from_literal(ast.parse("42", mode="eval").body)
    'int'
    >>> infer_type_from_literal(ast.parse("[1, 2]", mode="eval").body)
    'list[int]'
    >>> infer_type_from_literal(ast.parse("some_var", mode="eval").body)
    """
    if isinstance(node, ast.Constant):
        v = node.value
        # Order matters: bool must come before int (bool is a subtype)
        if isinstance(v, bool):     return "bool"
        if isinstance(v, int):      return "int"
        if isinstance(v, float):    return "float"
        if isinstance(v, str):      return "str"
        if isinstance(v, bytes):    return "bytes"
        if isinstance(v, complex):  return "complex"
        if v is None:               return "None"
        if v is ...:                return "Any"   # Ellipsis default → Any
    # Unary minus: -42 → int, -3.14 → float
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        inner = infer_type_from_literal(node.operand)
        if inner in ("int", "float"):
            return inner
    # Complex via addition: 1+2j → complex
    if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub)):
        left  = infer_type_from_literal(node.left)
        right = infer_type_from_literal(node.right)
        if "complex" in (left, right) and all(
            t in ("int", "float", "complex") for t in (left, right) if t
        ):
            return "complex"
    # Homogeneous list literals: [1, 2, 3] → list[int]
    if isinstance(node, ast.List):
        if not node.elts:
            return "list"
        elem_types = {infer_type_from_literal(e) for e in node.elts}
        if len(elem_types) == 1 and None not in elem_types:
            return f"list[{elem_types.pop()}]"
        return "list"
    # Homogeneous tuple literals: (1, 2) → tuple[int, int]
    if isinstance(node, ast.Tuple):
        if not node.elts:
            return "tuple[()]"
        types = [infer_type_from_literal(e) for e in node.elts]
        if all(t is not None for t in types):
            return f"tuple[{', '.join(types)}]"
        return "tuple"
    # Homogeneous set literals: {1, 2} → set[int]
    if isinstance(node, ast.Set):
        if not node.elts:
            return "set"
        elem_types = {infer_type_from_literal(e) for e in node.elts}
        if len(elem_types) == 1 and None not in elem_types:
            return f"set[{elem_types.pop()}]"
        return "set"
    # Dict literals: {"a": 1} → dict[str, int]
    if isinstance(node, ast.Dict):
        if not node.keys:
            return "dict"
        key_types = {infer_type_from_literal(k) for k in node.keys if k is not None}
        val_types = {infer_type_from_literal(v) for v in node.values}
        if (len(key_types) == 1 and len(val_types) == 1
                and None not in key_types and None not in val_types):
            return f"dict[{key_types.pop()}, {val_types.pop()}]"
        return "dict"
    return None


def _call_func_name(call: ast.Call) -> str:
    """Extract the bare function name from a :class:`ast.Call` node, or ``""``."""
    func = call.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return ""


def _is_typevar_call(node: ast.expr | None) -> str | None:
    """
    Return the TypeVar/ParamSpec/etc. kind if *node* is a call to one of
    those constructors, or ``None`` otherwise.
    """
    if not isinstance(node, ast.Call):
        return None
    name = _call_func_name(node)
    return name if name in _TYPEVAR_CALL_NAMES else None




def _has_ignore_directive(source: str) -> bool:
    """Return ``True`` if the source begins with a ``# stubpy: ignore`` directive.

    Only lines that are blank, comment-only, or a module docstring (before the
    first non-trivial code statement) are inspected.  The check is
    case-insensitive and tolerates extra whitespace around the colon.

    Parameters
    ----------
    source : str
        Raw Python source text.

    Returns
    -------
    bool

    Examples
    --------
    >>> _has_ignore_directive("# stubpy: ignore\\nclass Foo: pass\\n")
    True
    >>> _has_ignore_directive("# STUBPY: IGNORE\\nclass Foo: pass\\n")
    True
    >>> _has_ignore_directive("# regular comment\\nclass Foo: pass\\n")
    False
    >>> _has_ignore_directive("class Foo: pass\\n# stubpy: ignore")
    False
    """
    import re as _re
    _IGNORE_RE = _re.compile(r"#\s*stubpy\s*:\s*ignore\b", _re.IGNORECASE)
    for line in source.splitlines():
        stripped = line.strip()
        if not stripped:
            continue  # blank line
        if stripped.startswith("#"):
            if _IGNORE_RE.search(stripped):
                return True
            continue  # other comment — keep scanning
        # First non-blank, non-comment line reached — stop
        break
    return False


# ---------------------------------------------------------------------------
# Harvester
# ---------------------------------------------------------------------------

class ASTHarvester(ast.NodeVisitor):
    """
    Walk the top-level AST of a Python source file and collect structural
    metadata without executing any code.

    Only **top-level** definitions are collected (class/function/variable
    statements that are direct children of the module body).  Statements
    nested inside ``if``, ``with``, or ``try`` blocks at the module level
    are visited transitively so that patterns like
    ``if TYPE_CHECKING: ...`` are still partially harvested.

    Parameters
    ----------
    source : str
        Raw Python source text.

    Examples
    --------
    >>> h = ASTHarvester("async def foo(): pass")
    >>> syms = h.harvest()
    >>> syms.functions[0].is_async
    True
    """

    def __init__(self, source: str) -> None:
        self._source = source
        self.result  = ASTSymbols()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def harvest(self) -> ASTSymbols:
        """
        Parse the source and return the populated :class:`ASTSymbols`.

        Returns an empty (but valid) :class:`ASTSymbols` on
        :exc:`SyntaxError` without raising.

        If the source begins (before any code) with a ``# stubpy: ignore``
        comment, :attr:`~ASTSymbols.skip_file` is set to ``True`` and the
        returned :class:`ASTSymbols` is otherwise empty.
        """
        # Check for the ignore directive in leading comments/blank lines.
        if _has_ignore_directive(self._source):
            self.result.skip_file = True
            return self.result

        try:
            tree = ast.parse(self._source)
        except SyntaxError:
            return self.result
        # Only visit immediate children of the module node so we don't
        # accidentally recurse into class bodies from visit_Module itself.
        for child in ast.iter_child_nodes(tree):
            self.visit(child)
        return self.result

    # ------------------------------------------------------------------
    # Top-level node visitors
    # ------------------------------------------------------------------

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        """Harvest a class definition and its directly-defined methods."""
        bases = [_unparse(b) or "" for b in node.bases]
        decorators = [_decorator_name(d) for d in node.decorator_list]

        info = ClassInfo(
            name=node.name,
            lineno=node.lineno,
            bases=[b for b in bases if b],
            decorators=[d for d in decorators if d],
        )

        # Harvest methods defined directly in the class body only
        for child in node.body:
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                info.methods.append(self._harvest_function(child))

        self.result.classes.append(info)
        # Do NOT recurse further — nested classes stay out of scope here

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Harvest a top-level synchronous function."""
        self.result.functions.append(self._harvest_function(node))

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        """Harvest a top-level asynchronous function."""
        self.result.functions.append(self._harvest_function(node, is_async=True))

    def visit_Assign(self, node: ast.Assign) -> None:
        """
        Handle:

        1. ``__all__ = [...]`` — populates :attr:`~ASTSymbols.all_exports`.
        2. ``X = TypeVar(...)`` / ``X = NewType(...)`` — explicit TypeVar declarations.
        3. ``X = int | float`` / ``X = Union[int, str]`` — implicit TypeAlias
           (bare union or subscripted generic RHS without an annotation).
        4. Plain ``name = value`` assignments — recorded as :class:`VariableInfo`.
        """
        # 1. __all__
        all_names = _extract_all_list(node)
        if all_names is not None:
            self.result.all_exports = all_names
            return

        if len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            target_name = node.targets[0].id

            # 2. TypeVar / ParamSpec / TypeVarTuple / NewType  (X = TypeVar("X"))
            kind = _is_typevar_call(node.value)
            if kind:
                self.result.typevar_decls.append(TypeVarInfo(
                    name=target_name,
                    lineno=node.lineno,
                    kind=kind,
                    source_str=_unparse(node.value) or "",
                ))
                return

            # 3. Bare union / subscripted generic — treat as implicit TypeAlias.
            # e.g. ``Color = str | tuple[float, ...]`` or
            #      ``Length = Union[str, float, int]``
            if _is_implicit_alias(node.value):
                self.result.typevar_decls.append(TypeVarInfo(
                    name=target_name,
                    lineno=node.lineno,
                    kind="TypeAlias",
                    source_str=_unparse(node.value) or "",
                ))
                return

        # 4. Plain variable assignment (no annotation)
        for target in node.targets:
            if isinstance(target, ast.Name):
                inferred = infer_type_from_literal(node.value) if node.value else None
                self.result.variables.append(VariableInfo(
                    name=target.id,
                    lineno=node.lineno,
                    annotation_str=None,
                    value_repr=_unparse(node.value),
                    inferred_type_str=inferred,
                ))

    def visit_TypeAlias(self, node: ast.AST) -> None:
        """Handle Python 3.12+ ``type Name = ...`` soft-keyword statement (PEP 695).

        The AST node is ``ast.TypeAlias`` (available from Python 3.12).  We
        access fields by attribute so the code compiles on Python 3.10/3.11
        where the class does not exist but the method will never be called.

        Examples
        --------
        The following source::

            type Vector = list[float]

        produces a ``TypeVarInfo`` with ``kind="TypeAlias"`` and
        ``source_str="list[float"]``.
        """
        # ast.TypeAlias has: .name (ast.Name), .type_params (list), .value (expr)
        name_node = getattr(node, "name", None)
        value_node = getattr(node, "value", None)
        if name_node is None or not hasattr(name_node, "id"):
            return
        self.result.typevar_decls.append(TypeVarInfo(
            name=name_node.id,
            lineno=getattr(node, "lineno", 0),
            kind="TypeAlias",
            source_str=_unparse(value_node) or "",
        ))

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        """
        Handle annotated assignments:
        * ``name: TypeAlias = int | str``  → :class:`TypeVarInfo`
        * ``name: Type = value``           → :class:`VariableInfo`
        """
        if not isinstance(node.target, ast.Name):
            return
        name = node.target.id

        ann_str = _unparse(node.annotation)

        # Detect  MyType: TypeAlias = ...
        if ann_str in ("TypeAlias", "typing.TypeAlias"):
            rhs = _unparse(node.value) if node.value else ""
            self.result.typevar_decls.append(TypeVarInfo(
                name=name,
                lineno=node.lineno,
                kind="TypeAlias",
                source_str=rhs or "",
            ))
            return

        self.result.variables.append(VariableInfo(
            name=name,
            lineno=node.lineno,
            annotation_str=ann_str,
            value_repr=_unparse(node.value) if node.value else None,
        ))

    # ------------------------------------------------------------------
    # Transitively visit common wrapper nodes so that top-level
    # definitions inside ``if TYPE_CHECKING:`` etc. are still harvested.
    # ------------------------------------------------------------------

    def visit_If(self, node: ast.If) -> None:
        """Recurse into if/else bodies (handles ``if TYPE_CHECKING:`` blocks)."""
        for child in node.body + node.orelse:
            self.visit(child)

    def visit_Try(self, node: ast.Try) -> None:
        """Recurse into try/except/else/finally bodies."""
        for child in node.body + node.orelse + node.finalbody:  # type: ignore[attr-defined]
            self.visit(child)
        for handler in node.handlers:
            for child in handler.body:
                self.visit(child)

    def visit_TryStar(self, node: ast.AST) -> None:  # Python 3.11+ ExceptionGroup
        self.generic_visit(node)

    def visit_With(self, node: ast.With) -> None:
        """Recurse into ``with`` blocks."""
        for child in node.body:
            self.visit(child)

    # Suppress generic recursion for everything else (Import, Expr, etc.)
    def generic_visit(self, node: ast.AST) -> None:  # type: ignore[override]
        pass

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _harvest_function(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
        is_async: bool | None = None,
    ) -> FunctionInfo:
        """Build a :class:`FunctionInfo` from a function definition AST node.

        Also scans the function body to detect variadic-forwarding patterns:
        any call expression where ``**kwargs_name`` or ``*args_name`` is
        passed through becomes an entry in
        :attr:`~stubpy.ast_pass.FunctionInfo.kwargs_forwarded_to` /
        :attr:`~stubpy.ast_pass.FunctionInfo.args_forwarded_to`.

        These fields are consumed by
        :func:`~stubpy.resolver.resolve_function_params` at stub-emission
        time to expand variadic parameters into their concrete counterparts.
        """
        if is_async is None:
            is_async = isinstance(node, ast.AsyncFunctionDef)

        decorator_names = [_decorator_name(d) for d in node.decorator_list
                           if _decorator_name(d)]
        is_overload = any(n in _OVERLOAD_NAMES for n in decorator_names)

        # ── Collect annotated parameters ──────────────────────────────────
        raw_arg_anns: dict[str, str] = {}
        all_args = (
            node.args.posonlyargs
            + node.args.args
            + node.args.kwonlyargs
        )
        for arg in all_args:
            if arg.annotation:
                s = _unparse(arg.annotation)
                if s:
                    raw_arg_anns[arg.arg] = s

        if node.args.vararg and node.args.vararg.annotation:
            s = _unparse(node.args.vararg.annotation)
            if s:
                raw_arg_anns[f"*{node.args.vararg.arg}"] = s

        if node.args.kwarg and node.args.kwarg.annotation:
            s = _unparse(node.args.kwarg.annotation)
            if s:
                raw_arg_anns[f"**{node.args.kwarg.arg}"] = s

        # ── Infer types from literal default values (AST-only mode improvement) ─
        # Build a param_name → default_node mapping for all args with defaults.
        raw_arg_inferred: dict[str, str] = {}
        all_args_with_defaults: list[tuple[ast.arg, ast.expr | None]] = []
        # posonlyargs and args share the trailing defaults list
        n_pos = len(node.args.posonlyargs) + len(node.args.args)
        n_defaults = len(node.args.defaults)
        for i, arg in enumerate(node.args.posonlyargs + node.args.args):
            default_offset = i - (n_pos - n_defaults)
            default = node.args.defaults[default_offset] if default_offset >= 0 else None
            all_args_with_defaults.append((arg, default))
        for arg, kw_default in zip(node.args.kwonlyargs, node.args.kw_defaults):
            all_args_with_defaults.append((arg, kw_default))
        for arg, default in all_args_with_defaults:
            if arg.arg in raw_arg_anns:
                continue  # already annotated — don't infer
            if default is None:
                continue  # no default → can't infer
            inferred = infer_type_from_literal(default)
            if inferred:
                raw_arg_inferred[arg.arg] = inferred

        # ── Infer return type from simple return statements ─────────────────
        raw_inferred_return: str | None = None
        return_types: set[str] = set()
        for stmt in ast.walk(node):
            if isinstance(stmt, ast.Return) and stmt.value is not None:
                t = infer_type_from_literal(stmt.value)
                if t:
                    return_types.add(t)
        if len(return_types) == 1:
            raw_inferred_return = return_types.pop()
        elif len(return_types) > 1:
            # Multiple different return type literals → union
            raw_inferred_return = " | ".join(sorted(return_types))

        # ── Scan body for **kwargs / *args forwarding targets ─────────────
        kwargs_name   = node.args.kwarg.arg  if node.args.kwarg  else None
        varargs_name  = node.args.vararg.arg if node.args.vararg else None
        kw_targets:         list[str]        = []
        pos_targets:        list[str]        = []
        kw_method_targets:  list[str]        = []  # self.X(**kwargs) targets
        args_method_targets: list[str]       = []  # self.X(*args) targets
        kw_positional_skips: dict[str, int]  = {}
        kw_explicit_names:   dict[str, set]  = {}

        if kwargs_name or varargs_name:
            for body_node in _iter_body_calls(node):
                fname = _call_func_name(body_node)
                if not fname:
                    continue

                if kwargs_name:
                    has_kw_fwd = any(
                        kw.arg is None
                        and isinstance(kw.value, ast.Name)
                        and kw.value.id == kwargs_name
                        for kw in body_node.keywords
                    )
                    if has_kw_fwd:
                        # Detect whether this is a self/cls method call
                        is_self_call = (
                            isinstance(body_node.func, ast.Attribute)
                            and isinstance(body_node.func.value, ast.Name)
                            and body_node.func.value.id in ("self", "cls")
                        )
                        target_list = kw_method_targets if is_self_call else kw_targets
                        if fname not in target_list:
                            target_list.append(fname)
                        # Count positional args pre-bound in this call site.
                        # These fill the target's first N params positionally,
                        # so the resolver must skip them during expansion.
                        pos_count = sum(
                            1 for a in body_node.args
                            if not isinstance(a, ast.Starred)
                        )
                        kw_positional_skips[fname] = max(
                            kw_positional_skips.get(fname, 0), pos_count
                        )
                        # Record explicitly named kwargs (e.g. fmt=fmt)
                        # so the resolver can exclude them from expansion.
                        explicit = {
                            kw.arg for kw in body_node.keywords
                            if kw.arg is not None
                        }
                        kw_explicit_names.setdefault(fname, set()).update(explicit)

                if varargs_name:
                    has_pos_fwd = any(
                        isinstance(arg, ast.Starred)
                        and isinstance(arg.value, ast.Name)
                        and arg.value.id == varargs_name
                        for arg in body_node.args
                    )
                    if has_pos_fwd:
                        is_self_call = (
                            isinstance(body_node.func, ast.Attribute)
                            and isinstance(body_node.func.value, ast.Name)
                            and body_node.func.value.id in ("self", "cls")
                        )
                        target_list = args_method_targets if is_self_call else pos_targets
                        if fname not in target_list:
                            target_list.append(fname)

        # ── Build ordered RawParam list ─────────────────────────────────────
        raw_params_list: list[RawParam] = []
        all_pos = node.args.posonlyargs + node.args.args
        n_pos_total = len(all_pos)
        n_defs = len(node.args.defaults)
        for i, arg in enumerate(node.args.posonlyargs):
            def_offset = i - (n_pos_total - n_defs)
            default = node.args.defaults[def_offset] if def_offset >= 0 else None
            raw_params_list.append(RawParam(
                name=arg.arg,
                kind="POSITIONAL_ONLY",
                annotation_str=raw_arg_anns.get(arg.arg),
                inferred_type_str=raw_arg_inferred.get(arg.arg),
                default_repr=_unparse(default) if default is not None else None,
            ))
        for i, arg in enumerate(node.args.args):
            idx_g = len(node.args.posonlyargs) + i
            def_offset = idx_g - (n_pos_total - n_defs)
            default = node.args.defaults[def_offset] if def_offset >= 0 else None
            raw_params_list.append(RawParam(
                name=arg.arg,
                kind="POSITIONAL_OR_KEYWORD",
                annotation_str=raw_arg_anns.get(arg.arg),
                inferred_type_str=raw_arg_inferred.get(arg.arg),
                default_repr=_unparse(default) if default is not None else None,
            ))
        if node.args.vararg:
            raw_params_list.append(RawParam(
                name=node.args.vararg.arg,
                kind="VAR_POSITIONAL",
                annotation_str=raw_arg_anns.get(f"*{node.args.vararg.arg}"),
            ))
        for arg, kw_def in zip(node.args.kwonlyargs, node.args.kw_defaults):
            raw_params_list.append(RawParam(
                name=arg.arg,
                kind="KEYWORD_ONLY",
                annotation_str=raw_arg_anns.get(arg.arg),
                inferred_type_str=raw_arg_inferred.get(arg.arg),
                default_repr=_unparse(kw_def) if kw_def is not None else None,
            ))
        if node.args.kwarg:
            raw_params_list.append(RawParam(
                name=node.args.kwarg.arg,
                kind="VAR_KEYWORD",
                annotation_str=raw_arg_anns.get(f"**{node.args.kwarg.arg}"),
            ))

        return FunctionInfo(
            name=node.name,
            lineno=node.lineno,
            is_async=is_async,
            decorators=decorator_names,
            is_overload=is_overload,
            raw_arg_annotations=raw_arg_anns,
            raw_return_annotation=_unparse(node.returns),
            kwargs_forwarded_to=kw_targets,
            args_forwarded_to=pos_targets,
            kwargs_positional_skips=kw_positional_skips,
            kwargs_explicit_names={k: frozenset(v) for k, v in kw_explicit_names.items()},
            kwargs_method_targets=kw_method_targets,
            args_method_targets=args_method_targets,
            raw_arg_inferred_types=raw_arg_inferred,
            raw_inferred_return=raw_inferred_return,
            raw_params=raw_params_list,
        )


# ---------------------------------------------------------------------------
# Public convenience function
# ---------------------------------------------------------------------------

def ast_harvest(source: str) -> ASTSymbols:
    """
    Parse *source* and return structural metadata without executing any code.

    This is the main entry point for the AST pre-pass stage.  A fresh
    :class:`ASTHarvester` is created for each call, making this function
    fully re-entrant.

    Parameters
    ----------
    source : str
        Raw Python source text.

    Returns
    -------
    ASTSymbols
        Populated container of all harvested metadata.  On a
        :exc:`SyntaxError` the result will be empty but valid — no
        exception is raised.

    Examples
    --------
    >>> syms = ast_harvest("")
    >>> syms.classes
    []
    >>> syms = ast_harvest("class Foo(Bar): pass")
    >>> syms.classes[0].name, syms.classes[0].bases
    ('Foo', ['Bar'])
    >>> syms = ast_harvest("async def fetch(url: str) -> None: ...")
    >>> fn = syms.functions[0]
    >>> fn.is_async, fn.name
    (True, 'fetch')
    >>> syms = ast_harvest("X = TypeVar('X')")
    >>> syms.typevar_decls[0].kind
    'TypeVar'
    """
    return ASTHarvester(source).harvest()
