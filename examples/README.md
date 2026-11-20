# Examples

Run any script with `python examples/NN_topic.py` (files go to a temp folder, or to `STUBPY_EXAMPLES_OUT` if set), or open its notebook.

| # | Example | Notebook | What it shows | Key APIs |
|---|---|---|---|---|
| 01 | [01_render_a_module.py](01_render_a_module.py) | [01_render_a_module.ipynb](01_render_a_module.ipynb) | Build the stub of one module without writing it. | `render` |
| 02 | [02_forwarded_kwargs.py](02_forwarded_kwargs.py) | [02_forwarded_kwargs.ipynb](02_forwarded_kwargs.ipynb) | A class forwarding `**kwargs` to its base: the stub lists the parameters they stand for. | `render` |
| 03 | [03_generate_a_package.py](03_generate_a_package.py) | [03_generate_a_package.ipynb](03_generate_a_package.ipynb) | Write the stubs of a whole package and read the report. | `generate`, `Report` |
| 04 | [04_check_for_stale_stubs.py](04_check_for_stale_stubs.py) | [04_check_for_stale_stubs.ipynb](04_check_for_stale_stubs.ipynb) | Detect stubs that no longer match their source, as CI does. | `check`, `Report.stale` |
| 05 | [05_config_file.py](05_config_file.py) | [05_config_file.ipynb](05_config_file.ipynb) | Read `[tool.stubpy]` from a `pyproject.toml` and generate from it. | `load_config`, `Config` |
| 06 | [06_hints_for_compiled.py](06_hints_for_compiled.py) | [06_hints_for_compiled.ipynb](06_hints_for_compiled.ipynb) | Give a JIT-wrapped callable a signature the stub can use. | `hint.signature`, `hint.returns` |
| 07 | [07_compiled_from_pyx.py](07_compiled_from_pyx.py) | [07_compiled_from_pyx.ipynb](07_compiled_from_pyx.ipynb) | Stub a Cython extension from its `.pyx`, with no compiler. | `generate` |
| 08 | [08_sync_docstrings.py](08_sync_docstrings.py) | [08_sync_docstrings.ipynb](08_sync_docstrings.ipynb) | Copy runtime docstrings into a hand-written stub. | `sync_docstrings` |

Also here: [pre-commit-config.yaml](pre-commit-config.yaml), the `stubpy-check` pre-commit hook.
