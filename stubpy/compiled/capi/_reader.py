"""
Method tables, type objects, ``PyArg_Parse*`` calls and Argument Clinic blocks of C API source text.
"""
from __future__ import annotations

import re
from collections.abc import Iterator

from ..._constants import POS_ONLY, VAR_KW, VAR_POS
from .._constants import CAPI_MEMBER_TYPES, CAPI_RETURN_CALLS, CAPI_RETURN_MACROS
from ..signatures import Param, Signature
from ._formats import Unit, build_type, clinic_blocks, format_signature, parse_units
from ._lexer import (
    calls,
    entries,
    fields,
    functions,
    identifier,
    initialisers,
    split_args,
    string_value,
    strip_comments,
    strip_directives,
)
from .models import CModule

_KINDS = ("PyMethodDef", "PyGetSetDef", "PyMemberDef", "PyTypeObject", "PyType_Slot", "PyType_Spec")
_SLOTS = {"tp_methods": "methods", "tp_getset": "getset", "tp_members": "members", "tp_init": "init", "tp_new": "new"}
_KWLIST = re.compile(r"\bchar\s*\*\s*(?:const\s+)?(\w+)\s*\[\s*\]\s*=\s*\{([^{}]*)\}")
_TYPED_CONSTANT = re.compile(r'\bPyModule_Add(Int|String)(Constant|Macro)\s*\(\s*\w+\s*,\s*"?(\w+)"?')
_OBJECT_CONSTANT = re.compile(r'\bPyModule_AddObject(?:Ref)?\s*\(\s*\w+\s*,\s*"(\w+)"\s*,\s*(?:\(PyObject\s*\*\)\s*)?&?(\w+)')
_NEW_EXCEPTION = re.compile(r'\b(\w+)\s*=\s*PyErr_NewException(WithDoc)?\s*\(\s*"([\w.]+)"\s*,\s*((?:"(?:[^"\\]|\\.)*"\s*)+,\s*)?(PyExc_\w+|NULL)')
_NEW_VALUE = {"PyDict_New": "dict", "PyList_New": "list", "PyTuple_New": "tuple", "PyLong_From": "int",
              "PyFloat_From": "float", "PyUnicode_From": "str", "PyBool_From": "bool", "PyBytes_From": "bytes"}
_RETURN = re.compile(r"\breturn\b([^;]*);")
_ERROR_RETURNS = frozenset({"NULL", "0", "-1", "(PyObject *)NULL", "(PyObject*)NULL", ""})
_GENERIC = (Param("args", VAR_POS, "Any"), Param("kwargs", VAR_KW, "Any"))


def read_c_source(text: str) -> CModule:
    """Read the method tables, type objects and Argument Clinic blocks of C source *text*.

    Comments and preprocessor lines are dropped first, so both branches of an ``#if`` are
    read. Rows, calls and initialisers that do not have the expected shape are skipped.

    Parameters
    ----------
    text : str
        C source; several files may be joined into one text.

    Returns
    -------
    CModule
        The signatures and attribute types found; empty when there are none.

    See Also
    --------
    read_c_files : The same for the sources found next to a built extension.

    Examples
    --------
    >>> src = '''
    ... static PyObject *add(PyObject *self, PyObject *args) {
    ...     int a, b;
    ...     if (!PyArg_ParseTuple(args, "ii|d:add", &a, &b, &scale)) return NULL;
    ...     return PyLong_FromLong(a + b);
    ... }
    ... static PyMethodDef methods[] = {{"add", add, METH_VARARGS, NULL}, {NULL}};
    ... '''
    >>> read_c_source(src).signatures["add"].render()
    '(a: int, b: int, scale: float = ..., /) -> int'
    """
    code = strip_directives(strip_comments(text))
    funcs = functions(code)
    found = {kind: {} for kind in _KINDS}
    for kind, name, body in initialisers(code, _KINDS):
        found[kind].setdefault(name, body)
    module = CModule()
    owners = _types(found, module)
    reader = _Reader(code, funcs, module)
    for table, body in found["PyMethodDef"].items():
        prefix = owners.get(("methods", table), "")
        for row in entries(body):
            reader.method(row, prefix)
    for table, body in found["PyGetSetDef"].items():
        reader.getsets(body, owners.get(("getset", table)))
    for table, body in found["PyMemberDef"].items():
        reader.members(body, owners.get(("members", table)))
    for (slot, func), cls in owners.items():
        if slot in ("init", "new"):
            reader.constructor(func, cls, slot)
    _clinic(text, funcs, module)
    _module_attributes(code, module)
    return module


