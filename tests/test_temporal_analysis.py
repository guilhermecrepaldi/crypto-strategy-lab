from datetime import UTC, datetime, timedelta
from decimal import Decimal

from crypto_strategy_lab.microstructure.serial_replay import (
    SerialModelConfig,
    SerialScenarioConfig,
    SerialStrategy,
    SerialTape,
    replay_serial_model,
)
from crypto_strategy_lab.microstructure.temporal_analysis import (
    analyze_market_productivity_regime,
    analyze_replay_temporally,
)

START = datetime(2026, 1, 1, tzinfo=UTC)
TICK = Decimal("0.0001")


def _replay(events: list[tuple[datetime, Decimal]], *, end: datetime) -> tuple[object, SerialTape]:
    tape = SerialTape.from_events(events, tick_size=TICK)
    result = replay_serial_model(
        tape,
        SerialModelConfig(
            model_id="M001",
            parent_model_id=None,
            strategy=SerialStrategy.STATIC,
            lookback_minutes=10,
        ),
        SerialScenarioConfig(tick_size=TICK),
        start=START,
        end_exclusive=end,
    )
    return result, tape


def test_temporal_ledger_reconciles_full_replay_without_resetting_months() -> None:
    end = START + timedelta(days=2)
    events = [
        (START - timedelta(minutes=2), Decimal("0.9998")),
        (START - timedelta(minutes=1), Decimal("0.9999")),
        (START + timedelta(seconds=1), Decimal("0.9998")),
        (START + timedelta(seconds=2), Decimal("0.9999")),
        (START + timedelta(days=1, seconds=1), Decimal("0.9998")),
        (START + timedelta(days=1, seconds=3), Decimal("0.9999")),
        (end, Decimal("1.0000")),
    ]
    result, tape = _replay(events, end=end)
    analysis = analyze_replay_temporally(result, tape)  # type: ignore[arg-type]

    assert len(analysis.daily) == 2
    assert (
        sum((Decimal(str(item["mtm_delta"])) for item in analysis.daily), Decimal("0"))
        == result.final_marked_equity - result.initial_quote
    )  # type: ignore[attr-defined]
    assert analysis.monthly[0]["complete"] is False
    assert analysis.monthly[0]["completed_cycles"] == 2
    assert Decimal(analysis.monthly[0]["start_equity"]) == Decimal("100")
    assert Decimal(analysis.monthly[0]["end_equity"]) == result.final_marked_equity  # type: ignore[attr-defined]
    assert analysis.monthly[0]["zero_cycle_days"] == 0
    assert analysis.concentration["daily"]["all_periods"]["net"] == (
        result.final_marked_equity - result.initial_quote  # type: ignore[attr-defined]
    )


def test_long_open_position_is_cold_not_failure_or_time_stop() -> None:
    end = START + timedelta(hours=6)
    events = [
        (START - timedelta(minutes=2), Decimal("0.9998")),
        (START - timedelta(minutes=1), Decimal("0.9999")),
        (START + timedelta(seconds=1), Decimal("0.9998")),
        (end - timedelta(seconds=1), Decimal("0.9998")),
        (end, Decimal("0.9998")),
    ]
    result, tape = _replay(events, end=end)
    analysis = analyze_replay_temporally(result, tape)  # type: ignore[arg-type]
    hourly = analysis.horizons[0]

    assert result.open_cycle_censored is True  # type: ignore[attr-defined]
    assert result.completed_cycles == 0  # type: ignore[attr-defined]
    assert all(item.classification == "COLD" for item in hourly.blocks)
    assert all(item.classification != "FAILURE" for item in hourly.blocks)
    assert analysis.regime_contrasts["hourly_classification_contrast"]["COLD"]["hours"] == 6
    assert analysis.data_support["queue_ahead"] == "UNKNOWN"
    assert analysis.data_support["fills_partial_fills"] == "UNKNOWN_PRICE_PATH_ONLY"


def test_horizon_rankings_use_independent_blocks_and_rolling_is_hourly() -> None:
    end = START + timedelta(hours=10)
    events = [
        (START - timedelta(minutes=2), Decimal("0.9998")),
        (START - timedelta(minutes=1), Decimal("0.9999")),
    ]
    for hour in range(10):
        events.extend(
            [
                (START + timedelta(hours=hour, seconds=1), Decimal("0.9998")),
                (START + timedelta(hours=hour, seconds=2), Decimal("0.9999")),
            ]
        )
    events.append((end, Decimal("1.0000")))
    result, tape = _replay(events, end=end)
    analysis = analyze_replay_temporally(result, tape)  # type: ignore[arg-type]
    four_hours = next(item for item in analysis.horizons if item.horizon_hours == 4)

    assert len(four_hours.blocks) == 2
    assert four_hours.incomplete_tail is not None
    assert four_hours.incomplete_tail.complete is False
    assert len(four_hours.rolling) == 7
    assert four_hours.top_bottom_overlap is True
    assert all(item.complete for item in four_hours.top10)
    assert analysis.temporal_stability["aggregate"] is None


def test_market_regime_requires_three_distinct_comparable_models() -> None:
    end = START + timedelta(hours=6)
    events = [
        (START - timedelta(minutes=2), Decimal("0.9998")),
        (START - timedelta(minutes=1), Decimal("0.9999")),
        (START + timedelta(seconds=1), Decimal("0.9998")),
        (START + timedelta(seconds=2), Decimal("0.9999")),
        (end, Decimal("1.0000")),
    ]
    result, tape = _replay(events, end=end)
    first = analyze_replay_temporally(result, tape)  # type: ignore[arg-type]
    cohort = analyze_market_productivity_regime(
        [
            first,
            first.model_copy(update={"model_id": "M002"}),
            first.model_copy(update={"model_id": "M003"}),
        ],
        dataset_hash="dataset",
        scenario_hash="scenario",
        horizon_hours=1,
    )

    assert cohort.model_ids == ("M001", "M002", "M003")
    assert cohort.required_consensus == 2
    assert all(item["classification"].startswith("CONSENSUS_") for item in cohort.blocks)
