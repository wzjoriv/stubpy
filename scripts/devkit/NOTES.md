# Check

`python scripts/dev.py check` runs the steps of a project in order and exits 1 when any fails: `ruff check`,
pytest, a Sphinx build with warnings as errors, then the project's own check functions. Every step runs even
when an earlier one failed; the summary names the failures. `--no-docs` skips the docs build.

```toml
[tool.devkit.check]
lint = ["mypkg", "scripts", "tests"]   # ruff check these paths ([] or absent: no lint step)
tests = ["-q"]                         # pytest arguments (absent: no test step; [] runs pytest bare)
docs = "docs"                          # Sphinx source folder, built with -W (absent: no docs step)
docs_out = "docs/_build/html"          # where the docs check builds
hooks = ["mypkg_tools.i18n:check"]     # own checks: "module:function" returning a list of problems ([] = fine)
```

# Docs

`python scripts/dev.py docs` builds the HTML docs with Sphinx after the project's own steps (generated tables,
for example). A failing step is reported and the build goes on with the files as they are. Options: `--clean`
(rebuild every page), `--open` (open the result), `--no-steps` (skip the steps).

```toml
[tool.devkit.docs]
source = "docs"                              # Sphinx source folder
out = "docs/_build/html"                     # HTML output
before = ["mypkg_tools.tables:refresh"]      # "module:function" run first, in order
```

# Build and release

`python scripts/dev.py build` runs PyInstaller on the spec; the user files listed in `keep` that sit next to
an earlier build are moved aside and put back afterwards (also when the build fails). `release` zips the
build without those files. Needs `pyinstaller` in the environment.

```toml
[tool.devkit.build]
spec = "packaging/mypkg.spec"                # PyInstaller spec (required)
dist = "dist/mypkg"                          # folder the spec builds (required)
keep = ["mypkg.toml", "cache"]               # user files next to the executables: kept through builds, left out of the zip
zip = "mypkg-{version}-{os}.zip"             # zip name; {version}, {os} (windows / macos / linux)
version = "mypkg:__version__"                # "module:attribute" for {version} when [project] has no static version
before = ["mypkg_tools.i18n:compile_all"]    # run before PyInstaller (--no-steps skips them)
```

# Licenses

`python scripts/dev.py licenses` downloads the licence text of every catalogue entry into `<id>.txt` files
(`--all` downloads again, otherwise only the missing ones). Ship the folder as package data. The catalogue is
a TOML file of arrays of tables, each entry with an `id` and a `text` (a plain-text URL). Exit 1 when a
download fails.

```toml
[tool.devkit.licenses]
catalogue = "mypkg/about/licenses.toml"      # TOML with [[any-kind]] tables holding id and text (required)
out = "mypkg/about/licenses"                 # folder of the <id>.txt files (required)
user_agent = "mypkg-dev (https://example.org)"   # HTTP User-Agent of the downloads
```

# Diagrams

`python scripts/dev.py diagrams` turns each `<images>/<name>.tex` into `<name>.svg` next to it: `latex`, then
`dvisvgm` with the text as outlines, so it looks the same in every browser. The SVGs are committed, so building
the docs needs no LaTeX. Each `.tex` must be a whole standalone document (`\documentclass{standalone}` ...
`\begin{document}` tikzpicture `\end{document}`). Needs `latex` and `dvisvgm` (TeX Live, MiKTeX).

```toml
[tool.devkit.diagrams]
images = "docs/_static/images"               # folder of the .tex files, SVGs written beside them
```

# Stub