def _last(matches: Iterator[re.Match[str]]) -> re.Match[str] | None:
    """The last of *matches*, or ``None``."""
    return next(iter(reversed(list(matches))), None)


def _module_attributes(code: str, module: CModule) -> None:
    """Fill *module*'s constants and exceptions from the ``PyModule_Add*`` and ``PyErr_NewException`` calls in *code*."""
    exceptions: dict[str, tuple[str, str]] = {}
    for var, _, dotted, _, base in _NEW_EXCEPTION.findall(code):
        exceptions[var] = (dotted.rpartition(".")[2], base.removeprefix("PyExc_") if base != "NULL" else "Exception")
    for kind, _, name in _TYPED_CONSTANT.findall(code):
        module.constants.setdefault(name, "int" if kind == "Int" else "str")
    for found in _OBJECT_CONSTANT.finditer(code):
        name, var = found[1], found[2]
        if var in exceptions:
            module.exceptions[name] = exceptions[var][1]
        elif var not in module.classes and name not in module.constants:
            assigned = _last(re.finditer(r"\b" + re.escape(var) + r"\s*=\s*(Py\w+?)(?:Long|Double|String|Size_t|Ssize_t)?\s*\(", code[:found.start()]))
            made = assigned[1] if assigned else ""
            module.constants[name] = next((t for prefix, t in _NEW_VALUE.items() if made.startswith(prefix)), "Any")
    for name, base in exceptions.values():
        module.exceptions.setdefault(name, base)


def _types(found: dict[str, dict[str, str]], module: CModule) -> dict[tuple[str, str], str]:
    """``{(slot, C name): class}`` for the tables and constructors of every static type and type spec."""
    owners: dict[tuple[str, str], str] = {}
    tables = {kind: set(found[kind]) for kind in ("PyMethodDef", "PyGetSetDef", "PyMemberDef")}

    def claim(cls: str, named: dict[str, str], positional: list[str]) -> None:
        for slot, value in named.items():
            target = identifier(value)
            if slot in _SLOTS and target:
                owners.setdefault((_SLOTS[slot], target), cls)
        for value in positional:
            target = identifier(value)
            for kind, slot in (("PyMethodDef", "methods"), ("PyGetSetDef", "getset"), ("PyMemberDef", "members")):
                if target in tables[kind]:
                    owners.setdefault((slot, target), cls)

    for var, body in found["PyTypeObject"].items():
        named, positional = fields(body)
        cls = _class_name(named.get("tp_name"), positional)
        if cls:
            module.classes[var] = cls
            claim(cls, named, positional)
    for body in found["PyType_Spec"].values():
        named, positional = fields(body)
        cls = _class_name(named.get("name"), positional)
        slots = [identifier(v) for v in [named.get("slots", ""), *positional]]
        for name in slots:
            if cls and name in found["PyType_Slot"]:
                pairs = {row[0].removeprefix("Py_"): row[1] for row in entries(found["PyType_Slot"][name])
                         if len(row) == 2}
                claim(cls, pairs, [])
    return owners


def _class_name(value: str | None, positional: list[str]) -> str | None:
    text = string_value(value) if value else next((s for s in map(string_value, positional) if s), None)
    return text.rpartition(".")[2] or None if text else None


