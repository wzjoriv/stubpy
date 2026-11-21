"""The ``array_metadata`` option: nanobind ndarray shape, order and device kept as ``Annotated`` metadata."""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

import stubpy
from stubpy import Config
from stubpy.cli.commands import config_from_args
from stubpy.cli.parser import build_parser
from stubpy.compiled.signatures import array_metadata, nanobind_signatures

PLAIN_F32 = "numpy.typing.NDArray[numpy.float32]"
CORPUS = Path(__file__).resolve().parents[2] / "corpora" / "rasterlib"


class _NB:
    def __init__(self, text: str) -> None:
        self.__nb_signature__ = ((f"def f(a: ndarray[{text}]) -> None", None, None),)
        self.__name__ = "f"


def _annotation(text: str, keep: bool) -> str | None:
    with array_metadata(keep):
        (sig,) = nanobind_signatures(_NB(text))
    return sig.params[0].annotation


@pytest.mark.parametrize("text, expected", [
    ("dtype=float32, shape=(*, 3)", f"typing.Annotated[{PLAIN_F32}, dict(shape=(None, 3))]"),
    ("dtype=float32, shape=(3)", f"typing.Annotated[{PLAIN_F32}, dict(shape=(3,))]"),
    ("dtype=float32, shape=(2, *, 4)", f"typing.Annotated[{PLAIN_F32}, dict(shape=(2, None, 4))]"),
    ("dtype=float32, shape=(n, 3)", f"typing.Annotated[{PLAIN_F32}, dict(shape=(None, 3))]"),
    ("dtype=float32, order='C'", f"typing.Annotated[{PLAIN_F32}, dict(order='C')]"),
    ("dtype=float32, order='F'", f"typing.Annotated[{PLAIN_F32}, dict(order='F')]"),
    ("dtype=float32, device='cpu'", f"typing.Annotated[{PLAIN_F32}, dict(device='cpu')]"),
    ("dtype=float32, shape=(*, 3), order='C'", f"typing.Annotated[{PLAIN_F32}, dict(shape=(None, 3), order='C')]"),
    ("order='C', device='cuda', shape=(*), dtype=float32",
     f"typing.Annotated[{PLAIN_F32}, dict(shape=(None,), order='C', device='cuda')]"),
    ("dtype=float32, shape=(*, 3), order='C', device='cpu'",
     f"typing.Annotated[{PLAIN_F32}, dict(shape=(None, 3), order='C', device='cpu')]"),
    ("shape=(*, 3)", "typing.Annotated[numpy.typing.NDArray[typing.Any], dict(shape=(None, 3))]"),
])
def test_metadata_forms(text, expected):
    assert _annotation(text, True) == expected


@pytest.mark.parametrize("text", ["dtype=float32", "dtype=float32, writable=False"])
def test_no_metadata_stays_plain(text):
    assert _annotation(text, True) == PLAIN_F32


@pytest.mark.parametrize("text", ["dtype=float32, shape=(*, 3), order='C', device='cpu'", "dtype=float32"])
def test_off_by_default(text):
    assert _annotation(text, False) == PLAIN_F32
    (sig,) = nanobind_signatures(_NB(text))
    assert sig.params[0].annotation == PLAIN_F32


def test_switch_is_scoped():
    with array_metadata():
        pass
    assert _annotation("dtype=float32, shape=(3)", False) == PLAIN_F32


def test_option_default_flag_and_toml(tmp_path):
    assert Config().array_metadata is False
    assert Config.from_dict({"array-metadata": True}).array_metadata is True
    with pytest.raises(TypeError):
        Config(array_metadata="yes")
    args = build_parser().parse_args(["generate", "--array-metadata", "--no-config", str(tmp_path)])
    assert config_from_args(args).array_metadata is True


def _built() -> bool:
    sys.path.insert(0, str(CORPUS))
    try:
        importlib.import_module("rasterlib._composite")
        return True
    except Exception:
        return False
    finally:
        sys.path.remove(str(CORPUS))


@pytest.mark.skipif(not _built(), reason="rasterlib._composite is not built for this interpreter")
def test_corpus_composite(tmp_path):
    meta = "Annotated[numpy.typing.NDArray[numpy.float32], dict(shape=(None, None, 4), order='C', device='cpu')]"
    for keep in (False, True):
        out = tmp_path / str(keep)
        cfg = Config(array_metadata=keep)
        stubpy.generate(CORPUS / "rasterlib", out, config=cfg)
        text = (out / "rasterlib" / "_composite.pyi").read_text(encoding="utf-8")
        assert (f"dst: {meta}" in text) is keep
        assert ("from typing import Annotated" in text) is keep
        assert (f"dst: {PLAIN_F32}" in text) is not keep
