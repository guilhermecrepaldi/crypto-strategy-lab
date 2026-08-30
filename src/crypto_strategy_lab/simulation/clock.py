from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from crypto_strategy_lab.domain import Candle


@dataclass(frozen=True)
class ClockCheckpoint:
    next_index: int
    simulated_time: datetime | None


class HistoricalClock:
    def __init__(self, event_times: list[datetime]) -> None:
        self._events = sorted(set(event_times))
        self._index = 0
        self._paused = False
        self.simulated_time: datetime | None = None

    @classmethod
    def from_candles(cls, candles: list[Candle]) -> HistoricalClock:
        return cls([item.open_time for item in candles])

    def pause(self) -> None:
        self._paused = True

    def resume(self) -> None:
        self._paused = False

    def advance(self) -> datetime | None:
        if self._paused or self._index >= len(self._events):
            return None
        self.simulated_time = self._events[self._index]
        self._index += 1
        return self.simulated_time

    def checkpoint(self) -> ClockCheckpoint:
        return ClockCheckpoint(self._index, self.simulated_time)

    def restore(self, checkpoint: ClockCheckpoint) -> None:
        if not 0 <= checkpoint.next_index <= len(self._events):
            raise ValueError("checkpoint is outside this clock")
        self._index = checkpoint.next_index
        self.simulated_time = checkpoint.simulated_time
