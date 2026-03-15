"""
stubpy.generator
================

Top-level orchestrator for a complete stub-generation run.

This module exposes two public functions:

- :func:`collect_classes` — gathers classes from a loaded module in
  source-definition order.
- :func:`generate_stub` — the main entry point that sequences all
  pipeline stages and writes the ``.pyi`` file.
"""
from __future__ import annotations

import inspect
import types as _builtin_types
from pathlib import Path

from .aliases import build_alias_registry
from .context import StubContext
from .emitter import generate_class_stub
from .imports import (
    collect_cross_imports,
    collect_typing_imports,
    scan_import_statements,
)
from .loader import load_module


def collect_classes(
    module: _builtin_types.ModuleType,
    module_name: str,
) -> list[type]:
    """Return all classes *defined* in *module*, sorted by source-line order.

    Uses :func:`inspect.getmembers` filtered to classes whose
    ``__module__`` matches *module_name*, so only classes defined in the
    file itself are included — not classes imported into it.

    Parameters
    ----------
    module : types.ModuleType
        The loaded module returned by :func:`~stubpy.loader.load_module`.
    module_name : str
        Synthetic name assigned to the module by
        :func:`~stubpy.loader.load_module` (e.g.
        ``"_stubpy_target_graphics"``).

    Returns
    -------
    list of type
        Classes sorted by their first source line, mirroring source order.

    Examples
    --------
    >>> # Given shapes.py defining Shape, Circle, Rectangle in that order:
    >>> module, path, name = load_module("shapes.py")    # doctest: +SKIP
    >>> [c.__name__ for c in collect_classes(module, name)]  # doctest: +SKIP
    ['Shape', 'Circle', 'Rectangle']
    """
    classes: list[type] = []
    for _, obj in inspect.getmembers(module, inspect.isclass):
        if obj.__module__ == module_name:
            classes.append(obj)

    def _source_line(c: type) -> int:
        try:
            return inspect.getsourcelines(c)[1]
        except Exception:
            return 0

    return sorted(classes, key=_source_line)


def generate_stub(filepath: str, output_path: str | None = None) -> str:
    """Generate a ``.pyi`` stub file for the Python source at *filepath*.

    Runs the full pipeline in sequence:

    1. **Load** — import the source file as a live module.
    2. **Scan imports** — parse AST to build a ``{name: stmt}`` map.
    3. **Build alias registry** — discover type-alias sub-modules.
    4. **Collect classes** — gather classes in source order.
    5. **Emit stubs** — generate class and method stubs.
    6. **Assemble header** — collect used ``typing`` names, type-module
       imports, and cross-file class imports.
    7. **Write** — write the complete ``.pyi`` to *output_path*.

    A fresh :class:`~stubpy.context.StubContext` is created for every
    call, making this function fully re-entrant.

    Parameters
    ----------
    filepath : str
        Path to the ``.py`` source file. Relative paths are resolved
        against the current working directory.
    output_path : str, optional
        Where to write the ``.pyi`` file. Defaults to the same directory
        and stem as *filepath* with a ``.pyi`` extension.

    Returns
    -------
    str
        Full stub content as a string, identical to what is written to disk.

    Raises
    ------
    FileNotFoundError
        If *filepath* does not exist.
    ImportError
        If the source file cannot be loaded as a module.

    See Also
    --------
    stubpy.loader.load_module : Stage 1 — module loading.
    stubpy.aliases.build_alias_registry : Stage 3 — alias discovery.
    stubpy.emitter.generate_class_stub : Stage 5 — stub emission.

    Examples
    --------
    >>> from stubpy import generate_stub
    >>> content = generate_stub("mypackage/shapes.py")  # doctest: +SKIP
    >>> content.splitlines()[0]  # doctest: +SKIP
    'from __future__ import annotations'

    >>> # Write to a custom path
    >>> content = generate_stub(  # doctest: +SKIP
    ...     "mypackage/shapes.py",
    ...     "out/shapes.pyi",
    ... )
    """
    module, path, module_name = load_module(filepath)
    source     = path.read_text(encoding="utf-8")
    import_map = scan_import_statements(source)

    ctx = StubContext()
    build_alias_registry(module, import_map, ctx)

    classes = collect_classes(module, module_name)
    body    = "\n\n".join(generate_class_stub(cls, ctx) for cls in classes)

    typing_names = collect_typing_imports(body)
    header_lines = ["from __future__ import annotations"]

    if typing_names:
        header_lines.append(f"from typing import {', '.join(typing_names)}")

    for alias, import_stmt in sorted(ctx.used_type_imports.items()):
        if import_stmt and f"{alias}." in body:
            header_lines.append(import_stmt)

    cross_imports = collect_cross_imports(module, module_name, body, import_map)
    for stmt in sorted(cross_imports):
        header_lines.append(stmt)

    header_lines.append("")
    content = "\n".join(header_lines) + "\n" + body + "\n"

    out = Path(output_path) if output_path else path.with_suffix(".pyi")
    out.write_text(content, encoding="utf-8")
    return content
