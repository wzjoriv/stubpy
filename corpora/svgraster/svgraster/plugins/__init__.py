"""Optional GPU plugins; importing this package needs ``svgraster_gpu``, which is not installed."""
from __future__ import annotations

import svgraster_gpu

DEVICE = svgraster_gpu.default_device()
