import zipfile
from array import array
from bisect import bisect_left, bisect_right
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

import crypto_strategy_lab.microstructure.serial_replay as serial_replay
from crypto_strategy_lab.microstructure.data import (
    HistoryManifest,
    manifest_for,
    parse_archive,
)
from crypto_strategy_lab.microstructure.serial_replay import (
    SERIAL_TAPE_QUANTUM,
    USDCUSDT_FINE_GRID_OBSERVED_FROM,
    USDCUSDT_TICK_CATALOG,
    USDCUSDT_TICK_CHANGE,
    CandidateTimeline,
    SerialModelConfig,
    SerialScenarioConfig,
    SerialStrategy,
    SerialTape,
    TickCatalog,
    TickPeriod,
    TickTransition,
    load_serial_tape,
    preregistered_corrected_block,
    preregistered_first_block,
    replay_serial_model,
    scan_oracle_cpu,
    symmetric_break_even_fee,
)

START = datetime(2026, 1, 1, tzinfo=UTC)
TICK = Decimal("0.0001")


def _config(**changes: object) -> SerialModelConfig:
    values: dict[str, object] = {
        "model_id": "M001",
        "parent_model_id": None,
        "strategy": SerialStrategy.STATIC,
        "lookback_minutes": 10,
    }
    values.update(changes)
    return SerialModelConfig.model_validate(values)


def _scenario(**changes: object) -> SerialScenarioConfig:
    values: dict[str, object] = {
        "tick_size": TICK,
        "quantity_step": Decimal("0.01"),
    }
    values.update(changes)
    return SerialScenarioConfig.model_validate(values)


def _historical_scenario() -> SerialScenarioConfig:
    return SerialScenarioConfig(
        scenario_id="PRICE_PATH_HISTORICAL_TICK_ZERO_FEE_V2",
        tick_size=SERIAL_TAPE_QUANTUM,
        historical_tick_catalog_hash=USDCUSDT_TICK_CATALOG.catalog_hash,
        historical_tick_source_url=USDCUSDT_TICK_CATALOG.source_url,
        historical_tick_policy="CAUSAL_OBSERVED_GRID_THEN_OFFICIAL_COMPLETION_BOUND",
    )


def _tape(items: list[tuple[int, str]]) -> SerialTape:
    return SerialTape.from_events(
        [(START + timedelta(seconds=offset), Decimal(price)) for offset, price in items],
        tick_size=TICK,
    )


def test_first_block_is_frozen_and_model_hash_excludes_human_identity() -> None:
    models = preregistered_first_block()

    assert [item.model_id for item in models] == ["M001", "M002", "M003", "M004"]
    assert models[0].strategy == SerialStrategy.STATIC
    assert models[3].idle_threshold_minutes == 30
    assert models[3].confirmation_checks == 5
    assert models[3].switch_advantage == Decimal("0.10")
    assert models[3].cooldown_minutes == 60
    duplicate_identity = models[0].model_copy(update={"model_id": "M999"})
    assert duplicate_identity.model_hash == models[0].model_hash
    assert _scenario().scenario_hash != _scenario(maker_fee_per_leg=Decimal("0.0001")).scenario_hash


def test_corrected_block_has_new_ids_and_hashed_tick_semantics() -> None:
    legacy = preregistered_first_block()
    corrected = preregistered_corrected_block()

    assert [item.model_id for item in corrected] == ["M005", "M006", "M007", "M008"]
    assert corrected[-1].parent_model_id == "M007"
    assert all(
        item.distance_semantics == "ONE_EXCHANGE_TICK_AT_LEVEL_SELECTION" for item in corrected
    )
    assert all(item.selection_moment == "AT_LEVEL_SELECTION" for item in corrected)
    assert [item.model_hash for item in corrected] != [item.model_hash for item in legacy]


def test_official_tick_catalog_preserves_the_evidenced_rollout_window() -> None:
    assert USDCUSDT_TICK_CATALOG.tick_size_at(
        USDCUSDT_TICK_CHANGE - timedelta(minutes=1)
    ) == Decimal("0.0001")
    assert USDCUSDT_TICK_CATALOG.tick_size_at(USDCUSDT_TICK_CHANGE) == Decimal("0.00001")
    assert USDCUSDT_TICK_CATALOG.is_price_compatible(
        USDCUSDT_FINE_GRID_OBSERVED_FROM, Decimal("0.99949")
    )
    assert not USDCUSDT_TICK_CATALOG.is_price_compatible(
        USDCUSDT_TICK_CHANGE - timedelta(hours=1), Decimal("0.99949")
    )


