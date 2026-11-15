"""TOML reading via :mod:`tomllib`, :mod:`tomli`, or a minimal fallback parser."""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any


def parse_toml(path: Path) -> dict[str, Any]:
    """Parse *path* as TOML and return the top-level mapping."""
    if sys.version_info >= (3, 11):
        import tomllib
        with open(path, "rb") as fh:
            return tomllib.load(fh)

    try:
        import tomli  # type: ignore[import]
        with open(path, "rb") as fh:
            return tomli.load(fh)
    except ImportError:
        pass

    return minimal_toml_parse(path.read_text(encoding="utf-8"))


def minimal_toml_parse(text: str) -> dict[str, Any]:
    """Parse the TOML subset stubpy needs: sections, strings, booleans and string arrays."""
    result: dict[str, Any] = {}
    current_path: list[str] = []

    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        m = re.match(r"^\[([^\]]+)\]$", line)
        if m:
            current_path = [p.strip() for p in m.group(1).split(".")]
            node = result
            for part in current_path:
                node = node.setdefault(part, {})
            continue

        m = re.match(r'^(\w+)\s*=\s*(.+)$', line)
        if not m:
            continue
        key, raw_val = m.group(1), m.group(2).strip()

        value: Any
        if raw_val in ("true", "True"):
            value = True
        elif raw_val in ("false", "False"):
            value = False
        elif raw_val.startswith('"') and raw_val.endswith('"'):
            value = raw_val[1:-1]
        elif raw_val.startswith("'") and raw_val.endswith("'"):
            value = raw_val[1:-1]
        elif raw_val.startswith("[") and raw_val.endswith("]"):
            value = re.findall(r'["\']([^"\']*)["\']', raw_val[1:-1])
        else:
            continue

        node = result
        for part in current_path:
            node = node.setdefault(part, {})
        node[key] = value

    return result
