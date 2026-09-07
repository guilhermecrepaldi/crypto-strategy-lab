import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal as D

import pytest

from crypto_strategy_lab.microstructure import recovery_reserve as rr
from crypto_strategy_lab.microstructure.serial_replay import (
    SerialCycle,
    SerialModelConfig,
    SerialScenarioConfig,
    SerialStrategy,
    SerialTape,
    _State,
)

START = datetime(2026, 1, 1, tzinfo=UTC)


def runtime(monkeypatch, *, price="0.9999", skim="0.02", loss="10", floor="0"):
    tape = SerialTape.from_events(
        [
            (START, D("1")),
            (START + timedelta(minutes=59), D(price)),
            (START + timedelta(hours=1), D("0.1")),
            (START + timedelta(hours=2), D("2")),
        ],
        tick_size=D("0.0001"),
    )
    parent = SerialModelConfig(
        model_id="M007", parent_model_id=None, strategy=SerialStrategy.STATIC, lookback_minutes=1440
    )
    scenario = SerialScenarioConfig(tick_size=D("0.0001"), quantity_step=D("0.01"))
    instance = rr.RecoveryReserveRuntime(
        rr.ReserveConfig(D(skim), 1, D(loss), D(floor)), parent, scenario, tape, {}, None
    )
    original_timeline, destination_timeline = "original", "destination"
    instance.timelines = {(10000, 1): original_timeline, (9998, 1): destination_timeline}
    monkeypatch.setattr(
        rr,
        "_activity",
        lambda timeline, boundary: {
            "cycles_1h": 0 if timeline == original_timeline else 3,
            "cycles_4h": 0 if timeline == original_timeline else 3,
            "cycles_24h": 0 if timeline == original_timeline else 3,
        },
    )
    monkeypatch.setattr(rr, "_select", lambda *args, **kwargs: (9998, 1))
    monkeypatch.setattr(rr, "_score", lambda *args, **kwargs: D("1"))
    state = _State(
        cash=D(0),
        candidate=(10000, 1),
        candidate_tick_size=D("0.0001"),
        entry_event=int(tape.events[0]),
        inventory=D(100),
        inventory_cost=D(100),
    )
    return instance, state, instance.schedule(state.entry_event, None)


def test_grid_and_initial_invariants():
    configs = rr.grid_configs()
    assert len(configs) == len({c.scenario_id for c in configs}) == 18
    assert {c.skim_rate for c in configs} == {D("0.02")}
    assert {c.reserve_floor for c in configs} == {D(0), D("2.5")}
    with pytest.raises(ValueError, match="INITIAL_CAPITAL"):
        rr.ReserveConfig(D("0.02"), 1, D(1), initial_operating=D(105))
    with pytest.raises(ValueError, match="INITIAL_RESERVE"):
        rr.ReserveConfig(D("0.02"), 1, D(1), initial_reserve=D(6))
    with pytest.raises(ValueError, match="INVALID_RESERVE_CONFIG"):
        rr.ReserveConfig(D("0.01"), 1, D(1))


def test_exact_deficit_restores_bank_and_reconciles_total(monkeypatch):
    instance, state, event = runtime(monkeypatch)
    assert instance(state, event)
    assert state.cash == D(100)
    assert instance.reserve == D("4.99")
    assert state.cash + instance.reserve == D("104.99")
    assert state.inventory == 0 and state.entry_event is None
    assert len(state.cycles) == 0 and len(state.release_closures) == 1
    assert state.realized_profit == D("-0.01")
    assert instance.releases[0]["price_observation_event"] < event
    assert instance.releases[0]["release_price"] == "0.9999"
    assert state.candidate == (9998, 1)


def test_restores_grown_principal_not_100(monkeypatch):
    instance, state, event = runtime(monkeypatch)
    state.inventory = D(123)
    state.inventory_cost = D(123)
    assert instance(state, event)
    assert state.cash == D(123) and instance.reserve == D("4.9877")


@pytest.mark.parametrize("price", ["1", "1.0001"])
def test_nonpositive_loss_never_transfers(monkeypatch, price):
    instance, state, event = runtime(monkeypatch, price=price)
    assert not instance(state, event)
    assert instance.reserve == 5 and state.inventory == 100 and state.cash == 0


def test_insufficient_full_coverage_keeps_and_never_adds_inventory(monkeypatch):
    instance, state, event = runtime(monkeypatch)
    instance.reserve = D("0.005")
    assert not instance(state, event)
    assert state.inventory == 100 and state.inventory_cost == 100 and state.cash == 0
    assert instance.reserve == D("0.005")
    assert instance.evaluations["INSUFFICIENT_RESERVE"] == 1


def test_reserve_floor_keeps_full_coverage_available_but_preserves_ammunition(monkeypatch):
    instance, state, event = runtime(monkeypatch, floor="5")
    assert not instance(state, event)
    assert instance.evaluations["RESERVE_FLOOR"] == 1
    assert instance.reserve == 5 and state.inventory == 100


