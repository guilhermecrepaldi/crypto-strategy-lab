from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from typing import cast

import numpy as np
from numpy.typing import NDArray

from crypto_strategy_lab.data.temporal import TemporalMarketData
from crypto_strategy_lab.ml.partitions import PartitionName, TemporalPartition

FloatArray = NDArray[np.float32]


class FeatureVariant(StrEnum):
    BASE_FEATURES = "BASE_FEATURES"
    BASE_PLUS_RELATIVE_STRENGTH = "BASE_PLUS_RELATIVE_STRENGTH"


@dataclass(frozen=True)
class FeatureSetSpec:
    name: str = "causal-market-portfolio"
    version: str = "1.1.0"
    variant: FeatureVariant = FeatureVariant.BASE_FEATURES
    candles_per_window: int = 6
    relative_lookback_minutes: int = 24 * 60

    @property
    def features_per_asset(self) -> int:
        return 15 if self.variant == FeatureVariant.BASE_PLUS_RELATIVE_STRENGTH else 10


class FeatureNormalizer:
    def __init__(self) -> None:
        self.mean: FloatArray | None = None
        self.std: FloatArray | None = None
        self.fitted_partition: PartitionName | None = None

    def fit(self, samples: list[FloatArray], partition: PartitionName) -> None:
        if partition != PartitionName.TRAIN:
            raise ValueError("normalizer may only be fitted on TRAIN")
        if not samples:
            raise ValueError("normalizer requires samples")
        matrix = np.stack(samples).astype(np.float64)
        self.mean = matrix.mean(axis=0).astype(np.float32)
        std = matrix.std(axis=0)
        self.std = np.where(std < 1e-8, 1.0, std).astype(np.float32)
        self.fitted_partition = partition

    def transform(self, values: FloatArray) -> FloatArray:
        if self.mean is None or self.std is None:
            raise ValueError("normalizer is not fitted")
        return cast(
            FloatArray,
            np.clip((values - self.mean) / self.std, -10.0, 10.0).astype(np.float32),
        )

    def manifest(self) -> dict[str, object]:
        if self.mean is None or self.std is None or self.fitted_partition is None:
            raise ValueError("normalizer is not fitted")
        return {
            "fitted_partition": self.fitted_partition,
            "mean": self.mean.tolist(),
            "std": self.std.tolist(),
        }


