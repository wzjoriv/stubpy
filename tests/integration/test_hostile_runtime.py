"""Runtime objects that misbehave when inspected must not cost the stub its symbols."""
from __future__ import annotations

import textwrap

from stubpy import generate

MODULE = '''
class Ambiguous:
    """Answers every attribute with itself and refuses truth testing, like a dataframe expression."""
    def __getattribute__(self, name):
        return self
    def __bool__(self):
        raise TypeError("the truth value is ambiguous")
    def __call__(self, *args, **kwargs):
        return self


class _Missing:
    """A lazy optional dependency that raises on any attribute access."""
    def __getattr__(self, name):
        raise ModuleNotFoundError("requires an optional module")


col = Ambiguous()
optional = _Missing()


def total(*names: str, **kwargs) -> int:
    return col(*names, **kwargs).sum()


def convert(value: \"optional.Table\") -> int:
    return 0
'''


def test_hostile_objects_keep_every_function(tmp_path):
    src = tmp_path / "hostile.py"
    src.write_text(textwrap.dedent(MODULE))
    out = tmp_path / "out"
    report = generate(src, out)
    stub = (out / "hostile.pyi").read_text()
    assert "def total(" in stub and "def convert(" in stub
    assert not [d for r in report.results for d in r.diagnostics if "emission failed" in d.message]
