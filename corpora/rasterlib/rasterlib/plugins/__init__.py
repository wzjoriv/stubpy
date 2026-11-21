"""Optional GPU plugins; importing this package needs ``rasterlib_gpu``, which is not installed."""
from __future__ import annotations

import rasterlib_gpu

DEVICE = rasterlib_gpu.default_device()