class _Reader:
    """Turns table rows and function bodies into entries of one :class:`CModule`."""

    def __init__(self, code: str, funcs: dict[str, tuple[list[str], str]], module: CModule) -> None:
        self.code, self.funcs, self.module = code, funcs, module

    def method(self, row: list[str], prefix: str) -> None:
        """Add the ``PyMethodDef`` *row* ``{"name", func, flags, doc}``."""
        name = string_value(row[0]) if len(row) >= 3 else None
        func = identifier(row[1]) if name else None
        if not name or func not in self.funcs:
            return
        flags = set(re.findall(r"METH_\w+", row[2]))
        params, body = self.funcs[func]
        doc = string_value(row[3]) if len(row) > 3 else None
        if doc:
            self.module.docs[f"{prefix}.{name}" if prefix else name] = doc
        if "METH_NOARGS" in flags:
            sig: Signature | None = Signature(())
        elif "METH_O" in flags:
            receiverless = params[1] if len(params) > 1 and params[1] else "arg"
            sig = Signature((Param(receiverless, POS_ONLY, _converted(body, receiverless)),))
        elif "METH_VARARGS" in flags:
            sig = self.parsed(body, "METH_KEYWORDS" in flags)
        else:
            sig = None
        returns = infer_return(body, self.funcs)
        if sig is None and returns is None:
            return
        sig = Signature(sig.params if sig is not None else _GENERIC, returns)
        self.module.signatures[f"{prefix}.{name}" if prefix else name] = sig

    def constructor(self, func: str, cls: str, slot: str) -> None:
        """Add ``Class.__init__`` from the ``tp_init`` (or ``tp_new``) function *func*."""
        label = f"{cls}.__init__"
        if func not in self.funcs or slot == "new" and label in self.module.signatures:
            return
        sig = self.parsed(self.funcs[func][1], True)
        if sig is not None:
            self.module.signatures[label] = Signature(sig.params, "None")

    def parsed(self, body: str, keywords: bool) -> Signature | None:
        """The signature of the one ``PyArg_Parse*`` / ``PyArg_UnpackTuple`` call in *body*, or ``None``."""
        found = [("kw", a) for a in calls(body, "PyArg_ParseTupleAndKeywords")] if keywords else []
        found += [("tuple", a) for a in calls(body, "PyArg_ParseTuple")]
        found += [("unpack", a) for a in calls(body, "PyArg_UnpackTuple")]
        if len({tuple(a[:4]) for _, a in found}) != 1:
            return None
        kind, args = found[0]
        if kind == "unpack":
            return _unpacked(args)
        fmt = string_value(args[2 if kind == "kw" else 1]) if len(args) > 2 else None
        parsed = parse_units(fmt) if fmt is not None else None
        if parsed is None:
            return None
        units = parsed[0]
        varargs = args[4:] if kind == "kw" else args[2:]
        names = self.kwlist(args[3], body) if kind == "kw" else _variables(units, varargs)
        if names is None or kind == "kw" and len(names) < len(units):
            return None
        return format_signature(units, names, keywords=kind == "kw", varargs=varargs, types=self.module.classes)

    def kwlist(self, arg: str, body: str) -> list[str] | None:
        """The names in the ``char *kwlist[]`` that *arg* refers to, preferring one declared in *body*."""
        name = identifier(arg)
        for text in (body, self.code):
            for m in _KWLIST.finditer(text):
                if m[1] == name:
                    names = [string_value(v) for v in split_args(m[2]) if v not in ("NULL", "0")]
                    return None if None in names else names
        return None

    def getsets(self, body: str, cls: str | None) -> None:
        """Add the getter types of ``PyGetSetDef`` rows."""
        for row in entries(body) if cls else ():
            name = string_value(row[0]) if len(row) >= 2 else None
            getter = identifier(row[1]) if name else None
            returns = infer_return(self.funcs[getter][1], self.funcs) if getter in self.funcs else None
            if name and returns:
                self.module.attributes[f"{cls}.{name}"] = returns

    def members(self, body: str, cls: str | None) -> None:
        """Add the types of ``PyMemberDef`` rows (``T_INT`` / ``Py_T_DOUBLE`` ...)."""
        for row in entries(body) if cls else ():
            name = string_value(row[0]) if len(row) >= 2 else None
            mapped = CAPI_MEMBER_TYPES.get(re.sub(r"^(?:Py_)?T_", "", row[1].strip())) if name else None
            if name and mapped:
                self.module.attributes[f"{cls}.{name}"] = mapped


_CONVERTERS = (
    (r"PyLong_As\w+", "int"), (r"PyFloat_AsDouble", "float"), (r"PyUnicode_AsUTF8(?:AndSize)?", "str"),
    (r"PyBytes_As(?:String|StringAndSize)", "bytes"), (r"PyObject_GetBuffer", "typing_extensions.Buffer"),
    (r"PyCapsule_GetPointer", "typing_extensions.CapsuleType"),
)


def _converted(body: str, name: str) -> str:
    """The type the ``METH_O`` argument *name* is converted to first in *body*; ``Any`` without a known conversion.

    Examples
    --------
    >>> _converted("long v = PyLong_AsLong(arg);", "arg")
    'int'
    >>> _converted("return arg;", "arg")
    'Any'
    """
    found = [(m.start(), kind) for call, kind in _CONVERTERS
             for m in re.finditer(r"\b" + call + r"\s*\(\s*" + re.escape(name) + r"\s*[,)]", body)]
    return min(found)[1] if found else "Any"


