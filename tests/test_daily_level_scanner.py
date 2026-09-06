from array import array
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from crypto_strategy_lab.microstructure.level_scanner import (
    CandidateTimeline,
    CausalConfig,
    CausalState,
    DayEvents,
    PriceStats,
    _advance_state,
    _datetime_to_micros,
    _evaluate_config,
    _oracle_day,
    _select_candidate,
)


def _day(prices: list[int]) -> DayEvents:
    stats: dict[int, PriceStats] = {}
    previous = None
    for price in prices:
        item = stats.setdefault(price, PriceStats())
        item.trade_count += 1
        item.volume += Decimal("1")
        if price != previous:
            item.visit_count += 1
        previous = price
    return DayEvents(
        utc_date=date(2026, 1, 1),
        timestamps=array("q", range(1, len(prices) + 1)),
        prices=array("i", prices),
        quantities=[Decimal("1")] * len(prices),
        stats=stats,
    )


def test_oracle_counts_one_serial_lot_and_ranks_by_cycles_then_margin():
    result, _price_map = _oracle_day(_day([9988, 9988, 9989, 9988, 9989, 9989]))

    assert result.best is not None
    assert result.best.low == Decimal("0.9988")
    assert result.best.high == Decimal("0.9989")
    assert result.best.cycles == 2
    assert result.best.low_trade_count == 3
    assert result.best.high_trade_count == 3


def test_oracle_zero_day_is_not_omitted():
    result, _price_map = _oracle_day(_day([9988, 9988, 9988]))

    assert result.best is None
    assert result.top10 == ()
    assert result.zero_reason == "NO_ASCENDING_CYCLE"


def test_causal_score_excludes_future_and_boundary_event():
    timeline = CandidateTimeline(
        low_times=array("q", [10, 30]),
        high_times=array("q", [20, 40]),
    )
    timeline.build_cycles()
    config = CausalConfig(
        lookback_minutes=30,
        operating_minutes=15,
        distances=(1,),
        score="FREQUENCY",
    )

    assert _select_candidate(config, {(9988, 1): timeline}, start=0, end=20) is None
    assert _select_candidate(config, {(9988, 1): timeline}, start=0, end=21) == (9988, 1)
    assert _select_candidate(config, {(9988, 1): timeline}, start=21, end=40) is None


def test_pending_reselection_never_reprices_open_position():
    original = CandidateTimeline(array("q", [10]), array("q", [80]))
    original.build_cycles()
    replacement = CandidateTimeline(array("q", [30, 90]), array("q", [40, 100]))
    replacement.build_cycles()
    state = CausalState(active=(9988, 1))
    timelines = {(9988, 1): original, (9990, 1): replacement}

    _advance_state(state, timelines, 0, 50)
    assert state.entry_time == 10
    state.pending = (9990, 1)
    state.has_pending = True
    _advance_state(state, timelines, 50, 110)

    assert len(state.cycles) == 2
    assert state.cycles[0][2:4] == (9988, 1)
    assert state.cycles[1][2:4] == (9990, 1)


def test_causal_daily_snapshot_is_recorded_at_utc_midnight():
    start = date(2026, 1, 1)
    origin = _datetime_to_micros(datetime(2026, 1, 1, tzinfo=UTC)) * 4096
    minute = 60 * 1_000_000 * 4096
    timeline = CandidateTimeline(
        array("q", [origin - 20 * minute, origin + 10 * minute]),
        array("q", [origin - 10 * minute, origin + 20 * minute]),
    )
    timeline.build_cycles()
    result = _evaluate_config(
        CausalConfig(
            lookback_minutes=30,
            operating_minutes=360,
            distances=(1,),
            score="FREQUENCY",
        ),
        {(9988, 1): timeline},
        {start: 1},
        {start: 9989},
        start=start,
        end=start + timedelta(days=1),
        include_daily=True,
    )

    assert len(result["daily"]) == 1
    assert result["daily"][0].utc_date == start
