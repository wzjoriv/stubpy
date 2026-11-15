from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from collections.abc import Callable
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import svgwriter as svg  # noqa: E402
from svgwriter.elements.base import Element  # noqa: E402

SVG_NS = "{http://www.w3.org/2000/svg}"

REQUIRED_ARGS: dict[str, Callable[[], Element]] = {
    "hkern": lambda: svg.HKern(-10, u1="A", u2="V"),
    "vkern": lambda: svg.VKern(5, g1="a", g2="b"),
    "color-profile": lambda: svg.ColorProfile("sRGB", href="srgb.icc"),
}


def make(tag: str) -> Element:
    """Default instance of the element registered for *tag*."""
    factory = REQUIRED_ARGS.get(tag)
    return factory() if factory else svg.Element.lookup(tag)()  # type: ignore[misc]


def wellformed(text: str) -> ET.Element:
    """Parse with ``xml.etree`` (raises on malformed output)."""
    return ET.fromstring(text)


def roundtrip(element: Element, **options: object) -> tuple[str, str]:
    first = element.to_string(**options)
    second = svg.parse(first).to_string(**options)
    return first, second


ALL_TAGS = sorted(svg.Element.registered())


@pytest.fixture(params=ALL_TAGS)
def any_tag(request: pytest.FixtureRequest) -> str:
    return request.param
