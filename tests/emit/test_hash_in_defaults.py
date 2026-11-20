"""String defaults holding ``#``, quotes or separators never break the signature layout."""
from __future__ import annotations

import ast

import pytest

from stubpy.emit._def_layout import comment_start, format_def, join_params_multiline
from tests.conftest import make_stub_ctx

DEFAULTS = ['"#c8ccd4"', '"a # b"', "'url#frag'", '"{x}#"', 'b"#"', '"it\'s \\"#\\" here"', '", #)"']


@pytest.mark.parametrize("default", DEFAULTS)
def test_comment_start_ignores_hash_in_strings(default):
    assert comment_start(f"color: str = {default}") is None
    text = f"color={default}  # type: str"
    assert text[comment_start(text):] == "# type: str"


@pytest.mark.parametrize("default", DEFAULTS)
@pytest.mark.parametrize("extra", ["", ", max_faces: int = 0, scale: float = 1.0"])
@pytest.mark.parametrize("infer", [False, True])
@pytest.mark.parametrize("imports", [True, False])
def test_stub_with_hash_default_parses_and_keeps_the_value(default, extra, infer, imports):
    source = f"def load_obj(path: str, color={default}{extra}):\n    '''Load.\n\n    Parameters\n    ----------\n" \
             "    path : pathlib.Path\n        Where.\n    '''\n"
    stub, _ = make_stub_ctx(source, infer_types=infer, imports="all" if imports else "none")
    tree = ast.parse(stub)
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef))
    assert ast.literal_eval(fn.args.defaults[0]) == ast.literal_eval(default)


def test_multiline_join_puts_the_comma_before_a_real_comment_only():
    joined = join_params_multiline(['color: str = "#c8ccd4"', 'path  # type: Path'], "    ")
    assert joined == 'color: str = "#c8ccd4",\n    path,  # type: Path'


def test_short_signature_with_hash_default_stays_inline():
    assert format_def("", "def", "f", ['color: str = "#fff"'], "", 1) == ['def f(color: str = "#fff"): ...']
