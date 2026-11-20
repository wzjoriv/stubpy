"""
Compiled classes as harvest :class:`ClassInfo`: constructors, methods, properties, enums, constants.
"""
from __future__ import annotations

import enum
import inspect
import types
from typing import Any

from stubpy._constants import POS_KW, PUBLIC_DUNDERS
from stubpy.analysis.harvest.models import ClassInfo, FunctionInfo, VariableInfo
from stubpy.compiled._constants import BINDING_ROOT_MODULES, COMPILED_ENUM_INTERNALS, COMPILED_SKIP_MEMBERS
from stubpy.core.diagnostics import Stage

from ..detect import SLOT_WRAPPER_TYPES
from ..pyx import merge_signature
from ..signatures import Param, Signature, class_signatures, signatures_of, strip_signature_lines
from ._doc_types import doc_type
from ._functions import (
    Scope,
    accessor_signature,
    callable_infos,
    generic_signature,
    info_from_signature,
    inspect_kind,
    is_hint_ignored,
)
from ._values import is_writable, value_type

_SLOT_TYPES = SLOT_WRAPPER_TYPES
_DESCRIPTOR_TYPES = (property, types.GetSetDescriptorType, types.MemberDescriptorType)


def _enum_base(cls: type) -> str | None:
    """The ``enum`` base name of a real :class:`enum.Enum` subclass (nanobind 2 enums)."""
    if not issubclass(cls, enum.Enum):
        return None
    for base in ("IntFlag", "Flag", "IntEnum", "StrEnum"):
        found = getattr(enum, base, None)
        if found is not None and issubclass(cls, found):
            return base
    return "Enum"


def _is_pybind_enum(cls: type) -> bool:
    return "__members__" in vars(cls) and not issubclass(cls, enum.Enum)


def _binding_without_constructor(cls: type) -> bool:
    """True for a pybind11 / nanobind class: with no ``py::init`` it cannot be built from Python."""
    return type(cls).__module__ in BINDING_ROOT_MODULES or any(b.__module__ in BINDING_ROOT_MODULES for b in cls.__mro__)


def _constructor(cls: type, scope: Scope, label: str) -> list[FunctionInfo]:
    """``__init__`` from a binding ``__init__`` with signatures, else from the class's own signature text."""
    own = vars(cls)
    init = own.get("__init__")
    if init is not None and not isinstance(init, _SLOT_TYPES) and not inspect.isfunction(init) and signatures_of(
            init, "__init__"):
        infos = callable_infos("__init__", init, scope, owner=cls, receiver="self", label=f"{label}.__init__")
        for info in infos:
            info.raw_return_annotation = "None"
        return infos
    sigs = class_signatures(cls)
    source = scope.pyx.get(f"{label}.__init__")
    if source is not None:
        sigs = [merge_signature(sigs[0], source[0])] if len(sigs) == 1 else sigs or [
            Signature(tuple(p for p in source[0].params if p.name != "self"), None)]
    if sigs:
        overloaded = len(sigs) > 1
        infos = [info_from_signature("__init__", s, scope, receiver="self", returns="None",
                                     decorators=["overload"] if overloaded else []) for s in sigs]
        for info in infos:
            info.is_overload = overloaded
        return infos
    if ("__init__" in own or "__new__" in own) and not _binding_without_constructor(cls):
        scope.diagnostics.info(
            Stage.SYMBOL_TABLE, f"{label}.__init__",
            "No constructor signature found; stubbed as (*args: Any, **kwargs: Any)",
        )
        return [info_from_signature("__init__", generic_signature(), scope, receiver="self", returns="None")]
    return []


def _property(name: str, descriptor: Any, cls: type, scope: Scope) -> list[FunctionInfo]:
    """``@property`` plus ``@name.setter`` when the descriptor is writable."""
    getter = accessor_signature(getattr(descriptor, "fget", None))
    returns = (getter.returns if getter is not None else None) or doc_type(name, getattr(descriptor, "__doc__", None))
    ret = (scope.mapper(returns) if returns else None) or scope.hand_type(f"{cls.__qualname__}.{name}") or "Any"
    doc = getattr(descriptor, "__doc__", None) if scope.include_docstrings else None
    if not isinstance(doc, str) or doc.lstrip().startswith((f"{name}(", "(")):
        doc = None
    infos = [info_from_signature(name, Signature(()), scope, receiver="self", decorators=["property"],
                                 returns=ret, docstring=doc or None)]
    if is_writable(cls, descriptor):
        setter = accessor_signature(getattr(descriptor, "fset", None))
        value = setter.params[1].annotation if setter is not None and len(setter.params) > 1 else None
        sig = Signature((Param("value", POS_KW, value),), "None")
        info = info_from_signature(name, sig, scope, receiver="self", decorators=[f"{name}.setter"], returns="None")
        if not info.raw_params[1].annotation_str:
            info.raw_params[1].annotation_str = ret
            info.raw_arg_annotations["value"] = ret
        infos.append(info)
    return infos


