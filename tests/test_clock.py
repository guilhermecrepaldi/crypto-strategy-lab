from __future__ import annotations

from crypto_strategy_lab.simulation.clock import HistoricalClock


def test_clock_pause_checkpoint_resume_and_restore(fixture_bundle) -> None:
    candles, _, _ = fixture_bundle
    clock = HistoricalClock.from_candles(candles)
    first = clock.advance()
    checkpoint = clock.checkpoint()
    second = clock.advance()
    assert second is not None and second > first
    clock.restore(checkpoint)
    assert clock.advance() == second
    clock.pause()
    assert clock.advance() is None
    clock.resume()
    assert clock.advance() is not None
