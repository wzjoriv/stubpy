"""``[tool.stubpy.docstrings]``: which hand-written stubs ``stubpy docstrings`` keeps in step with their modules."""
from __future__ import annotations

import difflib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_KEYS = ("packages", "import_root", "overrides")


@dataclass(frozen=True)
class DocstringTargets:
    """The stubs ``stubpy docstrings`` acts on when it gets no STUB or ``-m MODULE``.

    Attributes
    ----------
    packages : tuple of str
        Folders searched for ``*.pyx`` files and compiled modules that have a
        ``.pyi`` of the same stem next to them.
    import_root : str or None
        The folder module names are relative to (``"src"`` for a src layout);
        ``None`` finds it by walking up ``__init__.py`` folders.
    overrides : tuple of (str, str)
        ``(module, stub path)`` pairs, from a mapping, for stubs of another
        name or place; an empty path drops a discovered module.

    Examples
    --------
    >>> DocstringTargets.coerce({"packages": ["mypkg"]}).packages
    ('mypkg',)
    """
    packages: tuple[str, ...] = ()
    import_root: str | None = None
    overrides: tuple[tuple[str, str], ...] = ()

    def __bool__(self) -> bool:
        return bool(self.packages or self.overrides)

    @classmethod
    def coerce(cls, value: Any) -> DocstringTargets:
        """Return *value* (an instance or a ``[tool.stubpy.docstrings]`` mapping) validated."""
        if isinstance(value, cls):
            return value
        if not isinstance(value, Mapping):
            raise TypeError(f"docstrings must be a table, not {type(value).__name__}")
        for key in value:
            name = str(key).replace("-", "_")
            if name not in _KEYS:
                close = difflib.get_close_matches(name, _KEYS, n=1)
                hint = f"; did you mean {close[0]!r}?" if close else ""
                raise ValueError(f"Unknown docstrings option {key!r}{hint}")
        data = {str(k).replace("-", "_"): v for k, v in value.items()}
        packages = data.get("packages", ())
        packages = (packages,) if isinstance(packages, str) else packages
        if not all(isinstance(p, str) for p in packages):
            raise TypeError("docstrings.packages must be a list of strings")
        root = data.get("import_root")
        if root is not None and not isinstance(root, str):
            raise TypeError("docstrings.import_root must be a string")
        overrides = data.get("overrides", {})
        if isinstance(overrides, (list, tuple)):
            overrides = dict(overrides)
        if not isinstance(overrides, Mapping) or not all(
            isinstance(k, str) and isinstance(v, str) for k, v in overrides.items()
        ):
            raise TypeError("docstrings.overrides must map module names to stub paths")
        return cls(tuple(packages), root, tuple(sorted(overrides.items())))

    def resolved(self, base: str) -> DocstringTargets:
        """Return a copy with relative paths joined onto *base* (the folder of the config file)."""
        def join(p: str) -> str:
            return p if not p or Path(p).is_absolute() else str(Path(base) / p)

        return DocstringTargets(
            tuple(join(p) for p in self.packages),
            join(self.import_root) if self.import_root is not None else None,
            tuple((m, join(s)) for m, s in self.overrides),
        )
