"""Runtime state that is awkward to inspect: lazy settings, context proxies, odd attribute names."""
from __future__ import annotations

import decimal
import importlib

from collections import namedtuple
from typing import TYPE_CHECKING, Any, Final, NamedTuple, Type, TypedDict, Union

from . import Glyph
from . import _predict as pred
from .compat import MutableMapping

codec = importlib.import_module("json")

if TYPE_CHECKING:
    from typing import TypeAlias

    from typing_extensions import Buffer, Unpack

    class ExportOptions(TypedDict, total=False):
        """Options only type checkers see; nothing defines them at runtime."""

        dpi: int
        background: str

    PixelData: TypeAlias = bytes | Buffer


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


VERSION = "1.4.0+local"
SHORT_VERSION = VERSION.split("+")[0]
READ, WRITE = 1, 2
MODE = READ | WRITE

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


def legend(shadow=None, loc="best", offset=(0.0, 0.0)):
    """Place a legend.

    Parameters
    ----------
    shadow : None, bool or dict
        Whether to draw a shadow, or its properties.
    offset : (float, float)
        Shift from the anchor, in points.
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


class Registry(MutableMapping[str, Any]):
    """Named styles; mutable, so unhashable."""

    __hash__ = None  # type: ignore[assignment]

    def __init__(self) -> None:
        self._items: dict[str, Any] = {}

    def __getitem__(self, key: str) -> Any:
        return self._items[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self._items[key] = value

    def __delitem__(self, key: str) -> None:
        del self._items[key]

    def __iter__(self):
        return iter(self._items)

    def __len__(self) -> int:
        return len(self._items)


def export(data: PixelData, **options: Unpack[ExportOptions]) -> None:
    """Write *data* with the options type checkers know about."""


class Canvas:
    """A canvas whose renderer class is nested and created through ``self``."""

    class Renderer:
        """Draws one canvas."""

    def __init__(self) -> None:
        self.renderer = self.Renderer()
        self.encoder = codec.JSONEncoder()

    def encode(self, value: object, encoder: codec.JSONEncoder | None = None) -> str:
        """Encode *value* with the canvas's encoder or *encoder*."""
        return (encoder or self.encoder).encode(value)


class DrawError(Exception):
    """Raised by drawing calls; documented as ``drawlib.DrawError``."""

    __module__ = "drawlib"


class ClipError(DrawError):
    """Raised when a shape falls outside the clip path."""


class URL:
    """A resource location."""


StrOrURL = Union[str, URL]


class Outline(Glyph.Glyph):
    """A glyph drawn as its outline; the base lives in a module of the same name."""


def fetch(source: StrOrURL) -> bytes:
    """Read *source*."""
    return b""


TagInfo = namedtuple("TagInfo", "value name")


class Selection:
    """A selection whose source text is fixed once set."""

    source: Final

    def __init__(self, source: str) -> None:
        self.source = source


class Norm:
    """Maps data values to [0, 1]."""

    def __call__(self, value: float) -> float:
        return value


def with_scale(scale: str):
    """Class decorator that wraps a norm class in a scaled subclass of the same name."""
    def wrap(cls: type) -> type:
        scaled = type(cls.__name__, (cls,), {"scale": scale})
        scaled.__qualname__ = cls.__qualname__
        scaled.__module__ = cls.__module__
        return scaled
    return wrap


@with_scale("log")
class LogNorm(Norm):
    """A norm on a logarithmic scale."""


class _Lookup:
    """A descriptor standing in for a dunder, as context proxies use."""

    def __get__(self, obj: object, owner: type | None = None) -> _Lookup:
        return self

    def __call__(self, *args: Any) -> Any:
        return None


class Proxy:
    """Forwards attribute access through descriptors."""

    __getattr__ = _Lookup()
    __setattr__ = _Lookup()


def round_to(value, step=decimal.Decimal("0.01"), encoder=codec.JSONEncoder):
    """Round *value* to *step*; the defaults are an instance of a library type and a class."""
    return value


class Model:
    """A fitted model whose prediction lives in a helper module."""

    def predict(self, x=None, transform=True, **kwargs):
        return pred.predict(self, x=x, transform=transform, **kwargs)


def relationship(Id=None, Type=None, type=None, Target=None):
    """A link; ``type`` is a shorthand for a full ``Type`` URL (openpyxl's naming)."""
    return None
