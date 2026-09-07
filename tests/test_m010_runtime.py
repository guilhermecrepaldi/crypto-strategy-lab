from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest

from crypto_strategy_lab.microstructure import capital_release as cr
from crypto_strategy_lab.microstructure.serial_replay import (
    EVENT_ORDER_SCALE,
    SERIAL_TAPE_QUANTUM,
    USDCUSDT_TICK_CATALOG,
    SerialModelConfig,
    SerialScenarioConfig,
    SerialTape,
    _advance,
    _datetime_to_micros,
    _State,
    preregistered_corrected_block,
    replay_serial_model,
)

START = datetime(2026, 1, 1, tzinfo=UTC)


def config() -> SerialModelConfig:
    return SerialModelConfig.model_validate(
        {
            **preregistered_corrected_block()[2].model_dump(),
            "model_id": "M010",
            "parent_model_id": "M007",
            "capital_release_protocol": "OWNER_EXPLORATORY_OVERRIDE_FROZEN_V1",
        }
    )


def scenario() -> SerialScenarioConfig:
    return SerialScenarioConfig(
        tick_size=SERIAL_TAPE_QUANTUM,
        historical_tick_catalog_hash=USDCUSDT_TICK_CATALOG.catalog_hash,
        historical_tick_source_url=USDCUSDT_TICK_CATALOG.source_url,
        historical_tick_policy="CAUSAL_OBSERVED_GRID_THEN_OFFICIAL_COMPLETION_BOUND",
    )


def event(seconds: float) -> int:
    return _datetime_to_micros(START + timedelta(seconds=seconds)) * EVENT_ORDER_SCALE


def test_rule_rejection_boundaries() -> None:
    base: dict[str, Any] = {
        "alternative": (99960, 10),
        "incumbent": (100000, 10),
        "survival_support": True,
        "activity_support": True,
        "loss_fraction": Decimal("0.0005"),
        "first_cycle_support": True,
        "exact_target_recovery": 6,
        "strict_comparison": True,
    }
    assert cr._candidate_rule_reason(**base) == "CAPITAL_RELEASE_RECOVERY_ADVANTAGE"
    for change in [
        {"loss_fraction": Decimal("0.00050000001")},
        {"survival_support": False},
        {"first_cycle_support": False},
        {"alternative": base["incumbent"]},
        {"activity_support": False},
        {"strict_comparison": False},
        {"exact_target_recovery": None},
    ]:
        assert cr._candidate_rule_reason(**{**base, **change}).startswith("KEEP_")


def test_keep_landmarks_preserve_high_and_exact_fractional_seconds() -> None:
    tape = SerialTape.from_events(
        [
            (START + timedelta(seconds=offset), Decimal(price))
            for offset, price in [(0.25, "1"), (60.25, "0.9996"), (900.25, "1.0001"), (1000, "1")]
        ],
        tick_size=SERIAL_TAPE_QUANTUM,
    )
    state = _State(cash=Decimal("100"), candidate=(100000, 10))
    checkpoints: list[int] = []

    def keep(s: _State, at: int) -> bool:
        checkpoints.append(at)
        assert s.candidate == (100000, 10)
        return False

    _advance(
        state,
        tape.timelines((10,)),
        config(),
        scenario(),
        event(0),
        event(1000),
        recalculate_after_exit=False,
        tick_catalog=USDCUSDT_TICK_CATALOG,
        tape_quantum=tape.tick_size,
        observed_tick_evidence_event=None,
        release_decision=keep,
    )
    assert checkpoints == [event(60.25), event(300.25), event(900.25)]
    assert len(state.cycles) == 1
    assert state.cycles[0].high == Decimal("1.0001")
    assert state.cycles[0].exit_event == event(900.25)
    assert state.release_closures == []


