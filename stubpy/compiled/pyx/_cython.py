"""
Read a ``.pyx`` with Cython's own parser (``Cython.Compiler``), when Cython is installed; nothing is compiled.
"""
from __future__ import annotations

from typing import Any

from .models import PyxClass, PyxEnum, PyxFunction, PyxModule, PyxParam


def available() -> bool:
    """True when ``Cython.Compiler.TreeFragment`` imports."""
    try:
        from Cython.Compiler.TreeFragment import parse_from_strings  # noqa: F401
    except Exception:
        return False
    return True


def read_with_cython(text: str, name: str = "module") -> PyxModule:
    """Parse *text* with Cython; raises whatever Cython raises on a source it cannot read."""
    from Cython.Compiler.TreeFragment import parse_from_strings

    tree = parse_from_strings(name, text)
    module = PyxModule(doc=_doc(getattr(tree, "doc", None)))
    for node in _stats(tree.body):
        kind = type(node).__name__
        if kind in ("DefNode", "CFuncDefNode"):
            fn = _function(node)
            if fn is not None:
                module.functions.append(fn)
        elif kind in ("CClassDefNode", "PyClassDefNode"):
            module.classes.append(_class(node))
        elif kind == "CEnumDefNode" and getattr(node, "create_wrapper", False) or (
                kind == "CEnumDefNode" and getattr(node, "visibility", "") == "public"):
            module.enums.append(_enum(node))
    return module


def _stats(node: Any) -> list[Any]:
    """Flatten ``StatListNode`` nesting."""
    if type(node).__name__ == "StatListNode":
        return [s for child in node.stats for s in _stats(child)]
    return [node]


def _doc(value: Any) -> str | None:
    return str(value) if value is not None else None


def _type(base: Any, declarator: Any) -> str | None:
    """The C or Python type text of an argument, ``None`` when untyped."""
    kind = type(base).__name__
    if kind == "CConstTypeNode" or kind == "CConstOrVolatileTypeNode":
        inner = _type(base.base_type, declarator)
        return f"const {inner}" if inner else None
    if kind == "MemoryViewSliceTypeNode":
        dtype = _type(base.base_type_node, None) or "object"
        axes = getattr(base, "axes", None) or [None]
        return f"{dtype}[{', '.join(':' for _ in axes)}]"
    name = getattr(base, "name", None)
    if not name or (declarator is not None and not getattr(declarator, "name", "")):
        return None
    words = []
    if getattr(base, "signed", 1) == 0:
        words.append("unsigned")
    longness = max(getattr(base, "longness", 0), 0)
    words += ["long"] * longness
    if longness and name == "int":
        return " ".join(words)
    return " ".join([*words, name])


def _default(node: Any) -> str | None:
    if node is None:
        return None
    kind = type(node).__name__
    if kind == "NameNode":
        return node.name
    if kind == "NoneNode":
        return "None"
    if kind == "BoolNode":
        return repr(bool(node.value))
    if kind in ("IntNode", "FloatNode"):
        return str(node.value)
    if kind in ("UnicodeNode", "StringNode", "BytesNode"):
        return repr(node.value)
    if kind == "AttributeNode":
        base = _default(node.obj)
        return f"{base}.{node.attribute}" if base else None
    if kind == "UnaryMinusNode":
        inner = _default(node.operand)
        return f"-{inner}" if inner else None
    return "..."


def _params(args: list[Any]) -> list[PyxParam]:
    out = []
    for arg in args:
        declarator = arg.declarator
        name = getattr(declarator, "name", "") or getattr(arg.base_type, "name", "")
        while not name and hasattr(declarator, "base"):
            declarator = declarator.base
            name = getattr(declarator, "name", "")
        out.append(PyxParam(name, _type(arg.base_type, arg.declarator), _default(arg.default)))
    return out


def _function(node: Any) -> PyxFunction | None:
    decorators = [_decorator(d.decorator) for d in (getattr(node, "decorators", None) or [])]
    if type(node).__name__ == "CFuncDefNode":
        if not getattr(node, "overridable", False):
            return None
        declarator = node.declarator
        while not hasattr(declarator, "args"):
            declarator = declarator.base
        name = declarator.base.name
        params = _params(declarator.args)
        returns = _type(node.base_type, None)
        fn = PyxFunction(name, params, returns if returns != "void" else "void", _doc(node.doc), decorators)
    else:
        args = _params(node.args)
        split = len(args) - (getattr(node, "num_kwonly_args", 0) or 0)
        annotation = getattr(node, "return_type_annotation", None)
        returns = getattr(getattr(annotation, "string", None), "value", None)
        fn = PyxFunction(node.name, args[:split], str(returns) if returns else None, _doc(node.doc), decorators)
        if getattr(node, "star_arg", None) is not None:
            fn.params.append(PyxParam(node.star_arg.name, star="*"))
        elif split < len(args):
            fn.kw_only = len(fn.params)
        fn.params.extend(args[split:])
        if getattr(node, "starstar_arg", None) is not None:
            fn.params.append(PyxParam(node.starstar_arg.name, star="**"))
    return fn


def _decorator(node: Any) -> str:
    if type(node).__name__ == "NameNode":
        return node.name
    if type(node).__name__ == "AttributeNode":
        return f"{_decorator(node.obj)}.{node.attribute}"
    return "?"


def _class(node: Any) -> PyxClass:
    name = getattr(node, "class_name", None) or node.name
    bases = []
    for base in getattr(getattr(node, "bases", None), "args", []) or []:
        bases.append(_decorator(base))
    if getattr(node, "base_class_name", None):
        bases.append(node.base_class_name)
    cls = PyxClass(name, bases, _doc(getattr(node, "doc", None)))
    for member in _stats(node.body) if node.body is not None else []:
        kind = type(member).__name__
        if kind in ("DefNode", "CFuncDefNode"):
            fn = _function(member)
            if fn is not None:
                cls.methods.append(fn)
        elif kind == "PropertyNode":
            cls.methods.append(PyxFunction(member.name, [PyxParam("self")], None, _doc(member.doc), ["property"]))
        elif kind == "CVarDefNode" and getattr(member, "visibility", "") in ("public", "readonly"):
            for declarator in member.declarators:
                cls.attributes[declarator.name] = (_type(member.base_type, None) or "object",
                                                   member.visibility == "readonly")
    return cls


def _enum(node: Any) -> PyxEnum:
    members = []
    for item in node.items:
        value = getattr(item, "value", None)
        number = int(value.value) if type(value).__name__ == "IntNode" and str(value.value).lstrip("-").isdigit() \
            else None
        members.append((item.name, number))
    return PyxEnum(node.name, members)
