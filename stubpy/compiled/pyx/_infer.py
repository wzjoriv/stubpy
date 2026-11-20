"""
Return types a ``.pyx`` does not declare, inferred from ``cdef`` declarations and ``return`` statements.
"""
from __future__ import annotations

import ast
import re

from stubpy.compiled._constants import BUILTIN_CALL_TYPES, NUMPY_ARRAY_FACTORIES

from ..signatures import ANY_ARRAY, normalize_type, split_top
from ._reader import _function, _statements
from .models import PyxFunction, PyxModule

_CLASS = re.compile(r"^(?:cdef\s+(?:public\s+|api\s+)*)?class\s+([A-Za-z_]\w*)")
_CDEF = re.compile(
    r"^cdef\s+(?!class\b|enum\b|extern\b|struct\b|union\b|cppclass\b|inline\b|public\b|readonly\b)(.+)$")
_FIELD = re.compile(r"^cdef\s+(?:public|readonly)\s+(.+)$")
_ASSIGN = re.compile(r"^([A-Za-z_]\w*)\s*=(?!=)\s*(.+)$")
_NUMPY_IMPORT = re.compile(r"^import\s+numpy(?:\s+as\s+([A-Za-z_]\w*))?\s*$")
_BLOCK = re.compile(r"^(?:async\s+)?(?:def|cpdef|class|cdef\s+class)\b")
_YIELD = re.compile(r"\byield\b")
_MAX_DEPTH = 8


def _declared(text: str) -> dict[str, str]:
    """Map the names of ``<type> a, b = 1`` (a ``cdef`` without its keyword) to the type."""
    parts = split_top(text)
    if not parts:
        return {}
    head = parts[0].partition("=")[0].strip()
    found = re.search(r"([A-Za-z_]\w*)\s*$", head)
    if found is None or not head[: found.start()].strip():
        return {}
    ctype = head[: found.start()].strip()
    names = [found.group(1)] + [p.partition("=")[0].strip() for p in parts[1:]]
    return {n: ctype for n in names if n.isidentifier()}


def _mapped(ctype: str | None) -> str | None:
    """Return the Python type of a C or Python type text; ``None`` for ``object`` and unknowns."""
    found = normalize_type(ctype, c_style=True) if ctype else None
    return found if found and found != "Any" else None


class _Body:
    """What one function body says: typed names, assignments and returned expressions."""

    def __init__(self, fn: PyxFunction, body: list[str], fields: dict[str, str], numpy: set[str],
                 classes: set[str]) -> None:
        self.ctypes = {p.name: p.ctype for p in fn.params if p.ctype and not p.star}
        self.values: dict[str, list[str]] = {}
        self.returns: list[str | None] = []
        self.generator = False
        self.fields, self.numpy, self.classes = fields, numpy, classes
        for line in body:
            if m := _CDEF.match(line):
                self.ctypes.update(_declared(m.group(1)))
            elif m := _ASSIGN.match(line):
                self.values.setdefault(m.group(1), []).append(m.group(2))
            elif line == "return" or line.startswith("return "):
                self.returns.append(line[len("return"):].strip() or None)
            elif _YIELD.search(line):
                self.generator = True

    def text(self, text: str, depth: int = 0) -> list[str] | None:
        """Return the types of the expression *text*, or ``None`` when one is unknown."""
        try:
            node = ast.parse(text, mode="eval").body
        except SyntaxError:
            return None
        return self.node(node, depth)

    def node(self, node: ast.expr, depth: int) -> list[str] | None:
        """Return the types of *node*, or ``None`` when one is unknown."""
        if depth > _MAX_DEPTH:
            return None
        if isinstance(node, ast.Constant):
            kind = type(node.value)
            return ["None" if node.value is None else kind.__name__] if node.value is None or kind in (
                int, float, complex, str, bytes, bool) else None
        if isinstance(node, ast.IfExp):
            a, b = self.node(node.body, depth + 1), self.node(node.orelse, depth + 1)
            return a + b if a is not None and b is not None else None
        if isinstance(node, ast.Compare) or (isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not)):
            return ["bool"]
        if isinstance(node, ast.Name):
            return self._name(node.id, depth)
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "self":
            found = _mapped(self.fields.get(node.attr))
            return [found] if found else None
        if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Attribute) and node.value.attr == "shape":
            return ["int"]
        if isinstance(node, ast.Call):
            return self._call(node)
        return None

    def _name(self, name: str, depth: int) -> list[str] | None:
        if name in self.ctypes:
            found = _mapped(self.ctypes[name])
            return [found] if found else None
        out: list[str] = []
        for value in self.values.get(name) or [None]:
            found = self.text(value, depth + 1) if value is not None else None
            if found is None:
                return None
            out += found
        return out

    def _call(self, node: ast.Call) -> list[str] | None:
        func = node.func
        if isinstance(func, ast.Name):
            if func.id in BUILTIN_CALL_TYPES:
                return [BUILTIN_CALL_TYPES[func.id]]
            return [func.id] if func.id in self.classes else None
        if (isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name) and func.value.id in self.numpy
                and func.attr in NUMPY_ARRAY_FACTORIES):
            dtype = next((k.value for k in node.keywords if k.arg == "dtype"), None)
            if isinstance(dtype, ast.Attribute) and isinstance(dtype.value, ast.Name) and dtype.value.id in self.numpy:
                return [f"numpy.typing.NDArray[numpy.{dtype.attr}]"]
            return [ANY_ARRAY]
        return None

    def result(self) -> str | None:
        """Return the union of the returned types, ``None`` (the text) without a value, or ``None`` if unknown."""
        if self.generator:
            return None
        found: list[str] = []
        for text in self.returns:
            types = ["None"] if text is None else self.text(text)
            if types is None:
                return None
            found += types
        rest = list(dict.fromkeys(t for t in found if t != "None"))
        return " | ".join(rest + (["None"] if "None" in found or not found else []))


