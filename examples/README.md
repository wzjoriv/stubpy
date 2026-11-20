# Examples

Runnable with `python examples/<name>.py` after `pip install stubpy`; each one works in a temporary folder.

- [`generate_stubs.py`](generate_stubs.py): stub a package whose class forwards `**kwargs` to its base class.
- [`render_and_check.py`](render_and_check.py): render one module, then check a stub for staleness.
- [`config_file.py`](config_file.py): read `[tool.stubpy]` from a `pyproject.toml` with `load_config`.
- [`hints_for_compiled.py`](hints_for_compiled.py): describe a JIT or compiled callable with `hint.signature` and `hint.returns`.
- [`pre-commit-config.yaml`](pre-commit-config.yaml): the `stubpy-check` pre-commit hook.
