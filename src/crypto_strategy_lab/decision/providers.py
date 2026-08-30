from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal, Protocol

from pydantic import ValidationError

from crypto_strategy_lab.domain import DecisionRequest, DecisionResponse, canonical_hash


class DecisionProvider(Protocol):
    name: str

    def decide(self, request: DecisionRequest) -> DecisionResponse | dict[str, Any]: ...


class DeterministicDecisionProvider:
    name = "deterministic-fixture"

    def __init__(self, decisions: list[DecisionResponse]) -> None:
        self._decisions = decisions
        self._index = 0

    def decide(self, request: DecisionRequest) -> DecisionResponse:
        del request
        if self._index >= len(self._decisions):
            return DecisionResponse.hold("fixture decision sequence exhausted")
        decision = self._decisions[self._index]
        self._index += 1
        return decision


class FeatureFlaggedAIDecisionProvider:
    """Real-provider seam. Network behavior is injected and remains disabled by default."""

    name = "feature-flagged-ai"

    def __init__(
        self,
        adapter: Callable[[dict[str, Any]], dict[str, Any]],
        *,
        enabled: bool = False,
    ) -> None:
        self._adapter = adapter
        self._enabled = enabled

    def decide(self, request: DecisionRequest) -> DecisionResponse | dict[str, Any]:
        if not self._enabled:
            return DecisionResponse.hold("AI provider feature flag is disabled")
        return self._adapter(request.model_dump(mode="json"))


@dataclass(frozen=True)
class DecisionRecord:
    input_hash: str
    input_payload: dict[str, Any]
    raw_response: dict[str, Any]
    normalized_response: DecisionResponse
    replayed: bool


class RecordReplayDecisionProvider:
    name = "record-replay"

    def __init__(
        self,
        mode: Literal["record", "replay"],
        delegate: DecisionProvider | None = None,
        recordings: list[DecisionRecord] | None = None,
    ) -> None:
        if mode == "record" and delegate is None:
            raise ValueError("record mode requires a delegate")
        self.mode = mode
        self.delegate = delegate
        self.records = list(recordings or [])
        self._replay_index = 0

    def decide(self, request: DecisionRequest) -> DecisionResponse:
        payload = request.model_dump(mode="json")
        input_hash = canonical_hash(payload)
        if self.mode == "replay":
            if self._replay_index >= len(self.records):
                return DecisionResponse.hold("missing replay recording")
            record = self.records[self._replay_index]
            self._replay_index += 1
            if record.input_hash != input_hash:
                return DecisionResponse.hold("replay input hash mismatch")
            return record.normalized_response

        assert self.delegate is not None
        raw_candidate = self.delegate.decide(request)
        raw = (
            raw_candidate.model_dump(mode="json")
            if isinstance(raw_candidate, DecisionResponse)
            else raw_candidate
        )
        try:
            normalized = DecisionResponse.model_validate(raw)
        except (ValidationError, TypeError, ValueError):
            normalized = DecisionResponse.hold("invalid decision provider response")
        self.records.append(
            DecisionRecord(
                input_hash=input_hash,
                input_payload=payload,
                raw_response=raw if isinstance(raw, dict) else {"value": str(raw)},
                normalized_response=normalized,
                replayed=False,
            )
        )
        return normalized
