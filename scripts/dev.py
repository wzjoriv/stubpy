"""The project's developer commands (scripts/devkit + the tools listed in pyproject [tool.devkit]).

python scripts/dev.py --help
"""

from devkit import make_app

app = make_app()

if __name__ == "__main__":
    app()
