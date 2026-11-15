"""NamedTuple stubs."""
from __future__ import annotations

import inspect

from stubpy.core.context import StubContext
from stubpy.emit.annotations import annotation_to_str, default_to_str
from stubpy.emit.methods import generate_method_stub, methods_defined_on

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
            default_s = default_to_str(defaults[name])
            lines.append(f"    {name}: {type_str} = {default_s}" if type_str else f"    {name} = {default_s}")
        else:
            lines.append(f"    {name}: {type_str}" if type_str else f"    {name}: ...")

    extra_method_names = [m for m in methods_defined_on(cls) if m not in _NT_GENERATED]
    if extra_method_names:
        lines.append("")
        for mn in extra_method_names:
            stub = generate_method_stub(cls, mn, ctx)
            if stub:
                lines.append(stub)

    return "\n".join(lines)
