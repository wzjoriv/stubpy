"""Tests for stubpy.stub_merge — incremental stub update with markers."""
from __future__ import annotations

import pytest

from stubpy.stub_merge import (
    BEGIN_MARKER,
    END_MARKER,
    _is_begin,
    _is_end,
    merge_stubs,
    read_and_merge,
    wrap_generated,
)


# ---------------------------------------------------------------------------
# Marker recognition (lenient matching)
# ---------------------------------------------------------------------------

class TestMarkerRecognition:
    def test_canonical_begin(self):
        assert _is_begin("# stubpy: auto-generated begin")

    def test_canonical_end(self):
        assert _is_end("# stubpy: auto-generated end")

    def test_case_insensitive(self):
        assert _is_begin("# STUBPY: AUTO-GENERATED BEGIN")
        assert _is_end("# Stubpy: Auto-Generated End")
        assert _is_begin("# StubPy: auto-GENERATED Begin")

    def test_extra_spaces(self):
        assert _is_begin("#  stubpy :  auto-generated  begin  ")
        assert _is_end("#  stubpy :  auto-generated  end  ")

    def test_no_colon(self):
        assert _is_begin("# stubpy auto-generated begin")

    def test_space_instead_of_hyphen(self):
        assert _is_begin("# stubpy: auto generated begin")
        assert _is_end("# stubpy: auto generated end")

    def test_non_markers_rejected(self):
        assert not _is_begin("# some other comment")
        assert not _is_end("x: int")
        assert not _is_begin("")
        assert not _is_end("def foo(): ...")

    def test_leading_whitespace(self):
        assert _is_begin("    # stubpy: auto-generated begin")


# ---------------------------------------------------------------------------
# wrap_generated
# ---------------------------------------------------------------------------

class TestWrapGenerated:
    def test_adds_markers(self):
        wrapped = wrap_generated("x: int\n")
        assert wrapped.startswith(BEGIN_MARKER)
        assert wrapped.strip().endswith(END_MARKER)
        assert "x: int" in wrapped

    def test_no_double_wrap(self):
        wrapped = wrap_generated("x: int\n")
        double = wrap_generated(wrapped)
        assert double.count(BEGIN_MARKER) == 1

    def test_ensures_trailing_newline(self):
        wrapped = wrap_generated("x: int")
        assert wrapped.endswith("\n")

    def test_empty_content(self):
        wrapped = wrap_generated("")
        assert BEGIN_MARKER in wrapped
        assert END_MARKER in wrapped


# ---------------------------------------------------------------------------
# merge_stubs — basic cases
# ---------------------------------------------------------------------------

