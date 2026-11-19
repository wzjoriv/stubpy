"""
``attrs`` classes: their fields and the ``__init__`` the decorator synthesises.
"""
from __future__ import annotations

import ast
import inspect
from dataclasses import dataclass
from typing import Any

from stubpy._constants import (
    ATTRS_AUTO_DECORATORS,
    ATTRS_DECORATORS,
    ATTRS_FACTORY_TYPES,
    ATTRS_FIELD_CALLS,
    KW_ONLY,
    POS_KW,
)
from stubpy.analysis.harvest import infer_type_from_literal
from stubpy.analysis.harvest.models import ClassInfo, NonLiteralDefault, VariableInfo

from ._lookup import ClassRef
from ._raw import SourceHints, literal_default


@dataclass
class AttrsField:
    """One ``attrs`` field: attribute name, ``__init__`` parameter, type and default."""
    name: str
    param: str
    type: str | None
    init_type: str | None
    default: Any
    init: bool
    kw_only: bool


def attrs_decorator(info: ClassInfo) -> str | None:
    """Return the class's ``attrs`` decorator text, or ``None``."""
    return next((d for d in info.decorators if d.split("(")[0].strip() in ATTRS_DECORATORS), None)


def _keywords(text: str) -> dict[str, str]:
    """Return the keyword arguments of a decorator or call written as *text*."""
    try:
        node = ast.parse(text, mode="eval").body
    except SyntaxError:
        return {}
    if not isinstance(node, ast.Call):
        return {}
    return {k.arg: ast.unparse(k.value) for k in node.keywords if k.arg is not None}


def _field_call(value: str | None) -> tuple[list[str], dict[str, str]] | None:
    """Return the positional and keyword arguments of an ``attr.ib()`` / ``field()`` value, else ``None``."""
    try:
        node = ast.parse(value or "", mode="eval").body
    except SyntaxError:
        return None
    if not isinstance(node, ast.Call) or ast.unparse(node.func) not in ATTRS_FIELD_CALLS:
        return None
    return [ast.unparse(a) for a in node.args], {k.arg: ast.unparse(k.value) for k in node.keywords if k.arg}


def _inferred(text: str) -> str | None:
    """The type of a literal default, or ``None``."""
    try:
        node = ast.parse(text, mode="eval").body
    except SyntaxError:
        return None
    found = infer_type_from_literal(node)
    return None if found in (None, "None", "Any") else found


def _factory_type(text: str) -> str | None:
    """The type a ``factory=`` / ``Factory(...)`` builds when it is a builtin container or scalar."""
    try:
        node = ast.parse(text, mode="eval").body
    except SyntaxError:
        return None
    if isinstance(node, ast.Call) and ast.unparse(node.func).rpartition(".")[2] == "Factory" and node.args:
        node = node.args[0]
    return node.id if isinstance(node, ast.Name) and node.id in ATTRS_FACTORY_TYPES else None


def _converter_type(converter: str | None, cref: ClassRef) -> str | None:
    """The annotated first-parameter type of a module-level converter function, or ``None``."""
    if not converter or not converter.isidentifier():
        return None
    fn = next((f for f in cref.module.symbols.functions if f.name == converter), None)
    if fn is None or not fn.raw_params:
        return None
    return fn.raw_params[0].annotation_str or None


def _field(attr: VariableInfo, auto: bool, kw_only: bool, cref: ClassRef) -> AttrsField | None:
    """Return the field *attr* declares, or ``None`` when it is not a field."""
    ann = attr.annotation_str
    if ann is not None and ann.replace("typing.", "").startswith("ClassVar"):
        return None
    call = _field_call(attr.value_repr)
    if call is None and not (auto and ann is not None):
        return None
    args, kw = call if call is not None else ([], {})
    default: Any = inspect.Parameter.empty
    found_type = ann or kw.get("type")
    default_text = kw.get("default", args[0] if args else None)
    if call is None and attr.value_repr is not None:
        default_text = attr.value_repr
    factory = kw.get("factory") or (default_text if default_text and "Factory(" in default_text else None)
    if factory is not None:
        default = NonLiteralDefault("...")
        found_type = found_type or _factory_type(factory)
    elif default_text is not None:
        default = literal_default(default_text)
        found_type = found_type or _inferred(default_text)
    return AttrsField(
        name=attr.name,
        param=kw.get("alias", "").strip("'\"") or attr.name.lstrip("_"),
        type=found_type,
        init_type=_converter_type(kw.get("converter"), cref) or found_type,
        default=default,
        init=kw.get("init") != "False",
        kw_only=kw.get("kw_only", str(kw_only)) == "True",
    )


def attrs_fields(cref: ClassRef) -> list[AttrsField]:
    """Return the fields an ``attrs`` class declares itself, in source order."""
    decorator = attrs_decorator(cref.info) or ""
    options = _keywords(decorator)
    auto = decorator.split("(")[0].strip() in ATTRS_AUTO_DECORATORS or options.get("auto_attribs") == "True"
    kw_only = options.get("kw_only") == "True"
    found = (_field(attr, auto, kw_only, cref) for attr in cref.info.attributes if not attr.name.startswith("__"))
    return [f for f in found if f is not None]


def attrs_init(chain: list[ClassRef]) -> list[tuple[inspect.Parameter, dict[str, Any]]] | None:
    """Return the synthesised ``__init__`` parameters of the ``attrs`` classes in *chain* (base first).

    ``None`` when the last class turns ``init`` off.
    """
    if _keywords(attrs_decorator(chain[-1].info) or "").get("init") == "False":
        return None
    fields: dict[str, tuple[inspect.Parameter, dict[str, Any]]] = {}
    for cref in chain:
        hints = SourceHints(cref.module)
        for f in attrs_fields(cref):
            fields.pop(f.name, None)
            if not f.init:
                continue
            annotation = f.init_type if f.init_type is not None else inspect.Parameter.empty
            kind = KW_ONLY if f.kw_only else POS_KW
            fields[f.name] = (inspect.Parameter(f.param, kind, default=f.default, annotation=annotation), hints)
    params = list(fields.values())
    return [p for p in params if p[0].kind == POS_KW] + [p for p in params if p[0].kind == KW_ONLY]
