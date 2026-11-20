"""
Constructors synthesised from class bodies: dataclasses, ``attrs`` classes, ``NamedTuple`` and ``TypedDict``.
"""
from __future__ import annotations

import ast
import inspect
import re
from typing import Any

from stubpy._constants import KW_ONLY, POS_KW
from stubpy.analysis.harvest.models import ClassInfo, NonLiteralDefault
from stubpy.resolve._constants import DATACLASS_DECORATORS, NAMEDTUPLE_BASES, TYPEDDICT_BASES

from ._attrs import attrs_decorator, attrs_init
from ._lookup import ClassRef
from ._raw import SourceHints, literal_default

_REQUIRED_RE = re.compile(r"^(?:typing(?:_extensions)?\.)?(Required|NotRequired)\[(.*)\]$", re.S)
_CLASSVAR_RE = re.compile(r"^(?:typing\.)?ClassVar\b")


def _dataclass_decorator(info: ClassInfo) -> str | None:
    return next((d for d in info.decorators if d.split("(")[0] in DATACLASS_DECORATORS), None)


def kind_of(info: ClassInfo) -> str | None:
    """Return ``"attrs"``, ``"dataclass"``, ``"namedtuple"`` or ``"typeddict"`` for a class whose constructor comes from its body."""
    if attrs_decorator(info) is not None:
        return "attrs"
    if _dataclass_decorator(info) is not None:
        return "dataclass"
    bases = {b.split("[")[0] for b in info.bases}
    if bases & NAMEDTUPLE_BASES:
        return "namedtuple"
    if bases & TYPEDDICT_BASES:
        return "typeddict"
    return None


def _field_call(value: str) -> dict[str, str] | None:
    """Return the keywords of a ``field(...)`` / ``dataclasses.field(...)`` value, else ``None``."""
    try:
        node = ast.parse(value, mode="eval").body
    except SyntaxError:
        return None
    if not isinstance(node, ast.Call) or ast.unparse(node.func) not in ("field", "dataclasses.field"):
        return None
    return {k.arg: ast.unparse(k.value) for k in node.keywords if k.arg is not None}


def _dataclass_fields(chain: list[ClassRef]) -> list[tuple[inspect.Parameter, dict[str, Any]]]:
    """Return the ``__init__`` parameters of the dataclasses in *chain* (base first)."""
    fields: dict[str, tuple[inspect.Parameter, dict[str, Any]]] = {}
    for cref in chain:
        decorator = _dataclass_decorator(cref.info) or ""
        kw_only = "kw_only=True" in decorator.replace(" ", "")
        hints = SourceHints(cref.module)
        for attr in cref.info.attributes:
            ann = attr.annotation_str
            if ann is None or _CLASSVAR_RE.match(ann):
                continue
            if ann.rpartition(".")[2] == "KW_ONLY":
                kw_only = True
                continue
            default: Any = inspect.Parameter.empty
            field_kw = _field_call(attr.value_repr) if attr.value_repr else None
            if field_kw is not None:
                if field_kw.get("init") == "False":
                    continue
                if "default" in field_kw:
                    default = literal_default(field_kw["default"])
                elif "default_factory" in field_kw:
                    default = NonLiteralDefault("...")
                own_kw = field_kw.get("kw_only")
                is_kw = own_kw == "True" if own_kw is not None else kw_only
            else:
                if attr.value_repr is not None:
                    default = literal_default(attr.value_repr)
                is_kw = kw_only
            kind = KW_ONLY if is_kw else POS_KW
            fields[attr.name] = (inspect.Parameter(attr.name, kind, default=default, annotation=ann), hints)
    return list(fields.values())


def _namedtuple_fields(cref: ClassRef) -> list[tuple[inspect.Parameter, dict[str, Any]]]:
    hints = SourceHints(cref.module)
    out = []
    for attr in cref.info.attributes:
        if attr.annotation_str is None or _CLASSVAR_RE.match(attr.annotation_str):
            continue
        default = literal_default(attr.value_repr) if attr.value_repr is not None else inspect.Parameter.empty
        out.append((inspect.Parameter(attr.name, POS_KW, default=default, annotation=attr.annotation_str), hints))
    return out


def typeddict_keys(chain: list[ClassRef]) -> list[tuple[inspect.Parameter, dict[str, Any]]]:
    """Return one keyword-only parameter per key of the ``TypedDict`` classes in *chain* (base first)."""
    keys: dict[str, tuple[inspect.Parameter, dict[str, Any]]] = {}
    for cref in chain:
        total = not any(b.replace(" ", "") == "total=False" for b in cref.info.bases)
        hints = SourceHints(cref.module)
        for attr in cref.info.attributes:
            ann = attr.annotation_str
            if ann is None:
                continue
            required = total
            match = _REQUIRED_RE.match(ann)
            if match:
                required = match.group(1) == "Required"
                ann = match.group(2)
            default = inspect.Parameter.empty if required else NonLiteralDefault("...")
            keys[attr.name] = (inspect.Parameter(attr.name, KW_ONLY, default=default, annotation=ann), hints)
    return list(keys.values())


def synthesised_init(chain: list[ClassRef]) -> list[tuple[inspect.Parameter, dict[str, Any]]] | None:
    """Return the constructor parameters of ``chain[-1]`` when its kind synthesises one, else ``None``.

    *chain* lists the class and its known ancestors, base first.
    """
    kind = kind_of(chain[-1].info)
    if kind == "attrs":
        return attrs_init([c for c in chain if kind_of(c.info) == "attrs"])
    if kind == "dataclass":
        return _dataclass_fields([c for c in chain if kind_of(c.info) == "dataclass"])
    if kind == "namedtuple":
        return _namedtuple_fields(chain[-1])
    if kind == "typeddict":
        return typeddict_keys([c for c in chain if kind_of(c.info) == "typeddict"])
    return None