@pytest.mark.parametrize(
    "candidate,score,reason",
    [
        (None, "1", "NO_VALID_CANDIDATE"),
        ((10000, 1), "1", "SAME_CANDIDATE"),
        ((9998, 1), "0", "NONPOSITIVE_SCORE"),
    ],
)
def test_valid_different_positive_candidate_required(monkeypatch, candidate, score, reason):
    instance, state, event = runtime(monkeypatch)
    monkeypatch.setattr(rr, "_select", lambda *args, **kwargs: candidate)
    monkeypatch.setattr(rr, "_score", lambda *args, **kwargs: D(score))
    assert not instance(state, event)
    assert instance.evaluations[reason] == 1 and instance.reserve == 5


def test_loss_cap_age_and_strict_prefix(monkeypatch):
    instance, state, event = runtime(monkeypatch, price="0.99")
    assert not instance(state, event - rr.HOUR)
    assert not instance(state, event)
    assert instance.evaluations["AGE"] == 1 and instance.evaluations["LOSS_CAP"] == 1
    instance, state, event = runtime(monkeypatch)
    ends = []

    def select(*args, **kwargs):
        ends.append(args[3])
        assert kwargs.get("excluded_candidate") is None
        return (9998, 1)

    monkeypatch.setattr(rr, "_select", select)
    assert instance(state, event + 17)
    assert ends == [event, event]
    assert instance.releases[0]["release_price"] == "0.9999"


def cycle(profit):
    return SerialCycle(
        entry_event=0,
        exit_event=rr.HOUR * 2,
        entry_timestamp=START,
        exit_timestamp=START + timedelta(hours=2),
        low=D(1),
        high=D(1) + D(profit) / 100,
        quantity=D(100),
        buy_fee_quote=D(0),
        sell_fee_quote=D(0),
    )


@pytest.mark.parametrize("profit,expected", [("2", "0.04"), ("0", "0"), ("-2", "0")])
def test_only_positive_realized_profit_skimmed(monkeypatch, profit, expected):
    instance, state, _event = runtime(monkeypatch)
    state.cash = D(100) + D(profit)
    equity = state.cash + instance.reserve
    instance.cycle_settled(state, cycle(profit))
    assert instance.total_skim == D(expected)
    assert state.cash == D(100) + D(profit) - D(expected)
    assert state.cash + instance.reserve == equity


def test_json_restart_and_repetition_deterministic(monkeypatch):
    first, state, event = runtime(monkeypatch)
    second, other_state, other_event = runtime(monkeypatch)
    assert first(state, event) == second(other_state, other_event)
    assert first.snapshot() == second.snapshot()
    restored, _, _ = runtime(monkeypatch)
    restored.restore(json.loads(json.dumps(first.snapshot())))
    state.cash += D(2)
    other_state.cash += D(2)
    first.cycle_settled(state, cycle("2"))
    restored.cycle_settled(other_state, cycle("2"))
    assert first.snapshot() == restored.snapshot()
    assert first.replenishments[0]["cycles_to_replenish"] == 1
    broken = first.snapshot()
    broken["reserve"] = "100"
    with pytest.raises(ValueError, match="RECONCILIATION"):
        restored.restore(broken)


def test_real_selector_ignores_future_cycles_and_same_timestamp_price():
    past = [
        (START, D("0.9998")),
        (START + timedelta(seconds=1), D("0.9999")),
        (START + timedelta(seconds=2), D("0.9998")),
        (START + timedelta(seconds=3), D("0.9999")),
        (START + timedelta(seconds=4), D("0.9998")),
        (START + timedelta(seconds=5), D("0.9999")),
        (START + timedelta(seconds=6), D("1")),
        (START + timedelta(seconds=7), D("0.9998")),
        (START + timedelta(seconds=8), D("0.9999")),
        (START + timedelta(seconds=9), D("0.9998")),
        (START + timedelta(seconds=10), D("0.9999")),
        (START + timedelta(seconds=11), D("0.9998")),
        (START + timedelta(seconds=12), D("0.9999")),
        (START + timedelta(minutes=59), D("0.9999")),
    ]
    decision = START + timedelta(hours=1, seconds=6)
    same_timestamp = [(decision, D("1.0001"))]
    future = [
        (decision + timedelta(seconds=i + 1), D("1") if i % 2 else D("1.0001")) for i in range(30)
    ]
    snapshots = []
    for events in (past + same_timestamp, past + same_timestamp + future):
        tape = SerialTape.from_events(events, tick_size=D("0.0001"))
        parent = SerialModelConfig(
            model_id="M007",
            parent_model_id=None,
            strategy=SerialStrategy.STATIC,
            lookback_minutes=1440,
        )
        scenario = SerialScenarioConfig(tick_size=D("0.0001"), quantity_step=D("0.01"))
        instance = rr.RecoveryReserveRuntime(
            rr.ReserveConfig(D("0.02"), 1, D(10)),
            parent,
            scenario,
            tape,
            tape.timelines((1,)),
            None,
        )
        state = _State(
            cash=D(0),
            candidate=(10000, 1),
            entry_event=int(tape.events[6]),
            inventory=D(100),
            inventory_cost=D(100),
        )
        assert instance(state, instance.schedule(state.entry_event, None))
        assert state.candidate == (9998, 1)
        snapshots.append(instance.snapshot())
    assert snapshots[0] == snapshots[1]
