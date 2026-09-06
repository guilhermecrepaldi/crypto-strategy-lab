from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from crypto_strategy_lab.domain import canonical_hash
from crypto_strategy_lab.microstructure.data import (
    MicrostructureManifest,
    manifest_for,
    parse_archive,
)
from crypto_strategy_lab.microstructure.execution import (
    MicrostructureRunResult,
    PassiveExecutionSimulator,
    environment_snapshot,
)
from crypto_strategy_lab.microstructure.models import (
    BookDeltaEvent,
    BookSnapshotEvent,
    CancelRequest,
    FeedGapEvent,
    FeeModel,
    LiquidityRole,
    MarketEvent,
    RiskHaltEvent,
    S0Config,
    TradeEvent,
)


class S0FixtureArtifact(BaseModel):
    model_config = ConfigDict(frozen=True)

    schema_version: str = "microstructure-s0-fixture-v1"
    code_version: str
    worktree_dirty: bool
    seed: int = 0
    config: S0Config
    environment: dict[str, str]
    result: MicrostructureRunResult


class LevelFrequencyAudit(BaseModel):
    model_config = ConfigDict(frozen=True)

    schema_version: str = "fdusdusdc-level-frequency-v1"
    run_id: str
    dataset: MicrostructureManifest
    lower: Decimal
    upper: Decimal
    spread: Decimal
    spread_bps_on_lower: Decimal
    lower_trade_count: int
    upper_trade_count: int
    lower_independent_visits: int
    upper_independent_visits: int
    lower_quantity: Decimal
    upper_quantity: Decimal
    completed_observed_paths: int
    observed_high_to_low_paths: int
    observed_low_high_low_cycles: int
    low_to_high_duration_seconds: dict[str, Decimal | None]
    high_to_low_duration_seconds: dict[str, Decimal | None]
    low_high_low_duration_seconds: dict[str, Decimal | None]
    observed_paths_are_fills: bool = False
    queue_evidence: Literal["UNAVAILABLE"] = "UNAVAILABLE"
    realistic_queue_status: Literal["INCONCLUSIVE"] = "INCONCLUSIVE"
    fee_scenarios_quote_pnl_per_100: dict[str, Decimal]
    can_2000_cycles_on_observed_day: Literal[
        "NO_PRICE_PATH_UPPER_BOUND_BELOW_TARGET", "INCONCLUSIVE_WITHOUT_FILLS"
    ]
    conclusion: Literal["DISCOVERY_ONLY_NOT_PROSPECTIVE"] = "DISCOVERY_ONLY_NOT_PROSPECTIVE"


def run_s0_fixture(path: Path) -> S0FixtureArtifact:
    raw = json.loads(path.read_text(encoding="utf-8"))
    config = S0Config.model_validate(raw["config"])
    events = [_market_event(item) for item in raw["events"]]
    cancellations = [CancelRequest.model_validate(item) for item in raw.get("cancellations", [])]
    dataset_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    result = PassiveExecutionSimulator(config).run(
        events,
        dataset_hash=dataset_hash,
        cancel_requests=cancellations,
    )
    return S0FixtureArtifact(
        code_version=_git_head(),
        worktree_dirty=_worktree_dirty(),
        config=config,
        environment=environment_snapshot(),
        result=result,
    )


def audit_trade_levels(
    archive: Path,
    *,
    kind: Literal["trades", "aggTrades"],
    source_url: str,
    period: str,
    lower: Decimal,
    upper: Decimal,
) -> LevelFrequencyAudit:
    events = parse_archive(archive, kind)
    manifest = manifest_for(archive, events, origin=source_url, period=period)
    lower_events = [event for event in events if event.price == lower]
    upper_events = [event for event in events if event.price == upper]
    low_high_durations = _transition_durations(events, start=lower, end=upper)
    high_low_durations = _transition_durations(events, start=upper, end=lower)
    cycle_durations = _cycle_durations(events, lower=lower, upper=upper)
    paths = len(low_high_durations)
    fee_scenarios: dict[str, Decimal] = {}
    fee_models = {
        "maker_zero_taker_10bps": FeeModel(maker_rate=Decimal("0"), taker_rate=Decimal("0.001")),
        "maker_1bp_taker_10bps": FeeModel(
            maker_rate=Decimal("0.0001"), taker_rate=Decimal("0.001")
        ),
    }
    for scenario, fee_model in fee_models.items():
        for buy_role in LiquidityRole:
            for sell_role in LiquidityRole:
                key = f"{scenario}:{buy_role.value}->{sell_role.value}"
                fee_scenarios[key] = fee_model.one_tick_net_quote(
                    lower=lower,
                    upper=upper,
                    quantity=Decimal("100"),
                    buy_role=buy_role,
                    sell_role=sell_role,
                )
    identity = {
        "dataset_sha256": manifest.sha256,
        "lower": lower,
        "upper": upper,
        "method": "arm-on-lower-complete-on-next-upper-reset",
        "fee_scenarios": {key: value.model_dump(mode="json") for key, value in fee_models.items()},
    }
    return LevelFrequencyAudit(
        run_id=canonical_hash(identity),
        dataset=manifest,
        lower=lower,
        upper=upper,
        spread=upper - lower,
        spread_bps_on_lower=(upper - lower) / lower * Decimal("10000"),
        lower_trade_count=len(lower_events),
        upper_trade_count=len(upper_events),
        lower_independent_visits=_independent_visits(events, lower),
        upper_independent_visits=_independent_visits(events, upper),
        lower_quantity=sum((item.quantity for item in lower_events), Decimal("0")),
        upper_quantity=sum((item.quantity for item in upper_events), Decimal("0")),
        completed_observed_paths=paths,
        observed_high_to_low_paths=len(high_low_durations),
        observed_low_high_low_cycles=len(cycle_durations),
        low_to_high_duration_seconds=_duration_stats(low_high_durations),
        high_to_low_duration_seconds=_duration_stats(high_low_durations),
        low_high_low_duration_seconds=_duration_stats(cycle_durations),
        fee_scenarios_quote_pnl_per_100=fee_scenarios,
        can_2000_cycles_on_observed_day=(
            "NO_PRICE_PATH_UPPER_BOUND_BELOW_TARGET"
            if paths < 2_000
            else "INCONCLUSIVE_WITHOUT_FILLS"
        ),
    )


