from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import numpy as np

from crypto_strategy_lab.data.temporal import TemporalMarketData
from crypto_strategy_lab.domain import Candle
from crypto_strategy_lab.ml.candidate_workflow import (
    _candidate_environment_config,
    _summarize,
    _write_evaluation_artifact,
)
from crypto_strategy_lab.ml.evaluation import EvaluationResult
from crypto_strategy_lab.ml.policies import CashPolicy, CostAwareMomentum24hPolicy

SYMBOLS = ("BTCUSDT", "ETHUSDT", "SHIBUSDT", "BNBUSDT")
MAPPING = {
    "0": "USDT",
    "1": "BTCUSDT",
    "2": "ETHUSDT",
    "3": "SHIBUSDT",
    "4": "BNBUSDT",
}


def _candles(momentum: dict[str, Decimal]) -> tuple[list[Candle], datetime]:
    decision_time = datetime(2022, 1, 2, 4, tzinfo=UTC)
    start = decision_time - timedelta(hours=24, minutes=5)
    candles: list[Candle] = []
    for symbol in SYMBOLS:
        change = momentum[symbol]
        for index in range(289):
            open_time = start + index * timedelta(minutes=5)
            close_time = open_time + timedelta(minutes=5) - timedelta(milliseconds=1)
            price = Decimal("100") * (1 + change * Decimal(index) / Decimal(288))
            candles.append(
                Candle(
                    symbol=symbol,
                    open_time=open_time,
                    close_time=close_time,
                    available_at=close_time,
                    open=price,
                    high=price,
                    low=price,
                    close=price,
                    volume=Decimal("1"),
                    quote_asset_volume=price,
                    trade_count=1,
                )
            )
    return candles, decision_time


def _info(
    decision_time: datetime,
    *,
    position: str = "USDT",
    mask: list[bool] | None = None,
) -> dict[str, object]:
    return {
        "simulated_time": decision_time.isoformat(),
        "available_data_until": (decision_time - timedelta(microseconds=1)).isoformat(),
        "position": position,
        "action_mapping": MAPPING,
        "action_mask": mask or [True] * 5,
    }


def test_candidate_uses_exact_causal_24h_window_and_ignores_future() -> None:
    candles, decision_time = _candles(
        {
            "BTCUSDT": Decimal("0.01"),
            "ETHUSDT": Decimal("0.02"),
            "SHIBUSDT": Decimal("0.015"),
            "BNBUSDT": Decimal("-0.01"),
        }
    )
    observation = np.zeros(1, dtype=np.float32)
    before = CostAwareMomentum24hPolicy(TemporalMarketData(candles)).predict(
        observation, _info(decision_time)
    )
    future = [
        item.model_copy(
            update={
                "open_time": item.open_time + timedelta(days=2),
                "close_time": item.close_time + timedelta(days=2),
                "available_at": item.available_at + timedelta(days=2),
                "open": item.open * 100,
                "high": item.high * 100,
                "low": item.low * 100,
                "close": item.close * 100,
            }
        )
        for item in candles[-4:]
    ]
    after = CostAwareMomentum24hPolicy(TemporalMarketData([*candles, *future])).predict(
        observation, _info(decision_time)
    )
    assert before == after == 2


def test_candidate_holds_between_decision_times_and_respects_action_mask() -> None:
    candles, decision_time = _candles(
        {
            "BTCUSDT": Decimal("0.01"),
            "ETHUSDT": Decimal("0.02"),
            "SHIBUSDT": Decimal("0.015"),
            "BNBUSDT": Decimal("0.012"),
        }
    )
    policy = CostAwareMomentum24hPolicy(TemporalMarketData(candles))
    observation = np.zeros(1, dtype=np.float32)
    assert (
        policy.predict(
            observation,
            _info(decision_time + timedelta(minutes=15), position="BNBUSDT"),
        )
        == 4
    )
    assert (
        policy.predict(
            observation,
            _info(decision_time, mask=[True, True, False, True, True]),
        )
        == 3
    )


