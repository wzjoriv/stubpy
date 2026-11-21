"""Level adjustment over numpy, forwarding keyword arguments to third-party callables."""
from __future__ import annotations

import numpy as np


def clamp(coverage: np.ndarray, lo: float = 0.0, hi: float = 1.0, **kwargs) -> np.ndarray:
    """Clamp coverage into ``[lo, hi]``; ``**kwargs`` go to :func:`numpy.clip`."""
    return np.clip(coverage, lo, hi, **kwargs)


def as_coverage(values, **kwargs) -> np.ndarray:
    """Coerce ``values`` to an array; ``**kwargs`` go to :func:`numpy.asarray`."""
    return np.asarray(values, **kwargs)


def scale(coverage: np.ndarray, factor: float, **kwargs) -> np.ndarray:
    """Scale coverage; ``**kwargs`` go to the :data:`numpy.multiply` ufunc."""
    return np.multiply(coverage, factor, **kwargs)
