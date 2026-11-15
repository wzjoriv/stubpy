"""Thai and Lao shaping: SARA AM decomposition with NIKHAHIT reordering."""
from __future__ import annotations

import unicodedata

from ._base import Shaper

SARA_AM = {0x0E33: (0x0E4D, 0x0E32), 0x0EB3: (0x0ECD, 0x0EB2)}
ABOVE_MARK_CATEGORY = "Mn"


class ThaiShaper(Shaper):
    """Thai and Lao: SARA AM becomes NIKHAHIT + SARA AA, NIKHAHIT moving before preceding above marks."""

    def preprocess(self, cps: list[int]) -> tuple[list[int], list[int]]:
        out: list[int] = []
        clusters: list[int] = []
        for i, cp in enumerate(cps):
            parts = SARA_AM.get(cp)
            if parts is None:
                out.append(cp)
                clusters.append(i)
                continue
            nikhahit, aa = parts
            k = len(out)
            while k > 0 and unicodedata.category(chr(out[k - 1])) == ABOVE_MARK_CATEGORY:
                k -= 1
            cluster = clusters[k - 1] if k > 0 else i
            out.insert(k, nikhahit)
            clusters.insert(k, cluster)
            for j in range(k, len(clusters)):
                clusters[j] = cluster
            out.append(aa)
            clusters.append(cluster)
        return out, clusters
