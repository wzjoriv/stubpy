"""Shared fixtures and helpers for the svgraster tests."""
from __future__ import annotations

import importlib

import numpy as np
import pytest

import svgraster

SVG_NS = 'xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink"'
SEED = 1234


def svg(body: str, width: int = 20, height: int = 20, extra: str = "") -> str:
    """Wrap ``body`` in an ``svg`` root of the given size."""
    return f'<svg {SVG_NS} width="{width}" height="{height}" {extra}>{body}</svg>'


def render_float(markup: str, **kwargs) -> np.ndarray:
    """Render to straight-alpha float32."""
    return svgraster.render(markup, dtype="float32", **kwargs)


def native_module(name: str):
    """Import a compiled module or skip the test."""
    try:
        return importlib.import_module(f"svgraster.{name}")
    except ImportError:
        pytest.skip(f"svgraster.{name} is not built")


@pytest.fixture
def rng() -> np.random.Generator:
    """A deterministic random generator."""
    return np.random.default_rng(SEED)


@pytest.fixture
def rgba(rng) -> np.ndarray:
    """A random premultiplied float32 image with some transparent pixels."""
    img = rng.random((17, 23, 4)).astype(np.float32)
    img[..., 3] = np.where(rng.random((17, 23)) < 0.15, 0.0, img[..., 3])
    img[..., :3] *= img[..., 3:4]
    return img


@pytest.fixture
def rgba2(rng) -> np.ndarray:
    """A second random premultiplied image of the same size."""
    img = rng.random((17, 23, 4)).astype(np.float32)
    img[..., :3] *= img[..., 3:4]
    return img