def test_rollout_grid_changes_only_after_evidence_enters_the_prefix() -> None:
    tape = SerialTape.from_events(
        [
            (USDCUSDT_FINE_GRID_OBSERVED_FROM - timedelta(seconds=1), Decimal("0.99950")),
            (USDCUSDT_FINE_GRID_OBSERVED_FROM, Decimal("0.99949")),
        ],
        tick_size=SERIAL_TAPE_QUANTUM,
        tick_catalog=USDCUSDT_TICK_CATALOG,
    )
    evidence_event = tape.observed_tick_evidence_event
    assert evidence_event is not None

    before_prefix = USDCUSDT_TICK_CATALOG.tick_size_at_decision(
        USDCUSDT_FINE_GRID_OBSERVED_FROM,
        decision_event=evidence_event,
        observed_tick_evidence_event=evidence_event,
    )
    after_prefix = USDCUSDT_TICK_CATALOG.tick_size_at_decision(
        USDCUSDT_FINE_GRID_OBSERVED_FROM,
        decision_event=evidence_event + 1,
        observed_tick_evidence_event=evidence_event,
    )

    assert before_prefix == Decimal("0.0001")
    assert after_prefix == Decimal("0.00001")


@pytest.mark.parametrize(
    "periods",
    [
        (
            TickPeriod(
                start=datetime(2025, 1, 1, tzinfo=UTC),
                end_exclusive=datetime(2025, 2, 1, tzinfo=UTC),
                tick_size=Decimal("0.0001"),
            ),
            TickPeriod(start=datetime(2025, 2, 2, tzinfo=UTC), tick_size=Decimal("0.00001")),
        ),
        (
            TickPeriod(
                start=datetime(2025, 1, 1, tzinfo=UTC),
                end_exclusive=datetime(2025, 2, 2, tzinfo=UTC),
                tick_size=Decimal("0.0001"),
            ),
            TickPeriod(start=datetime(2025, 2, 1, tzinfo=UTC), tick_size=Decimal("0.00001")),
        ),
    ],
)
def test_tick_catalog_rejects_gaps_and_overlaps(periods: tuple[TickPeriod, ...]) -> None:
    with pytest.raises(ValueError, match="gap or overlap"):
        TickCatalog(periods=periods)


def test_future_catalog_change_does_not_change_past_selection_grid() -> None:
    future_change = datetime(2026, 7, 1, tzinfo=UTC)
    alternative = TickCatalog(
        periods=(
            TickPeriod(
                start=datetime(2025, 1, 1, tzinfo=UTC),
                end_exclusive=USDCUSDT_TICK_CHANGE,
                tick_size=Decimal("0.0001"),
            ),
            TickPeriod(
                start=USDCUSDT_TICK_CHANGE,
                end_exclusive=future_change,
                tick_size=Decimal("0.00001"),
            ),
            TickPeriod(start=future_change, tick_size=Decimal("0.00002")),
        ),
        transitions=(
            TickTransition(
                start=USDCUSDT_FINE_GRID_OBSERVED_FROM,
                end_exclusive=USDCUSDT_TICK_CHANGE,
                allowed_tick_sizes=(Decimal("0.0001"), Decimal("0.00001")),
                evidence="known rollout window",
            ),
        ),
    )
    decision = datetime(2026, 3, 1, tzinfo=UTC)

    assert alternative.catalog_hash != USDCUSDT_TICK_CATALOG.catalog_hash
    assert alternative.absolute_distances_at(decision, (1,)) == (
        USDCUSDT_TICK_CATALOG.absolute_distances_at(decision, (1,))
    )


def test_static_model_keeps_absolute_high_across_tick_change() -> None:
    start = USDCUSDT_TICK_CHANGE - timedelta(minutes=1)
    end = USDCUSDT_TICK_CHANGE + timedelta(minutes=1)
    tape = SerialTape.from_events(
        [
            (start - timedelta(seconds=20), Decimal("0.9998")),
            (start - timedelta(seconds=19), Decimal("0.9999")),
            (start + timedelta(seconds=1), Decimal("0.9998")),
            (USDCUSDT_TICK_CHANGE + timedelta(seconds=1), Decimal("0.99981")),
            (USDCUSDT_TICK_CHANGE + timedelta(seconds=2), Decimal("0.9999")),
            (end - timedelta(microseconds=1), Decimal("0.9999")),
        ],
        tick_size=SERIAL_TAPE_QUANTUM,
        tick_catalog=USDCUSDT_TICK_CATALOG,
    )
    model = preregistered_corrected_block()[0].model_copy(update={"lookback_minutes": 10})

    result = replay_serial_model(
        tape,
        model,
        _historical_scenario(),
        start=start,
        end_exclusive=end,
        tick_catalog=USDCUSDT_TICK_CATALOG,
    )

    assert result.completed_cycles == 1
    assert result.cycles[0].high == Decimal("0.9999")
    assert result.cycles[0].tick_at_selection == Decimal("0.0001")
    assert result.reselection_count == 0