class TestMergeStubs:
    def test_replaces_single_pair(self):
        existing = (
            "# manual\n"
            f"{BEGIN_MARKER}\n"
            "x: int\n"
            f"{END_MARKER}\n"
            "# after\n"
        )
        generated = f"{BEGIN_MARKER}\ny: str\n{END_MARKER}\n"
        result = merge_stubs(existing, generated)
        assert "y: str" in result
        assert "x: int" not in result
        assert "# manual" in result
        assert "# after" in result

    def test_preserves_content_outside_markers(self):
        existing = (
            "# type: ignore\n"
            f"{BEGIN_MARKER}\n"
            "old_content: int\n"
            f"{END_MARKER}\n"
            "MyCustomClass = ...\n"
        )
        generated = f"{BEGIN_MARKER}\nnew_content: str\n{END_MARKER}\n"
        result = merge_stubs(existing, generated)
        assert "# type: ignore" in result
        assert "MyCustomClass = ..." in result
        assert "new_content: str" in result
        assert "old_content: int" not in result

    def test_no_markers_appends(self):
        existing = "# fully manual file\nx: int\n"
        generated = "y: str\n"
        result = merge_stubs(existing, generated)
        assert "# fully manual file" in result
        assert "x: int" in result
        assert BEGIN_MARKER in result
        assert "y: str" in result

    def test_multiple_pairs(self):
        existing = (
            "# header\n"
            f"{BEGIN_MARKER}\n"
            "first_old: int\n"
            f"{END_MARKER}\n"
            "# between\n"
            f"{BEGIN_MARKER}\n"
            "second_old: str\n"
            f"{END_MARKER}\n"
            "# footer\n"
        )
        generated = (
            f"{BEGIN_MARKER}\n"
            "first_new: float\n"
            f"{END_MARKER}\n"
            f"{BEGIN_MARKER}\n"
            "second_new: bool\n"
            f"{END_MARKER}\n"
        )
        result = merge_stubs(existing, generated)
        assert "first_new: float" in result
        assert "second_new: bool" in result
        assert "first_old: int" not in result
        assert "second_old: str" not in result
        assert "# header" in result
        assert "# between" in result
        assert "# footer" in result

    def test_half_open_end_without_begin(self):
        # End marker without preceding begin → file-start is implicit begin
        existing = (
            "x: int\n"
            f"{END_MARKER}\n"
            "# manual below\n"
        )
        generated = f"{BEGIN_MARKER}\ny: str\n{END_MARKER}\n"
        result = merge_stubs(existing, generated)
        assert "y: str" in result
        assert "# manual below" in result

    def test_half_open_begin_without_end(self):
        # Begin marker without following end → rest of file is implicit end
        existing = (
            "# header\n"
            f"{BEGIN_MARKER}\n"
            "x: int\n"
            "y: str\n"
            # no end marker — rest of file is the body
        )
        generated = f"{BEGIN_MARKER}\nnew: float\n{END_MARKER}\n"
        result = merge_stubs(existing, generated)
        assert "new: float" in result
        assert "# header" in result

    def test_case_insensitive_markers_recognised(self):
        existing = (
            "# manual\n"
            "# STUBPY: AUTO-GENERATED BEGIN\n"
            "old: int\n"
            "# stubpy: AUTO-GENERATED end\n"
        )
        generated = f"{BEGIN_MARKER}\nnew: str\n{END_MARKER}\n"
        result = merge_stubs(existing, generated)
        assert "new: str" in result
        assert "old: int" not in result
        assert "# manual" in result


# ---------------------------------------------------------------------------
# read_and_merge
# ---------------------------------------------------------------------------

class TestReadAndMerge:
    def test_new_file_returns_wrapped(self, tmp_path):
        out = tmp_path / "mod.pyi"
        result = read_and_merge(out, "x: int\n")
        assert BEGIN_MARKER in result
        assert "x: int" in result
        assert not out.exists()  # function doesn't write

    def test_existing_file_merged(self, tmp_path):
        out = tmp_path / "mod.pyi"
        out.write_text(
            f"# manual\n{BEGIN_MARKER}\nold: int\n{END_MARKER}\n",
            encoding="utf-8",
        )
        result = read_and_merge(out, "new: str\n")
        assert "new: str" in result
        assert "# manual" in result
        assert "old: int" not in result


# ---------------------------------------------------------------------------
# Integration: incremental_update config
# ---------------------------------------------------------------------------

class TestIncrementalUpdateConfig:
    def test_incremental_wraps_and_merges(self, tmp_path):
        src = tmp_path / "mod.py"
        src.write_text("x: int = 1\n")
        pyi = tmp_path / "mod.pyi"

        from stubpy import generate_stub
        from stubpy.context import StubConfig, StubContext

        # First run: creates file with markers
        ctx1 = StubContext(config=StubConfig(incremental_update=True))
        generate_stub(str(src), str(pyi), ctx=ctx1)
        content1 = pyi.read_text()
        assert BEGIN_MARKER in content1

        # Manually add content outside markers
        pyi.write_text("# my custom type\n" + content1)

        # Second run: merges, preserves manual content
        src.write_text("y: str = 'hello'\n")
        ctx2 = StubContext(config=StubConfig(incremental_update=True))
        generate_stub(str(src), str(pyi), ctx=ctx2)
        content2 = pyi.read_text()
        assert "# my custom type" in content2
        assert "y: str" in content2

    def test_no_incremental_overwrites(self, tmp_path):
        src = tmp_path / "mod.py"
        src.write_text("x: int = 1\n")
        pyi = tmp_path / "mod.pyi"
        pyi.write_text("# manual content\n")

        from stubpy import generate_stub
        from stubpy.context import StubConfig, StubContext

        ctx = StubContext(config=StubConfig(incremental_update=False))
        generate_stub(str(src), str(pyi), ctx=ctx)
        content = pyi.read_text()
        assert "# manual content" not in content
        assert BEGIN_MARKER not in content