def _enum_info(cls: type, base: str, scope: Scope, lineno: int) -> ClassInfo:
    members = [VariableInfo(n, 0, value_repr=repr(m.value)) for n, m in cls.__members__.items()]
    doc = cls.__doc__ if scope.include_docstrings and cls.__doc__ != "An enumeration." else None
    return ClassInfo(cls.__name__, lineno, bases=[base], attributes=members, docstring=doc)


def _visible(name: str, scope: Scope) -> bool:
    if name in COMPILED_SKIP_MEMBERS:
        return False
    if name.startswith("__") and name.endswith("__"):
        return name in PUBLIC_DUNDERS
    return scope.include_private or not name.startswith("_")


def class_info(cls: type, scope: Scope, lineno: int, label: str | None = None) -> ClassInfo:
    """Build the :class:`ClassInfo` of a compiled class, nested classes included."""
    label = label or cls.__name__
    base = _enum_base(cls)
    if base is not None:
        return _enum_info(cls, base, scope, lineno)
    pybind_enum = _is_pybind_enum(cls)
    info = ClassInfo(cls.__name__, lineno, bases=_bases(cls, scope))
    if scope.include_docstrings and cls.__doc__:
        info.docstring = strip_signature_lines(cls.__name__, _enum_doc(cls.__doc__) if pybind_enum else cls.__doc__)
    info.methods.extend(_constructor(cls, scope, label))
    for name, raw in vars(cls).items():
        if name in ("__init__", "__new__") or not _visible(name, scope) or is_hint_ignored(raw):
            continue
        if pybind_enum and name in COMPILED_ENUM_INTERNALS - {"name", "value"}:
            continue
        if isinstance(raw, type):
            if raw.__qualname__ == f"{cls.__qualname__}.{name}":
                info.classes.append(class_info(raw, scope, 0, f"{label}.{name}"))
            continue
        if isinstance(raw, cls):
            info.attributes.append(VariableInfo(name, 0, annotation_str=f"ClassVar[{cls.__name__}]"))
        elif isinstance(raw, _DESCRIPTOR_TYPES):
            info.methods.extend(_property(name, raw, cls, scope))
        elif callable(raw) or isinstance(raw, (staticmethod, classmethod)):
            info.methods.extend(_method(name, raw, cls, scope, f"{label}.{name}"))
        elif not isinstance(raw, types.ModuleType):
            ann = value_type(raw, scope.mapper, {cls: cls.__name__})
            info.attributes.append(VariableInfo(name, 0, annotation_str=f"ClassVar[{ann}]"))
    return info


def _method(name: str, raw: Any, cls: type, scope: Scope, label: str) -> list[FunctionInfo]:
    kind = inspect_kind(raw)
    func = raw.__func__ if isinstance(raw, (staticmethod, classmethod)) else raw
    if kind == "static":
        return callable_infos(name, func, scope, decorators=["staticmethod"], label=label)
    if kind == "class":
        return callable_infos(name, func, scope, owner=cls, receiver="cls", decorators=["classmethod"], label=label)
    return callable_infos(name, func, scope, owner=cls, receiver="self", label=label)


def _bases(cls: type, scope: Scope) -> list[str]:
    """Base classes other than ``object`` and the binding's own root types (``pybind11_object``)."""
    out = []
    for base in cls.__bases__:
        if base is object or base.__module__ in BINDING_ROOT_MODULES:
            continue
        mapped = scope.mapper(f"{base.__module__}.{base.__qualname__}") if base.__module__ != "builtins" else base.__name__
        if mapped and mapped != "Any":
            out.append(mapped)
    return out


def _enum_doc(doc: str) -> str:
    """A pybind11 enum docstring without its generated ``Members:`` listing."""
    head, sep, _ = doc.partition("\n\nMembers:")
    return head if sep else doc
