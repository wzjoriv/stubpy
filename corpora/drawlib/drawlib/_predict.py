"""Module-level helpers that methods forward to with their own ``self`` (statsmodels' ``_prediction``)."""
from __future__ import annotations


def predict(self, x=None, transform=True, *, scale: float = 1.0):
    """Predict for *x* with the fitted *self*."""
    return None
