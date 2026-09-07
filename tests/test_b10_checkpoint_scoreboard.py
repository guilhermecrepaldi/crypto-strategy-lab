from copy import deepcopy
from decimal import Decimal

from scripts.b10_checkpoint_scoreboard import DAY_US, HOUR_US, summarize


def d(value):
    return {"decimal": str(value)}


def fixture():
    start = 1767225600000000
    engine = {
        "entry_us": start + DAY_US,
        "orders": [],
        "counts": {"FULLY_FILLED_CYCLES": 2, "NET_POSITIVE_CYCLES": 1},
        "profile": {"fields": {"name": "A_OBSERVED_BEST_SUPPORTED"}},
        "settlements": [{"net_profit": "1.25", "gross_pnl": "1.5"}],
        "sell_net": d(20),
        "sold_cost": d(19.5),
        "realized_cycle_fees": d(0.1),
        "cash": d(40),
        "reserve": d(5),
        "inventory": d(60),
        "dust": d(0),
        "cost": d(59),
        "bids": [[d(1), d(1000)]],
        "fees": d(0.35),
        "reserve_funding": d(0.025),
        "reserve_consumption": d(0.025),
        "reserve_min": d(4.99),
    }
    state = {
        "start_us": start,
        "last_us": start + 2 * DAY_US + 5 * HOUR_US,
        "end_us": start + 4 * DAY_US,
        "completed": False,
        "full_days": {"2026-01-01": 1, "2026-01-03": 1},
        "holds_us": [26 * HOUR_US],
        "processed_trades": 50,
        "max_drawdown": d(0.02),
        "identity": {
            "profile_config_sha256": "f" * 64,
            "published_config_sha": "a" * 40,
            "expected_trade_count": 100,
        },
    }
    return {"state": state, "execution": {"state": engine}, "release_evaluations": {}}


def test_same_prefix_not_full_history_and_closed_days():
    result = summarize(fixture(), 20)
    assert result["reality_retention_same_prefix"] == "0.1"
    assert result["calendar_days_processed"] == 2
    assert result["calendar_days_total"] == 4
    assert result["active_days_so_far"] == 1
    assert result["zero_cycle_days_so_far"] == 1
    assert result["current_partial_day_cycles"] == 1
    assert Decimal(result["progress_percent"]).quantize(Decimal("0.0001")) == Decimal("55.2083")
    assert result["verdict"] == "PENDING"


def test_open_hold_partial_realized_pnl_and_unknown_slippage():
    result = summarize(fixture(), 20)
    assert result["max_hold"] == "29"
    assert result["lock_hours"] == "7"
    assert result["net_pnl_fixed_100"] == "1.75"
    assert result["gross_pnl_fixed_100"] == "2.1"
    assert result["marked_total_equity"] == "105"
    assert result["slippage_cost"] is None
    assert result["reserve_final"] == "5"


def test_order_cohorts_exclude_release_and_count_partial_only():
    payload = fixture()
    fields = {"side": "SELL", "release": False, "quantity": d(10), "filled": d(0)}
    payload["execution"]["state"]["orders"] = [
        {"fields": deepcopy(fields)},
        {"fields": {**fields, "filled": d(5)}},
        {"fields": {**fields, "filled": d(10)}},
        {"fields": {**fields, "filled": d(10), "release": True}},
    ]
    result = summarize(payload, 20)
    assert result["sell_not_filled"] == 1
    assert result["sell_partial_only"] == 1
    assert result["sell_full"] == 1
    assert result["release_ioc_orders"] == 1


def test_complete_uses_physical_end_for_open_hold():
    payload = fixture()
    payload["state"]["completed"] = True
    payload["state"]["last_us"] = payload["state"]["end_us"] - 1
    result = summarize(payload, 3580880)
    assert result["progress_percent"] == "100"
    assert result["calendar_days_processed"] == 4
    assert result["max_hold"] == "72"
    assert result["status"] == "COMPLETE"
    assert result["verdict"] == "INCONCLUSIVE_EXECUTION_DATA"


def test_zero_prefix_is_unknown_not_division_or_total_substitution():
    assert summarize(fixture(), 0)["reality_retention_same_prefix"] is None