def test_release_debits_bank_and_reentry_uses_post_release_cash() -> None:
    tape = SerialTape.from_events(
        [
            (START + timedelta(seconds=offset), Decimal(price))
            for offset, price in [
                (0, "1"),
                (59, "0.9996"),
                (61, "0.9996"),
                (70, "0.9997"),
                (80, "1"),
                (100, "1.0001"),
            ]
        ],
        tick_size=SERIAL_TAPE_QUANTUM,
    )
    state = _State(cash=Decimal("100"), candidate=(100000, 10))
    observed_cash: list[Decimal] = []

    def release(s: _State, at: int) -> bool:
        snapshot = {
            "candidate_rule": {"would_release": True},
            "current_price": "0.9996",
            "checkpoint_event": at,
            "release_cash_R_T": "99.96",
            "alternative_low_tick": 99960,
            "alternative_high_tick": 99970,
        }
        cr.apply_release(s, snapshot, scenario(), config(), tape)
        observed_cash.append(s.cash)
        return True

    _advance(
        state,
        tape.timelines((10,)),
        config(),
        scenario(),
        event(0),
        event(80),
        recalculate_after_exit=False,
        tick_catalog=USDCUSDT_TICK_CATALOG,
        tape_quantum=tape.tick_size,
        observed_tick_evidence_event=None,
        release_decision=release,
    )
    assert observed_cash == [Decimal("99.96")]
    assert state.release_closures[0].quantity == Decimal("100")
    assert len(state.cycles) == 1
    assert state.cycles[0].quantity == Decimal("100")
    assert state.cash == Decimal("99.97")
    assert state.realized_profit == Decimal("-0.03")
    assert state.inventory == 0


def test_physical_frozen_keep_replay_deterministic_and_parent_equivalent() -> None:
    tape = SerialTape.from_events(
        [
            (START + timedelta(seconds=offset), Decimal(price))
            for offset, price in [
                (-120, "1"),
                (-100, "1.0001"),
                (0, "1"),
                (59, "0.9996"),
                (301, "1.0001"),
                (600, "1.0001"),
            ]
        ],
        tick_size=SERIAL_TAPE_QUANTUM,
    )
    args = {
        "start": START,
        "end_exclusive": START + timedelta(seconds=600),
        "tick_catalog": USDCUSDT_TICK_CATALOG,
    }
    parent = replay_serial_model(tape, preregistered_corrected_block()[2], scenario(), **args)
    first = replay_serial_model(tape, config(), scenario(), release_support_tape=tape, **args)
    again = replay_serial_model(tape, config(), scenario(), release_support_tape=tape, **args)
    assert first == again
    assert first.initial_quote == Decimal("100")
    assert first.release_evaluations
    assert first.release_closures == ()
    assert first.cycles == parent.cycles
    assert first.selection_changes == parent.selection_changes
    assert first.final_cash == parent.final_cash
    # Changing a future HIGH cannot change any checkpoint <=300 seconds.
    altered = SerialTape.from_events(
        [
            (START + timedelta(seconds=offset), Decimal(price))
            for offset, price in [
                (-120, "1"),
                (-100, "1.0001"),
                (0, "1"),
                (59, "0.9996"),
                (599, "1.0001"),
                (600, "1.0001"),
            ]
        ],
        tick_size=SERIAL_TAPE_QUANTUM,
    )
    other = replay_serial_model(altered, config(), scenario(), release_support_tape=altered, **args)
    assert first.release_evaluations == other.release_evaluations


def test_noncanonical_initial_or_missing_support_fails_closed() -> None:
    with pytest.raises(ValueError, match="INITIAL_CAPITAL_INVARIANT_VIOLATION"):
        SerialScenarioConfig(tick_size=SERIAL_TAPE_QUANTUM, initial_quote=Decimal("200"))
    assert cr.next_checkpoint(event(0) + 7, event(172800)) == event(259200)
    with pytest.raises(ValueError, match="M010_FROZEN_PARENT_PROTOCOL_VIOLATION"):
        SerialModelConfig.model_validate({**config().model_dump(), "lookback_minutes": 60})
