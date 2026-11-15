"""Build script for svgraster's optional native layers.

Every extension is optional: a missing toolchain or a failed compile is
reported and skipped. OpenMP is tried first and dropped on failure. Set
``SVGRASTER_SKIP`` to a comma-separated subset of ``capi,cython,pybind11,
nanobind`` to skip layers, and ``SVGRASTER_NO_OPENMP=1`` to build serially.
"""
import os
import sys

from setuptools import Extension, setup
from setuptools.command.build_ext import build_ext
from setuptools.errors import CCompilerError, CompileError, ExecError, LinkError, PlatformError

PACKAGE = "svgraster"
SKIP = {s.strip() for s in os.environ.get("SVGRASTER_SKIP", "").split(",") if s.strip()}
USE_OPENMP = os.environ.get("SVGRASTER_NO_OPENMP", "") in ("", "0")
MSVC = sys.platform == "win32"
OPENMP_COMPILE = ["/openmp"] if MSVC else ["-fopenmp"]
OPENMP_LINK = [] if MSVC else ["-fopenmp"]
BUILD_ERRORS = (CCompilerError, CompileError, ExecError, LinkError, PlatformError, ValueError)


def _src(name):
    return os.path.join(PACKAGE, name)


def _warn(msg):
    print(f"{PACKAGE}: {msg}", file=sys.stderr)


def _with_openmp(ext):
    if USE_OPENMP:
        ext.extra_compile_args = list(ext.extra_compile_args or []) + OPENMP_COMPILE
        ext.extra_link_args = list(ext.extra_link_args or []) + OPENMP_LINK
        ext.svgr_openmp = True
    return ext


def capi_extensions():
    """The CPython C API modules: the scanline filler (OpenMP) and the glyph decoder."""
    flags = [] if MSVC else ["-std=c99"]
    return [
        _with_openmp(Extension(f"{PACKAGE}._scanline", [_src("_scanline.c")], extra_compile_args=list(flags))),
        Extension(f"{PACKAGE}._glyf", [_src("_glyf.c")], extra_compile_args=list(flags)),
    ]


def cython_extensions():
    """The Cython modules: paint servers, patterns (OpenMP), the image codecs and bidi resolution."""
    try:
        from Cython.Build import cythonize
    except ImportError:
        _warn("Cython not installed; skipping _paint, _pattern, _codec and _bidi")
        return []
    exts = [
        _with_openmp(Extension(f"{PACKAGE}._paint", [_src("_paint.pyx")])),
        _with_openmp(Extension(f"{PACKAGE}._pattern", [_src("_pattern.pyx")])),
        Extension(f"{PACKAGE}._codec", [_src("_codec.pyx")]),
        Extension(f"{PACKAGE}._bidi", [_src("_bidi.pyx")]),
    ]
    built = cythonize(exts, compiler_directives={"language_level": 3}, quiet=True, nthreads=0)
    for ext in built:
        ext.svgr_openmp = USE_OPENMP and ext.name not in (f"{PACKAGE}._codec", f"{PACKAGE}._bidi")
    return built


def pybind11_extensions():
    """The pybind11 filter module."""
    try:
        from pybind11.setup_helpers import Pybind11Extension
    except ImportError:
        _warn("pybind11 not installed; skipping _filters")
        return []
    ext = Pybind11Extension(f"{PACKAGE}._filters", [_src("_filters.cpp")], cxx_std=17)
    return [_with_openmp(ext)]


def nanobind_extensions():
    """The nanobind compositing module, compiled with nanobind's runtime sources."""
    try:
        import nanobind
    except ImportError:
        _warn("nanobind not installed; skipping _composite")
        return []
    src_dir = nanobind.source_dir()
    robin_map = os.path.join(os.path.dirname(src_dir), "ext", "robin_map", "include")
    if MSVC:
        cflags = ["/std:c++17", "/EHsc", "/bigobj", "/permissive-"]
    else:
        cflags = ["-std=c++17", "-fvisibility=hidden", "-fno-strict-aliasing"]
    return [
        _with_openmp(Extension(
            f"{PACKAGE}._composite",
            [_src("_composite.cpp"), _src("_native/nb_runtime.cpp")],
            include_dirs=[nanobind.include_dir(), robin_map, src_dir],
            define_macros=[("NDEBUG", "1")],
            extra_compile_args=cflags,
            language="c++",
        ))
    ]


class OptionalBuildExt(build_ext):
    """build_ext that retries without OpenMP and skips extensions that fail."""

    def run(self):
        try:
            super().run()
        except PlatformError as exc:
            _warn(f"no usable compiler ({exc}); skipping all native extensions")

    def build_extension(self, ext):
        try:
            super().build_extension(ext)
            return
        except BUILD_ERRORS as exc:
            if not getattr(ext, "svgr_openmp", False):
                _warn(f"failed to build {ext.name}: {exc}; continuing without it")
                return
            _warn(f"failed to build {ext.name} with OpenMP ({exc}); retrying without it")
        ext.extra_compile_args = [a for a in ext.extra_compile_args if a not in OPENMP_COMPILE]
        ext.extra_link_args = [a for a in ext.extra_link_args if a not in OPENMP_LINK]
        try:
            super().build_extension(ext)
        except BUILD_ERRORS as exc:
            _warn(f"failed to build {ext.name}: {exc}; continuing without it")


def collect():
    """All configured extensions, honouring ``SVGRASTER_SKIP``."""
    builders = {
        "capi": capi_extensions,
        "cython": cython_extensions,
        "pybind11": pybind11_extensions,
        "nanobind": nanobind_extensions,
    }
    exts = []
    for name, builder in builders.items():
        if name in SKIP:
            _warn(f"skipping {name} (SVGRASTER_SKIP)")
            continue
        try:
            exts.extend(builder())
        except Exception as exc:
            _warn(f"could not configure {name} extensions: {exc}")
    return exts


setup(ext_modules=collect(), cmdclass={"build_ext": OptionalBuildExt})
