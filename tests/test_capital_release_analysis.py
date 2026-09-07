from datetime import UTC, datetime, timedelta
from decimal import Decimal as D

import pytest

from crypto_strategy_lab.microstructure.capital_release_analysis import (
    analyze_capital_release,
    compare_zero_release,
)
from crypto_strategy_lab.microstructure.serial_replay import (
    EVENT_ORDER_SCALE,
    SerialCycle,
    SerialModelConfig,
    SerialScenarioConfig,
    SerialTape,
    _datetime_to_micros,
    replay_serial_model,
)

START = datetime(2026, 1, 1, tzinfo=UTC)


def _base():
    tape = SerialTape.from_events(
        [
            (START + timedelta(seconds=s), D(p))
            for s, p in [
                (-1, "1"),
                (0, "1"),
                (60, "0.9996"),
                (61, "0.9996"),
                (120, "1.0002"),
                (180, "1.0002"),
            ]
        ],
        tick_size=D("0.0001"),
    )
    result = replay_serial_model(
        tape,
        SerialModelConfig(
            model_id="M007", parent_model_id=None, strategy="STATIC", lookback_minutes=10
        ),
        SerialScenarioConfig(tick_size=D("0.0001")),
        start=START,
        end_exclusive=START + timedelta(seconds=180),
    )
    return result, tape


def test_zero_release_equivalence_checks_decisions_and_full_economics():
    parent, _ = _base()
    child = parent.model_copy(
        update={
            "model_id": "M010",
            "model_hash": "different",
            "release_evaluations": ({"extra": True},),
        }
    )
    assert compare_zero_release(parent, child)["M010_BEHAVIORALLY_EQUIVALENT_TO_M007"] == "YES"
    with pytest.raises(ValueError, match="ZERO_RELEASE_BEHAVIORAL_DIVERGENCE"):
        compare_zero_release(parent, child.model_copy(update={"blocked_reselection_checks": 1}))


def test_release_loss_recovery_and_fixed_ruler_are_actual_cash():
    base, tape = _base()

    def event(s):
        return _datetime_to_micros(START + timedelta(seconds=s)) * EVENT_ORDER_SCALE

    def cycle(entry, exit, low, high, quantity):
        return SerialCycle(
            entry_event=event(entry),
            exit_event=event(exit),
            entry_timestamp=START + timedelta(seconds=entry),
            exit_timestamp=START + timedelta(seconds=exit),
            low=D(low),
            high=D(high),
            quantity=D(quantity),
            buy_fee_quote=D(0),
            sell_fee_quote=D(0),
        )

    release = cycle(0, 60, "1", "0.9996", "100")
    normal = cycle(61, 120, "0.9996", "1.0002", "100")
    snapshot = {
        "checkpoint_event": event(60),
        "candidate_rule": {"would_release": True},
        "B_cash_before_buy": "100",
        "release_cash_R_T": "99.96",
        "target_cash_K_at_high": "100.01",
    }
    result = base.model_copy(
        update={
            "cycles": (normal,),
            "release_closures": (release,),
            "release_evaluations": (snapshot,),
            "completed_cycles": 1,
            "daily_cycles": {START.date(): 1},
            "zero_cycle_days": 0,
            "final_cash": D("100.02"),
            "final_marked_equity": D("100.02"),
            "return_fraction": D("0.0002"),
            "realized_profit": D("0.02"),
        }
    )
    metrics = analyze_capital_release(result, tape)
    assert D(metrics["TOTAL_RELEASE_LOSS"]) == D("0.04")
    assert metrics["COMPLETED_CYCLES"] == 1
    assert metrics["RELEASES_RECOVERED_B"] == metrics["RELEASES_RECOVERED_K"] == 1
    assert D(metrics["RECOVERY_CYCLES_P50"]) == 1
    assert D(metrics["RECOVERY_TIME_P50"]) == 60
    assert D(metrics["MAX_DRAWDOWN"]) == D("0.0004")
    assert D(metrics["FIXED_NOTIONAL_100"]["additive_pnl"]) == D("0.020024")
    unrecovered = result.model_copy(
        update={
            "cycles": (),
            "completed_cycles": 0,
            "daily_cycles": {START.date(): 0},
            "zero_cycle_days": 1,
            "final_cash": D("99.96"),
            "final_marked_equity": D("99.96"),
            "return_fraction": D("-0.0004"),
            "realized_profit": D("-0.04"),
        }
    )
    metrics = analyze_capital_release(unrecovered, tape)
    assert metrics["RELEASES_NOT_RECOVERED_K"] == 1
    assert metrics["RECOVERY_TIME_P50"] is None
    assert metrics["release_recoveries"][0]["recovery_K_censored"] is True


def test_terminal_inventory_is_included_in_exposure_drawdown_and_fixed_mark():
    base, tape = _base()
    result = base.model_copy(
        update={
            "open_cycle_censored": True,
            "open_entry_event": _datetime_to_micros(START) * EVENT_ORDER_SCALE,
            "open_entry_timestamp": START,
            "open_entry_price": D(1),
            "open_buy_fee_quote": D(0),
            "open_holding_seconds": D(180),
            "final_inventory": D(100),
            "final_cash": D(0),
            "final_marked_equity": D("100.02"),
            "return_fraction": D("0.0002"),
            "unrealized_profit": D("0.02"),
        }
    )
    metrics = analyze_capital_release(result, tape)
    assert D(metrics["TIME_INVENTORY_OPEN"]) == 180
    assert D(metrics["MAX_HOLD"]) == 180
    assert D(metrics["IDLE_HOURS"]) == 0
    assert D(metrics["MAX_DRAWDOWN"]) == D("0.0004")
    assert D(metrics["FIXED_NOTIONAL_100"]["additive_pnl"]) == D("0.02")


def test_zero_release_recovery_is_not_false_success_and_initial_capital_fails():
    result, tape = _base()
    metrics = analyze_capital_release(result, tape)
    assert metrics["FROZEN_RULE_DID_NOT_TRIGGER"] is True
    assert metrics["RECOVERY_TIME_P50"] is None
    assert metrics["RELEASES_RECOVERED"] == 0
    with pytest.raises(ValueError, match="INITIAL_CAPITAL_INVARIANT_VIOLATION"):
        analyze_capital_release(result.model_copy(update={"initial_quote": D(99)}), tape)
