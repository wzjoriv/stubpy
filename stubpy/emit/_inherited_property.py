"""
A setter or deleter declared as ``@Base.name.setter`` in a subclass: the inherited getter is written too.
"""
from __future__ import annotations

import dataclasses
import re

from stubpy.analysis.harvest.models import ClassInfo, FunctionInfo
from stubpy.core.context import StubContext
from stubpy.resolve.static import FuncRef

from ._static import bind_names, names_in, resolver_of
from .annotations.style import style_text

_ACCESSOR_RE = re.compile(r"^([\w.]+)\.(\w+)\.(setter|deleter)$")


def inherited_accessor(minfo: FunctionInfo, ci: ClassInfo, ctx: StubContext,
                       indent: str) -> tuple[list[str], FunctionInfo] | None:
    """Return the getter lines and *minfo* rewritten to ``@name.setter`` when it extends a base class property."""
    for i, dec in enumerate(minfo.decorators):
        match = _ACCESSOR_RE.match(dec)
        if match is None or match.group(2) != minfo.name:
            continue
        if any(m.name == minfo.name and "property" in m.decorators for m in ci.methods):
            return None
        ret = _getter_return(match.group(1), minfo.name, ctx)
        getter = [f"{indent}@property", f"{indent}def {minfo.name}(self){f' -> {ret}' if ret else ''}: ..."]
        decorators = list(minfo.decorators)
        decorators[i] = f"{minfo.name}.{match.group(3)}"
        return getter, dataclasses.replace(minfo, decorators=decorators)
    return None


def _getter_return(owner: str, name: str, ctx: StubContext) -> str:
    """Return the annotated return of ``owner.name``'s getter, as source, when its names can be written here."""
    if ctx.source_module is None or ctx.source_index is None:
        return ""
    ref = resolver_of(ctx.source_index).names.dotted(ctx.source_module, f"{owner}.{name}")
    if not isinstance(ref, FuncRef) or not ref.info.raw_return_annotation:
        return ""
    text = ref.info.raw_return_annotation
    names = names_in(text)
    if names is None or (ref.module is not ctx.source_module and not bind_names(names, ref.module, ctx)):
        return ""
    return style_text(text, ctx) or text
