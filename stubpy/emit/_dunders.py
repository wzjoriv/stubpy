"""
Fixed protocol types of dunder methods, filled in where the source leaves them out.
"""
from __future__ import annotations

import inspect

from stubpy._constants import DUNDER_RETURNS
from stubpy.emit._constants import DUNDER_PARAMS, PROTOCOL_PARAMS


def dunder_return(name: str) -> str:
    """The protocol return type of the dunder *name*, or ``""``."""
    return DUNDER_RETURNS.get(name, "")


def dunder_param_types(name: str, params: list[inspect.Parameter]) -> dict[str, str]:
    """The protocol types of the dunder *name*'s positional *params* (receiver excluded), by name."""
    types = DUNDER_PARAMS.get(name, ())
    positional = [p for p in params if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)]
    return {p.name: t for p, t in zip(positional, types, strict=False)}


def protocol_params(name: str) -> list[tuple[inspect.Parameter, dict]]:
    """The standard parameters of the protocol dunder *name* (``__getattr__(self, name: str)``); empty for others.

    Used when a dunder is a descriptor whose signature cannot be read, so the stub is not ``def __getattr__(self)``.

    Examples
    --------
    >>> [(p.name, p.annotation) for p, _ in protocol_params("__setattr__")]
    [('name', 'str'), ('value', 'Any')]
    """
    params = []
    for raw, annotation in PROTOCOL_PARAMS.get(name, ()):
        if raw.startswith("**"):
            kind = inspect.Parameter.VAR_KEYWORD
        elif raw.startswith("*"):
            kind = inspect.Parameter.VAR_POSITIONAL
        else:
            kind = inspect.Parameter.POSITIONAL_OR_KEYWORD
        params.append((inspect.Parameter(raw.lstrip("*"), kind, annotation=annotation), {}))
    return params
