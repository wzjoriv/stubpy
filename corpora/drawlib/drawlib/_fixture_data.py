"""A generated-test module that reads a data file at import, as statsmodels' result generators do."""
from __future__ import annotations

with open("results/survival_data.csv") as handle:
    ROWS = handle.read().splitlines()


def load(name: str) -> list[str]:
    """The rows of *name*."""
    return ROWS
