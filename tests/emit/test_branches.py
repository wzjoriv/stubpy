"""Tests for stubpy.emit.branches and stubpy.emit.lowering."""
from stubpy.analysis.harvest.models import VersionBlock
from stubpy.emit.branches import Unit, join_sections, weave
from stubpy.emit.lowering import lower_type_params


def _text(units: list[Unit]) -> str:
    return join_sections(weave(units))


class TestWeave:
    def test_unconditional_units_pass_through(self):
        assert _text([Unit("X: int", True), Unit("Y: str", True)]) == "X: int\nY: str"

    def test_if_elif_else(self):
        block = VersionBlock(1, ["sys.version_info >= (3, 12)", "sys.platform == 'win32'", None])
        text = _text([Unit("def f(): ...", False, ((block, i),)) for i in range(3)])
        assert text == (
            "if sys.version_info >= (3, 12):\n    def f(): ...\n"
            "elif sys.platform == 'win32':\n    def f(): ...\n"
            "else:\n    def f(): ..."
        )

    def test_nested_blocks_and_empty_branches(self):
        outer = VersionBlock(1, ["A", "B", None])
        inner = VersionBlock(2, ["C", None])
        text = _text([
            Unit("x: int", True, ((outer, 1), (inner, 1))),
            Unit("y: int", True),
        ])
        assert text == "if A:\n    ...\nelif B:\n    if C:\n        ...\n    else:\n        x: int\n\ny: int"

    def test_two_blocks_stay_apart(self):
        a, b = VersionBlock(1, ["A"]), VersionBlock(5, ["B"])
        assert _text([Unit("x: int", True, ((a, 0),)), Unit("y: int", True, ((b, 0),))]) == (
            "if A:\n    x: int\n\nif B:\n    y: int"
        )


class TestLowerTypeParams:
    def test_kinds(self):
        decls, args = lower_type_params(["T", "B: int", "C: (int, str)", "*Ts", "**P", "D = int"])
        assert decls == [
            'T = TypeVar("T")',
            'B = TypeVar("B", bound=int)',
            'C = TypeVar("C", int, str)',
            'Ts = TypeVarTuple("Ts")',
            'P = ParamSpec("P")',
            'D = TypeVar("D", default=int)',
        ]
        assert args == ["T", "B", "C", "Unpack[Ts]", "P", "D"]