def write_artifact(artifact: BaseModel, output: Path) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(artifact.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return output


def _market_event(raw: dict[str, Any]) -> MarketEvent:
    event_type = raw.get("type")
    payload = {key: value for key, value in raw.items() if key != "type"}
    if event_type == "snapshot":
        return BookSnapshotEvent.model_validate(payload)
    if event_type == "delta":
        return BookDeltaEvent.model_validate(payload)
    if event_type == "gap":
        return FeedGapEvent.model_validate(payload)
    if event_type == "trade":
        return TradeEvent.model_validate(payload)
    if event_type == "risk_halt":
        return RiskHaltEvent.model_validate(payload)
    raise ValueError(f"unknown market event type {event_type!r}")


def _transition_durations(
    events: list[TradeEvent], *, start: Decimal, end: Decimal
) -> list[Decimal]:
    armed_at: datetime | None = None
    durations: list[Decimal] = []
    for event in events:
        if event.price == start and armed_at is None:
            armed_at = event.timestamp
        elif armed_at is not None and event.price == end:
            durations.append(_seconds(event.timestamp - armed_at))
            armed_at = None
    return durations


def _cycle_durations(events: list[TradeEvent], *, lower: Decimal, upper: Decimal) -> list[Decimal]:
    state = "WAIT_LOW"
    started_at: datetime | None = None
    durations: list[Decimal] = []
    for event in events:
        if state == "WAIT_LOW" and event.price == lower:
            started_at = event.timestamp
            state = "WAIT_HIGH"
        elif state == "WAIT_HIGH" and event.price == upper:
            state = "WAIT_RETURN_LOW"
        elif state == "WAIT_RETURN_LOW" and event.price == lower:
            if started_at is None:  # pragma: no cover - state invariant
                raise AssertionError("cycle start missing")
            durations.append(_seconds(event.timestamp - started_at))
            started_at = event.timestamp
            state = "WAIT_HIGH"
    return durations


def _seconds(delta: timedelta) -> Decimal:
    return Decimal(delta.days * 86_400 + delta.seconds) + Decimal(delta.microseconds) / Decimal(
        "1000000"
    )


def _duration_stats(values: list[Decimal]) -> dict[str, Decimal | None]:
    if not values:
        return {key: None for key in ("mean", "p50", "p90", "p95", "p99", "max")}
    ordered = sorted(values)
    return {
        "mean": sum(ordered, Decimal("0")) / Decimal(len(ordered)),
        "p50": _percentile(ordered, Decimal("0.50")),
        "p90": _percentile(ordered, Decimal("0.90")),
        "p95": _percentile(ordered, Decimal("0.95")),
        "p99": _percentile(ordered, Decimal("0.99")),
        "max": ordered[-1],
    }


def _percentile(ordered: list[Decimal], quantile: Decimal) -> Decimal:
    position = Decimal(len(ordered) - 1) * quantile
    lower_index = int(position)
    upper_index = min(lower_index + 1, len(ordered) - 1)
    fraction = position - Decimal(lower_index)
    return ordered[lower_index] + (ordered[upper_index] - ordered[lower_index]) * fraction


def _independent_visits(events: list[TradeEvent], level: Decimal) -> int:
    visits = 0
    previous_at_level = False
    for event in events:
        at_level = event.price == level
        if at_level and not previous_at_level:
            visits += 1
        previous_at_level = at_level
    return visits


def _git_head() -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, check=True, text=True
    )
    return completed.stdout.strip()


def _worktree_dirty() -> bool:
    completed = subprocess.run(
        ["git", "status", "--porcelain"], capture_output=True, check=True, text=True
    )
    return bool(completed.stdout.strip())