def test_adaptive_selection_uses_new_tick_only_at_next_decision() -> None:
    start = USDCUSDT_TICK_CHANGE - timedelta(minutes=1)
    end = USDCUSDT_TICK_CHANGE + timedelta(minutes=1)
    tape = SerialTape.from_events(
        [
            (start - timedelta(seconds=20), Decimal("0.9995")),
            (start - timedelta(seconds=19), Decimal("0.9996")),
            (USDCUSDT_FINE_GRID_OBSERVED_FROM, Decimal("0.99981")),
            (USDCUSDT_FINE_GRID_OBSERVED_FROM + timedelta(seconds=1), Decimal("0.99982")),
            (USDCUSDT_TICK_CHANGE + timedelta(seconds=1), Decimal("0.99981")),
            (USDCUSDT_TICK_CHANGE + timedelta(seconds=2), Decimal("0.99982")),
            (end - timedelta(microseconds=1), Decimal("0.99982")),
        ],
        tick_size=SERIAL_TAPE_QUANTUM,
        tick_catalog=USDCUSDT_TICK_CATALOG,
    )
    model = preregistered_corrected_block()[1].model_copy(
        update={"decision_interval_minutes": 1, "lookback_minutes": 10}
    )

    result = replay_serial_model(
        tape,
        model,
        _historical_scenario(),
        start=start,
        end_exclusive=end,
        tick_catalog=USDCUSDT_TICK_CATALOG,
    )

    assert result.completed_cycles == 1
    assert result.cycles[0].high - result.cycles[0].low == Decimal("0.00001")
    assert result.cycles[0].tick_at_selection == Decimal("0.00001")
    assert result.selection_changes[0].timestamp == USDCUSDT_TICK_CHANGE
    assert result.selection_changes[0].selected_tick_at_selection == Decimal("0.00001")


def test_price_outside_historical_grid_is_rejected_without_rounding() -> None:
    with pytest.raises(ValueError, match="incompatible"):
        SerialTape.from_events(
            [
                (
                    USDCUSDT_TICK_CHANGE - timedelta(hours=1),
                    Decimal("0.99949"),
                )
            ],
            tick_size=SERIAL_TAPE_QUANTUM,
            tick_catalog=USDCUSDT_TICK_CATALOG,
        )


def test_coarser_selection_grid_excludes_misaligned_high_score_candidate() -> None:
    grid_change = START + timedelta(minutes=10)
    catalog = TickCatalog(
        periods=(
            TickPeriod(
                start=START - timedelta(hours=1),
                end_exclusive=grid_change,
                tick_size=Decimal("0.00001"),
            ),
            TickPeriod(start=grid_change, tick_size=Decimal("0.0001")),
        )
    )
    start = grid_change + timedelta(minutes=1)
    end = start + timedelta(minutes=1)
    tape = SerialTape.from_events(
        [
            (grid_change - timedelta(minutes=2), Decimal("0.99981")),
            (grid_change - timedelta(minutes=2) + timedelta(seconds=1), Decimal("0.99991")),
            (grid_change - timedelta(minutes=1), Decimal("0.99981")),
            (grid_change - timedelta(minutes=1) + timedelta(seconds=1), Decimal("0.99991")),
            (grid_change - timedelta(seconds=2), Decimal("0.9998")),
            (grid_change - timedelta(seconds=1), Decimal("0.9999")),
            (start + timedelta(seconds=1), Decimal("0.9998")),
            (start + timedelta(seconds=2), Decimal("0.9999")),
            (end - timedelta(microseconds=1), Decimal("0.9999")),
        ],
        tick_size=SERIAL_TAPE_QUANTUM,
        tick_catalog=catalog,
    )
    model = preregistered_corrected_block()[0].model_copy(update={"lookback_minutes": 10})
    scenario = _historical_scenario().model_copy(
        update={
            "historical_tick_catalog_hash": catalog.catalog_hash,
            "historical_tick_source_url": catalog.source_url,
        }
    )

    result = replay_serial_model(
        tape,
        model,
        scenario,
        start=start,
        end_exclusive=end,
        tick_catalog=catalog,
    )

    assert result.completed_cycles == 1
    assert result.cycles[0].low == Decimal("0.9998")
    assert result.cycles[0].high == Decimal("0.9999")


