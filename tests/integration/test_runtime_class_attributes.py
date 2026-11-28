"""Values a class gains at runtime (``setattr`` in a decorator or after the class) appear in its stub."""
from __future__ import annotations

from stubpy import generate

SOURCE = '''
import re
from fractions import Fraction


def ranges(cls):
    for name, lo, hi in (("DIGITS", 48, 58), ("UPPER", 65, 91)):
        setattr(cls, name, range(lo, hi))
    cls.PATTERN = re.compile("x")
    cls.HALF = Fraction(1, 2)
    return cls


@ranges
class Charset:
    def size(self) -> int: ...
'''


def test_values_set_on_the_class_at_runtime_are_declared(tmp_path):
    src = tmp_path / "chars.py"
    src.write_text(SOURCE)
    generate(src, tmp_path / "out")
    body = (tmp_path / "out" / "chars.pyi").read_text().split("class Charset:")[1]
    for line in ("DIGITS: range", "UPPER: range", "PATTERN: Pattern", "HALF: Fraction"):
        assert f"    {line}\n" in body
