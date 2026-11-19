"""Source back-tracing reads installed packages (and their bundled stubs) without importing them."""
from __future__ import annotations

import stubpy
from stubpy import Config
from stubpy.analysis._installed import installed_file
from tests.conftest import write_tree


def _project(tmp_path, base_module: str) -> str:
    root = write_tree(tmp_path / "proj", {
        "app/__init__.py": "",
        "app/widgets.py": f"""
            from {base_module} import Base

            class Button(Base):
                def __init__(self, label: str, **kwargs) -> None:
                    super().__init__(**kwargs)
        """,
    })
    return str(root / "app" / "widgets.py")


def test_third_party_base_resolves_from_its_source_without_running_it(tmp_path, monkeypatch):
    site = write_tree(tmp_path / "site", {
        "thirdpkg_src/__init__.py": "raise RuntimeError('must not run')\n",
        "thirdpkg_src/base.py": """
            raise RuntimeError('must not run either')
            class Base:
                def __init__(self, width: int = 1, *, visible: bool = True) -> None: ...
        """,
    })
    monkeypatch.syspath_prepend(str(site))
    text = stubpy.render(_project(tmp_path, "thirdpkg_src.base"), config=Config(imports="none")).text
    assert "label: str," in text and "width: int = 1," in text and "visible: bool = True," in text
    assert "**kwargs" not in text


def test_bundled_stub_wins_over_the_source(tmp_path, monkeypatch):
    site = write_tree(tmp_path / "site", {
        "thirdpkg_typed/__init__.py": "",
        "thirdpkg_typed/base.py": "class Base:\n    def __init__(self, width=1): ...\n",
        "thirdpkg_typed/base.pyi": "class Base:\n    def __init__(self, width: float = ...) -> None: ...\n",
    })
    monkeypatch.syspath_prepend(str(site))
    assert installed_file(["thirdpkg_typed", "base"]) == site / "thirdpkg_typed" / "base.pyi"
    text = stubpy.render(_project(tmp_path, "thirdpkg_typed.base"), config=Config(imports="none")).text
    assert "width: float = ...," in text


def test_stubs_distribution_is_used(tmp_path, monkeypatch):
    site = write_tree(tmp_path / "site", {
        "thirdpkg_dist/__init__.py": "",
        "thirdpkg_dist-stubs/__init__.pyi": "class Base:\n    def __init__(self, size: int) -> None: ...\n",
    })
    monkeypatch.syspath_prepend(str(site))
    assert installed_file(["thirdpkg_dist"]) == site / "thirdpkg_dist-stubs" / "__init__.pyi"


def test_standard_library_is_not_read():
    assert installed_file(["json", "decoder"]) is None