def test_contained_cycles_matches_bruteforce_for_causal_windows() -> None:
    cases = (
        ([1, 2, 3, 10, 11, 20], [4, 5, 12, 13, 21]),
        ([1, 2, 10, 11, 12, 20], [3, 4, 13, 14, 21]),
        ([10, 11, 12, 30, 31], [1, 2, 3, 13, 14, 32]),
        # Distinct ordinals at equal timestamps are adjacent encoded events.
        ([100, 101, 300, 301, 500], [102, 103, 302, 303, 502]),
        ([1, 2, 3], []),
        ([], [1, 2, 3]),
    )
    for low_events, high_events in cases:
        timeline = CandidateTimeline(
            1,
            1,
            array("q", low_events),
            array("q", high_events),
        )
        timeline.build()
        for start in range(-1, 35):
            for end in range(start, 36):
                expected = _brute_contained_cycles(timeline, start, end)
                assert timeline.contained_cycles(start, end) == expected

    # Exhaustively exercise short LOW/HIGH patterns, including repeated runs.
    for mask in range(1, 1 << 8):
        lows = [index * 3 + 1 for index in range(8) if mask & (1 << index)]
        highs = [index * 3 + 2 for index in range(8) if not mask & (1 << index)]
        timeline = CandidateTimeline(1, 1, array("q", lows), array("q", highs))
        timeline.build()
        for start in range(-1, 26):
            for end in range(start, 27):
                assert timeline.contained_cycles(start, end) == _brute_contained_cycles(
                    timeline, start, end
                )


def _brute_contained_cycles(timeline: CandidateTimeline, start: int, end: int) -> int:
    low_index = bisect_left(timeline.low_events, start)
    high_index = bisect_left(timeline.high_events, start)
    after = start - 1
    count = 0
    while low_index < len(timeline.low_events):
        low_index = bisect_right(timeline.low_events, after, lo=low_index)
        if low_index >= len(timeline.low_events) or timeline.low_events[low_index] >= end:
            break
        entry = timeline.low_events[low_index]
        high_index = bisect_right(timeline.high_events, entry, lo=high_index)
        if high_index >= len(timeline.high_events) or timeline.high_events[high_index] >= end:
            break
        after = timeline.high_events[high_index]
        count += 1
        low_index += 1
        high_index += 1
    return count


def test_serial_cycle_uses_one_lot_and_never_reuses_one_event() -> None:
    tape = _tape(
        [
            (-120, "0.9998"),
            (-110, "0.9999"),
            (-100, "0.9998"),
            (-90, "0.9999"),
            (1, "0.9998"),
            (2, "0.9998"),
            (3, "0.9999"),
            (4, "0.9999"),
            (5, "0.9998"),
            (6, "0.9999"),
            (3_600, "1.0000"),
        ]
    )

    result = replay_serial_model(
        tape,
        _config(),
        _scenario(),
        start=START,
        end_exclusive=START + timedelta(minutes=59),
    )

    assert result.completed_cycles == 2
    assert result.cycles[0].entry_timestamp == START + timedelta(seconds=1)
    assert result.cycles[0].exit_timestamp == START + timedelta(seconds=3)
    assert result.cycles[1].entry_timestamp == START + timedelta(seconds=5)
    assert result.final_inventory == 0
    assert result.final_marked_equity > Decimal("100")
    assert result.execution_class == "PRICE_PATH_NOT_FILL_EVIDENCE"
    assert result.capacity_capped_final_capital is None


def test_open_cycle_is_carried_and_marked_without_time_stop() -> None:
    tape = _tape(
        [
            (-120, "0.9998"),
            (-110, "0.9999"),
            (1, "0.9998"),
            (3_500, "0.9997"),
            (3_600, "0.9997"),
        ]
    )

    result = replay_serial_model(
        tape,
        _config(),
        _scenario(),
        start=START,
        end_exclusive=START + timedelta(minutes=59),
    )

    assert result.completed_cycles == 0
    assert result.open_cycle_censored is True
    assert result.open_holding_seconds == Decimal("3539.0")
    assert result.final_inventory > 0
    assert result.unrealized_profit < 0


def test_selector_never_uses_boundary_or_future_events() -> None:
    tape = _tape(
        [
            (-120, "0.9998"),
            (-110, "0.9999"),
            (0, "1.0000"),
            (1, "1.0001"),
            (30, "0.9998"),
        ]
    )

    result = replay_serial_model(
        tape,
        _config(),
        _scenario(),
        start=START,
        end_exclusive=START + timedelta(seconds=20),
    )

    assert result.active_low == Decimal("0.9998")
    assert result.completed_cycles == 0


