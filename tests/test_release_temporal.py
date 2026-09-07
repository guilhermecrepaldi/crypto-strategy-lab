from datetime import UTC, datetime, timedelta
from decimal import Decimal

from crypto_strategy_lab.microstructure.serial_replay import (
    EVENT_ORDER_SCALE,
    MICROS_PER_SECOND,
    SerialCycle,
    SerialReplayResult,
    SerialTape,
)
from crypto_strategy_lab.microstructure.temporal_analysis import _Ledger, analyze_replay_temporally

START = datetime(2026, 1, 1, tzinfo=UTC)
TICK = Decimal("0.0001")


def _event(value: datetime) -> int:
    return int(value.timestamp() * MICROS_PER_SECOND) * EVENT_ORDER_SCALE


def _release_result() -> tuple[SerialReplayResult, SerialTape, SerialCycle]:
    entry = START + timedelta(hours=1)
    exit = START + timedelta(hours=3)
    closure = SerialCycle(
        entry_event=_event(entry),
        exit_event=_event(exit),
        entry_timestamp=entry,
        exit_timestamp=exit,
        low=Decimal("0.9990"),
        high=Decimal("0.9980"),
        quantity=Decimal("10"),
        buy_fee_quote=Decimal("0.01"),
        sell_fee_quote=Decimal("0.01"),
    )
    end = START + timedelta(hours=4)
    tape = SerialTape.from_events(
        [
            (START - timedelta(minutes=1), Decimal("1.0000")),
            (START, Decimal("1.0000")),
            (entry, Decimal("0.9990")),
            (START + timedelta(hours=2), Decimal("0.9985")),
            (exit, Decimal("0.9980")),
            (end, Decimal("0.9980")),
        ],
        tick_size=TICK,
    )
    result = SerialReplayResult(
        model_id="M010",
        model_hash="model",
        scenario_id="scenario",
        scenario_hash="scenario",
        start=START,
        end_exclusive=end,
        initial_quote=Decimal("100"),
        final_cash=Decimal("99.97"),
        final_inventory=Decimal("0"),
        last_price=Decimal("0.9980"),
        final_marked_equity=Decimal("99.97"),
        return_fraction=Decimal("-0.0003"),
        realized_profit=Decimal("-0.03"),
        unrealized_profit=Decimal("0"),
        total_fees=Decimal("0.02"),
        completed_cycles=0,
        daily_cycles={},
        zero_cycle_days=1,
        reselection_count=0,
        blocked_reselection_checks=0,
        cooldown_violations=0,
        reversal_24h_count=0,
        active_low=None,
        active_high=None,
        open_entry_event=None,
        open_entry_timestamp=None,
        open_entry_price=None,
        open_buy_fee_quote=None,
        open_holding_seconds=None,
        open_cycle_censored=False,
        execution_class="PRICE_PATH_ONLY",
        selection_changes=(),
        cycles=(),
        release_closures=(closure,),
    )
    return result, tape, closure


def test_release_reconstructs_cash_inventory_holding_and_capital_hours() -> None:
    result, tape, closure = _release_result()
    ledger = _Ledger(result, tape)
    entry = closure.entry_event
    exit = closure.exit_event
    end = _event(result.end_exclusive)

    assert ledger.state(entry + 1)[0] == Decimal("90.00")
    assert ledger.state(entry + 1)[1] == Decimal("10")
    assert ledger.state(exit + 1) == (Decimal("99.97"), Decimal("0"))
    assert ledger.holding(end) == Decimal("2")
    assert ledger.integral(end) == Decimal("399.945")


def test_release_realization_enters_period_economics_but_not_cycle_count() -> None:
    result, tape, _ = _release_result()
    analysis = analyze_replay_temporally(result, tape)
    day = analysis.daily[0]

    assert Decimal(day["gross_edge_quote"]) == Decimal("-0.01")
    assert Decimal(day["fees_quote"]) == Decimal("0.02")
    assert Decimal(day["realized_net_profit"]) == Decimal("-0.03")
    assert day["completed_cycles"] == 0