def test_candidate_switch_exit_tie_and_incomplete_window_are_deterministic() -> None:
    observation = np.zeros(1, dtype=np.float32)
    rising, decision_time = _candles(
        {
            "BTCUSDT": Decimal("0.01"),
            "ETHUSDT": Decimal("0.01"),
            "SHIBUSDT": Decimal("0.02"),
            "BNBUSDT": Decimal("0.02"),
        }
    )
    rising_policy = CostAwareMomentum24hPolicy(TemporalMarketData(rising))
    assert rising_policy.predict(observation, _info(decision_time)) == 3
    assert rising_policy.predict(observation, _info(decision_time, position="ETHUSDT")) == 3

    falling, falling_time = _candles(
        {
            "BTCUSDT": Decimal("-0.01"),
            "ETHUSDT": Decimal("0.01"),
            "SHIBUSDT": Decimal("0.02"),
            "BNBUSDT": Decimal("0.03"),
        }
    )
    assert (
        CostAwareMomentum24hPolicy(TemporalMarketData(falling)).predict(
            observation, _info(falling_time, position="ETHUSDT")
        )
        == 0
    )

    incomplete = [
        item
        for item in rising
        if not (item.symbol == "BTCUSDT" and item.open_time == rising[1].open_time)
    ]
    incomplete_policy = CostAwareMomentum24hPolicy(TemporalMarketData(incomplete))
    assert incomplete_policy.predict(observation, _info(decision_time)) == 0
    assert incomplete_policy.decisions[-1]["unavailable_reason"].startswith("INCOMPLETE")


def test_candidate_capital_exposure_costs_and_controls_are_frozen() -> None:
    config = _candidate_environment_config(30)
    assert config.initial_capital == Decimal("100")
    assert config.max_exposure == Decimal("0.75")
    assert config.reserve_ratio == Decimal("0.25")
    assert config.costs.fee_rate == Decimal("0.001")
    assert config.costs.spread_rate == Decimal("0.0002")
    assert config.costs.slippage_rate == Decimal("0.0003")
    assert config.controls.enabled
    assert config.episode_duration == timedelta(days=30)


def test_candidate_artifact_is_byte_reproducible(tmp_path) -> None:
    result = EvaluationResult(
        policy="cash",
        seed=11,
        episode_start="2022-01-01T00:00:00+00:00",
        episode_end="2022-01-31T00:00:00+00:00",
        actions=[0],
        transitions=[{"simulated_time": "2022-01-01T00:00:00+00:00"}],
        final_equity_usdt=Decimal("100"),
        total_reward=Decimal("0"),
        terminated=False,
        truncated=True,
    )
    path, first_hash = _write_evaluation_artifact(
        tmp_path, "a" * 64, "TRAIN_30D_1", 11, CashPolicy(), result
    )
    first_bytes = path.read_bytes()
    repeated_path, repeated_hash = _write_evaluation_artifact(
        tmp_path, "a" * 64, "TRAIN_30D_1", 11, CashPolicy(), result
    )
    assert repeated_path == path
    assert repeated_hash == first_hash
    assert repeated_path.read_bytes() == first_bytes


def test_repeated_current_position_is_hold_not_rejection(tmp_path) -> None:
    transition = {
        "position": "USDT",
        "costs_usdt": "0",
        "turnover": "0",
        "drawdown": "0",
        "fills": [],
        "failures": [],
        "requested_action": 0,
        "effective_action": 0,
        "avoided_operation_reason": "REPEATED_CURRENT_POSITION",
    }
    result = EvaluationResult(
        policy="cash",
        seed=11,
        episode_start="2022-01-01T00:00:00+00:00",
        episode_end="2022-01-01T00:15:00+00:00",
        actions=[0],
        transitions=[transition],
        final_equity_usdt=Decimal("100"),
        total_reward=Decimal("0"),
        terminated=False,
        truncated=True,
    )

    summary = _summarize(
        result,
        period_name="TRAIN_30D_1",
        period_kind="PRIMARY_NON_OVERLAPPING",
        artifact_path=tmp_path / "artifact.json.gz",
        artifact_hash="a" * 64,
        candidate_decisions=[],
    )

    assert summary["rejected_requests"] == 0
