from decimal import Decimal
from unittest.mock import patch

import numpy as np

from crypto_strategy_lab.microstructure.hold_risk_quantiles import RollingQuantiles


def oracle(values: list[int], extra: int | None = None) -> dict[str, str | None]:
    data = sorted(values + ([] if extra is None else [extra]))
    if not data:
        return {name: None for name in ("p50", "p75", "p90", "p95")}
    result = {}
    for name, p in (
        ("p50", Decimal("0.5")),
        ("p75", Decimal("0.75")),
        ("p90", Decimal("0.9")),
        ("p95", Decimal("0.95")),
    ):
        x = Decimal(len(data) - 1) * p
        lo = int(x)
        hi = min(lo + 1, len(data) - 1)
        interpolated = Decimal(data[lo]) + (Decimal(data[hi]) - Decimal(data[lo])) * (x - lo)
        result[name] = str(interpolated / Decimal(1_000_000))
    return result


def test_moving_ranges_forward_backward_and_empty() -> None:
    values = np.array([0, 7, 7, 2_000_000, 9_000_001, 12], dtype=np.int64)
    rolling = RollingQuantiles(values)
    for lo, hi in ((0, 4), (1, 6), (2, 2), (0, 2), (4, 6)):
        assert rolling.quantiles(lo, hi) == oracle(values[lo:hi].tolist())


def test_extra_boundary_episode_and_repeated_zero() -> None:
    values = np.zeros(31, dtype=np.int64)
    values[0] = 1_000_001
    rolling = RollingQuantiles(values)
    assert rolling.quantiles(0, 30, extra=3_000_001) == oracle(values[:30].tolist(), 3_000_001)
    assert rolling.quantiles(0, 30, extra=0) == oracle(values[:30].tolist(), 0)


def test_large_integer_interpolation_does_not_use_float() -> None:
    values = np.array([9_000_000_000_001_001, 9_000_000_000_001_003], dtype=np.int64)
    assert RollingQuantiles(values).quantiles(0, 2)["p50"] == "9000000000.001002"


def test_one_step_slide_adjusts_only_one_removed_and_one_added_index() -> None:
    values = np.arange(10, dtype=np.int64)
    rolling = RollingQuantiles(values)
    rolling.quantiles(0, 5)
    with patch.object(rolling, "_adjust_index", wraps=rolling._adjust_index) as adjust:
        rolling.quantiles(1, 6)
    assert adjust.call_count == 2
    assert [call.args for call in adjust.call_args_list] == [(0, -1), (5, 1)]
