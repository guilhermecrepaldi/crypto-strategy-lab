from __future__ import annotations

import random
from datetime import datetime, timedelta
from enum import StrEnum
from itertools import pairwise

from pydantic import BaseModel, ConfigDict, model_validator

from crypto_strategy_lab.domain import Candle, require_utc


class PartitionName(StrEnum):
    TRAIN = "TRAIN"
    VALIDATION = "VALIDATION"
    LOCKED_TEST = "LOCKED_TEST"
    WALK_FORWARD = "WALK_FORWARD"


class TemporalPartition(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: PartitionName
    start: datetime
    end: datetime
    observed: bool = False

    @model_validator(mode="after")
    def validate_boundary(self) -> TemporalPartition:
        require_utc(self.start)
        require_utc(self.end)
        if self.start >= self.end:
            raise ValueError("partition must have positive duration")
        return self


class PartitionManifest(BaseModel):
    model_config = ConfigDict(frozen=True)

    partitions: list[TemporalPartition]

    @model_validator(mode="after")
    def reject_overlap(self) -> PartitionManifest:
        ordered = sorted(self.partitions, key=lambda item: item.start)
        for left, right in pairwise(ordered):
            if left.end > right.start:
                raise ValueError(f"partitions overlap: {left.name} and {right.name}")
        return self


class EpisodeWindow(BaseModel):
    model_config = ConfigDict(frozen=True)

    partition: PartitionName
    start: datetime
    end: datetime
    warmup_start: datetime
    seed: int


class EpisodeSampler:
    def __init__(
        self,
        candles: list[Candle],
        partition: TemporalPartition,
        *,
        warmup: timedelta,
        duration: timedelta,
    ) -> None:
        if duration <= timedelta(0) or warmup < timedelta(0):
            raise ValueError("episode duration must be positive and warmup non-negative")
        self.partition = partition
        self.warmup = warmup
        self.duration = duration
        by_symbol: dict[str, set[datetime]] = {}
        for candle in candles:
            by_symbol.setdefault(candle.symbol, set()).add(candle.open_time)
        common_times = set.intersection(*by_symbol.values()) if by_symbol else set()
        self.valid_starts = sorted(
            time
            for time in common_times
            if time.minute % 15 == 0
            and time.second == 0
            and time >= partition.start + warmup
            and time + duration <= partition.end
            and all(
                time + duration - timedelta(minutes=5) in values for values in by_symbol.values()
            )
        )
        if not self.valid_starts:
            raise ValueError("partition has no complete episode window")

    def sample(self, seed: int) -> EpisodeWindow:
        start = random.Random(seed).choice(self.valid_starts)
        return EpisodeWindow(
            partition=self.partition.name,
            start=start,
            end=start + self.duration,
            warmup_start=start - self.warmup,
            seed=seed,
        )

    def explicit(self, start: datetime, seed: int) -> EpisodeWindow:
        start = require_utc(start)
        if start not in self.valid_starts:
            raise ValueError("explicit episode start is not complete inside the partition")
        return EpisodeWindow(
            partition=self.partition.name,
            start=start,
            end=start + self.duration,
            warmup_start=start - self.warmup,
            seed=seed,
        )
