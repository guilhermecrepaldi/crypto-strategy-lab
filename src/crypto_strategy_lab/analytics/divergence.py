from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from itertools import combinations
from typing import Any

import numpy as np

from crypto_strategy_lab.analytics.schemas import DivergenceReport, ReportProvenance
from crypto_strategy_lab.data.aggregation import aggregate_candles
from crypto_strategy_lab.domain import Candle, require_utc
from crypto_strategy_lab.ml.controls import estimated_rotation_cost_rate
from crypto_strategy_lab.simulation.portfolio import ExecutionCosts


def analyze_divergence(
    candles_5m: list[Candle],
    *,
    start: datetime,
    end: datetime,
    timeframe_minutes: int,
    provenance: ReportProvenance,
    costs: ExecutionCosts,
) -> DivergenceReport:
    start, end = require_utc(start), require_utc(end)
    if timeframe_minutes not in {15, 30, 60}:
        raise ValueError("divergence timeframe must be 15m, 30m or 1h")
    candles = [
        item
        for item in aggregate_candles(candles_5m, timeframe_minutes)
        if start <= item.open_time < end
    ]
    symbols, times, closes = _aligned_closes(candles)
    if "BTCUSDT" not in symbols:
        raise ValueError("BTCUSDT is required as the divergence reference")
    simple = {symbol: _simple_returns(values) for symbol, values in closes.items()}
    pairwise = [
        _pair_metrics(left, right, simple[left], simple[right])
        for left, right in combinations(symbols, 2)
    ]
    contexts = _rolling_context(simple, timeframe_minutes)
    strong = _strong_event_analysis(
        candles_5m,
        start=start,
        end=end,
        symbols=symbols,
        main_returns=simple,
        costs=costs,
    )
    relative = _relative_strength(times, closes, simple, timeframe_minutes)
    feature_rows = causal_divergence_features(
        candles_5m,
        simulated_time=end,
        timeframe_minutes=timeframe_minutes,
    )
    return DivergenceReport(
        provenance=provenance,
        alignment={
            "start": start.isoformat(),
            "end": end.isoformat(),
            "timestamps": len(times),
            "return_rows": len(times) - 1,
            "missing_aligned_rows": 0,
            "neutral_return_policy": "zero is neutral and excluded from directional denominator",
            "first_timestamp": times[0].isoformat(),
            "last_timestamp": times[-1].isoformat(),
        },
        pairwise=pairwise,
        rolling_context=contexts,
        strong_btc_events=strong,
        relative_strength=relative,
        causal_feature_contract={
            "observation_cutoff": end.isoformat(),
            "maximum_source_available_at": feature_rows["maximum_source_available_at"],
            "uses_post_event_outcomes": False,
            "ranking_rule": "trailing close return through t-1 only",
        },
        post_event_analysis={
            "separate_from_agent_observation": True,
            "lead_lag": {
                symbol: _lead_lag(simple["BTCUSDT"], simple[symbol])
                for symbol in symbols
                if symbol != "BTCUSDT"
            },
            "event_outcomes": strong["post_event_outcomes"],
        },
    )


def causal_divergence_features(
    candles_5m: list[Candle],
    *,
    simulated_time: datetime,
    timeframe_minutes: int = 15,
) -> dict[str, Any]:
    """Feature snapshot which cannot observe a candle available at or after simulated_time."""

    cutoff = require_utc(simulated_time)
    visible = [item for item in candles_5m if item.available_at < cutoff]
    aggregated = aggregate_candles(visible, timeframe_minutes)
    latest_time = max(item.open_time for item in aggregated)
    lower = latest_time - timedelta(days=30)
    symbols, times, closes = _aligned_closes(
        [item for item in aggregated if item.open_time >= lower]
    )
    simple = {symbol: _simple_returns(values) for symbol, values in closes.items()}
    trailing = {
        symbol: float(values[-1] / values[max(0, len(values) - 97)] - 1)
        for symbol, values in closes.items()
    }
    ranking = sorted(trailing, key=lambda symbol: (-trailing[symbol], symbol))
    return {
        "simulated_time": cutoff.isoformat(),
        "maximum_source_available_at": max(item.available_at for item in visible).isoformat(),
        "last_aligned_timestamp": times[-1].isoformat(),
        "trailing_return_by_symbol": trailing,
        "causal_ranking": ranking,
        "btc_latest_return": float(simple["BTCUSDT"][-1]),
        "symbols": symbols,
    }


