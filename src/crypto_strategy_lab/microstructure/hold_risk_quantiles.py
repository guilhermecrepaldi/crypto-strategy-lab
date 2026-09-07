"""Exact rolling empirical quantiles for completed hold durations.

This helper is deliberately independent of the replay engine.  Durations are integer
microseconds and all interpolation is performed with :class:`~decimal.Decimal`.
"""

from bisect import bisect_left, bisect_right
from decimal import Decimal

import numpy as np


class RollingQuantiles:
    """Maintain order statistics for a moving half-open range of durations."""

    _REBUILD_THRESHOLD = 4096

    def __init__(self, durations_us: np.ndarray) -> None:
        values = np.asarray(durations_us)
        if values.ndim != 1 or values.dtype != np.int64:
            raise TypeError("durations_us must be a one-dimensional int64 array")
        self.durations_us = values
        self.unique_values, self.inverse_ranks = np.unique(values, return_inverse=True)
        self._tree = np.zeros(self.unique_values.size + 1, dtype=np.int64)
        self._lo = 0
        self._hi = 0

    def _add_rank(self, rank: int, delta: int) -> None:
        index = rank + 1
        while index < self._tree.size:
            self._tree[index] += delta
            index += index & -index

    def _prefix(self, end: int) -> int:
        total = 0
        index = end
        while index:
            total += int(self._tree[index])
            index -= index & -index
        return total

    def _rebuild(self, lo: int, hi: int) -> None:
        counts = np.bincount(self.inverse_ranks[lo:hi], minlength=self.unique_values.size).astype(
            np.int64, copy=False
        )
        self._tree.fill(0)
        for rank, count in enumerate(counts):
            if count:
                self._add_rank(rank, int(count))

    @staticmethod
    def _difference(lo: int, hi: int, other_lo: int, other_hi: int) -> tuple[tuple[int, int], ...]:
        """Return the at-most-two half-open pieces in ``[lo, hi)`` not in other."""
        pieces = []
        if lo < min(hi, other_lo):
            pieces.append((lo, min(hi, other_lo)))
        if max(lo, other_hi) < hi:
            pieces.append((max(lo, other_hi), hi))
        return tuple(pieces)

    def _adjust_index(self, index: int, delta: int) -> None:
        self._add_rank(int(self.inverse_ranks[index]), delta)

    def _adjust_range(self, lo: int, hi: int, delta: int) -> None:
        for index in range(lo, hi):
            self._adjust_index(index, delta)

    def _move(self, lo: int, hi: int) -> None:
        removed = max(0, min(hi, self._hi) - max(lo, self._lo))
        old_count = self._hi - self._lo
        new_count = hi - lo
        changed = old_count + new_count - 2 * removed
        if changed > self._REBUILD_THRESHOLD:
            self._rebuild(lo, hi)
        else:
            for start, end in self._difference(self._lo, self._hi, lo, hi):
                self._adjust_range(start, end, -1)
            for start, end in self._difference(lo, hi, self._lo, self._hi):
                self._adjust_range(start, end, 1)
        self._lo, self._hi = lo, hi

    def _count_le(self, value: int) -> int:
        rank = bisect_right(self.unique_values, value)
        return self._prefix(rank)

    def _kth(self, ordinal: int) -> int:
        target = ordinal + 1
        index = 0
        bit = 1 << (self._tree.size.bit_length() - 1)
        while bit:
            candidate = index + bit
            if candidate < self._tree.size and self._tree[candidate] < target:
                target -= int(self._tree[candidate])
                index = candidate
            bit >>= 1
        return int(self.unique_values[index])

    def _value_at(self, ordinal: int, extra: int | None) -> int:
        if extra is None:
            return self._kth(ordinal)
        less = self._prefix(bisect_left(self.unique_values, extra))
        if ordinal < less:
            return self._kth(ordinal)
        if ordinal == less:
            return extra
        return self._kth(ordinal - 1)

    @staticmethod
    def _interpolate(value0: int, value1: int, fraction: Decimal) -> str:
        micros = Decimal(value0) + (Decimal(value1) - Decimal(value0)) * fraction
        return str(micros / Decimal(1_000_000))

    def quantiles(self, lo: int, hi: int, extra: int | None = None) -> dict[str, str | None]:
        """Return p50/p75/p90/p95 for ``durations_us[lo:hi]`` plus ``extra``."""
        if lo < 0 or hi < lo or hi > self.durations_us.size:
            raise IndexError("invalid contiguous duration range")
        self._move(lo, hi)
        count = hi - lo + (extra is not None)
        if count == 0:
            return {name: None for name in ("p50", "p75", "p90", "p95")}
        result: dict[str, str | None] = {}
        for name, fraction in (
            ("p50", Decimal("0.5")),
            ("p75", Decimal("0.75")),
            ("p90", Decimal("0.9")),
            ("p95", Decimal("0.95")),
        ):
            position = Decimal(count - 1) * fraction
            lower = int(position)
            upper = lower + (position != lower)
            interpolation = position - lower
            left = self._value_at(lower, extra)
            right = self._value_at(upper, extra)
            result[name] = self._interpolate(left, right, interpolation)
        return result