# ---------------------------------------------------------------------------
# Indentation-aware merge (new in v0.6.0)
# ---------------------------------------------------------------------------

class TestIndentationAwareMerge:
    """Markers inside class/method bodies use the marker's own indentation."""

    def test_markers_inside_class_body(self):
        existing = (
            "class Widget:\n"
            "    title: str\n"
            f"    {BEGIN_MARKER}\n"
            "    width: int\n"
            f"    {END_MARKER}\n"
            "    custom: str\n"
        )
        generated = f"{BEGIN_MARKER}\nwidth: int\ndepth: float\n{END_MARKER}\n"
        result = merge_stubs(existing, generated)
        # Generated content must be re-indented to match class body
        assert "    width: int" in result
        assert "    depth: float" in result
        assert "    custom: str" in result
        import ast
        ast.parse(result)  # must be valid Python

    def test_markers_at_file_level_no_indent_added(self):
        existing = (
            f"{BEGIN_MARKER}\n"
            "x: int\n"
            f"{END_MARKER}\n"
        )
        generated = f"{BEGIN_MARKER}\ny: str\n{END_MARKER}\n"
        result = merge_stubs(existing, generated)
        assert "y: str\n" in result
        # No extra indent at file level
        assert "\n    y:" not in result

    def test_deeply_indented_markers(self):
        """Markers nested 8 spaces deep (inside method body)."""
        existing = (
            "class A:\n"
            "    def f(self) -> None:\n"
            f"        {BEGIN_MARKER}\n"
            "        x: int\n"
            f"        {END_MARKER}\n"
            "        pass\n"
        )
        generated = f"{BEGIN_MARKER}\nx: int\ny: str\n{END_MARKER}\n"
        result = merge_stubs(existing, generated)
        assert "        x: int" in result
        assert "        y: str" in result

    def test_multiple_pairs_with_mixed_indentation(self):
        existing = (
            "class A:\n"
            f"    {BEGIN_MARKER}\n"
            "    x: int\n"
            f"    {END_MARKER}\n"
            "\n"
            f"{BEGIN_MARKER}\n"
            "top_level: bool\n"
            f"{END_MARKER}\n"
        )
        generated_sec1 = "x: int\ny: str\n"
        generated_sec2 = "top_level: bool\nbottom: float\n"
        generated = (
            f"{BEGIN_MARKER}\n{generated_sec1}{END_MARKER}\n"
            f"{BEGIN_MARKER}\n{generated_sec2}{END_MARKER}\n"
        )
        result = merge_stubs(existing, generated)
        # Class-body pair: indented
        assert "    x: int" in result
        assert "    y: str" in result
        # File-level pair: not indented
        assert "\ntop_level: bool" in result
        assert "\nbottom: float" in result

    def test_indented_marker_produces_valid_syntax(self):
        """merge_stubs correctly handles class-body markers with indentation.

        Note: class-body markers work via direct ``merge_stubs`` calls.
        The ``incremental_update`` config option works at the *file level*
        (it wraps the entire generated stub and replaces file-level marker
        regions).  Placing markers inside class bodies is for manual use
        with ``merge_stubs``/``read_and_merge`` directly.
        """
        existing = (
            "class Foo:\n"
            "    title: str  # manual\n"
            f"    {BEGIN_MARKER}\n"
            "    x: int\n"
            f"    {END_MARKER}\n"
        )
        # Only inject class body content (not a full file with headers)
        generated = f"{BEGIN_MARKER}\nx: int\ny: str\n{END_MARKER}\n"
        result = merge_stubs(existing, generated)
        assert "title: str  # manual" in result
        assert "    x: int" in result
        assert "    y: str" in result
        import ast
        ast.parse(result)
