"""Runtime state that is awkward to inspect: lazy settings, context proxies, odd attribute names."""
from __future__ import annotations

from typing import Any, NamedTuple, Type, TypedDict


class SettingsNotConfigured(Exception):
    """Raised when the settings are read before :func:`configure`."""


class _LazySettings:
    """Settings that load on first attribute access and raise until configured."""

    _wrapped: dict[str, Any] | None = None

    def __getattribute__(self, name: str) -> Any:
        if object.__getattribute__(self, "_wrapped") is None:
            raise SettingsNotConfigured(f"settings.{name} read before configure()")
        return object.__getattribute__(self, "_wrapped")[name]


class _ContextProxy:
    """The current drawing context; only usable inside ``with Document(...)``."""

    def __getattr__(self, name: str) -> Any:
        raise RuntimeError("Working outside of a drawing context.")

    @property
    def __class__(self) -> type:  # type: ignore[override]
        raise RuntimeError("Working outside of a drawing context.")


settings = _LazySettings()
current = _ContextProxy()


def configure(**options: Any) -> None:
    """Load the settings."""
    object.__setattr__(settings, "_wrapped", dict(options))


class Point(NamedTuple):
    x: float
    y: float


class Style(TypedDict, total=False):
    fill: str
    stroke: str


def from_tuple(cls: Type["NamedTuple"], values: tuple[float, ...]) -> Type["NamedTuple"]:
    """Build *cls* from *values*; the first parameter of a module function may be named ``cls``."""
    return cls


def element(tag: str, **attrs: Any) -> dict[str, Any]:
    """An element whose attributes include the Python keyword ``class``."""
    return {"tag": tag, "class": attrs["class"], "id": attrs["id"]}


def legend(shadow=None, loc="best"):
    """Place a legend.

    Parameters
    ----------
    shadow : None, bool or dict
        Whether to draw a shadow, or its properties.
    loc : {'best', 'upper right', 'lower left'}
        Where to place it.

    Returns
    -------
    list of str
        The legend entries.
    """
    return []


class Token:
    """A token whose fields include a keyword name, as code generators produce."""

    __slots__ = ("value", "return")

    def __init__(self, value: str) -> None:
        self.value = value
        setattr(self, "return", None)
