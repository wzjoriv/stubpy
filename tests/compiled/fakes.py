"""Fake binding objects that look like C API, Cython, pybind11 and nanobind callables, on any interpreter."""
from __future__ import annotations

import enum
import types

MODULE = "fakeext"


class FakeBuiltin:
    """A callable that is not a Python function, with a binding-style ``__doc__`` and optional metadata."""

    def __init__(self, name: str, doc: str | None = None, *, text_signature: str | None = None,
                 nb_signature: tuple | None = None, module: str = MODULE) -> None:
        self.__name__ = name
        self.__qualname__ = name
        self.__doc__ = doc
        self.__module__ = module
        if text_signature is not None:
            self.__text_signature__ = text_signature
        if nb_signature is not None:
            self.__nb_signature__ = nb_signature

    def __call__(self, *args, **kwargs):
        return None


PYBIND_OVERLOADED = (
    "blur(*args, **kwargs)\n"
    "Overloaded function.\n\n"
    "1. blur(img: numpy.typing.NDArray[numpy.float32], std_x: typing.SupportsFloat, std_y: typing.SupportsFloat)"
    " -> numpy.typing.NDArray[numpy.float32]\n\n"
    "Separate deviations.\n\n"
    "2. blur(img: numpy.typing.NDArray[numpy.float32], std: typing.SupportsFloat)"
    " -> numpy.typing.NDArray[numpy.float32]\n\n"
    "One deviation.\n"
)


class Mode:
    """A pybind11-style enum: instances as class attributes and a ``__members__`` mapping."""

    __init__ = FakeBuiltin("__init__", "__init__(self: fakeext.Mode, value: typing.SupportsInt) -> None\n")
    name = property(FakeBuiltin("name", "name(self: object, /) -> str\n"))
    value = property(FakeBuiltin("", "(arg0: fakeext.Mode) -> int\n"))


Mode.__module__ = MODULE
Mode.FAST = Mode.__new__(Mode)
Mode.SLOW = Mode.__new__(Mode)
Mode.__members__ = {"FAST": Mode.FAST, "SLOW": Mode.SLOW}


class Cap(enum.Enum):
    """Stroke caps (a nanobind 2 enum is a real Enum)."""

    BUTT = 0
    ROUND = 1


Cap.__module__ = MODULE


class Widget:
    """A widget."""

    __slots__ = ("tag",)
    __init__ = FakeBuiltin(
        "__init__",
        "__init__(*args, **kwargs)\nOverloaded function.\n\n"
        "1. __init__(self: fakeext.Widget) -> None\n\n"
        "2. __init__(self: fakeext.Widget, size: typing.SupportsInt, mode: fakeext.Mode = <Mode.FAST: 0>) -> None\n",
    )
    resize = FakeBuiltin("resize", "resize(self: fakeext.Widget, w: int, h: int) -> fakeext.Widget\n\nResize it.\n")
    make = staticmethod(FakeBuiltin("make", "make(n: int = 3) -> fakeext.Widget\n"))
    width = property(FakeBuiltin("", "(arg0: fakeext.Widget) -> int\n"), doc="Width in pixels.")
    height = property(
        FakeBuiltin("", "(self: fakeext.Widget) -> float\n"),
        FakeBuiltin("", "(self: fakeext.Widget, arg0: typing.SupportsFloat) -> None\n"),
    )
    mystery = FakeBuiltin("mystery", "Does something.")
    LIMIT = 10

    class Kind:
        """A nested kind."""

        clear = FakeBuiltin("clear", "clear(self) -> None\n")


Widget.__module__ = MODULE
Widget.Kind.__module__ = MODULE
Widget.Kind.__qualname__ = "Widget.Kind"


def fake_module(**extra: object) -> types.ModuleType:
    """A module named ``fakeext`` holding the fakes above."""
    module = types.ModuleType(MODULE, "A fake extension module.")
    namespace = {
        "area": FakeBuiltin("area", "area($module, points, /)\n--\n\nShoelace area.", text_signature="($module, points, /)"),
        "blur": FakeBuiltin("blur", PYBIND_OVERLOADED),
        "over": FakeBuiltin(
            "over", "over(...)",
            nb_signature=(("def over(dst: numpy.ndarray[dtype=float32, shape=(*, *, 4), order='C'], "
                           "*, opacity: float = \\0) -> None", "Composite in place.", (1.0,)),),
        ),
        "lerp": FakeBuiltin("lerp", "lerp(double a, double b, double t=0.5) -> double\n\nInterpolate."),
        "fill": FakeBuiltin("fill", "fill(float[:, ::1] out, int value) -> void"),
        "opaque": FakeBuiltin("opaque", "No signature here."),
        "hinted": FakeBuiltin("hinted", "Hinted."),
        "Mode": Mode,
        "Cap": Cap,
        "Widget": Widget,
        "FAST": Mode.FAST,
        "COUNT": 3,
        "NAMES": ("a", "b"),
        "_private": FakeBuiltin("_private", "_private() -> None"),
        "np": types.ModuleType("numpy"),
        "imported": FakeBuiltin("imported", "imported() -> int", module="elsewhere"),
    }
    namespace["hinted"].__stubpy_signature__ = "(x: float) -> float"
    namespace.update(extra)
    vars(module).update(namespace)
    return module
