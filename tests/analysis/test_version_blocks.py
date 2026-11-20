"""Version blocks in the AST harvest: ``is_version_test``, ``version_chain`` and branch tags."""
import ast
import sys

import pytest

from stubpy.analysis.astutil import is_version_test, static_truth, version_chain
from stubpy.analysis.harvest import ast_harvest
from stubpy.analysis.harvest._part_models import on_taken_path


def _expr(text: str) -> ast.expr:
    return ast.parse(text, mode="eval").body


@pytest.mark.parametrize("text", [
    "sys.version_info >= (3, 12)",
    "sys.version_info[:2] < (3, 10)",
    "sys.version_info[0] == 3",
    "sys.platform == 'win32'",
    "sys.platform != 'linux'",
    "sys.platform.startswith('linux')",
    "not sys.platform.startswith('win')",
    "sys.version_info >= (3, 11) and sys.platform == 'darwin'",
    "sys.platform == 'win32' or sys.platform == 'cygwin'",
])
def test_version_tests(text):
    assert is_version_test(_expr(text))
    assert static_truth(_expr(text)) is not None


@pytest.mark.parametrize("text", [
    "TYPE_CHECKING",
    "HAS_X",
    "os.environ.get('X')",
    "sys.version_info >= LIMIT",
    "sys.platform < 'x'",
    "sys.version_info >= (3, 11) or HAS_X",
    "sys.maxsize > 2**32",
])
def test_other_tests(text):
    assert not is_version_test(_expr(text))


def test_platform_startswith_is_evaluated():
    assert static_truth(_expr(f"sys.platform.startswith({sys.platform[:3]!r})")) is True


def test_chain_stops_at_a_non_version_elif():
    node = ast.parse("if sys.version_info >= (3, 12):\n    a = 1\nelif HAS_X:\n    b = 1\nelse:\n    c = 1\n").body[0]
    chain = version_chain(node)
    assert [ast.unparse(t) if t is not None else None for t, _ in chain] == ["sys.version_info >= (3, 12)", None]
    assert isinstance(chain[1][1][0], ast.If)


SOURCE = """
import sys
if sys.version_info >= (3, 0):
    from typing import Self
    def f() -> int: ...
    if sys.platform == "win32":
        X: int = 1
    else:
        X: str = ""
elif sys.version_info >= (2, 7):
    def f() -> str: ...
else:
    class C: ...
class K:
    if sys.version_info >= (3, 0):
        def m(self) -> None: ...
    else:
        attr: int
def g() -> None: ...
"""


class TestHarvest:
    def test_every_branch_is_tagged(self):
        syms = ast_harvest(SOURCE, version_branches=True)
        f_new, f_old = syms.functions[:2]
        block = f_new.branch[0][0]
        assert block.tests == ["sys.version_info >= (3, 0)", "sys.version_info >= (2, 7)", None]
        assert block.taken == 0
        assert f_new.branch == ((block, 0),) and f_old.branch == ((block, 1),)
        assert syms.classes[0].name == "C" and syms.classes[0].branch == ((block, 2),)
        x_win, x_other = syms.variables
        inner = x_win.branch[1][0]
        assert x_win.branch == ((block, 0), (inner, 0)) and x_other.branch == ((block, 0), (inner, 1))
        assert on_taken_path(x_win.branch) == (sys.platform == "win32")
        assert [i.name for i in syms.imports if i.branch] == ["Self"]
        assert syms.functions[2].name == "g" and syms.functions[2].branch == ()

    def test_class_members_are_tagged(self):
        k = ast_harvest(SOURCE, version_branches=True).classes[1]
        assert k.methods[0].branch[0][1] == 0 and k.attributes[0].branch[0][1] == 1

    def test_default_keeps_the_taken_branch(self):
        syms = ast_harvest(SOURCE)
        assert [f.name for f in syms.functions] == ["f", "g"]
        assert all(not f.branch for f in syms.functions)
        assert [c.name for c in syms.classes] == ["K"]
        assert [m.name for m in syms.classes[0].methods] == ["m"] and not syms.classes[0].attributes
