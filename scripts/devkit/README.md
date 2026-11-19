# devkit

Project-agnostic developer tools (lint, test, docs, build, licences, diagrams, stubs, test tiers, benchmarks,
versioning, requirements) behind one typer app, configured from the `[tool.devkit.*]` tables of a project's `pyproject.toml`.
A tool is offered only when its table exists.

The canonical copy lives in `E:\Engineering\Libraries\Python\devkit`; projects copy it verbatim into
`scripts/devkit` and never edit the copy; changes go to the canonical copy first.

`scripts/dev.py` is only:

```python
from devkit import make_app

app = make_app()

if __name__ == "__main__":
    app()
```

Run `python scripts/dev.py --help`.

## Dev extra

```toml
dev = ["typer>=0.12", "tomli; python_version < '3.11'", "ruff>=0.6", "pytest>=7.0", "stubpy"]
```

plus per-tool extras: `sphinx` for docs, `pyinstaller` for build, `pytest-xdist` for tiers using `-n`.
Run `python scripts/dev.py deps` to get the list for the tools a project enables.

## Tools

Each tool's commands and a full `pyproject.toml` snippet are in [NOTES.md](NOTES.md).

| Table | Commands | Does |
| --- | --- | --- |
| `check` | `check` | lint, tests, docs build and own checks |
| `docs` | `docs` | build the Sphinx docs |
| `build` | `build`, `release` | PyInstaller build and a zip of it |
| `licenses` | `licenses` | download licence texts |
| `diagrams` | `diagrams` | TikZ to SVG |
| `stub` | `stub generate`, `stub check`, `stub docstrings sync\|check\|list` | stubpy: write, check and docstring-sync stubs |
| `tiers` | `test` | named, memory-capped, logged test runs |
| `bench` | `bench` | interleaved A/B benchmarks |
| `version` | `version show`, `version bump`, `version set` | `__version__` and the files that repeat it |
| (always) | `deps` | requirements of the enabled tools: dev extra, `--install`, `--check` |

## Principles

- **Local by default.** Every tool works on the local checkout only: nothing is committed, tagged, pushed,
  uploaded or published unless the command exists for that purpose (`licenses` downloads licence texts;
  `version` only rewrites files and prints the tag command for you to run).
- **Internal names start with `_`** (`_file.py`, `_folder/`); everything else is the tool's public surface.
