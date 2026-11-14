"""Tests for stubpy.core.api: render, generate and check."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

import stubpy
from stubpy.config import Config, Mode
from stubpy.core.results import Report, StubResult
from tests.conftest import write_tree


def _pkg(root: Path, name: str = "mypkg", **files: str) -> Path:
    """Write a package *name* under *root* with ``__init__.py`` plus *files*; return its folder."""
    write_tree(root, {f"{name}/__init__.py": "", **{f"{name}/{k}.py": v for k, v in files.items()}})
    return root / name


class TestRender:
    def test_returns_stub_result(self, tmp_path):
        src = tmp_path / "mod.py"
        src.write_text("def f(x: int) -> str: ...\n")
        result = stubpy.render(src)
        assert isinstance(result, StubResult)
        assert result.ok
        assert "def f(x: int) -> str: ..." in result.text
        assert result.source == src.resolve()
        assert result.output is None

    def test_writes_nothing(self, tmp_path):
        src = tmp_path / "mod.py"
        src.write_text("x: int = 1\n")
        stubpy.render(str(src))
        assert not (tmp_path / "mod.pyi").exists()

    def test_module_name_for_package_file(self, tmp_path):
        pkg = _pkg(tmp_path, "renderpkg_a", core="def f() -> int: ...\n")
        assert stubpy.render(pkg / "core.py").module_name == "renderpkg_a.core"

    def test_dotted_module_name(self, tmp_path, monkeypatch):
        _pkg(tmp_path, "renderpkg_b", core="def g() -> int: ...\n")
        monkeypatch.syspath_prepend(str(tmp_path))
        result = stubpy.render("renderpkg_b.core")
        assert result.ok
        assert "def g() -> int: ..." in result.text
        assert result.module_name == "renderpkg_b.core"

    def test_package_renders_its_init(self, tmp_path):
        pkg = _pkg(tmp_path, "renderpkg_c")
        (pkg / "__init__.py").write_text("VERSION: str = '1'\n")
        assert "VERSION: str" in stubpy.render(pkg).text

    def test_plain_folder_rejected(self, tmp_path):
        with pytest.raises(ValueError, match="folder"):
            stubpy.render(tmp_path)

    def test_glob_must_match_one(self, tmp_path):
        (tmp_path / "a.py").write_text("")
        (tmp_path / "b.py").write_text("")
        with pytest.raises(ValueError, match="matches 2"):
            stubpy.render(str(tmp_path / "*.py"))

    def test_unknown_module(self):
        with pytest.raises(ModuleNotFoundError):
            stubpy.render("no_such_module_for_stubpy_xyz")

    def test_missing_path(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            stubpy.render(tmp_path / "missing.py")

    def test_non_python_file(self, tmp_path):
        data = tmp_path / "data.txt"
        data.write_text("")
        with pytest.raises(ValueError, match="not a Python source"):
            stubpy.render(data)

    def test_compiled_module_not_supported_yet(self):
        with pytest.raises(ValueError, match="no Python source"):
            stubpy.render("_json" if "_json" in sys.builtin_module_names else "math")

    def test_load_failure_is_a_result_not_an_exception(self, tmp_path):
        src = tmp_path / "bad.py"
        src.write_text("raise RuntimeError('boom')\n")
        result = stubpy.render(src)
        assert not result.ok
        assert result.text == ""
        assert any("boom" in d.message for d in result.errors)

    def test_config_is_applied(self, tmp_path):
        src = tmp_path / "mod.py"
        src.write_text("def _hidden() -> None: ...\n")
        assert "_hidden" not in stubpy.render(src).text
        assert "_hidden" in stubpy.render(src, config=Config(include_private=True)).text


class TestGenerate:
    def test_single_file_next_to_source(self, tmp_path):
        src = tmp_path / "mod.py"
        src.write_text("x: int = 1\n")
        report = stubpy.generate(src)
        assert isinstance(report, Report)
        assert report.written == [tmp_path / "mod.pyi"]
        assert "x: int" in (tmp_path / "mod.pyi").read_text()

    def test_single_file_explicit_pyi(self, tmp_path):
        src = tmp_path / "mod.py"
        src.write_text("x: int = 1\n")
        out = tmp_path / "deep" / "custom.pyi"
        stubpy.generate(src, out)
        assert out.read_text() == stubpy.render(src).text

    def test_single_file_into_root(self, tmp_path):
        pkg = _pkg(tmp_path / "src", "genpkg_a", core="x: int = 1\n")
        stubpy.generate(pkg / "core.py", tmp_path / "stubs")
        assert (tmp_path / "stubs" / "genpkg_a" / "core.pyi").exists()
        assert (tmp_path / "stubs" / "genpkg_a" / "__init__.pyi").exists()

    def test_package_mirrors_under_its_name(self, tmp_path):
        pkg = _pkg(tmp_path / "src", "genpkg_b", a="x: int = 1\n")
        write_tree(pkg, {"sub/__init__.py": "", "sub/b.py": "y: str = 'b'\n"})
        out = tmp_path / "stubs"
        report = stubpy.generate(pkg, out)
        assert report.ok
        assert sorted(p.relative_to(out).as_posix() for p in report.written) == [
            "genpkg_b/__init__.pyi", "genpkg_b/a.pyi", "genpkg_b/sub/__init__.pyi", "genpkg_b/sub/b.pyi",
        ]

    def test_plain_folder_mirrors_its_contents(self, tmp_path):
        src = tmp_path / "src"
        _pkg(src, "genpkg_c", a="x: int = 1\n")
        (src / "script.py").write_text("y: int = 2\n")
        out = tmp_path / "stubs"
        stubpy.generate(src, out)
        assert (out / "script.pyi").exists()
        assert (out / "genpkg_c" / "a.pyi").exists()

    def test_placeholder_init_for_excluded_init(self, tmp_path):
        pkg = _pkg(tmp_path, "genpkg_d", a="x: int = 1\n")
        out = tmp_path / "stubs"
        report = stubpy.generate(pkg, out, config=Config(exclude=["__init__.py"]))
        init = out / "genpkg_d" / "__init__.pyi"
        assert init.exists()
        assert init in report.written

    def test_existing_placeholder_kept(self, tmp_path):
        pkg = _pkg(tmp_path, "genpkg_e", a="x: int = 1\n")
        out = tmp_path / "stubs"
        init = out / "genpkg_e" / "__init__.pyi"
        init.parent.mkdir(parents=True)
        init.write_text("# mine\n")
        stubpy.generate(pkg, out, config=Config(exclude=["__init__.py"]))
        assert init.read_text() == "# mine\n"

    def test_glob_target(self, tmp_path):
        (tmp_path / "a.py").write_text("x: int = 1\n")
        (tmp_path / "b.py").write_text("y: int = 1\n")
        (tmp_path / "c.txt").write_text("")
        report = stubpy.generate(str(tmp_path / "*.py"))
        assert sorted(p.name for p in report.written) == ["a.pyi", "b.pyi"]

    def test_several_targets(self, tmp_path):
        (tmp_path / "a.py").write_text("x: int = 1\n")
        (tmp_path / "b.py").write_text("y: int = 1\n")
        report = stubpy.generate([tmp_path / "a.py", str(tmp_path / "b.py")])
        assert len(report.written) == 2

    def test_duplicate_targets_stubbed_once(self, tmp_path):
        (tmp_path / "a.py").write_text("x: int = 1\n")
        report = stubpy.generate([tmp_path, tmp_path / "a.py"])
        assert len(report.results) == 1

    def test_dotted_package_name(self, tmp_path, monkeypatch):
        _pkg(tmp_path / "src", "genpkg_f", a="x: int = 1\n")
        monkeypatch.syspath_prepend(str(tmp_path / "src"))
        out = tmp_path / "stubs"
        report = stubpy.generate("genpkg_f", out)
        assert report.ok
        assert (out / "genpkg_f" / "a.pyi").exists()

    def test_pyi_output_needs_single_file(self, tmp_path):
        pkg = _pkg(tmp_path, "genpkg_g")
        with pytest.raises(ValueError, match="single .py file"):
            stubpy.generate(pkg, tmp_path / "out.pyi")

    def test_config_output_dir_used(self, tmp_path):
        src = tmp_path / "mod.py"
        src.write_text("x: int = 1\n")
        stubpy.generate(src, config=Config(output_dir=str(tmp_path / "stubs")))
        assert (tmp_path / "stubs" / "mod.pyi").exists()

    def test_explicit_output_beats_config(self, tmp_path):
        src = tmp_path / "mod.py"
        src.write_text("x: int = 1\n")
        stubpy.generate(src, tmp_path / "here", config=Config(output_dir=str(tmp_path / "there")))
        assert (tmp_path / "here" / "mod.pyi").exists()
        assert not (tmp_path / "there").exists()

    def test_config_targets_and_modules(self, tmp_path, monkeypatch):
        (tmp_path / "a.py").write_text("x: int = 1\n")
        _pkg(tmp_path / "lib", "genpkg_h", m="y: int = 1\n")
        monkeypatch.syspath_prepend(str(tmp_path / "lib"))
        cfg = Config(targets=[str(tmp_path / "a.py")], modules=["genpkg_h.m"])
        report = stubpy.generate(config=cfg)
        assert sorted(p.name for p in report.written) == ["a.pyi", "m.pyi"]

    def test_no_target_and_nothing_configured(self):
        with pytest.raises(ValueError, match="No target"):
            stubpy.generate()

    def test_failed_module_reported_and_not_written(self, tmp_path):
        pkg = _pkg(tmp_path, "genpkg_i", good="x: int = 1\n", bad="raise RuntimeError('nope')\n")
        out = tmp_path / "stubs"
        report = stubpy.generate(pkg, out, config=Config(mode=Mode.RUNTIME))
        assert not report.ok
        assert [r.source.name for r in report.failed] == ["bad.py"]
        assert "nope" in report.failed[0].errors[0].message
        assert not (out / "genpkg_i" / "bad.pyi").exists()
        assert (out / "genpkg_i" / "good.pyi").exists()

    def test_strict_counts_warnings(self, tmp_path):
        src = tmp_path / "mod.py"
        src.write_text("sentinel = object()\n")
        report = stubpy.generate(src)
        assert report.results[0].warnings
        assert report.ok
        assert not stubpy.generate(src, config=Config(strict=True)).ok

    def test_incremental_merge_keeps_manual_edits(self, tmp_path):
        src = tmp_path / "mod.py"
        src.write_text("x: int = 1\n")
        cfg = Config(incremental=True)
        stubpy.generate(src, config=cfg)
        pyi = tmp_path / "mod.pyi"
        pyi.write_text(pyi.read_text() + "\n# manual\nextra: str\n")
        src.write_text("x: int = 1\ny: str = 'a'\n")
        report = stubpy.generate(src, config=cfg)
        text = pyi.read_text()
        assert "extra: str" in text and "y: str" in text
        assert report.results[0].text == text

    def test_summary_and_iteration(self, tmp_path):
        pkg = _pkg(tmp_path, "genpkg_j", a="x: int = 1\n", b="y: str = 'hi'\n")
        report = stubpy.generate(pkg, tmp_path / "stubs")
        assert report.summary() == "Generated 3 stubs, 0 failed."
        assert len(list(report)) == len(report) == 3
        assert all(isinstance(r, StubResult) for r in report)


class TestCheck:
    def _setup(self, tmp_path):
        pkg = _pkg(tmp_path, "chkpkg", a="x: int = 1\n", b="y: int = 1\n")
        out = tmp_path / "stubs"
        stubpy.generate(pkg, out)
        return pkg, out

    def test_up_to_date(self, tmp_path):
        pkg, out = self._setup(tmp_path)
        report = stubpy.check(pkg, out)
        assert report.ok
        assert report.stale == []
        assert report.written == []
        assert report.summary() == "Checked 3 stubs: 0 stale, 0 failed."

    def test_changed_stub_is_stale(self, tmp_path):
        pkg, out = self._setup(tmp_path)
        (out / "chkpkg" / "a.pyi").write_text("# edited\n")
        report = stubpy.check(pkg, out)
        assert not report.ok
        assert report.stale == [out / "chkpkg" / "a.pyi"]

    def test_changed_source_is_stale(self, tmp_path):
        pkg, out = self._setup(tmp_path)
        (pkg / "b.py").write_text("y: str = 'changed'\n")
        assert stubpy.check(pkg, out).stale == [out / "chkpkg" / "b.pyi"]

    def test_missing_stub_is_stale(self, tmp_path):
        pkg, out = self._setup(tmp_path)
        (pkg / "c.py").write_text("z: int = 1\n")
        assert stubpy.check(pkg, out).stale == [out / "chkpkg" / "c.pyi"]

    def test_writes_nothing(self, tmp_path):
        pkg = _pkg(tmp_path, "chkpkg2", a="x: int = 1\n")
        out = tmp_path / "stubs"
        report = stubpy.check(pkg, out)
        assert not out.exists()
        assert len(report.stale) == 2

    def test_stale_result_text_is_what_generate_writes(self, tmp_path):
        pkg, out = self._setup(tmp_path)
        (out / "chkpkg" / "a.pyi").unlink()
        result = next(r for r in stubpy.check(pkg, out) if r.output == out / "chkpkg" / "a.pyi")
        stubpy.generate(pkg, out)
        assert (out / "chkpkg" / "a.pyi").read_text() == result.text

    def test_incremental_check_respects_manual_edits(self, tmp_path):
        src = tmp_path / "mod.py"
        src.write_text("x: int = 1\n")
        cfg = Config(incremental=True)
        stubpy.generate(src, config=cfg)
        pyi = tmp_path / "mod.pyi"
        pyi.write_text(pyi.read_text() + "\n# manual\n")
        assert stubpy.check(src, config=cfg).ok
        src.write_text("x: int = 2\ny: int = 3\n")
        assert not stubpy.check(src, config=cfg).ok

    def test_failed_module_is_failed_not_stale(self, tmp_path):
        src = tmp_path / "bad.py"
        src.write_text("raise RuntimeError('x')\n")
        report = stubpy.check(src)
        assert report.stale == []
        assert len(report.failed) == 1
        assert not report.ok


class TestReportAndResult:
    def test_empty_summaries(self):
        assert Report().summary() == "Generated 0 stubs, 0 failed."
        assert Report(action="check").summary() == "Checked 0 stubs: 0 stale, 0 failed."

    def test_singular(self):
        assert Report(written=[Path("a.pyi")]).summary() == "Generated 1 stub, 0 failed."

    def test_result_levels(self):
        from stubpy import Diagnostic, Level
        from stubpy.extend import Stage
        warn = Diagnostic(Level.WARNING, Stage.EMIT, "f", "w")
        err = Diagnostic(Level.ERROR, Stage.LOAD, "m", "e")
        assert StubResult("x").ok
        assert StubResult("x", (warn,)).ok
        assert StubResult("x", (warn,)).warnings == [warn]
        result = StubResult("", (warn, err))
        assert not result.ok and result.errors == [err]
        assert Report(results=[StubResult("x", (warn,))], strict=True).failed