Stubs come from [stubpy](https://pypi.org/project/stubpy/) (`pip install stubpy`, in the dev extra); devkit
runs `python -m stubpy ...` from the repository root. stubpy reads its own `[tool.stubpy]` table, including
`[tool.stubpy.docstrings]` (`packages`, `import_root`, `overrides`); no mode flag is passed. Without stubpy
installed the commands print "pip install stubpy (add it to your dev extra)" and exit 2.

Commands:

- `stub generate`: `stubpy generate <targets> [-o output] <args>`.
- `stub check`: `stubpy check --diff ...`; exit 1 when a stub is stale.
- `stub docstrings sync|check|list`: copy docstrings of compiled modules (Cython etc.) into hand-written
  stubs; `check` exits 1 when one is out of date. Extra arguments (stub files, folders, `-m module`) go to
  stubpy; with none, `docstring_args` and then stubpy's own configuration apply. `list` needs a stubpy that
  has it; older ones run `check`.

```toml
[tool.devkit.stub]
targets = ["mypkg"]                          # TARGET arguments of generate / check (absent: stubpy's configured targets)
output = ""                                  # -o: stub root folder ("" : stubpy's output_dir, else next to the sources)
args = []                                    # extra stubpy CLI flags for generate / check, e.g. ["--exclude", "tests/*"]
docstring_args = []                          # default arguments of `stub docstrings ...`, e.g. ["mypkg/_native.pyi"]
```

# Tiers

`python scripts/dev.py test [tier] [-- pytest args]` runs a named pytest configuration with the output shown and
written to `<log_dir>/<tier>-<YYYYmmdd-HHMMSS>.log`. A run is
`systemd-run --user --scope -q -p MemoryMax=<cap> nice -n <nice> <runner> <args> <extra>` with `PYTHONPATH`
unset (stray paths break pytest; `--keep-pythonpath` keeps yours) and `OMP_NUM_THREADS` set. Without a working
`systemd-run --user` (Windows, macOS, containers) the cap is skipped, without `nice` the priority. The exit code
is pytest's (of a multi-part tier: the first failing part's). `--dry-run` prints the commands, `--no-cap`
skips the cap.

```toml
[tool.devkit.tiers]
default = "quick"                            # tier run without a name (default: the first)
log_dir = "build/test-logs"                  # one log file per run
memory_max = "8G"                            # systemd MemoryMax for every tier ("" or absent: no cap)
nice = 10                                    # nice -n (0: none)
omp_threads = 4                              # OMP_NUM_THREADS (0: leave unset)
runner = ["{python}", "-m", "pytest"]        # command before the args; {python} is this interpreter

[tool.devkit.tiers.quick]                    # a tier: pytest args, or parts
help = "Every fast test."                    # shown in `dev.py test --help`
args = ["tests", "-n", "2", "-m", "not slow"]
memory_max = "14G"                           # any default above can be overridden per tier
env = {MY_FLAG = "1"}                        # added to the environment

[tool.devkit.tiers.full]
help = "Everything, in two runs."
parts = ["quick", "slow"]                    # other tiers (with args) run one after another
```

# Bench

`python scripts/dev.py bench A B [--rounds N] [--warmup N] [--out file.json] [--keep] [-v] -- <command>` runs
one benchmark command against two checkouts alternately (A, B, A, B, ...), so drift on the machine hits both
alike, then prints best-of per key and the B/A ratios. A and B are folders (already built) or git refs, checked
out into a temporary worktree, built with `build`, and removed afterwards. Each run starts in the repository
root with `PYTHONPATH` set to the checkout and `DEVKIT_CHECKOUT` too; in the command `{python}` is this
interpreter and `{checkout}` the side's folder.

The benchmark prints one line per measurement, `<key>: <number> <unit>` (unit ns, us, µs, ms or s; shown in ms,
lower is better), for example `plan N=256: 41.3 ms`; other lines are ignored.

```toml
[tool.devkit.bench]
rounds = 5                                   # A/B pairs (--rounds)
build = ["{python}", "setup.py", "build_ext", "--inplace"]   # run in a ref's temporary worktree
keep_pythonpath = false                      # true: append your PYTHONPATH after the checkout
omp_threads = 4                              # OMP_NUM_THREADS of the runs (0: inherit)
pattern = '^\s*(?P<key>[^:]+?)\s*:\s*(?P<value>[-+0-9.eE]+)\s*(?P<unit>ms)\s*$'   # custom measurement line (groups key, value, optional unit)
```

# Version

`python scripts/dev.py version show` prints the version. `version bump major|minor|patch` and
`version set X.Y.Z` rewrite `__version__ = "..."` in `file` and, in each `also` file, the literal `pattern`
with `{version}` replaced by the old and new version. Only plain `X.Y.Z` is accepted: dirty, pre-release,
`v`-prefixed or partial versions are refused, as is a file that does not contain the expected text. Nothing is
written unless every file checks out. `--dry-run` shows the changes. No git tag is created; the tag command
is printed.

