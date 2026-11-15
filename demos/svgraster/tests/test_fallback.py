"""The package with every native layer blocked, and native-vs-fallback full renders."""
from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path

import numpy as np
import pytest

import svgraster
from svgraster import _backend
from tests.conftest import svg

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
SCENE = svg(
    '<defs><linearGradient id="g" x2="0" y2="1" color-interpolation="linearRGB">'
    '<stop offset="0" stop-color="gold"/><stop offset="1" stop-color="purple" stop-opacity="0.6"/></linearGradient>'
    '<radialGradient id="r" fx="0.3" spreadMethod="reflect" r="0.3"><stop offset="0" stop-color="white"/>'
    '<stop offset="1" stop-color="teal"/></radialGradient>'
    '<pattern id="p" width="5" height="5" patternUnits="userSpaceOnUse" patternTransform="rotate(30)">'
    '<circle cx="2.5" cy="2.5" r="1.5" fill="crimson"/></pattern>'
    '<clipPath id="c"><circle cx="30" cy="30" r="14"/></clipPath>'
    '<mask id="m"><rect width="60" height="60" fill="url(#g)"/></mask>'
    '<marker id="k" markerWidth="4" markerHeight="4" refX="2" refY="2" orient="auto">'
    '<path d="M0 0 L4 2 L0 4 z"/></marker>'
    '<filter id="f"><feTurbulence baseFrequency="0.08" numOctaves="2" seed="4" result="t"/>'
    '<feDisplacementMap in="SourceGraphic" in2="t" scale="4" xChannelSelector="R" yChannelSelector="G"/>'
    '<feGaussianBlur stdDeviation="0.8"/><feMorphology radius="0.5" operator="dilate"/>'
    '<feColorMatrix type="hueRotate" values="40"/></filter>'
    '<filter id="l"><feSpecularLighting surfaceScale="4" specularExponent="12" result="s">'
    '<fePointLight x="10" y="40" z="20"/></feSpecularLighting>'
    '<feComposite in="s" in2="SourceGraphic" operator="arithmetic" k2="1" k3="1"/>'
    '<feBlend in2="SourceGraphic" mode="multiply"/></filter></defs>'
    '<rect width="60" height="60" fill="url(#g)"/>'
    '<rect x="5" y="5" width="25" height="20" fill="url(#r)" stroke="black" stroke-dasharray="3 1" rx="4"/>'
    '<rect width="60" height="60" fill="url(#p)" clip-path="url(#c)" opacity="0.7"/>'
    '<path d="M5 50 C 15 35 30 60 45 45 A 8 6 20 1 1 55 55" fill="none" stroke="navy" stroke-width="2" '
    'stroke-linejoin="round" marker-mid="url(#k)" marker-end="url(#k)"/>'
    '<ellipse cx="45" cy="15" rx="10" ry="7" fill="orange" filter="url(#f)"/>'
    '<circle cx="15" cy="40" r="7" fill="seagreen" filter="url(#l)" mask="url(#m)"/>'
    '<text x="30" y="58" font-size="7" text-anchor="middle" fill="white">SVG 1.1</text>',
    60, 60)
BLOCKER = textwrap.dedent("""
    import importlib.abc, sys
    BLOCKED = {"svgraster._scanline", "svgraster._paint", "svgraster._pattern", "svgraster._filters",
               "svgraster._composite", "numba"}

    class Blocker(importlib.abc.MetaPathFinder):
        def find_spec(self, name, path, target=None):
            if name in BLOCKED:
                raise ImportError(f"blocked {name}")
            return None

    sys.meta_path.insert(0, Blocker())
    import numpy as np
    import svgraster
    info = svgraster.backend_info()
    assert not any(v["available"] for v in info.values()), info
    img = svgraster.Renderer(antialias=8).render(sys.argv[1], dtype="float32", premultiplied=True)
    np.save(sys.argv[2], img)
    print("ok")
""")


def _native_built() -> bool:
    return all(_backend.module(layer) is not None for layer in _backend.NATIVE_MODULES)


def test_every_layer_blocked_still_renders(tmp_path):
    scene = tmp_path / "scene.svg"
    scene.write_text(SCENE)
    out = tmp_path / "blocked.npy"
    env = dict(os.environ, PYTHONPATH=str(PACKAGE_ROOT))
    env.pop(_backend.PURE_ENV, None)
    result = subprocess.run([sys.executable, "-c", BLOCKER, str(scene), str(out)], capture_output=True, text=True,
                            env=env, cwd=tmp_path, timeout=600)
    assert result.returncode == 0, result.stderr
    blocked = np.load(out)
    assert blocked.shape == (60, 60, 4) and blocked[..., 3].max() == pytest.approx(1.0)
    current = svgraster.Renderer(antialias=8).render(SCENE, dtype="float32", premultiplied=True)
    np.testing.assert_allclose(blocked, current, atol=1e-4)


def test_pure_env_disables_native(tmp_path):
    code = "import svgraster; print(sum(v['available'] for k, v in svgraster.backend_info().items() if k != 'jit'))"
    env = dict(os.environ, PYTHONPATH=str(PACKAGE_ROOT), **{_backend.PURE_ENV: "1"})
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env, cwd=tmp_path,
                            timeout=300)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "0"


@pytest.mark.parametrize("antialias", [4, 16])
def test_full_scene_native_matches_fallback(antialias):
    if not _native_built():
        pytest.skip("native layers are not all built")
    native = svgraster.Renderer(antialias=antialias).render(SCENE, dtype="float32", premultiplied=True)
    fallback = svgraster.Renderer(antialias=antialias, native=False).render(SCENE, dtype="float32",
                                                                            premultiplied=True)
    np.testing.assert_allclose(native, fallback, atol=1e-4)
    assert native[..., 3].mean() > 0.5


def test_pure_python_context_is_scoped():
    if not _native_built():
        pytest.skip("native layers are not all built")
    with svgraster.pure_python():
        assert _backend.native("scanline") is None
    assert _backend.native("scanline") is not None
