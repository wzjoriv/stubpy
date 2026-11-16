"""Build script for the svgraster native modules; each one is optional.

OpenMP is tried first and dropped when it fails; set SVGRASTER_NO_OPENMP=1 to
build without it. Compilation is single-threaded.
"""
import os
import sys

from setuptools import Extension, setup
from setuptools.command.build_ext import build_ext
from setuptools.errors import CCompilerError, CompileError, ExecError, LinkError, PlatformError

PACKAGE = "svgraster"
MSVC = sys.platform == "win32"
USE_OPENMP = os.environ.get("SVGRASTER_NO_OPENMP", "") in ("", "0")
OPENMP_COMPILE = ["/openmp"] if MSVC else ["-fopenmp"]
OPENMP_LINK = [] if MSVC else ["-fopenmp"]
BUILD_ERRORS = (CCompilerError, CompileError, ExecError, LinkError, PlatformError, ValueError)


def _src(name):
    return os.path.join(PACKAGE, name)


def _warn(msg):
    print(f"{PACKAGE}: {msg}", file=sys.stderr)


def _openmp(ext):
    if USE_OPENMP:
        ext.extra_compile_args = list(ext.extra_compile_args or []) + OPENMP_COMPILE
        ext.extra_link_args = list(ext.extra_link_args or []) + OPENMP_LINK
        ext.openmp = True
    return ext


def collect():
    exts = [_openmp(Extension(f"{PACKAGE}._scanline", [_src("_scanline.c")],
                              extra_compile_args=[] if MSVC else ["-std=c99"]))]
    try:
        from Cython.Build import cythonize

        exts += cythonize(
            [Extension(f"{PACKAGE}._codec", [_src("_codec.pyx")]),
             _openmp(Extension(f"{PACKAGE}._pattern", [_src("_pattern.pyx")]))],
            compiler_directives={"language_level": 3}, quiet=True, nthreads=0,
        )
    except ImportError:
        _warn("Cython not installed; skipping _codec and _pattern")
    try:
        from pybind11.setup_helpers import Pybind11Extension

        exts.append(Pybind11Extension(f"{PACKAGE}._filters", [_src("_filters.cpp")], cxx_std=17))
    except ImportError:
        _warn("pybind11 not installed; skipping _filters")
    try:
        import nanobind

        src_dir = nanobind.source_dir()
        robin_map = os.path.join(os.path.dirname(src_dir), "ext", "robin_map", "include")
        flags = ["/std:c++17", "/EHsc", "/bigobj", "/permissive-"] if MSVC else ["-std=c++17", "-fvisibility=hidden"]
        exts.append(Extension(
            f"{PACKAGE}._composite",
            [_src("_composite.cpp"), _src("_native/nb_runtime.cpp")],
            include_dirs=[nanobind.include_dir(), robin_map, src_dir],
            define_macros=[("NDEBUG", "1")],
            extra_compile_args=flags,
            language="c++",
        ))
    except ImportError:
        _warn("nanobind not installed; skipping _composite")
    return exts


class OptionalBuildExt(build_ext):
    """build_ext that retries without OpenMP and skips extensions that fail."""

    def build_extension(self, ext):
        try:
            return super().build_extension(ext)
        except BUILD_ERRORS as exc:
            if not getattr(ext, "openmp", False):
                return _warn(f"failed to build {ext.name}: {exc}; continuing without it")
            _warn(f"failed to build {ext.name} with OpenMP ({exc}); retrying without it")
        ext.extra_compile_args = [a for a in ext.extra_compile_args if a not in OPENMP_COMPILE]
        ext.extra_link_args = [a for a in ext.extra_link_args if a not in OPENMP_LINK]
        try:
            super().build_extension(ext)
        except BUILD_ERRORS as exc:
            _warn(f"failed to build {ext.name}: {exc}; continuing without it")


setup(ext_modules=collect(), cmdclass={"build_ext": OptionalBuildExt})