def test_same_timestamp_distinct_events_can_complete_but_one_event_cannot() -> None:
    timestamp = START - timedelta(seconds=30)
    tape = SerialTape.from_events(
        [
            (START - timedelta(minutes=2), Decimal("0.9998")),
            (START - timedelta(minutes=2) + timedelta(seconds=1), Decimal("0.9999")),
            (timestamp, Decimal("1.0000")),
            (timestamp, Decimal("1.0001")),
            (START + timedelta(seconds=1), Decimal("0.9998")),
            (START + timedelta(seconds=1), Decimal("0.9999")),
            (START + timedelta(minutes=1), Decimal("1.0000")),
        ],
        tick_size=TICK,
    )

    result = replay_serial_model(
        tape,
        _config(),
        _scenario(),
        start=START,
        end_exclusive=START + timedelta(seconds=30),
    )

    assert result.completed_cycles == 1
    assert result.cycles[0].entry_event < result.cycles[0].exit_event
    assert result.cycles[0].entry_timestamp == result.cycles[0].exit_timestamp


def test_fee_accounting_and_break_even_are_exact() -> None:
    low = Decimal("0.9998")
    high = Decimal("0.9999")
    break_even = symmetric_break_even_fee(low, high)

    assert abs(high * (1 - break_even) - low * (1 + break_even)) < Decimal("1e-27")
    with pytest.raises(ValueError):
        symmetric_break_even_fee(high, low)


def test_terminal_mark_excludes_future_prices() -> None:
    tape = _tape(
        [
            (-120, "0.9998"),
            (-110, "0.9999"),
            (1, "0.9998"),
            (20, "0.9997"),
            (30, "1.0001"),
        ]
    )

    result = replay_serial_model(
        tape,
        _config(),
        _scenario(),
        start=START,
        end_exclusive=START + timedelta(seconds=21),
    )

    assert result.last_price == Decimal("0.9997")
    assert result.daily_cycles == {START.date(): 0}


def test_replay_rejects_missing_physical_cutoff() -> None:
    tape = _tape([(-120, "0.9998"), (-110, "0.9999"), (10, "1.0000")])

    with pytest.raises(ValueError, match="physical event tape"):
        replay_serial_model(
            tape,
            _config(),
            _scenario(),
            start=START,
            end_exclusive=START + timedelta(days=1),
        )


def test_oracle_resets_flat_at_window_boundary_and_returns_exact_event_indexes() -> None:
    tape = _tape(
        [
            (-10, "0.9998"),
            (1, "0.9999"),
            (2, "0.9998"),
            (3, "0.9999"),
            (4, "0.9998"),
            (5, "0.9999"),
            (20, "1.0000"),
        ]
    )

    results = scan_oracle_cpu(
        tape,
        distances=(1,),
        start=START,
        end_exclusive=START + timedelta(seconds=10),
    )
    candidate = next(item for item in results if item.low_tick == 9_998)

    assert candidate.cycles == 2
    assert len(candidate.entry_events) == len(candidate.exit_events) == 2
    assert all(
        entry < exit_event
        for entry, exit_event in zip(candidate.entry_events, candidate.exit_events, strict=True)
    )


def test_periodic_selector_does_not_keep_stale_level_when_window_has_no_candidate() -> None:
    tape = _tape(
        [
            (-120, "0.9998"),
            (-110, "0.9999"),
            (120, "1.0005"),
        ]
    )
    config = _config(
        model_id="M002",
        parent_model_id="M001",
        strategy=SerialStrategy.PERIODIC_RESELECT,
        decision_interval_minutes=1,
        lookback_minutes=1,
    )

    result = replay_serial_model(
        tape,
        config,
        _scenario(),
        start=START,
        end_exclusive=START + timedelta(seconds=90),
    )

    assert result.completed_cycles == 0
    assert result.active_low is None
    assert result.final_inventory == 0


def test_idle_triggered_never_treats_waiting_high_as_idle() -> None:
    events = [
        (-120, "0.9998"),
        (-110, "0.9999"),
        (1, "0.9998"),
    ]
    for offset in range(60, 1_800, 20):
        events.extend(((offset, "1.0000"), (offset + 1, "1.0001")))
    events.append((2_000, "1.0002"))
    tape = _tape(events)
    config = _config(
        model_id="M004",
        parent_model_id="M003",
        strategy=SerialStrategy.IDLE_TRIGGERED,
        decision_interval_minutes=1,
        idle_threshold_minutes=5,
        confirmation_checks=2,
        switch_advantage=Decimal("0.10"),
        cooldown_minutes=1,
    )

    result = replay_serial_model(
        tape,
        config,
        _scenario(),
        start=START,
        end_exclusive=START + timedelta(minutes=30),
    )

    assert result.open_cycle_censored is True
    assert result.active_low == Decimal("0.9998")
    assert result.reselection_count == 0
    assert result.blocked_reselection_checks == 29