def _aligned_closes(
    candles: list[Candle],
) -> tuple[list[str], list[datetime], dict[str, np.ndarray[Any, np.dtype[np.float64]]]]:
    by_symbol: dict[str, dict[datetime, float]] = {}
    for candle in candles:
        by_symbol.setdefault(candle.symbol, {})[candle.open_time] = float(candle.close)
    symbols = sorted(by_symbol)
    if not symbols:
        raise ValueError("divergence period has no candles")
    expected = set(by_symbol[symbols[0]])
    for symbol in symbols[1:]:
        actual = set(by_symbol[symbol])
        if actual != expected:
            raise ValueError(f"unaligned timestamps for {symbol}; gaps cannot be silently filled")
    times = sorted(expected)
    if len(times) < 3:
        raise ValueError("divergence analysis requires at least three aligned timestamps")
    closes = {
        symbol: np.asarray([by_symbol[symbol][time] for time in times], dtype=np.float64)
        for symbol in symbols
    }
    return symbols, times, closes


def _simple_returns(values: np.ndarray[Any, np.dtype[np.float64]]) -> np.ndarray[Any, Any]:
    return values[1:] / values[:-1] - 1.0


def _log_returns(values: np.ndarray[Any, np.dtype[np.float64]]) -> np.ndarray[Any, Any]:
    return np.diff(np.log(values))


def _pearson(left: np.ndarray[Any, Any], right: np.ndarray[Any, Any]) -> float:
    if len(left) < 2 or np.std(left) == 0 or np.std(right) == 0:
        return 0.0
    return float(np.corrcoef(left, right)[0, 1])


def _ranks(values: np.ndarray[Any, Any]) -> np.ndarray[Any, Any]:
    order = np.argsort(values, kind="mergesort")
    ranks = np.empty(len(values), dtype=np.float64)
    cursor = 0
    while cursor < len(order):
        end = cursor + 1
        while end < len(order) and values[order[end]] == values[order[cursor]]:
            end += 1
        ranks[order[cursor:end]] = (cursor + end - 1) / 2.0
        cursor = end
    return ranks


def _pair_metrics(
    left_name: str,
    right_name: str,
    left: np.ndarray[Any, Any],
    right: np.ndarray[Any, Any],
) -> dict[str, Any]:
    active = (left != 0) & (right != 0)
    opposite = np.sign(left[active]) != np.sign(right[active])
    left_up = left > 0
    left_down = left < 0
    divergent = active & (np.sign(left) != np.sign(right))
    max_streak, streaks = _streaks(divergent)
    beta = float(np.cov(left, right, ddof=0)[0, 1] / np.var(left)) if np.var(left) else 0.0
    residual = right - beta * left
    return {
        "left": left_name,
        "right": right_name,
        "pearson_simple": _pearson(left, right),
        "spearman_simple": _pearson(_ranks(left), _ranks(right)),
        "pearson_log": _pearson(np.log1p(left), np.log1p(right)),
        "opposite_direction_percent": float(np.mean(opposite) * 100) if len(opposite) else 0.0,
        "p_right_down_given_left_up": float(np.mean(right[left_up] < 0))
        if np.any(left_up)
        else 0.0,
        "p_right_up_given_left_down": float(np.mean(right[left_down] > 0))
        if np.any(left_down)
        else 0.0,
        "divergence_frequency_percent": float(np.mean(divergent) * 100),
        "maximum_divergence_streak": max_streak,
        "divergence_streak_count": len(streaks),
        "beta": beta,
        "residual_mean": float(np.mean(residual)),
        "residual_std": float(np.std(residual)),
    }


def _streaks(flags: np.ndarray[Any, Any]) -> tuple[int, list[int]]:
    streaks: list[int] = []
    current = 0
    for flag in flags:
        if flag:
            current += 1
        elif current:
            streaks.append(current)
            current = 0
    if current:
        streaks.append(current)
    return max(streaks, default=0), streaks


def _rolling_context(simple: dict[str, np.ndarray[Any, Any]], timeframe: int) -> dict[str, Any]:
    btc = simple["BTCUSDT"]
    periods = {
        "1h": 60 // timeframe,
        "24h": 24 * 60 // timeframe,
        "7d": 7 * 24 * 60 // timeframe,
        "30d": 30 * 24 * 60 // timeframe,
    }
    result: dict[str, Any] = {}
    for label, window in periods.items():
        result[label] = {}
        for symbol, values in simple.items():
            if symbol == "BTCUSDT":
                continue
            correlations = [
                _pearson(btc[index - window : index], values[index - window : index])
                for index in range(window, len(btc) + 1)
            ]
            betas = [
                float(
                    np.cov(btc[index - window : index], values[index - window : index], ddof=0)[
                        0, 1
                    ]
                    / np.var(btc[index - window : index])
                )
                if np.var(btc[index - window : index])
                else 0.0
                for index in range(window, len(btc) + 1)
            ]
            result[label][symbol] = {
                "window_periods": window,
                "observations": len(correlations),
                "correlation_mean": float(np.mean(correlations)) if correlations else None,
                "correlation_latest": correlations[-1] if correlations else None,
                "beta_mean": float(np.mean(betas)) if betas else None,
                "beta_latest": betas[-1] if betas else None,
            }
    return result


