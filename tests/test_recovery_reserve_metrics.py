from datetime import UTC, datetime, timedelta
from decimal import Decimal, localcontext
from itertools import product

from crypto_strategy_lab.microstructure.recovery_reserve_metrics import (
    _duration_hours,
    robust_regions,
    summarize_replay,
)
from crypto_strategy_lab.microstructure.serial_replay import SerialReplayResult


def _result() -> SerialReplayResult:
    return SerialReplayResult.model_construct(
        initial_quote=Decimal("100"),
        final_cash=Decimal("102"),
        final_inventory=Decimal("0"),
        last_price=Decimal("1"),
        start=datetime(2026, 1, 1, tzinfo=UTC),
        end_exclusive=datetime(2026, 1, 3, tzinfo=UTC),
        completed_cycles=2,
        zero_cycle_days=0,
        daily_cycles={},
        cycles=(),
        release_closures=(),
        open_entry_timestamp=None,
    )


def test_summary_uses_24_hour_ruler_and_segregated_reserve():
    out = summarize_replay(_result(), Decimal("5"), Decimal("5"), Decimal("1"), [])
    assert out["total_initial_equity"] == Decimal("105")
    assert out["total_final_equity"] == Decimal("107")
    assert out["lock_hours"] == Decimal("0")
    assert out["operating_uptime"] == Decimal("1")
    assert out["maximum_drawdown"] is None
    assert out["total_return"].quantize(Decimal("0.0000000001")) == Decimal("0.0190476190")
    assert out["hours_gt24h"] == out["lock_hours"]


def test_duration_uses_integer_microseconds_without_float_round_trip():
    start = datetime(2026, 1, 1, tzinfo=UTC)
    with localcontext() as context:
        context.prec = 128
        expected = Decimal(1) / Decimal(3_600_000_000)
    assert _duration_hours(start, start + timedelta(microseconds=1)) == expected


def _row(sid, lock="4", loss="5", floor="2.5", **kw):
    return {
        "scenario_id": sid,
        "skim_rate": "0.02",
        "lock_hours_threshold": lock,
        "max_loss_bps": loss,
        "reserve_floor": floor,
        "total_final_equity": "106",
        "operating_uptime": "0.9",
        "lock_hours": "90",
        "completed_cycles": 101,
        "zero_cycle_days": 9,
        "reserve_final": "5.1",
        "total_skim": "1",
        "reserve_dollars_consumed": "0.9",
        "release_count": 1,
        "hold_p99_hours": "20",
        "min_reserve_balance": "2",
        "reserve_depletion_events": 0,
        "maximum_drawdown": "0.1",
        "integrity_pass": True,
        **kw,
    }


def test_single_win_is_not_robust_and_missing_gate_fails_closed():
    baseline = {
        "total_final_equity": "105",
        "operating_uptime": "0.8",
        "lock_hours": "100",
        "completed_cycles": 100,
        "zero_cycle_days": 10,
        "hold_p99_hours": "24",
        "maximum_drawdown": "0.1",
    }
    result = robust_regions([_row("center")], baseline)
    assert result["qualifying_centers"] == []
    assert result["actual_checks"]["single_win_not_robust"]
    bad = robust_regions([_row("bad", maximum_drawdown=None)], baseline)
    assert bad["qualifying_centers"] == []


def test_immediate_neighbors_on_all_axes_are_required():
    baseline = {
        "total_final_equity": "105",
        "operating_uptime": "0.8",
        "lock_hours": "100",
        "completed_cycles": 100,
        "zero_cycle_days": 10,
        "hold_p99_hours": "24",
        "maximum_drawdown": "0.1",
    }
    rows = []
    configs = product(("1", "4", "12"), ("2", "5", "10"), ("0", "2.5"))
    for index, (lock, loss, floor) in enumerate(configs):
        rows.append(_row(str(index), lock=lock, loss=loss, floor=floor))
    out = robust_regions(rows, baseline)
    assert out["qualifying_centers"]
    assert out["qualifying_centers"][0]["axis_neighbors_pass"] == {
        "lock_hours_threshold": True,
        "max_loss_bps": True,
        "reserve_floor": True,
    }


def test_equity_gate_accepts_exact_point_one_cent_and_order_is_stable():
    baseline = {
        "total_final_equity": "105",
        "operating_uptime": "0.8",
        "lock_hours": "100",
        "completed_cycles": 100,
        "zero_cycle_days": 10,
        "hold_p99_hours": "24",
        "maximum_drawdown": "0.1",
    }
    configs = product(("1", "4", "12"), ("2", "5", "10"), ("0", "2.5"))
    rows = [
        _row(str(i), lock=h, loss=b, floor=f, total_final_equity="105.01")
        for i, (h, b, f) in enumerate(configs)
    ]
    first = robust_regions(rows, baseline)
    second = robust_regions(list(reversed(rows)), baseline)
    assert first["qualifying_centers"]
    assert first["regions"] == second["regions"]


def test_large_equity_gate_does_not_round_away_exact_cent_threshold():
    baseline = {
        "total_final_equity": "123456789012345678901234567.894",
        "operating_uptime": "0.8",
        "lock_hours": "100",
        "completed_cycles": 100,
        "zero_cycle_days": 10,
        "hold_p99_hours": "24",
        "maximum_drawdown": "0.1",
    }
    configs = list(product(("1", "4", "12"), ("2", "5", "10"), ("0", "2.5")))
    below = [
        _row(str(i), lock=h, loss=b, floor=f, total_final_equity="123456789012345678901234567.903")
        for i, (h, b, f) in enumerate(configs)
    ]
    exact = [
        _row(str(i), lock=h, loss=b, floor=f, total_final_equity="123456789012345678901234567.904")
        for i, (h, b, f) in enumerate(configs)
    ]

    assert robust_regions(below, baseline)["qualifying_centers"] == []
    assert robust_regions(exact, baseline)["qualifying_centers"]
