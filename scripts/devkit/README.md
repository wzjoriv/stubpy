# devkit

Project-agnostic developer tools (check, docs, build / release, licences, diagrams, test tiers, bench,
pyi) behind one typer app. Shared between projects: **copy this folder verbatim**; never edit it in a
project. What is a project's own goes outside it:

- settings: `[tool.devkit.<tool>]` tables in the project's `pyproject.toml` (a tool is offered only when
  its table exists);
- the project's own commands: `[tool.devkit] tools = ["module:attribute", ...]` (a typer app becomes a
  command group, a function a command), modules in `scripts/`;
- steps run before a command (`before`, `hooks`): `"module:function"` strings in those tables.

`scripts/dev.py` is only:

```python
from devkit import make_app

app = make_app()

if __name__ == "__main__":
    app()
```

The canonical copy is juam-sim's `scripts/devkit`; a change made there is copied to the other projects
(Larp, Larp2).
