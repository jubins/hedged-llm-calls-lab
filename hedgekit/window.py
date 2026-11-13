"""A rolling window of recent latencies, used to pick the hedge delay."""
from __future__ import annotations

from collections import deque


class RollingQuantile:
    def __init__(self, size: int = 500, default: float = 0.5) -> None:
        self._values: deque[float] = deque(maxlen=size)
        self._default = default

    def add(self, seconds: float) -> None:
        self._values.append(seconds)

    def __len__(self) -> int:
        return len(self._values)

    def quantile(self, q: float, min_samples: int = 50) -> float:
        """Return the q-quantile, or the default until enough samples exist."""
        if len(self._values) < min_samples:
            return self._default
        ordered = sorted(self._values)
        index = min(len(ordered) - 1, int(q * len(ordered)))
        return ordered[index]
