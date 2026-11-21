"""
Registered hooks: forwarding-target resolvers and stub text hooks.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .context import StubContext

ForwardResolver = Callable[[str, dict[str, Any]], Any]
StubHook = Callable[[str, StubContext], str]

FORWARD_RESOLVERS: list[ForwardResolver] = []
STUB_HOOKS: list[StubHook] = []


def register_forward_resolver(fn: ForwardResolver) -> ForwardResolver:
    """Register *fn* to name the target of a ``**kwargs`` / ``*args`` forward, such as one stubpy cannot find.

    *fn* is called as ``fn(name, namespace)`` with the call-site text (``"draw"``,
    ``"self.backend.draw"``) and the module's globals, and returns the callable or class the
    call forwards to, or ``None`` to leave it to stubpy. Resolvers are asked before stubpy's own
    lookup, in registration order; the first non-``None`` result wins. They need the module's live objects, so they are not
    used with ``imports="none"``. Usable as a decorator.

    Parameters
    ----------
    fn : callable
        ``(name: str, namespace: dict[str, Any]) -> object | None``.

    Returns
    -------
    callable
        *fn*, unchanged.

    See Also
    --------
    register_stub_hook : Change the finished stub text.

    Examples
    --------
    >>> @register_forward_resolver
    ... def backend(name: str, namespace: dict) -> object | None:
    ...     return namespace.get("Renderer").draw if name == "self.backend.draw" else None
    >>> FORWARD_RESOLVERS.remove(backend)
    """
    FORWARD_RESOLVERS.append(fn)
    return fn


def register_stub_hook(fn: StubHook) -> StubHook:
    """Register *fn* to change each module's finished stub text before it is written or compared.

    *fn* is called as ``fn(text, ctx)``; ``ctx.module_name`` names the module. Hooks run in
    registration order, each on the previous one's result. Usable as a decorator.

    Parameters
    ----------
    fn : callable
        ``(text: str, ctx: StubContext) -> str``.

    Returns
    -------
    callable
        *fn*, unchanged.

    See Also
    --------
    register_forward_resolver : Name forwarding targets stubpy cannot find.

    Examples
    --------
    >>> @register_stub_hook
    ... def banner(text: str, ctx: StubContext) -> str:
    ...     return "# Generated; do not edit.\\n" + text
    >>> STUB_HOOKS.remove(banner)
    """
    STUB_HOOKS.append(fn)
    return fn


def forward_target(name: str, namespace: dict[str, Any]) -> Any:
    """The first registered resolver's target for *name*, or ``None``."""
    for fn in FORWARD_RESOLVERS:
        found = fn(name, namespace)
        if found is not None:
            return found
    return None


def run_stub_hooks(text: str, ctx: StubContext) -> str:
    """*text* passed through every registered stub hook."""
    for fn in STUB_HOOKS:
        text = fn(text, ctx)
    return text