def _variables(units: list[Unit], varargs: list[str]) -> list[str] | None:
    """Parameter names for ``PyArg_ParseTuple`` units: the C variable each one stores into."""
    names, used = [], 0
    for unit in units:
        target = used + (1 if unit.code in ("O!", "O&", "es", "et", "es#", "et#") else 0)
        names.append(identifier(varargs[target]) or "" if unit.code != "(" and target < len(varargs) else "")
        used += unit.args
    return names


def _unpacked(args: list[str]) -> Signature | None:
    """``PyArg_UnpackTuple(args, "name", min, max, &a, ...)`` as positional-only ``Any`` parameters."""
    if len(args) < 4 or not args[2].strip().isdigit():
        return None
    low = int(args[2])
    params = [Param(identifier(v) or f"arg{i}", POS_ONLY, "Any", None if i < low else "...") for i, v in enumerate(args[4:])]
    return Signature(tuple(params))


def infer_return(body: str, funcs: dict[str, tuple[list[str], str]] | None = None, _depth: int = 0) -> str | None:
    """The Python type every non-error ``return`` of a C function *body* gives, or ``None`` when unclear.

    Parameters
    ----------
    body : str
        The function body, comments removed.
    funcs : dict, optional
        The source's functions; ``return helper(...)`` then takes *helper*'s return type (two levels deep).

    Returns
    -------
    str or None
        ``None``, ``int``, ``float``, ``bool``, ``str``, ``bytes``, a ``Py_BuildValue``
        type, ``T | None`` when ``None`` is the only other result, or ``None`` when any
        returned value is not one of those.

    Examples
    --------
    >>> infer_return("if (x) return NULL; return PyFloat_FromDouble(x);")
    'float'
    >>> infer_return("Py_RETURN_NONE;")
    'None'
    """
    kinds = [kind for macro, kind in CAPI_RETURN_MACROS.items() if re.search(r"\b" + macro + r"\b", body)]
    for m in _RETURN.finditer(body):
        expr = m[1].strip()
        if expr in _ERROR_RETURNS:
            continue
        kind = _expression_type(expr, funcs, _depth)
        if kind is None:
            return None
        kinds.append(kind)
    unique = list(dict.fromkeys(kinds))
    if len(unique) == 2 and "None" in unique:
        unique.remove("None")
        return f"{unique[0]} | None"
    return unique[0] if len(unique) == 1 else None


def _expression_type(expr: str, funcs: dict[str, tuple[list[str], str]] | None = None, depth: int = 0) -> str | None:
    if re.fullmatch(r"(?:Py_NewRef\s*\(\s*)?Py_None\s*\)?", expr):
        return "None"
    if re.fullmatch(r"(?:Py_NewRef\s*\(\s*)?Py_(?:True|False)\s*\)?", expr):
        return "bool"
    m = re.match(r"^(\w+)\s*\(", expr)
    if m is None:
        return None
    if m[1] == "Py_BuildValue":
        args = calls(expr, "Py_BuildValue")
        fmt = string_value(args[0][0]) if args and args[0] else None
        return build_type(fmt) if fmt is not None else None
    known = next((kind for pattern, kind in CAPI_RETURN_CALLS if re.fullmatch(pattern, m[1])), None)
    if known is None and funcs and m[1] in funcs and depth < 2:
        return infer_return(funcs[m[1]][1], funcs, depth + 1)
    return known


def _clinic(text: str, funcs: dict[str, tuple[list[str], str]], module: CModule) -> None:
    """Add Argument Clinic signatures; they replace what the method tables gave."""
    classes = set(module.classes.values()) | set(re.findall(r"^class\s+[\w.]*?(\w+)\s", text, re.M))
    for dotted, sig in clinic_blocks(text):
        parts = dotted.split(".")
        owner = parts[-2] if len(parts) > 1 and parts[-2] in classes else ""
        name = "__init__" if parts[-1] == "__new__" else parts[-1]
        if sig.returns is None:
            impl = funcs.get(dotted.replace(".", "_") + "_impl")
            sig = Signature(sig.params, infer_return(impl[1], funcs) if impl else None)
        if name == "__init__":
            sig = Signature(sig.params, "None")
        module.signatures[f"{owner}.{name}" if owner else name] = sig