def test_idle_triggered_requires_continuous_flat_time_and_confirmations() -> None:
    events = [(-120, "0.9998"), (-110, "0.9999")]
    for offset in range(60, 1_800, 20):
        events.extend(((offset, "1.0000"), (offset + 1, "1.0001")))
    events.extend(((2_050, "1.0000"), (2_051, "1.0001"), (2_200, "1.0002")))
    tape = _tape(events)
    config = _config(
        model_id="M004",
        parent_model_id="M003",
        strategy=SerialStrategy.IDLE_TRIGGERED,
        decision_interval_minutes=1,
        idle_threshold_minutes=30,
        confirmation_checks=5,
        switch_advantage=Decimal("0.10"),
        cooldown_minutes=60,
    )

    first = replay_serial_model(
        tape,
        config,
        _scenario(),
        start=START,
        end_exclusive=START + timedelta(minutes=36),
    )
    repeated = replay_serial_model(
        tape,
        config,
        _scenario(),
        start=START,
        end_exclusive=START + timedelta(minutes=36),
    )

    assert first == repeated
    assert first.reselection_count == 1
    assert first.active_low == Decimal("1.0000")
    assert first.completed_cycles == 1


def test_relative_score_hysteresis_schema_requires_only_advantage() -> None:
    base = {
        "model_id": "M009",
        "parent_model_id": "M007",
        "strategy": SerialStrategy.RELATIVE_SCORE_HYSTERESIS,
        "decision_interval_minutes": 1,
        "switch_advantage": Decimal("0.10"),
        "lookback_minutes": 1_440,
    }
    config = SerialModelConfig.model_validate(base)

    assert config.strategy == SerialStrategy.RELATIVE_SCORE_HYSTERESIS
    assert config.switch_advantage == Decimal("0.10")
    for field in ("idle_threshold_minutes", "confirmation_checks", "cooldown_minutes"):
        with pytest.raises(ValueError, match="idle-control"):
            SerialModelConfig.model_validate({**base, field: 1})
    with pytest.raises(ValueError, match="requires switch_advantage"):
        SerialModelConfig.model_validate(
            {key: value for key, value in base.items() if key != "switch_advantage"}
        )


def test_relative_score_hysteresis_switches_only_above_strict_advantage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config(
        model_id="M009",
        parent_model_id="M007",
        strategy=SerialStrategy.RELATIVE_SCORE_HYSTERESIS,
        decision_interval_minutes=1,
        switch_advantage=Decimal("0.10"),
    )
    incumbent = (9_998, 1)
    challenger = (9_999, 1)

    def decide(current_score: Decimal, best_score: Decimal) -> tuple[int, int] | None:
        state = serial_replay._State(cash=Decimal("100"), candidate=incumbent)
        monkeypatch.setattr(serial_replay, "_select", lambda *args, **kwargs: challenger)
        monkeypatch.setattr(
            serial_replay,
            "_score",
            lambda candidate, *args, **kwargs: (
                current_score if candidate == incumbent else best_score
            ),
        )
        serial_replay._decision(
            state,
            {},
            config,
            now=0,
            lookback=1,
            tick_catalog=None,
            tape_quantum=TICK,
            observed_tick_evidence_event=None,
        )
        return state.candidate

    assert decide(Decimal("100"), Decimal("110")) == incumbent
    assert decide(Decimal("100"), Decimal("111")) == challenger
    assert decide(Decimal("0"), Decimal("0")) == incumbent
    assert decide(Decimal("0"), Decimal("1")) == challenger