def _block(stmts: list[tuple[int, str]], start: int, indent: int) -> list[str]:
    """Return the statements of the block opened at *start*, nested function and class bodies left out."""
    out: list[str] = []
    skip: int | None = None
    for ind, line in stmts[start + 1:]:
        if ind <= indent:
            break
        if skip is not None and ind > skip:
            continue
        skip = ind if _BLOCK.match(line) else None
        if skip is None:
            out.append(line)
    return out


def _target(module: PyxModule, owner: str | None, name: str) -> PyxFunction | None:
    """Return the function *name* of *module*, or the method *name* of class *owner*."""
    if owner is None:
        return next((f for f in module.functions if f.name == name), None)
    cls = next((c for c in module.classes if c.name == owner), None)
    return next((m for m in cls.methods if m.name == name), None) if cls is not None else None


def infer_returns(module: PyxModule, text: str) -> PyxModule:
    """Fill the return type of each function and method of *module* that declares none, from *text*.

    Returned literals, typed parameters and ``cdef`` locals, ``cdef`` fields of
    the class (``self.x``), ``.shape[i]``, builtin conversions, classes of the
    module and NumPy array factories are understood; a function whose returns
    are all understood gets their union, one without a returned value gets
    ``None``.  Generators and anything else are left untyped.

    Parameters
    ----------
    module : PyxModule
        What a reader found in *text*; changed in place.
    text : str
        The ``.pyx`` source.

    Returns
    -------
    PyxModule
        *module*.

    See Also
    --------
    stubpy.compiled.pyx.read_pyx_file : Reads a file and applies this.

    Examples
    --------
    >>> from stubpy.compiled.pyx import read_pyx
    >>> src = "def f(int n):\\n    cdef double x = n\\n    return x\\n"
    >>> infer_returns(read_pyx(src), src).functions[0].returns
    'float'
    """
    stmts = _statements(text)
    numpy = {m.group(1) or "numpy" for _, line in stmts if (m := _NUMPY_IMPORT.match(line))}
    classes = {c.name for c in module.classes} | {e.name for e in module.enums}
    owners: list[tuple[int, str]] = []
    fields: dict[str, dict[str, str]] = {}
    for i, (indent, line) in enumerate(stmts):
        while owners and indent <= owners[-1][0]:
            owners.pop()
        owner = owners[-1][1] if owners else None
        if m := _CLASS.match(line):
            owners.append((indent, m.group(1)))
            continue
        if owner is not None and (m := _FIELD.match(line) or _CDEF.match(line)):
            fields.setdefault(owner, {}).update(_declared(m.group(1)))
            continue
        fn = _function(line, [], None)
        target = _target(module, owner, fn.name) if fn is not None else None
        if target is None or target.returns or target.name == "__init__":
            continue
        body = _Body(target, _block(stmts, i, indent), fields.get(owner or "", {}), numpy, classes)
        target.returns = body.result()
    return module
