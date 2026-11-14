"""Min/max decimation for display: keeps peaks visible while bounding the point count."""

from __future__ import annotations

import itertools
from typing import Any

import numpy as np
from numpy.typing import NDArray


def minmax_decimate(
    x: NDArray[Any], ys: list[NDArray[Any]], max_points: int
) -> tuple[NDArray[Any], list[NDArray[Any]]]:
    """Reduce to about ``max_points`` samples keeping, per bucket, the samples where the first
    trace reaches its minimum and maximum (same indices for every trace, so traces stay aligned).
    """
    n = x.size
    if n <= max_points or max_points < 4:
        return x, ys
    buckets = max_points // 2
    edges = np.linspace(0, n, buckets + 1, dtype=int)
    ref = ys[0] if ys else x
    keep: list[int] = [0]
    for a, b in itertools.pairwise(edges):
        if b <= a:
            continue
        seg = ref[a:b]
        i_min, i_max = a + int(np.argmin(seg)), a + int(np.argmax(seg))
        keep.extend(sorted((i_min, i_max)))
    keep.append(n - 1)
    idx = np.unique(np.asarray(keep))
    return x[idx], [y[idx] for y in ys]
