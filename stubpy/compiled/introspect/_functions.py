"""
Compiled callables as harvest :class:`FunctionInfo` entries: one per signature, overloads marked.
"""
from __future__ import annotations

import ast
import inspect
import re
from dataclasses import dataclass, field
from typing import Any

from stubpy._constants import (
    COMPILED_RECEIVER_NAMES,
    DUNDER_RETURNS,
    HINT_IGNORE_ATTR,
    HINT_RETURNS_ATTR,
    HINT_SIGNATURE_ATTR,
    POS_KW,
    POS_ONLY,
    VAR_KW,
    VAR_POS,
)
from stubpy.analysis.harvest.models import FunctionInfo, RawParam
from stubpy.analysis.hints import live_hint
from stubpy.core.diagnostics import DiagnosticCollector, Stage

from ..pyx import merge_signature
from ..signatures import Param, Signature, parse_signature, signatures_of, strip_signature_lines
from ..typemap import TypeMapper
from ._doc_types import variant_docs


@dataclass
class Scope:
    """What every builder needs: the module name, the type mapper, options and diagnostics."""
    module_name: str
    mapper: TypeMapper
    diagnostics: DiagnosticCollector
    include_docstrings: bool = False
    include_private: bool = False
    hand: dict[str, str] = field(default_factory=dict)
    pyx: dict[str, tuple[Signature, str | None]] = field(default_factory=dict)

    def hand_type(self, qualified: str) -> str | None:
        """The annotation a hand-written sibling stub gives *qualified*, when it maps without losing names."""
        text = self.hand.get(qualified)
        mapped = self.mapper(text) if text else None
        return mapped if mapped and ("Any" not in mapped or "Any" in text) else None


_MEMBER = re.compile(r"[A-Za-z_]\w*\.[A-Za-z_]\w*")
_DOTTED = re.compile(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)+")


def _literal_type(default: str | None) -> str | None:
    """The type of a literal default (``0`` gives ``int``); ``None`` for ``None``, ``...`` and non-literals."""
    if default is None:
        return None
    try:
        value = ast.literal_eval(default)
    except (ValueError, TypeError, SyntaxError, MemoryError, RecursionError):
        return None
    return type(value).__name__ if isinstance(value, (bool, int, float, complex, str, bytes)) else None


def _member_default(param: Param, mapper: TypeMapper) -> str | None:
    """An enum default (``Mode.FAST``) qualified from the annotation and mapped, so the stub imports its class."""
    default = param.default
    if default and _MEMBER.fullmatch(default) and param.annotation:
        cls = default.partition(".")[0]
        found = re.search(rf"(?<![\w.])((?:[A-Za-z_]\w*\.)+{cls})(?![\w])", param.annotation)
        if found:
            default = f"{found.group(1)}.{default.partition('.')[2]}"
    if default and default.count(".") >= 2 and _DOTTED.fullmatch(default):
        return mapper(default) or default
    return default


def _raw(param: Param, mapper: TypeMapper) -> RawParam:
    annotation = mapper(param.annotation)
    inferred = None if annotation else _literal_type(param.default)
    return RawParam(param.name, param.kind.name, annotation, inferred, _member_default(param, mapper))


def _receiver_free(sig: Signature, owner: type | None, mapper: TypeMapper) -> Signature:
    """*sig* without a leading ``self`` / ``cls`` / ``arg0`` or a first parameter typed as *owner*."""
    if not sig.params or sig.params[0].kind not in (POS_ONLY, POS_KW):
        return sig
    first = sig.params[0]
    typed_as_owner = owner is not None and first.annotation is not None and (
        mapper(first.annotation) or "").split(".")[-1] == owner.__name__
    if first.name in COMPILED_RECEIVER_NAMES or typed_as_owner:
        return Signature(sig.params[1:], sig.returns)
    return sig


def info_from_signature(name: str, sig: Signature, scope: Scope, *, receiver: str | None = None,
                        decorators: list[str] | None = None, docstring: str | None = None,
                        returns: str | None = None) -> FunctionInfo:
    """A :class:`FunctionInfo` for *sig*; *receiver* (``self`` / ``cls``) is prepended for methods."""
    raw = [_raw(p, scope.mapper) for p in sig.params]
    if receiver is not None:
        raw.insert(0, RawParam(receiver, POS_KW.name))
    ret = returns if returns is not None else scope.mapper(sig.returns) or DUNDER_RETURNS.get(name)
    return FunctionInfo(
        name=name, lineno=0, decorators=list(decorators or []),
        raw_params=raw,
        raw_arg_annotations={_key(p): p.annotation_str for p in raw if p.annotation_str},
        raw_arg_inferred_types={p.name: p.inferred_type_str for p in raw if p.inferred_type_str},
        raw_return_annotation=ret,
        docstring=docstring,
    )