def _strong_event_analysis(
    candles_5m: list[Candle],
    *,
    start: datetime,
    end: datetime,
    symbols: list[str],
    main_returns: dict[str, np.ndarray[Any, Any]],
    costs: ExecutionCosts,
) -> dict[str, Any]:
    result: dict[str, Any] = {"thresholds": {"15m": 0.005, "1h": 0.01}}
    all_outcomes: dict[str, Any] = {}
    for label, minutes, threshold in (("15m", 15, 0.005), ("1h", 60, 0.01)):
        if minutes == 15:
            returns = main_returns
        else:
            aggregated = [
                item for item in aggregate_candles(candles_5m, 60) if start <= item.open_time < end
            ]
            aligned_symbols, _, closes = _aligned_closes(aggregated)
            if aligned_symbols != symbols:
                raise ValueError("1h divergence symbols differ from main timeframe")
            returns = {symbol: _simple_returns(values) for symbol, values in closes.items()}
        btc = returns["BTCUSDT"]
        events = np.abs(btc) >= threshold
        summary: dict[str, Any] = {"event_count": int(np.sum(events)), "assets": {}}
        for symbol in symbols:
            if symbol == "BTCUSDT":
                continue
            alt = returns[symbol]
            divergent = events & (alt != 0) & (np.sign(alt) != np.sign(btc))
            outcomes = _post_event_outcomes(alt, divergent, estimated_rotation_cost_rate(costs))
            summary["assets"][symbol] = {
                "divergent_event_count": int(np.sum(divergent)),
                "divergent_share": float(np.sum(divergent) / np.sum(events))
                if np.sum(events)
                else 0,
                "maximum_streak": _streaks(divergent)[0],
            }
            all_outcomes[f"{label}:{symbol}"] = outcomes
        result[label] = summary
    result["post_event_outcomes"] = all_outcomes
    return result


def _post_event_outcomes(
    returns: np.ndarray[Any, Any], flags: np.ndarray[Any, Any], cost_rate: Decimal
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for horizon in (1, 4, 16):
        values = []
        for index in np.flatnonzero(flags):
            if index + horizon < len(returns):
                values.append(float(np.prod(1 + returns[index + 1 : index + 1 + horizon]) - 1))
        gross = float(np.mean(values)) if values else None
        result[str(horizon)] = {
            "samples": len(values),
            "gross_mean": gross,
            "net_mean_after_roundtrip_costs": gross - float(cost_rate)
            if gross is not None
            else None,
        }
    return result


def _relative_strength(
    times: list[datetime],
    closes: dict[str, np.ndarray[Any, Any]],
    simple: dict[str, np.ndarray[Any, Any]],
    timeframe: int,
) -> dict[str, Any]:
    btc = closes["BTCUSDT"]
    window = 24 * 60 // timeframe
    ratios: dict[str, Any] = {}
    latest_scores: dict[str, float] = {}
    for symbol, values in closes.items():
        if symbol == "BTCUSDT":
            continue
        ratio = values / btc
        latest_scores[symbol] = float(ratio[-1] / ratio[max(0, len(ratio) - window - 1)] - 1)
        sample_step = max(1, len(ratio) // 300)
        ratios[f"{symbol.removesuffix('USDT')}/BTC"] = {
            "latest_ratio": float(ratio[-1]),
            "trailing_24h_change": latest_scores[symbol],
            "series": [
                {"timestamp": times[index].isoformat(), "ratio": float(ratio[index])}
                for index in range(0, len(ratio), sample_step)
            ],
        }
    return {
        "ratios": ratios,
        "causal_latest_ranking": sorted(
            latest_scores, key=lambda item: (-latest_scores[item], item)
        ),
        "ranking_scores": latest_scores,
        "return_definition": "simple and log returns are computed from aligned closes",
    }


def _lead_lag(btc: np.ndarray[Any, Any], alt: np.ndarray[Any, Any]) -> list[dict[str, Any]]:
    result = []
    for lag in range(-6, 7):
        if lag < 0:
            left, right = btc[-lag:], alt[:lag]
        elif lag > 0:
            left, right = btc[:-lag], alt[lag:]
        else:
            left, right = btc, alt
        result.append({"lag": lag, "pearson": _pearson(left, right)})
    return result
