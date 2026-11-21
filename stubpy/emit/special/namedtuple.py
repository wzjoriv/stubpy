"""
NamedTuple stubs.
"""
from __future__ import annotations

import inspect

from stubpy.emit._method_lookup import methods_defined_on
from stubpy.emit.annotations import annotation_to_str, default_to_str
from stubpy.emit.methods import generate_method_stub
from stubpy.state.context import StubContext

_NT_GENERATED: frozenset[str] = frozenset({
    "_make", "_asdict", "_replace", "_fields", "_field_defaults",
    "__getnewargs__", "__getnewargs_ex__", "__new__",
})


def generate_namedtuple_stub(cls: type, ctx: StubContext) -> str:
    """Return ``class Name(NamedTuple):`` with its fields, then any user-defined methods."""
    lines: list[str] = [f"class {cls.__name__}(NamedTuple):"]

    field_names: tuple[str, ...] = cls._fields  # type: ignore[attr-defined]
    ann = getattr(cls, "__annotations__", {})
    defaults: dict = getattr(cls, "_field_defaults", {})

    if not field_names:
        lines.append("    ...")
        return "\n".join(lines)

    for name in field_names:
        type_ann = ann.get(name, inspect.Parameter.empty)
        type_str = annotation_to_str(type_ann, ctx) if type_ann is not inspect.Parameter.empty else ""
        if name in defaults:
            default_s = default_to_str(defaults[name], ctx)
            lines.append(f"    {name}: {type_str or 'Any'} = {default_s}")
        else:
            lines.append(f"    {name}: {type_str or 'Any'}")

    extra_method_names = [
        m for m in methods_defined_on(cls)
        if m not in _NT_GENERATED and m not in field_names and _written_in(cls, m)
    ]
    if extra_method_names:
        lines.append("")
        for mn in extra_method_names:
            stub = generate_method_stub(cls, mn, ctx)
            if stub:
                lines.append(stub)

    return "\n".join(lines)


def _written_in(cls: type, name: str) -> bool:
    """Return ``True`` when method *name* comes from *cls*'s own module, not the namedtuple factory."""
    fn = cls.__dict__.get(name)
    fn = getattr(fn, "__func__", fn)
    return getattr(fn, "__module__", cls.__module__) == cls.__module__