class FeaturePipeline:
    def __init__(
        self,
        market: TemporalMarketData,
        symbols: tuple[str, ...],
        spec: FeatureSetSpec | None = None,
    ) -> None:
        if len(symbols) != 4:
            raise ValueError("baseline observation requires exactly four cryptoassets")
        self.market = market
        self.symbols = symbols
        self.spec = spec or FeatureSetSpec()
        self.market_feature_count = len(symbols) * self.spec.features_per_asset
        self.portfolio_feature_count = 10
        self.observation_size = self.market_feature_count + self.portfolio_feature_count

    def raw_observation(
        self,
        *,
        simulated_time: datetime,
        position_index: int,
        equity: Decimal,
        initial_equity: Decimal,
        drawdown: Decimal,
        time_in_position: int,
        costs: Decimal,
        previous_action: int,
    ) -> FloatArray:
        cutoff = simulated_time - timedelta(microseconds=1)
        histories: dict[str, list[float]] = {}
        raw: list[float] = []
        for symbol in self.symbols:
            candles = self.market.visible_candles(
                symbol,
                simulated_time=simulated_time,
                available_until=cutoff,
                lookback=timedelta(minutes=5 * self.spec.candles_per_window),
            )
            closes = [float(item.close) for item in candles[-self.spec.candles_per_window :]]
            histories[symbol] = closes
        anchor_returns = _returns(histories[self.symbols[0]])
        relative = self._relative_features(simulated_time)
        for symbol in self.symbols:
            candles = self.market.visible_candles(
                symbol,
                simulated_time=simulated_time,
                available_until=cutoff,
                lookback=timedelta(minutes=5 * self.spec.candles_per_window),
            )[-self.spec.candles_per_window :]
            closes = histories[symbol]
            if len(candles) < self.spec.candles_per_window:
                raw.extend([0.0] * 9 + [1.0] + relative[symbol])
                continue
            returns = _returns(closes)
            last = closes[-1]
            high = float(candles[-1].high)
            low = float(candles[-1].low)
            volumes = [float(item.volume) for item in candles]
            mean_close = sum(closes) / len(closes)
            correlation = (
                float(np.corrcoef(returns, anchor_returns)[0, 1])
                if len(returns) > 1 and np.std(returns) > 0 and np.std(anchor_returns) > 0
                else 0.0
            )
            raw.extend(
                [
                    returns[-1],
                    closes[-1] / closes[-4] - 1.0,
                    float(np.std(returns)),
                    (high - low) / last,
                    (last - low) / (high - low) if high > low else 0.5,
                    volumes[-1] / (sum(volumes) / len(volumes)) - 1.0,
                    last / mean_close - 1.0,
                    last / max(closes) - 1.0,
                    correlation,
                    0.0,
                ]
                + relative[symbol]
            )
        position = [1.0 if position_index == index else 0.0 for index in range(5)]
        raw.extend(
            [
                *position,
                float(equity / initial_equity - 1),
                float(drawdown),
                min(time_in_position / 100.0, 10.0),
                float(costs / initial_equity),
                previous_action / 4.0,
            ]
        )
        return np.asarray(raw, dtype=np.float32)

    def manifest(self) -> dict[str, object]:
        return {
            "name": self.spec.name,
            "version": self.spec.version,
            "variant": self.spec.variant,
            "candles_per_window": self.spec.candles_per_window,
            "relative_lookback_minutes": self.spec.relative_lookback_minutes,
            "features_per_asset": self.spec.features_per_asset,
        }

    def _relative_features(self, simulated_time: datetime) -> dict[str, list[float]]:
        if self.spec.variant == FeatureVariant.BASE_FEATURES:
            return {symbol: [] for symbol in self.symbols}
        cutoff = simulated_time - timedelta(microseconds=1)
        lookback = timedelta(minutes=self.spec.relative_lookback_minutes)
        histories: dict[str, list[float]] = {}
        for symbol in self.symbols:
            histories[symbol] = [
                float(item.close)
                for item in self.market.visible_candles(
                    symbol,
                    simulated_time=simulated_time,
                    available_until=cutoff,
                    lookback=lookback,
                )
            ]
        btc_returns = np.asarray(_returns(histories["BTCUSDT"]), dtype=np.float64)
        trailing_returns = {
            symbol: values[-1] / values[0] - 1.0 if len(values) > 1 else 0.0
            for symbol, values in histories.items()
        }
        ranking = sorted(self.symbols, key=lambda item: (trailing_returns[item], item))
        result: dict[str, list[float]] = {}
        for symbol in self.symbols:
            asset_returns = np.asarray(_returns(histories[symbol]), dtype=np.float64)
            size = min(len(btc_returns), len(asset_returns))
            btc = btc_returns[-size:] if size else np.asarray([], dtype=np.float64)
            asset = asset_returns[-size:] if size else np.asarray([], dtype=np.float64)
            variance = float(np.var(btc)) if size else 0.0
            beta = (
                float(np.cov(btc, asset, ddof=0)[0, 1] / variance)
                if size > 1 and variance > 0
                else 0.0
            )
            correlation = (
                float(np.corrcoef(btc, asset)[0, 1])
                if size > 1 and np.std(btc) > 0 and np.std(asset) > 0
                else 0.0
            )
            residual = float(asset[-1] - beta * btc[-1]) if size else 0.0
            rank = ranking.index(symbol) / max(1, len(ranking) - 1)
            regime = float(np.sign(trailing_returns["BTCUSDT"]))
            result[symbol] = [
                correlation,
                beta,
                residual,
                trailing_returns[symbol] - trailing_returns["BTCUSDT"],
                rank * regime,
            ]
        return result


def fit_train_normalizer(
    pipeline: FeaturePipeline,
    partition: TemporalPartition,
    initial_equity: Decimal,
) -> FeatureNormalizer:
    if partition.name != PartitionName.TRAIN:
        raise ValueError("feature statistics can only be fitted on TRAIN")
    samples: list[FloatArray] = []
    time = partition.start + timedelta(minutes=30)
    while time < partition.end:
        if time.minute % 15 == 0:
            samples.append(
                pipeline.raw_observation(
                    simulated_time=time,
                    position_index=0,
                    equity=initial_equity,
                    initial_equity=initial_equity,
                    drawdown=Decimal("0"),
                    time_in_position=0,
                    costs=Decimal("0"),
                    previous_action=0,
                )
            )
        time += timedelta(minutes=5)
    normalizer = FeatureNormalizer()
    normalizer.fit(samples, partition.name)
    return normalizer


def _returns(values: list[float]) -> list[float]:
    return [values[index] / values[index - 1] - 1.0 for index in range(1, len(values))]