def _key(p: RawParam) -> str:
    return {VAR_POS.name: f"*{p.name}", VAR_KW.name: f"**{p.name}"}.get(p.kind, p.name)


def generic_signature() -> Signature:
    """``(*args: Any, **kwargs: Any) -> Any``."""
    return Signature((Param("args", VAR_POS, "Any"), Param("kwargs", VAR_KW, "Any")), "Any")


def docstring_of(name: str, obj: Any, scope: Scope) -> str | None:
    """The runtime docstring without its signature lines, when docstrings are on."""
    if not scope.include_docstrings:
        return None
    doc = getattr(obj, "__doc__", None)
    if not isinstance(doc, str):
        return None
    return strip_signature_lines(name, doc) or None


def accessor_signature(fn: Any) -> Signature | None:
    """The signature of a property getter / setter (pybind11 writes ``(arg0: T) -> R`` without a name)."""
    if fn is None:
        return None
    doc = getattr(fn, "__doc__", None)
    if isinstance(doc, str) and doc.lstrip().startswith("("):
        parsed = parse_signature("f" + doc.strip().splitlines()[0])
        if parsed is not None:
            return parsed[1]
    found = signatures_of(fn)
    return found[0] if found else None


def is_hint_ignored(obj: Any) -> bool:
    return live_hint(obj, HINT_IGNORE_ATTR) is True


def callable_infos(name: str, obj: Any, scope: Scope, *, owner: type | None = None,
                   receiver: str | None = None, decorators: list[str] | None = None,
                   label: str | None = None) -> list[FunctionInfo]:
    """One :class:`FunctionInfo` per signature of *obj*; several become ``@overload`` variants.

    Without a usable signature the stub falls back to ``(*args: Any, **kwargs: Any) -> Any``
    and an INFO diagnostic is recorded.
    """
    label = label or name
    hint_sig = live_hint(obj, HINT_SIGNATURE_ATTR)
    hint_ret = live_hint(obj, HINT_RETURNS_ATTR)
    doc = docstring_of(name, obj, scope)
    nb_docs = _nanobind_docs(obj) if scope.include_docstrings else []
    sigs = signatures_of(obj, name)
    source = scope.pyx.get(label)
    if source is not None:
        sigs = [source[0]] if not sigs or all(s.is_generic() for s in sigs) else (
            [merge_signature(sigs[0], source[0])] if len(sigs) == 1 else sigs)
        if doc is None and scope.include_docstrings:
            doc = source[1]
    if owner is not None:
        sigs = [_receiver_free(s, owner, scope.mapper) for s in sigs]
    if isinstance(hint_sig, str):
        info = info_from_signature(name, generic_signature(), scope, receiver=receiver, decorators=decorators,
                                   docstring=doc)
        info.hint_signature = hint_sig
        return [info]
    if not sigs:
        scope.diagnostics.info(
            Stage.SYMBOL_TABLE, label,
            "No signature found (no text signature, binding docstring or nanobind metadata); "
            "stubbed as (*args: Any, **kwargs: Any) -> Any",
        )
        sigs = [generic_signature()]
    overloaded = len(sigs) > 1
    infos = []
    for i, sig in enumerate(sigs):
        decos = list(decorators or [])
        if overloaded:
            decos = ["overload", *decos]
        variant_doc = nb_docs[i] if overloaded and i < len(nb_docs) else doc
        if overloaded and i >= len(nb_docs):
            numbered = variant_docs(getattr(obj, "__doc__", None)) if scope.include_docstrings else []
            variant_doc = numbered[i] if i < len(numbered) else None
        info = info_from_signature(name, sig, scope, receiver=receiver, decorators=decos,
                                   docstring=variant_doc or None)
        info.is_overload = overloaded
        if info.raw_return_annotation in (None, "Any") and not overloaded:
            info.raw_return_annotation = scope.hand_type(label) or info.raw_return_annotation
        if isinstance(hint_ret, str):
            info.hint_returns = hint_ret
        infos.append(info)
    return infos


def _nanobind_docs(obj: Any) -> list[str]:
    entries = getattr(obj, "__nb_signature__", None) or ()
    return [e[1] for e in entries if isinstance(e, tuple) and len(e) > 1 and isinstance(e[1], str)]


def inspect_kind(obj: Any) -> str:
    """``"static"``, ``"class"`` or ``"method"`` for a class-dict entry."""
    if isinstance(obj, staticmethod):
        return "static"
    if isinstance(obj, (classmethod, type(dict.__dict__["fromkeys"]))):
        return "class"
    if inspect.isbuiltin(obj) and isinstance(getattr(obj, "__self__", None), type):
        return "class"
    return "method"
