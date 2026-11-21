"""Gamma tables that do not depend on the GPU runtime."""
from __future__ import annotations

import numpy as np

DEFAULT_GAMMA = 2.2


def gamma_table(gamma: float = DEFAULT_GAMMA, size: int = 256) -> np.ndarray:
    """Build a lookup table mapping linear coverage to ``gamma``-encoded values."""
    return np.linspace(0.0, 1.0, size) ** (1.0 / gamma)


class GammaCurve:
    """A reusable gamma curve.

    Parameters
    ----------
    gamma : float
        Exponent of the decoded curve.
    """

    def __init__(self, gamma: float = DEFAULT_GAMMA) -> None:
        self.gamma = gamma

    def encode(self, linear: np.ndarray) -> np.ndarray:
        """Encode linear values."""
        return np.power(linear, 1.0 / self.gamma)
