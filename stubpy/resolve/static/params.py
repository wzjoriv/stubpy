"""``**kwargs`` / ``*args`` back-tracing from source alone, mirroring :mod:`stubpy.resolve.params`.

Classes, functions and imports are looked up in a :class:`SourceIndex`, so
callees in other modules of the package resolve without importing anything.
"""
from __future__ import annotations

import dataclasses

from stubpy._constants import VAR_KW, VAR_POS
from stubpy.analysis.harvest.models import FunctionInfo

from .._merge import (
    ParamWithHints,
    bind_call_site,
    bind_partial,
    call_site,
    concrete_own,
    consumed_params,
    finalise_variadics,
    has_kind,
    merge_concrete_params,
    resolved_has_kind,
)
from ._lookup import ClassRef, FuncRef, PartialRef, Ref, Resolver, method_ref
from ._mro import Opaque, static_mro
from ._raw import SourceHints, literal_default, own_params
from ._special import kind_of, synthesised_init, typeddict_keys
from .index import SourceIndex, SourceModule
from .unpack import unpacked_typeddict


class StaticResolver:
    """Expand variadics of functions and methods found in a :class:`SourceIndex`."""

    def __init__(self, index: SourceIndex) -> None:
        self.names = Resolver(index)

    def function(self, ref: FuncRef, _seen: frozenset[str] = frozenset(), callee: bool = False,
                 ) -> list[ParamWithHints]:
        """Return the parameters of a module-level function with its variadics expanded.

        ``**kwargs: Unpack[TD]`` stays as written, and is replaced by the keys of ``TD`` for a *callee*.
        """
        info = ref.info
        hints = SourceHints(ref.module)
        params = own_params(info, method=False)
        if _is_unpack(params):
            return self._unpacked(ref.module, params, hints) if callee else [(p, hints) for p in params]
        if not has_kind(params, VAR_KW) and not has_kind(params, VAR_POS):
            return [(p, hints) for p in params]
        kw_targets = info.kwargs_forwarded_to if has_kind(params, VAR_KW) else []
        pos_targets = info.args_forwarded_to if has_kind(params, VAR_POS) else []
        if not kw_targets and not pos_targets:
            return [(p, hints) for p in params]
        seen = _seen | {ref.key}
        merged = concrete_own(params, hints)
        seen_names = {p.name for p, _ in merged}
        merged += consumed_params(info, seen_names)
        still_kw, still_pos = self._targets(
            _dedupe(kw_targets + pos_targets), kw_targets, pos_targets, ref.module, info, seen,
            merged, seen_names, has_kind(params, VAR_KW), has_kind(params, VAR_POS),
        )
        return finalise_variadics(merged, params, hints, still_pos, still_kw)

    def _unpacked(self, module: SourceModule, params: list, hints: SourceHints) -> list[ParamWithHints]:
        """Replace ``**kwargs: Unpack[TD]`` with the keys of ``TD`` as keyword-only parameters."""
        kw = next(p for p in params if p.kind == VAR_KW)
        cref = self.names.dotted(module, unpacked_typeddict(kw.annotation) or "")
        if not isinstance(cref, ClassRef) or kind_of(cref.info) != "typeddict":
            return [(p, hints) for p in params]
        names = {p.name for p in params}
        keys = [(p, h) for p, h in typeddict_keys(self._chain(cref)) if p.name not in names]
        return [(p, hints) for p in params if p.kind != VAR_KW] + keys

    def method(self, cref: ClassRef, name: str, _seen: frozenset[str] | None = None) -> list[ParamWithHints] | None:
        """Return the parameters of method *name* of *cref* with its variadics expanded; ``None`` if unknown."""
        mro = static_mro(self.names, cref)
        ref = method_ref(cref, name)
        if ref is None:
            for parent in mro[1:]:
                if isinstance(parent, Opaque):
                    if parent.defines(name):
                        return None
                    continue
                if method_ref(parent, name) is not None:
                    return self.method(parent, name, _seen)
            return None
        info = ref.info
        hints = SourceHints(cref.module)
        params = own_params(info, method=True)
        has_kw, has_pos = has_kind(params, VAR_KW), has_kind(params, VAR_POS)
        if not has_kw and not has_pos:
            return [(p, hints) for p in params]
        seen = _seen if _seen is not None else frozenset({f"{cref.info.name}.{name}"})
        merged = concrete_own(params, hints)
        seen_names = {p.name for p, _ in merged}
        merged += consumed_params(info, seen_names)

        if has_kw and name != "__init__" and "__init__" not in seen and "cls" in info.kwargs_forwarded_to:
            init = self.constructor(cref, seen | {"__init__"})
            if init is not None:
                resolved, keep_kw = bind_call_site(init, call_site(info, "cls"))
                merge_concrete_params(merged, seen_names, resolved)
                still_kw = keep_kw or resolved_has_kind(resolved, VAR_KW)
                return finalise_variadics(merged, params, hints, has_pos, still_kw)

        still_kw, still_pos = self._walk_mro(mro, name, info, merged, seen_names, has_kw, has_pos)
        if still_kw or still_pos:
            kw_targets = info.kwargs_forwarded_to if still_kw else []
            pos_targets = info.args_forwarded_to if still_pos else []
            skip = ("cls", "self") + tuple(
                n for n in kw_targets + pos_targets if n.partition(".")[0] == cref.info.name and "." in n
            )
            still_kw, still_pos = self._targets(
                _dedupe(kw_targets + pos_targets, skip), kw_targets, pos_targets, cref.module, info, seen,
                merged, seen_names, still_kw, still_pos,
            )
            for target in info.kwargs_method_targets + info.args_method_targets:
                if target in seen:
                    continue
                resolved = self.method(cref, target, seen | {target})
                if not resolved:
                    continue
                resolved, keep_kw = bind_call_site(resolved, call_site(info, target))
                merge_concrete_params(merged, seen_names, resolved)
                if target in info.kwargs_method_targets and not keep_kw and not resolved_has_kind(resolved, VAR_KW):
                    still_kw = False
                if target in info.args_method_targets and not resolved_has_kind(resolved, VAR_POS):
                    still_pos = False
        return finalise_variadics(merged, params, hints, still_pos, still_kw)

    def _chain(self, cref: ClassRef) -> list[ClassRef]:
        """Return the known classes of *cref*'s MRO, base first."""
        return [c for c in reversed(static_mro(self.names, cref)) if isinstance(c, ClassRef)]

    def constructor(self, cref: ClassRef, _seen: frozenset[str] = frozenset()) -> list[ParamWithHints] | None:
        """Return the parameters of ``cref(...)``: a synthesised or explicit ``__init__``."""
        for c in static_mro(self.names, cref):
            if isinstance(c, Opaque):
                if c.defines("__init__"):
                    return None
                continue
            if method_ref(c, "__init__") is not None:
                return self.method(c, "__init__", _seen | {f"{c.info.name}.__init__"})
            if kind_of(c.info) is not None:
                return synthesised_init(self._chain(c))
        return None

    def _walk_mro(self, mro: list, name: str, info: FunctionInfo, merged: list[ParamWithHints],
                  seen_names: set[str], still_kw: bool, still_pos: bool) -> tuple[bool, bool]:
        """Merge ancestor parameters into the variadics, as :func:`stubpy.resolve._mro.walk_mro` does."""
        caller = info
        args_open = still_pos
        for i, parent in enumerate(mro[1:], start=1):
            if isinstance(parent, Opaque):
                if parent.defines(name):
                    break
                continue
            pref = method_ref(parent, name)
            if pref is None:
                continue
            target = _super_target(caller, name, parent.info.name)
            if target is None:
                later = {f"{c.info.name}.{name}" for c in mro[i + 1:] if isinstance(c, ClassRef)}
                if later & set(caller.kwargs_forwarded_to + caller.args_forwarded_to):
                    continue
                break
            site = call_site(caller, target, forwards_args=args_open)
            site = dataclasses.replace(site, forwards_args=site.forwards_args and args_open)
            parent_params = own_params(pref.info, method=True)
            resolved, keep_kw = bind_call_site([(p, SourceHints(parent.module)) for p in parent_params], site)
            args_open = site.forwards_args and resolved_has_kind(resolved, VAR_POS)
            merge_concrete_params(merged, seen_names, resolved)
            still_kw = still_kw and (keep_kw or resolved_has_kind(resolved, VAR_KW))
            if site.forwards_args:
                still_pos = resolved_has_kind(resolved, VAR_POS)
            if not still_kw and not (still_pos and site.forwards_args):
                break
            caller = pref.info
        return still_kw, still_pos

    def target(self, module: SourceModule, name: str, caller: FunctionInfo | None,
               seen: frozenset[str]) -> list[ParamWithHints] | None:
        """Return the parameters of the callee *name* as seen from *module*, or ``None`` when unknown."""
        if name.endswith("()") or "()." in name:
            owner, _, meth = name.partition("().")
            ref = self.names.dotted(module, owner, caller)
            return self.method(ref, meth, seen) if isinstance(ref, ClassRef) else None
        return self.of_ref(self.names.dotted(module, name, caller), seen)

    def of_ref(self, ref: Ref | None, seen: frozenset[str]) -> list[ParamWithHints] | None:
        """Return the parameters a call to *ref* accepts."""
        if isinstance(ref, ClassRef):
            return self.constructor(ref, seen)
        if isinstance(ref, FuncRef):
            if ref.owner is not None:
                return self.method(ref.owner, ref.info.name, seen)
            return self.function(ref, seen, callee=True)
        if isinstance(ref, PartialRef):
            inner = self.of_ref(ref.target, seen)
            keywords = {k: literal_default(v) for k, v in ref.keywords.items()}
            return bind_partial(inner, (None,) * ref.positional, keywords) if inner is not None else None
        return None

    def _targets(self, names: list[str], kw_targets: list[str], pos_targets: list[str],
                 module: SourceModule, info: FunctionInfo, seen: frozenset[str],
                 merged: list[ParamWithHints], seen_names: set[str], still_kw: bool, still_pos: bool,
                 ) -> tuple[bool, bool]:
        """Merge the parameters of each named callee, as :func:`stubpy.resolve._targets.resolve_targets` does."""
        for target in names:
            if target in seen:
                continue
            resolved = self.target(module, target, info, seen | {target})
            if resolved is None:
                continue
            resolved, keep_kw = bind_call_site(resolved, call_site(info, target))
            merge_concrete_params(merged, seen_names, resolved)
            if target in kw_targets and not keep_kw and not resolved_has_kind(resolved, VAR_KW):
                still_kw = False
            if target in pos_targets and not resolved_has_kind(resolved, VAR_POS):
                still_pos = False
        return still_kw, still_pos


def _is_unpack(params: list) -> bool:
    """True when ``**kwargs`` is annotated ``Unpack[TD]``."""
    kw = next((p for p in params if p.kind == VAR_KW), None)
    return kw is not None and isinstance(kw.annotation, str) and unpacked_typeddict(kw.annotation) is not None


def _super_target(caller: FunctionInfo, method_name: str, parent_name: str) -> str | None:
    """Return the target name *caller* uses for the parent's method, as the runtime walk does."""
    if caller.is_stub_body:
        return method_name
    targets = caller.kwargs_forwarded_to + caller.args_forwarded_to
    for name in (f"{parent_name}.{method_name}", method_name):
        if name in targets:
            return name
    return None


def _dedupe(names: list[str], skip: tuple[str, ...] = ()) -> list[str]:
    out: list[str] = []
    for n in names:
        if n not in out and n not in skip:
            out.append(n)
    return out
