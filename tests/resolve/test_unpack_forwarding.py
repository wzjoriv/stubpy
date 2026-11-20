"""``**kwargs: Unpack[TD]`` forwarded into a callee expands the same way for functions and methods."""
from __future__ import annotations

import re

import pytest

import stubpy
from stubpy.config import Config
from tests.conftest import assert_valid_syntax, on_sys_path, write_tree

TYPES = '''
from typing import TypedDict

class Options(TypedDict, total=False):
    timeout: float
    verify: bool
'''

API = '''
from __future__ import annotations
{binding}
from typing_extensions import Unpack

def request(method: str, url: str, **kwargs: Unpack[_t.Options]) -> int:
    return 0

def get(url: str, params=None, **kwargs: Unpack[_t.Options]) -> int:
    return request("get", url, params=params, **kwargs)

def own(**kwargs: Unpack[_t.Options]) -> int:
    return 0

class Session:
    def request(self, method: str, url: str, **kwargs: Unpack[_t.Options]) -> int:
        return 0

    def get(self, url: str, **kwargs: Unpack[_t.Options]) -> int:
        return self.request("GET", url, **kwargs)

    def own(self, **kwargs: Unpack[_t.Options]) -> int:
        return 0
'''

BINDINGS = {
    "runtime": "from . import _types as _t",
    "type_checking": "from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    from . import _types as _t",
}
EXPANDED = "*, timeout: float = ..., verify: bool = ...) -> int: ..."


@pytest.mark.parametrize("imports", ["all", "none"])
@pytest.mark.parametrize("binding", list(BINDINGS))
def test_forwarded_unpack_expands_for_functions_and_methods(tmp_path, binding, imports):
    package = f"upk_{binding}_{imports}"
    root = write_tree(tmp_path / "src", {
        f"{package}/__init__.py": "",
        f"{package}/_types.py": TYPES,
        f"{package}/api.py": API.replace("{binding}", BINDINGS[binding]),
    })
    with on_sys_path(root, package):
        report = stubpy.generate(root / package / "api.py", tmp_path / "out", config=Config(imports=imports))
    assert report.ok
    stub = (tmp_path / "out" / package / "api.pyi").read_text(encoding="utf-8")
    assert_valid_syntax(stub)
    flat = re.sub(r",?\s*\)", ")", re.sub(r"\(\s+", "(", re.sub(r",\s+", ", ", stub)))
    assert f"def get(url: str, params=None, {EXPANDED}" in flat
    assert f"def get(self, url: str, {EXPANDED}" in flat
    assert "def own(**kwargs: Unpack[" in flat
    assert "def own(self, **kwargs: Unpack[" in flat
    assert "def request(method: str, url: str, **kwargs: Unpack[" in flat
