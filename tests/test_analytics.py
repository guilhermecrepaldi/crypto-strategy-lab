from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from crypto_strategy_lab.analytics.dashboard import render_dashboard
from crypto_strategy_lab.analytics.divergence import (
    analyze_divergence,
    causal_divergence_features,
)
from crypto_strategy_lab.analytics.schemas import (
    CostBreakdownReport,
    ReportProvenance,
    TurnoverDiagnosticReport,
)
from crypto_strategy_lab.analytics.walk_forward import WalkForwardPlan
from crypto_strategy_lab.domain import Candle
from crypto_strategy_lab.simulation.portfolio import ExecutionCosts


def _provenance(policy: str = "test") -> ReportProvenance:
    return ReportProvenance(
        dataset_hash="a" * 64,
        period_start="2022-01-01T00:00:00+00:00",
        period_end="2022-01-01T05:00:00+00:00",
        timeframe="15m",
        symbols=["BNBUSDT", "BTCUSDT", "ETHUSDT", "SHIBUSDT"],
        configuration={"scenario": "unit"},
        seed=11,
        policy=policy,
        execution_costs={"fee_rate": "0.001", "spread_rate": "0.0002", "slippage_rate": "0.0003"},
        code_version="deadbeef",
        partition="TRAIN",
    )


def _market() -> list[Candle]:
    start = datetime(2022, 1, 1, tzinfo=UTC)
    values = {
        "BTCUSDT": Decimal("100"),
        "ETHUSDT": Decimal("50"),
        "SHIBUSDT": Decimal("10"),
        "BNBUSDT": Decimal("30"),
    }
    result: list[Candle] = []
    for index in range(60):
        bucket = index // 3
        btc_move = Decimal("1.01") if bucket % 2 == 0 else Decimal("0.99")
        if index % 3 == 0 and index > 0:
            values["BTCUSDT"] *= btc_move
            values["ETHUSDT"] *= btc_move
            values["SHIBUSDT"] *= Decimal("2") - btc_move
            values["BNBUSDT"] *= Decimal("1.002") if bucket % 3 else Decimal("0.998")
        for symbol, value in values.items():
            open_time = start + timedelta(minutes=5 * index)
            result.append(
                Candle(
                    symbol=symbol,
                    open_time=open_time,
                    close_time=open_time + timedelta(minutes=5) - timedelta(milliseconds=1),
                    available_at=open_time + timedelta(minutes=5),
                    open=value,
                    high=value,
                    low=value,
                    close=value,
                    volume=Decimal("1"),
                    quote_asset_volume=value,
                    trade_count=1,
                )
            )
    return result


def test_divergence_perfect_correlation_inverse_and_zero_policy() -> None:
    report = analyze_divergence(
        _market(),
        start=datetime(2022, 1, 1, tzinfo=UTC),
        end=datetime(2022, 1, 1, 5, tzinfo=UTC),
        timeframe_minutes=15,
        provenance=_provenance(),
        costs=ExecutionCosts(),
    )
    btc_eth = next(
        item for item in report.pairwise if {item["left"], item["right"]} == {"BTCUSDT", "ETHUSDT"}
    )
    btc_shib = next(
        item for item in report.pairwise if {item["left"], item["right"]} == {"BTCUSDT", "SHIBUSDT"}
    )
    assert btc_eth["pearson_simple"] == pytest.approx(1.0)
    assert btc_eth["opposite_direction_percent"] == 0
    assert btc_shib["pearson_simple"] < -0.99
    assert btc_shib["opposite_direction_percent"] == 100
    assert report.alignment["neutral_return_policy"].startswith("zero is neutral")


def test_divergence_rejects_unaligned_gap() -> None:
    candles = _market()
    missing_time = datetime(2022, 1, 1, 1, 5, tzinfo=UTC)
    candles = [
        item
        for item in candles
        if not (item.symbol == "ETHUSDT" and item.open_time == missing_time)
    ]
    with pytest.raises(ValueError, match="unaligned timestamps"):
        analyze_divergence(
            candles,
            start=datetime(2022, 1, 1, tzinfo=UTC),
            end=datetime(2022, 1, 1, 5, tzinfo=UTC),
            timeframe_minutes=15,
            provenance=_provenance(),
            costs=ExecutionCosts(),
        )


def test_causal_divergence_features_ignore_future_data() -> None:
    candles = _market()
    cutoff = datetime(2022, 1, 1, 4, tzinfo=UTC)
    before = causal_divergence_features(candles, simulated_time=cutoff)
    changed_future = [
        item.model_copy(update={"close": item.close * 100, "high": item.high * 100})
        if item.available_at >= cutoff
        else item
        for item in candles
    ]
    after = causal_divergence_features(changed_future, simulated_time=cutoff)
    assert before == after
    assert datetime.fromisoformat(before["maximum_source_available_at"]) < cutoff


def test_dashboard_is_deterministic_offline_and_escapes_dynamic_content() -> None:
    report = TurnoverDiagnosticReport(
        run_id="run-1",
        provenance=_provenance('</script><img src=x onerror="alert(1)">'),
        costs=CostBreakdownReport(
            initial_equity_usdt="80",
            final_equity_usdt="79",
            costless_final_equity_usdt="80",
            market_return_percent={"BTCUSDT": "1"},
            gross_pnl_usdt="0",
            net_pnl_usdt="-1",
            loss_exclusively_from_costs_usdt="1",
            direct_fees_usdt="0.5",
            direct_spread_usdt="0.1",
            direct_slippage_usdt="0.4",
            direct_costs_usdt="1",
            reconciliation_difference_usdt="0",
            conservation_error_usdt="0",
            per_asset_realized_pnl_usdt={},
            per_asset_costs_usdt={},
            ruin_reason=None,
        ),
        buys=1,
        sells=0,
        rotations=0,
        operations=1,
        avoided_operations={"REPEATED_CURRENT_POSITION": 3},
        total_turnover="0.75",
        average_position_duration_steps="3",
        average_exposure_ratio="0.75",
        time_in_usdt_ratio="0",
        max_drawdown="0.01",
        terminated=False,
        truncated=True,
        warning="offline smoke",
        transitions=[
            {
                "simulated_time": "2022-01-01T00:15:00+00:00",
                "equity_usdt": "79",
            }
        ],
    )
    first = render_dashboard(report)
    second = render_dashboard(report)
    assert first == second
    assert "https://" not in first and "http://" not in first
    assert "</script><img" not in first
    assert "&lt;/script&gt;&lt;img" in first
    assert "LOCKED_TEST" in first


def test_walk_forward_is_preparation_only() -> None:
    with pytest.raises(ValueError, match="outside the current gate"):
        WalkForwardPlan(
            start=datetime(2022, 1, 1, tzinfo=UTC),
            end=datetime(2022, 7, 1, tzinfo=UTC),
            execute=True,
        )
