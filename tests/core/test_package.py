"""Tests for stubpy.core.package.generate_package."""
from __future__ import annotations

from pathlib import Path

from stubpy import generate_package
from stubpy.config import ExecutionMode, StubConfig
from stubpy.core.context import StubContext
from stubpy.core.results import PackageResult


class TestCtxFactoryFileInfo:
    """ctx_factory with (source_path, output_path) signature."""

    def test_no_arg_factory_works(self, tmp_path):
        src = tmp_path / "pkg"
        src.mkdir()
        (src / "__init__.py").write_text("")
        (src / "mod.py").write_text("x: int = 1\n")
        seen = []
        def factory():
            seen.append("called")
            return StubContext()
        result = generate_package(str(src), str(tmp_path / "stubs"), ctx_factory=factory)
        assert len(seen) >= 1
        assert len(result.failed) == 0

    def test_two_arg_factory_receives_paths(self, tmp_path):
        src = tmp_path / "pkg"
        src.mkdir()
        (src / "__init__.py").write_text("")
        (src / "mod.py").write_text("x: int = 1\n")
        received = []
        def factory(source: Path, output: Path):
            received.append((source, output))
            return StubContext()
        generate_package(str(src), str(tmp_path / "stubs"), ctx_factory=factory)
        assert len(received) >= 1
        src_path, out_path = received[0]
        assert str(src_path).endswith(".py")
        assert str(out_path).endswith(".pyi")

    def test_custom_config_per_file(self, tmp_path):
        src = tmp_path / "pkg"
        src.mkdir()
        (src / "__init__.py").write_text("")
        (src / "slow.py").write_text("x: int = 1\n")
        modes = []
        def factory(source: Path, output: Path):
            mode = ExecutionMode.AST_ONLY if "slow" in source.name else ExecutionMode.RUNTIME
            modes.append(mode)
            return StubContext(config=StubConfig(execution_mode=mode))
        generate_package(str(src), str(tmp_path / "stubs"), ctx_factory=factory)
        assert ExecutionMode.AST_ONLY in modes


class TestGeneratePackagePipeline:
    def test_creates_init_pyi_for_subpackages(self, tmp_path):
        pkg = tmp_path / "mypkg"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("")
        sub = pkg / "sub"
        sub.mkdir()
        (sub / "__init__.py").write_text("")
        (sub / "mod.py").write_text("x: int = 1\n")
        out = tmp_path / "stubs"
        result = generate_package(str(pkg), str(out))
        assert len(result.failed) == 0
        assert (out / "sub" / "__init__.pyi").exists()

    def test_exclude_patterns(self, tmp_path):
        pkg = tmp_path / "mypkg"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("")
        (pkg / "secret.py").write_text("SECRET: str = 'x'\n")
        (pkg / "public.py").write_text("PUB: int = 1\n")
        out = tmp_path / "stubs"
        cfg = StubConfig(exclude=["secret.py"])
        generate_package(str(pkg), str(out), config=cfg)
        assert not (out / "secret.pyi").exists()
        assert (out / "public.pyi").exists()

    def test_failed_files_reported(self, tmp_path):
        pkg = tmp_path / "mypkg"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("")
        (pkg / "bad.py").write_text("import __absolutely_nothing_exists__\nraise RuntimeError()\n")
        out = tmp_path / "stubs"
        cfg = StubConfig(execution_mode=ExecutionMode.RUNTIME)
        result = generate_package(str(pkg), str(out), config=cfg)
        assert isinstance(result, PackageResult)

    def test_package_result_summary(self, tmp_path):
        pkg = tmp_path / "mypkg"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("")
        (pkg / "a.py").write_text("x: int = 1\n")
        (pkg / "b.py").write_text("y: str = 'hi'\n")
        out = tmp_path / "stubs"
        result = generate_package(str(pkg), str(out))
        summary = result.summary()
        assert "Generated" in summary
        assert "failed" in summary