```toml
[tool.devkit.version]
file = "mypkg/__init__.py"                   # module holding __version__ = "X.Y.Z" (required)
tag = "v{version}"                            # tag name printed after a bump ("{version}" for no prefix)
also = [                                     # other places repeating the version
  {file = "README.md", pattern = "rev: {version}"},   # literal text, {version} is the number
]
```

# Notebooks

`python scripts/dev.py notebooks build` turns every example script into a Jupyter notebook next to it (or in
`out`) and runs it, so the notebook shows the results on GitHub without anyone running it. Scripts stay plain
Python and remain the only source:

- the module docstring becomes the first markdown cell;
- `# %%` starts a code cell (text after the marker becomes a comment on the cell's first line);
- `# %% [markdown]` starts a markdown cell written as `#` comments;
- a script without markers becomes one code cell; files starting with `_` are skipped.

A cell that should show a picture ends with an expression (`doc`), which a plain `python script.py` run
ignores. Notebooks run in a temporary folder, so files the examples save do not land in the repository.
`build name ...` rebuilds only those scripts; `--no-run` writes the cells without outputs.
`notebooks check` exits 1 when a notebook is missing or its cells differ from its script. It compares
cell sources only, not outputs, so it is fast and gives the same answer on every OS; use it in CI.
Needs `nbformat`, `nbclient` and `ipykernel` (`dev.py deps` lists them).

```toml
[tool.devkit.notebooks]
source = "examples"        # folder of the scripts
out = "examples"           # where the .ipynb files go (default: the source folder)
pattern = "*.py"           # which scripts
exclude = ["helpers.py"]   # file names to skip
execute = true             # run notebooks on build (false: cells only)
timeout = 600              # seconds per cell
kernel = "python3"         # Jupyter kernel name
```

# Logo

`python scripts/dev.py logo build` renders every logo asset from one svgwriter function and writes it to
`output`; nothing is committed or published. `--check` writes nothing and exits 1 when a file on disk differs
from what would be generated (svgwriter output is deterministic, so this is the "are the assets stale" check
for CI). The project root is put on `sys.path` to import `source`; without svgwriter installed the command
prints "pip install svgwriter (add it to your dev extra)" and exits 2.

`source` is `"package.module:function"`, a function `logo(**variant)` returning an `svgwriter.Document`. The
variant `default` (no keyword arguments) always exists; every other variant adds `logo-<name>` files.

Per variant: `logo.svg`, `logo-<size>.png` for each size, `logo.ico` (the sizes up to 256) and `logo.icns`.
The default variant also gets `favicon.ico` (16, 32, 48), `apple-touch-icon.png` (180) and `site.webmanifest`,
whose icons list points at `logo-192.png` and `logo-512.png` (added to the PNGs when the sizes lack them).

```toml
[tool.devkit.logo]
source = "mypkg.logo:logo"                   # "module:function" returning an svgwriter Document (required)
variants = { dark = { theme = "dark" } }     # name -> keyword arguments of the function
output = "docs/_static/logo"                 # output folder
png_sizes = [16, 32, 48, 64, 128, 256, 512]  # square PNG sizes
formats = ["svg", "png", "ico", "icns", "favicon", "webmanifest"]   # which assets to write (default: all)
presets = ["web"]                           # any of web, ios, android, desktop; --preset overrides
```

Presets: `web` is the set above. `ios` writes `ios/AppIcon.appiconset/` (every iPhone and iPad size plus
the 1024 px marketing icon, on white as the App Store requires, with Xcode's `Contents.json`). `android`
writes `android/mipmap-<density>/ic_launcher.png` for mdpi to xxxhdpi and a 512 px `play-store-icon.png`.
`desktop` writes `desktop/` with an ICO, an ICNS and Linux `hicolor/<n>x<n>/apps/logo.png` sizes plus the
scalable SVG. Platform presets use the default variant.

# Deps

`python scripts/dev.py deps` is always available. It lists the requirements of the enabled tools (the
`[tool.devkit.*]` tables present) next to the core's, the external programs they call, and a ready-to-paste
dev extra (deduplicated, sorted, always with `typer` and the `tomli` marker). `--install` runs
`python -m pip install ...` with the current interpreter. `--check` exits 1 and lists the requirements whose
package is not installed (`importlib.metadata`; a `python_version` marker that does not apply is skipped).
External programs missing from `PATH` are reported on stderr.

| Tool | Requirements | External |
| --- | --- | --- |
| core | `typer>=0.12`, `tomli` (Python 3.10) | |
| `check` | `ruff>=0.6`, `pytest>=7.0`, `sphinx` when `docs` is set | |
| `docs` | `sphinx` | |
| `build` | `pyinstaller` | |
| `licenses` | | |
| `diagrams` | | `latex`, `dvisvgm` |
| `stub` | `stubpy` | |
| `tiers` | `pytest>=7.0` | |
| `bench` | | `git` |
| `version` | | |
| `logo` | `svgwriter` | |

Each tool module declares `REQUIRES` and `EXTERNAL` (tuples of strings); `check` also has `requires(cfg)` for
the ones that depend on its table. Docs extras and `pytest-xdist` are the project's to add.

```toml
dev = ["pyinstaller", "pytest>=7.0", "ruff>=0.6", "sphinx", "stubpy", "tomli; python_version < '3.11'", "typer>=0.12"]
```

# Internals

- `paths.py`: the repository root is the nearest folder above `scripts/devkit` holding a `pyproject.toml`
  (found from the file's location, not the working directory); `SCRIPTS` is the folder of `dev.py`.
- `config.py`: reads `pyproject.toml` (`tomli` on Python 3.10); `[tool.devkit]` holds one table per tool, and
  a tool is offered only when its table exists. A wrong value raises `ConfigError`, shown as
  `devkit: <message>` with exit 2.
- `hooks.py`: a hook is a `"module:function"` string importable from `scripts/`, resolved when the tool runs.
- `__init__.py`: `make_app()` registers the general tools, then the project's own; consoles that cannot encode
  a character print `?` instead of failing.
- `[tool.devkit.pyi]` was renamed `[tool.devkit.stub]`; the old name is reported as an error.

```toml
[tool.devkit]
tools = ["mypkg_tools:app"]                  # the project's own tools, see Extensions
```

# Extensions

A project adds its own commands and steps without touching `scripts/devkit`.

## Own commands

Put them in `scripts/mypkg_tools/` (a package) or `scripts/mypkg_tools.py` and list them:

```toml
[tool.devkit]
tools = ["mypkg_tools:app", "mypkg_tools.extra:report"]   # "module:attribute", importable from scripts/
```

- A `typer.Typer` becomes a command group, named by its `name=` or else by the module's top-level package
  (`mypkg_tools` becomes `mypkg-tools`).
- A plain function becomes one command, named by the function (`_` as `-`).

Conventions:

- `add_completion=False` and `no_args_is_help=True` on every Typer.
- The Typer's `help` is the module docstring (`help=__doc__`), written as the devkit modules are.
- Command names in kebab-case (`@app.command("sync-translations")`).
- Exit non-zero (`raise typer.Exit(1)`) when something fails.

```python
"""
Project tools: refresh the generated tables and check the translations.
"""

import typer

app = typer.Typer(name="mypkg", help=__doc__, add_completion=False, no_args_is_help=True)


@app.command("refresh-tables")
def refresh_tables() -> None:
    """Rewrite the generated tables."""
    typer.echo("done")
```

## Hooks

A hook is a `"module:function"` string, importable from `scripts/`, called with no arguments.

- `before = [...]` in `[tool.devkit.docs]` and `[tool.devkit.build]`: run first, in order (`--no-steps`
  skips them). A docs step that fails is reported and the build goes on; a build step that fails stops it.
- `hooks = [...]` in `[tool.devkit.check]`: each returns a list of problem lines (empty means fine); any
  problem fails `check`.

```toml
[tool.devkit.docs]
before = ["mypkg_tools.tables:refresh"]

[tool.devkit.check]
hooks = ["mypkg_tools.i18n:check"]
```
