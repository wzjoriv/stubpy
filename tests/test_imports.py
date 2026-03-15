"""
tests/test_imports.py
---------------------
Unit tests for stubpy.imports:
  - scan_import_statements
  - collect_typing_imports
  - collect_cross_imports
"""
from __future__ import annotations

import types as _builtin_types

import pytest

from stubpy.imports import (
    collect_cross_imports,
    collect_typing_imports,
    scan_import_statements,
)


# ---------------------------------------------------------------------------
# scan_import_statements
# ---------------------------------------------------------------------------

class TestScanImportStatements:
    def test_from_import(self):
        src = "from typing import Optional"
        result = scan_import_statements(src)
        assert result["Optional"] == "from typing import Optional"

    def test_from_import_as(self):
        src = "from typing import Optional as Opt"
        result = scan_import_statements(src)
        assert result["Opt"] == "from typing import Optional as Opt"

    def test_plain_import(self):
        src = "import os"
        result = scan_import_statements(src)
        assert result["os"] == "import os"

    def test_plain_import_dotted(self):
        src = "import os.path"
        result = scan_import_statements(src)
        # local name is last component
        assert result["path"] == "import os.path"

    def test_from_package(self):
        src = "from demo import types"
        result = scan_import_statements(src)
        assert result["types"] == "from demo import types"

    def test_multiple_imports(self):
        src = (
            "from typing import Optional, List\n"
            "from demo import types\n"
            "import sys\n"
        )
        result = scan_import_statements(src)
        assert "Optional" in result
        assert "List"     in result
        assert "types"    in result
        assert "sys"      in result

    def test_from_import_multiple_names(self):
        src = "from typing import Optional, List, Dict"
        result = scan_import_statements(src)
        assert result["Optional"] == "from typing import Optional"
        assert result["List"]     == "from typing import List"
        assert result["Dict"]     == "from typing import Dict"

    def test_invalid_syntax_returns_empty(self):
        src = "this is not valid python !!!"
        result = scan_import_statements(src)
        assert result == {}

    def test_empty_source(self):
        result = scan_import_statements("")
        assert result == {}

    def test_from_local_module(self):
        src = "from demo.element import Element"
        result = scan_import_statements(src)
        assert result["Element"] == "from demo.element import Element"


# ---------------------------------------------------------------------------
# collect_typing_imports
# ---------------------------------------------------------------------------

class TestCollectTypingImports:
    def test_optional_found(self):
        body = "def foo(x: Optional[str]) -> None: ..."
        result = collect_typing_imports(body)
        assert "Optional" in result

    def test_unused_names_excluded(self):
        body = "def foo(x: int) -> None: ..."
        result = collect_typing_imports(body)
        assert "Optional" not in result
        assert "List"     not in result

    def test_multiple_names(self):
        body = "def foo(x: Optional[str], y: List[int], z: Dict[str, Any]) -> None: ..."
        result = collect_typing_imports(body)
        assert "Optional" in result
        assert "List"     in result
        assert "Dict"     in result
        assert "Any"      in result

    def test_result_is_sorted(self):
        body = "Union[str, int] Optional[str] List[int] Callable[[], None]"
        result = collect_typing_imports(body)
        assert result == sorted(result)

    def test_all_candidates_present(self):
        body = (
            "Any Callable ClassVar Dict FrozenSet Iterator "
            "List Literal Optional Sequence Set Tuple Type Union"
        )
        result = collect_typing_imports(body)
        assert len(result) == 14

    def test_empty_body(self):
        result = collect_typing_imports("")
        assert result == []


# ---------------------------------------------------------------------------
# collect_cross_imports
# ---------------------------------------------------------------------------

class TestCollectCrossImports:
    def _make_module(self, name: str) -> _builtin_types.ModuleType:
        return _builtin_types.ModuleType(name)

    def test_base_class_import_collected(self):
        body = "class Container(Element):\n    pass"
        import_map = {"Element": "from demo.element import Element"}
        module = self._make_module("demo.container")
        result = collect_cross_imports(module, "demo.container", body, import_map)
        assert "from demo.element import Element" in result

    def test_typing_imports_excluded(self):
        body = "def foo(x: Optional[str]) -> None: ..."
        import_map = {"Optional": "from typing import Optional"}
        module = self._make_module("mymod")
        result = collect_cross_imports(module, "mymod", body, import_map)
        assert "from typing import Optional" not in result

    def test_future_imports_excluded(self):
        body = "class Foo: ..."
        import_map = {"annotations": "from __future__ import annotations"}
        module = self._make_module("mymod")
        result = collect_cross_imports(module, "mymod", body, import_map)
        assert result == []

    def test_names_defined_in_this_module_excluded(self):
        """If a class in the stub body is defined in *this* module, no import needed."""
        body = "class Container(Element):\n    pass\nclass Element:\n    pass"
        import_map = {"Element": "from somewhere import Element"}

        module = self._make_module("_stubpy_target_container")

        class Element:
            pass
        Element.__module__ = "_stubpy_target_container"
        module.Element = Element                        # type: ignore[attr-defined]

        result = collect_cross_imports(module, "_stubpy_target_container", body, import_map)
        assert "from somewhere import Element" not in result

    def test_annotation_names_collected(self):
        body = "def foo(self, el: Element) -> Container: ..."
        import_map = {
            "Element":   "from demo.element import Element",
            "Container": "from demo.container import Container",
        }
        module = self._make_module("mymod")
        result = collect_cross_imports(module, "mymod", body, import_map)
        assert "from demo.element import Element"     in result
        assert "from demo.container import Container" in result

    def test_deduplicated(self):
        """Same import should not appear twice even if name used multiple times."""
        body = (
            "class A(Element):\n"
            "    def foo(self, x: Element) -> Element: ..."
        )
        import_map = {"Element": "from demo.element import Element"}
        module = self._make_module("mymod")
        result = collect_cross_imports(module, "mymod", body, import_map)
        assert result.count("from demo.element import Element") == 1

    def test_name_not_in_import_map_skipped(self):
        body = "class Foo(UnknownBase):\n    pass"
        import_map = {}
        module = self._make_module("mymod")
        result = collect_cross_imports(module, "mymod", body, import_map)
        assert result == []