def test_relative_score_hysteresis_preserves_missing_candidate_behavior(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config(
        model_id="M009",
        parent_model_id="M007",
        strategy=SerialStrategy.RELATIVE_SCORE_HYSTERESIS,
        decision_interval_minutes=1,
        switch_advantage=Decimal("0.10"),
    )
    incumbent = (9_998, 1)
    state = serial_replay._State(cash=Decimal("100"), candidate=incumbent)
    monkeypatch.setattr(serial_replay, "_select", lambda *args, **kwargs: None)

    serial_replay._decision(
        state,
        {},
        config,
        now=10,
        lookback=5,
        tick_catalog=None,
        tape_quantum=TICK,
        observed_tick_evidence_event=None,
    )

    assert state.candidate is None
    assert len(state.changes) == 1


def test_relative_score_hysteresis_reselects_immediately_after_exit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config(
        model_id="M009",
        parent_model_id="M007",
        strategy=SerialStrategy.RELATIVE_SCORE_HYSTERESIS,
        decision_interval_minutes=1,
        switch_advantage=Decimal("0.10"),
    )
    incumbent = (9_998, 1)
    challenger = (9_999, 1)
    timelines = {
        incumbent: CandidateTimeline(9_998, 1, array("q", [1]), array("q", [2])),
        challenger: CandidateTimeline(9_999, 1, array("q"), array("q")),
    }
    for timeline in timelines.values():
        timeline.build()
    state = serial_replay._State(
        cash=Decimal("100"),
        candidate=incumbent,
        candidate_tick_size=TICK,
    )
    monkeypatch.setattr(serial_replay, "_select", lambda *args, **kwargs: challenger)
    monkeypatch.setattr(
        serial_replay,
        "_score",
        lambda candidate, *args, **kwargs: (
            Decimal("2") if candidate == challenger else Decimal("1")
        ),
    )

    serial_replay._advance(
        state,
        timelines,
        config,
        _scenario(),
        start=0,
        end=3,
        recalculate_after_exit=True,
        tick_catalog=None,
        tape_quantum=TICK,
        observed_tick_evidence_event=None,
    )

    assert state.candidate == challenger
    assert state.changes[0][0] == 2


def test_relative_score_hysteresis_scores_only_the_causal_prefix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config(
        model_id="M009",
        parent_model_id="M007",
        strategy=SerialStrategy.RELATIVE_SCORE_HYSTERESIS,
        decision_interval_minutes=1,
        switch_advantage=Decimal("0.10"),
    )
    incumbent = (9_998, 1)
    challenger = (9_999, 1)
    state = serial_replay._State(cash=Decimal("100"), candidate=incumbent)
    observed: list[tuple[int, int]] = []
    monkeypatch.setattr(serial_replay, "_select", lambda *args, **kwargs: challenger)

    def score(
        candidate: tuple[int, int] | None, _timelines: object, _config: object, start: int, end: int
    ) -> Decimal:
        observed.append((start, end))
        return Decimal("2") if candidate == challenger else Decimal("1")

    monkeypatch.setattr(serial_replay, "_score", score)
    serial_replay._decision(
        state,
        {},
        config,
        now=100,
        lookback=10,
        tick_catalog=None,
        tape_quantum=TICK,
        observed_tick_evidence_event=None,
    )

    assert observed == [(90, 100), (90, 100)]


def test_relative_score_hysteresis_uses_real_causal_timeline_scores() -> None:
    items: list[tuple[int, str]] = []
    for index in range(10):
        items.extend(((-300 + index * 2, "0.9990"), (-299 + index * 2, "0.9991")))
    for index in range(9):
        items.extend(((-200 + index * 2, "1.0010"), (-199 + index * 2, "1.0011")))
    items.extend(((1, "1.0010"), (2, "1.0011"), (3, "1.0010"), (4, "1.0011")))
    items.append((61, "1.0020"))
    tape = _tape(items)
    common = {
        "decision_interval_minutes": 1,
        "lookback_minutes": 10,
    }
    m007 = _config(
        model_id="M007",
        parent_model_id="M006",
        strategy=SerialStrategy.ALWAYS_BEST,
        **common,
    )
    m009 = _config(
        model_id="M009",
        parent_model_id="M007",
        strategy=SerialStrategy.RELATIVE_SCORE_HYSTERESIS,
        switch_advantage=Decimal("0.10"),
        **common,
    )

    always_best = replay_serial_model(
        tape,
        m007,
        _scenario(),
        start=START,
        end_exclusive=START + timedelta(seconds=61),
    )
    hysteresis = replay_serial_model(
        tape,
        m009,
        _scenario(),
        start=START,
        end_exclusive=START + timedelta(seconds=61),
    )

    assert always_best.active_low == Decimal("1.0010")
    assert hysteresis.active_low == Decimal("0.9990")
    assert always_best.completed_cycles == hysteresis.completed_cycles == 0


def test_relative_score_hysteresis_keeps_open_band_across_tick_change() -> None:
    start = USDCUSDT_TICK_CHANGE - timedelta(seconds=2)
    end = start + timedelta(minutes=2)
    tape = SerialTape.from_events(
        [
            (start - timedelta(seconds=20), Decimal("1.0000")),
            (start - timedelta(seconds=19), Decimal("1.0001")),
            (start - timedelta(seconds=10), Decimal("1.0000")),
            (start - timedelta(seconds=9), Decimal("1.0001")),
            (start + timedelta(milliseconds=500), Decimal("1.0000")),
            (USDCUSDT_TICK_CHANGE + timedelta(milliseconds=100), Decimal("1.00002")),
            (USDCUSDT_TICK_CHANGE + timedelta(milliseconds=200), Decimal("1.00003")),
            (USDCUSDT_TICK_CHANGE + timedelta(seconds=30), Decimal("1.00002")),
            (USDCUSDT_TICK_CHANGE + timedelta(seconds=31), Decimal("1.00003")),
            (end, Decimal("1.00002")),
        ],
        tick_size=SERIAL_TAPE_QUANTUM,
        tick_catalog=USDCUSDT_TICK_CATALOG,
    )
    config = _config(
        model_id="M009",
        parent_model_id="M007",
        strategy=SerialStrategy.RELATIVE_SCORE_HYSTERESIS,
        distances=(1,),
        decision_interval_minutes=1,
        lookback_minutes=10,
        switch_advantage=Decimal("0.10"),
        distance_semantics="ONE_EXCHANGE_TICK_AT_LEVEL_SELECTION",
        selection_moment="AT_LEVEL_SELECTION",
        tick_source="BINANCE_ANNOUNCEMENT_PLUS_CAUSAL_TRADE_PREFIX",
        tick_evidence_class="OBSERVED_ACCEPTED_GRID",
        selected_levels_remain_absolute=True,
    )

    result = replay_serial_model(
        tape,
        config,
        _historical_scenario(),
        start=start,
        end_exclusive=end,
        tick_catalog=USDCUSDT_TICK_CATALOG,
    )

    assert result.open_cycle_censored is True
    assert result.open_entry_price == Decimal("1.0000")
    assert result.active_low == Decimal("1.0000")
    assert result.active_high == Decimal("1.0001")
    assert result.blocked_reselection_checks == 1


def test_relative_score_hysteresis_keeps_absolute_candidate_endpoints(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config(
        model_id="M009",
        parent_model_id="M007",
        strategy=SerialStrategy.RELATIVE_SCORE_HYSTERESIS,
        decision_interval_minutes=1,
        switch_advantage=Decimal("0"),
    )
    incumbent = (99_981, 10)
    challenger = (99_981, 1)
    state = serial_replay._State(cash=Decimal("100"), candidate=incumbent)
    monkeypatch.setattr(serial_replay, "_select", lambda *args, **kwargs: challenger)
    monkeypatch.setattr(
        serial_replay,
        "_score",
        lambda candidate, *args, **kwargs: (
            Decimal("2") if candidate == challenger else Decimal("1")
        ),
    )

    serial_replay._decision(
        state,
        {},
        config,
        now=0,
        lookback=1,
        tick_catalog=None,
        tape_quantum=TICK,
        observed_tick_evidence_event=None,
    )

    assert state.candidate == challenger


def test_manifest_tape_loader_accepts_only_active_valid_campaign(tmp_path: Path) -> None:
    archive = tmp_path / "USDCUSDT-trades-2026-01-01.zip"
    first_raw = int(START.timestamp() * 1_000_000)
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr(
            "USDCUSDT-trades-2026-01-01.csv",
            f"1,0.9998,1,0,{first_raw},true,true\n"
            f"2,0.9999,1,0,{first_raw + 1_000_000},false,true\n",
        )
    events = parse_archive(archive, "trades")
    item = manifest_for(
        archive,
        events,
        origin="official-fixture",
        period="2026-01-01",
        symbol="USDCUSDT",
        kind="trades",
    )
    manifest = HistoryManifest(
        symbol="USDCUSDT",
        kind="trades",
        requested_start=START.date(),
        requested_end=START.date(),
        all_available=False,
        discovered_first_date=START.date(),
        discovered_last_date=START.date(),
        archives=(item,),
        missing_dates=(),
        cross_archive_gaps=(),
        cross_archive_overlaps=(),
        total_records=2,
        total_size_bytes=item.size_bytes,
        first_timestamp=item.first_timestamp,
        last_timestamp=item.last_timestamp,
        dataset_hash="verified-by-caller",
        integrity_status="VALID",
    )

    tape = load_serial_tape(
        manifest,
        tick_size=TICK,
        start=START,
        end_exclusive=events[-1].timestamp + timedelta(microseconds=1),
    )

    assert len(tape.events) == 2
    with pytest.raises(ValueError, match="VALID"):
        load_serial_tape(
            manifest.model_copy(
                update={"integrity_status": "INVALID", "invalidity_reasons": ("gap",)}
            ),
            tick_size=TICK,
            start=START,
            end_exclusive=events[-1].timestamp + timedelta(microseconds=1),
        )
