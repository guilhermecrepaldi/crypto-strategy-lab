from __future__ import annotations

from datetime import UTC, datetime, timedelta

from crypto_strategy_lab.decision.providers import (
    DeterministicDecisionProvider,
    FeatureFlaggedAIDecisionProvider,
    RecordReplayDecisionProvider,
)
from crypto_strategy_lab.domain import Action, DecisionRequest, DecisionResponse


def _request() -> DecisionRequest:
    simulated = datetime(2022, 1, 1, 0, 15, tzinfo=UTC)
    return DecisionRequest(
        simulated_time=simulated,
        available_data_until=simulated - timedelta(microseconds=1),
        portfolio={},
        market_context={"symbols": {}},
    )


def test_record_and_replay_are_network_free_and_identical() -> None:
    expected = DecisionResponse(
        action=Action.BUY_FROM_USDT,
        to_symbol="BTCUSDT",
        allocation_percent=75,
        confidence=0.8,
    )
    recorder = RecordReplayDecisionProvider("record", DeterministicDecisionProvider([expected]))
    assert recorder.decide(_request()) == expected
    replay = RecordReplayDecisionProvider("replay", recordings=recorder.records)
    assert replay.decide(_request()) == expected


def test_replay_hash_mismatch_fails_closed_to_hold() -> None:
    recorder = RecordReplayDecisionProvider(
        "record", DeterministicDecisionProvider([DecisionResponse.hold("recorded")])
    )
    recorder.decide(_request())
    changed = _request().model_copy(update={"portfolio": {"usdt": "79"}})
    replay = RecordReplayDecisionProvider("replay", recordings=recorder.records)
    response = replay.decide(changed)
    assert response.action == Action.HOLD
    assert "mismatch" in response.reasoning_summary


def test_invalid_provider_payload_becomes_hold() -> None:
    class InvalidProvider:
        name = "invalid"

        def decide(self, request: DecisionRequest):
            del request
            return {"action": "BUY_FROM_USDT", "allocation_percent": 900}

    recorder = RecordReplayDecisionProvider("record", InvalidProvider())
    assert recorder.decide(_request()).action == Action.HOLD


def test_real_ai_adapter_is_disabled_by_default() -> None:
    calls = 0

    def adapter(payload):
        nonlocal calls
        del payload
        calls += 1
        return {"action": "HOLD"}

    provider = FeatureFlaggedAIDecisionProvider(adapter)
    assert provider.decide(_request()).action == Action.HOLD
    assert calls == 0
