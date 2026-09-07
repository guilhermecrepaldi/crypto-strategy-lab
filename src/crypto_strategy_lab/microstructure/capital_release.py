"""Causal, read-only CAPITAL_RELEASE diagnostic for the frozen M007 run.

This module deliberately does not register a model, replay a model, or attach
post-checkpoint outcomes to the sealed causal snapshots.  It consumes the
canonical evaluated-run loader and the existing serial selection primitives.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
from bisect import bisect_left, bisect_right
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import ROUND_CEILING, ROUND_DOWN, Decimal
from pathlib import Path
from typing import Any, Final

import numpy as np
from numpy.typing import NDArray

from crypto_strategy_lab.domain import canonical_hash
from crypto_strategy_lab.microstructure.data import HistoryManifest
from crypto_strategy_lab.microstructure.evolution_diagnostics import (
    _RunEvidence,
    load_evaluated_run_evidence,
)
from crypto_strategy_lab.microstructure.serial_replay import (
    EVENT_ORDER_SCALE,
    USDCUSDT_TICK_CATALOG,
    CandidateTimeline,
    SerialTape,
    _datetime_to_micros,
    _event_to_datetime,
    _score,
    _select,
    _selection_grid,
    symmetric_break_even_fee,
)
from crypto_strategy_lab.microstructure.tape_cache import TapeCacheManifest, load_or_build_tape

PROTOCOL_VERSION: Final = "capital-release-diagnostic-v1"
MODEL_ID: Final = "M007"
REPLAY_HASH: Final = "f622acb767d0dbaa39edfb7c90e6ef349dfaf6d694ee17dcde29f22a3d740d21"
EVALUATION_HASH: Final = "f46a51ecbd3002f54a46c47d350bc20d14e408a2e53f520111524c0caf7f0b82"
TAPE_HASH: Final = "505fd6c31b010eac4e8da2d7e290137bb455d475b95409ac306d1ded7be55b6c"
CAUSAL_START: Final = datetime(2025, 1, 1, tzinfo=UTC)
RMST_CAP_SECONDS: Final = Decimal("86400")
FIXED_RULER_CAPITAL: Final = Decimal("100")
QUANTITY_STEP: Final = Decimal("0.01")
INITIAL_AGES: Final = (60, 300, 900, 1800, 3600, 7200, 14400, 21600, 43200, 86400, 172800)


class CapitalReleaseDiagnosticError(ValueError):
    """Raised when immutable M007 evidence cannot support the diagnostic."""


@dataclass(frozen=True, slots=True)
class CapitalReleaseDiagnosticResult:
    artifact_id: str
    artifact_dir: Path
    report_path: Path
    summary: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class KaplanMeierResult:
    rmst: Decimal | None
    lower_bound: Decimal
    upper_bound: Decimal
    survival_at_support_end: Decimal
    maximum_time: Decimal
    identified: bool


@dataclass(frozen=True, slots=True)
class _Position:
    index: int
    entry_event: int
    entry_timestamp: datetime
    exit_event: int | None
    low: Decimal
    high: Decimal
    quantity: Decimal
    buy_fee: Decimal
    sell_fee: Decimal
    cash_before_buy: Decimal
    residual_cash: Decimal
    terminal: bool = False


@dataclass(frozen=True, slots=True)
class _EpisodeIndex:
    """Vectorized immutable view of one full timeline, queried by causal prefix."""

    timeline: CandidateTimeline
    entries: NDArray[np.int64]
    exits: NDArray[np.int64]

    @classmethod
    def from_timeline(cls, timeline: CandidateTimeline) -> _EpisodeIndex:
        entries = np.frombuffer(timeline.cycle_entries, dtype=np.int64)
        exits = np.frombuffer(timeline.cycle_exits, dtype=np.int64)
        if entries.shape != exits.shape:
            raise CapitalReleaseDiagnosticError("timeline entry/exit arrays disagree")
        return cls(timeline, entries, exits)


def kaplan_meier_rmst(
    durations: Sequence[Decimal | int | str],
    events: Sequence[bool],
    cap: Decimal,
) -> Decimal:
    """Return restricted mean survival time using exact Decimal arithmetic.

    ``events[i]`` is true when the duration is an observed completion; false
    denotes right censoring.  The implementation groups tied times and applies
    all event drops after integrating the preceding interval.
    """
    result = _kaplan_meier(durations, events, cap)
    return result.rmst if result.rmst is not None else result.lower_bound


def _kaplan_meier(
    durations: Sequence[Decimal | int | str],
    events: Sequence[bool],
    cap: Decimal,
) -> KaplanMeierResult:
    if cap <= 0:
        raise ValueError("KM cap must be positive")
    if len(durations) != len(events):
        raise ValueError("durations and events must have equal length")
    observations = sorted(
        (Decimal(str(duration)), bool(event))
        for duration, event in zip(durations, events, strict=True)
    )
    if any(duration < 0 for duration, _ in observations):
        raise ValueError("KM durations must be non-negative")
    if not observations:
        return KaplanMeierResult(
            None,
            Decimal("0"),
            cap,
            Decimal("1"),
            Decimal("0"),
            False,
        )
    maximum = max(duration for duration, _ in observations)
    support_end = min(cap, maximum)
    rmst = Decimal("0")
    survival = Decimal("1")
    previous = Decimal("0")
    at_risk = len(observations)
    index = 0
    while index < len(observations) and previous <= support_end:
        time = observations[index][0]
        if time > support_end:
            rmst += (support_end - previous) * survival
            previous = support_end
            break
        rmst += (time - previous) * survival
        tied_events = 0
        tied_total = 0
        while index < len(observations) and observations[index][0] == time:
            tied_total += 1
            tied_events += int(observations[index][1])
            index += 1
        if tied_events:
            if at_risk <= 0 or tied_events > at_risk:
                raise ValueError("invalid KM event count")
            survival *= Decimal(at_risk - tied_events) / Decimal(at_risk)
        at_risk -= tied_total
        previous = time
    if previous < support_end:
        rmst += (support_end - previous) * survival
    identified = maximum >= cap or survival == 0
    lower = rmst
    upper = rmst if identified else rmst + (cap - support_end) * survival
    return KaplanMeierResult(
        rmst if identified else None,
        lower,
        upper,
        survival,
        maximum,
        identified,
    )


def kaplan_meier_q90(
    durations: Sequence[Decimal | int | str],
    events: Sequence[bool],
    cap: Decimal,
) -> Decimal | None:
    """Return the first time KM survival reaches the 10% tail, or ``None``."""
    if cap <= 0 or len(durations) != len(events):
        raise ValueError("invalid KM quantile inputs")
    observations = sorted(
        (min(Decimal(str(duration)), cap), bool(event) and Decimal(str(duration)) <= cap)
        for duration, event in zip(durations, events, strict=True)
    )
    if not observations:
        return None
    survival = Decimal("1")
    at_risk = len(observations)
    index = 0
    while index < len(observations):
        time = observations[index][0]
        tied_events = 0
        tied_total = 0
        while index < len(observations) and observations[index][0] == time:
            tied_total += 1
            tied_events += int(observations[index][1])
            index += 1
        if tied_events:
            survival *= Decimal(at_risk - tied_events) / Decimal(at_risk)
            if survival <= Decimal("0.1"):
                return time
        at_risk -= tied_total
    return None


def diagnose_capital_release(
    *,
    support_manifest: str | Path,
    artifact_root: str | Path = Path("artifacts"),
    report_root: str | Path = Path("reports"),
) -> CapitalReleaseDiagnosticResult:
    """Build the sealed causal CAPITAL_RELEASE artifact from M007 only."""
    evidence = load_evaluated_run_evidence(
        MODEL_ID, artifact_root=artifact_root, report_root=report_root
    )
    _validate_evidence_identity(evidence)
    try:
        manifest = HistoryManifest.model_validate_json(
            Path(support_manifest).read_text(encoding="utf-8")
        )
        end_exclusive = _parse_dt(evidence.run_manifest["interval"]["end_exclusive"])
        support_start = max(CAUSAL_START, manifest.first_timestamp)
        support_result = load_or_build_tape(
            manifest,
            start=support_start,
            end_exclusive=end_exclusive,
            artifact_root=Path(artifact_root),
            tick_catalog=USDCUSDT_TICK_CATALOG,
        )
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise CapitalReleaseDiagnosticError(
            "official validated support manifest cannot build the 2025-01-01 tape"
        ) from error
    code_sha = _git_sha()
    return build_capital_release_diagnostic(
        evidence,
        support_tape=support_result.tape,
        support_tape_manifest=support_result.manifest,
        artifact_root=Path(artifact_root),
        report_root=Path(report_root),
        code_sha=code_sha,
    )


def build_capital_release_diagnostic(
    evidence: _RunEvidence,
    *,
    support_tape: SerialTape | None = None,
    support_tape_manifest: TapeCacheManifest | None = None,
    artifact_root: Path = Path("artifacts"),
    report_root: Path = Path("reports"),
    code_sha: str = "UNKNOWN",
) -> CapitalReleaseDiagnosticResult:
    """Build from already-loaded evidence; public for focused offline tests."""
    _validate_evidence_identity(evidence)
    positions = _positions(evidence)
    if not positions:
        raise CapitalReleaseDiagnosticError("M007 evidence has no positions")
    analysis_tape = support_tape or evidence.tape
    snapshots = build_capital_release_snapshots(evidence, positions=positions, tape=analysis_tape)
    identity = {
        "protocol_version": PROTOCOL_VERSION,
        "model_id": MODEL_ID,
        "model_hash": evidence.model_hash,
        "run_hash": evidence.run_hash,
        "evaluation_hash": evidence.evaluation_hash,
        "dataset_hash": evidence.run_manifest.get("dataset_hash"),
        "tape_hash": evidence.tape.tape_hash,
        "tape_content_hash": evidence.tape_manifest.content_hash,
        "support_tape_hash": analysis_tape.tape_hash,
        "support_tape_cache_key": (
            analysis_tape.tape_cache_key
            if analysis_tape.tape_cache_key is not None
            else support_tape_manifest.cache_key
            if support_tape_manifest is not None
            else None
        ),
        "support_tape_content_hash": (
            support_tape_manifest.content_hash if support_tape_manifest is not None else None
        ),
        "historical_support_start": (
            support_tape_manifest.start.isoformat()
            if support_tape_manifest is not None
            else _event_to_datetime(int(analysis_tape.events[0])).isoformat()
        ),
        "code_sha": code_sha,
        "checkpoint_ages_seconds": _checkpoint_ages(),
        "ruler_capital": str(FIXED_RULER_CAPITAL),
        "quantity_step": str(QUANTITY_STEP),
    }
    artifact_id = canonical_hash(identity)
    root = artifact_root / "usdcusdt" / "capital-release-diagnostics" / artifact_id
    report_path = report_root / "usdcusdt" / "capital-release-diagnostic.json"
    summary = _summary(
        evidence,
        artifact_id,
        identity,
        positions,
        snapshots,
        support_tape_manifest=support_tape_manifest,
    )
    files = {
        "causal-snapshots.jsonl": _jsonl_bytes(snapshots),
        "summary.json": _json_bytes(summary),
    }
    if root.exists():
        _validate_artifact(root, artifact_id)
    else:
        _write_artifact(root, artifact_id, files)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_bytes(_json_bytes(summary))
    return CapitalReleaseDiagnosticResult(artifact_id, root, report_path, summary)


def _validate_evidence_identity(evidence: _RunEvidence) -> None:
    if evidence.model_id != MODEL_ID:
        raise CapitalReleaseDiagnosticError("CAPITAL_RELEASE accepts M007 only")
    if evidence.run_hash != REPLAY_HASH or evidence.evaluation_hash != EVALUATION_HASH:
        raise CapitalReleaseDiagnosticError("physical M007 run/evaluation identity changed")
    if evidence.tape.tape_hash != TAPE_HASH:
        raise CapitalReleaseDiagnosticError("physical M007 tape identity changed")


def build_capital_release_snapshots(
    evidence: _RunEvidence,
    *,
    positions: Sequence[_Position] | None = None,
    tape: SerialTape | None = None,
) -> tuple[dict[str, Any], ...]:
    """Seal only causal snapshots; no post-checkpoint outcomes are read."""
    if evidence.model_id != MODEL_ID:
        raise CapitalReleaseDiagnosticError("CAPITAL_RELEASE accepts M007 only")
    positions = tuple(positions or _positions(evidence))
    cycles = evidence.replay.get("cycles", [])
    if not isinstance(cycles, list):
        raise CapitalReleaseDiagnosticError("M007 cycles are missing")
    analysis_tape = tape or evidence.tape
    distances = (
        USDCUSDT_TICK_CATALOG.absolute_distances(evidence.model.distances)
        if evidence.model.distance_semantics is not None
        else evidence.model.distances
    )
    timelines = analysis_tape.timelines(distances)
    relevant_candidates = {
        (
            _tick(position.low, analysis_tape.tick_size),
            _tick(position.high, analysis_tape.tick_size)
            - _tick(position.low, analysis_tape.tick_size),
        )
        for position in positions
        if position.exit_event is None
        or _event_elapsed_micros(position.exit_event, position.entry_event)
        >= INITIAL_AGES[0] * 1_000_000
    }
    episode_indexes = {
        candidate: _EpisodeIndex.from_timeline(timelines[candidate])
        for candidate in relevant_candidates
        if candidate in timelines
    }
    end_exclusive = _parse_dt(evidence.run_manifest["interval"]["end_exclusive"])
    sorted_price_ticks = tuple(sorted(analysis_tape.occurrences))
    snapshots: list[dict[str, Any]] = []
    for position in positions:
        for age in _checkpoint_ages():
            checkpoint = position.entry_timestamp + timedelta(seconds=age)
            if checkpoint >= end_exclusive:
                break
            if (
                position.exit_event is not None
                and _event_to_datetime(position.exit_event) < checkpoint
            ):
                break
            snapshot = _snapshot(
                evidence,
                position,
                checkpoint,
                age,
                timelines,
                episode_indexes,
                analysis_tape,
                sorted_price_ticks,
            )
            sealed = dict(snapshot)
            sealed["snapshot_hash"] = canonical_hash(snapshot)
            snapshots.append(sealed)
    return tuple(snapshots)


def _snapshot(
    evidence: _RunEvidence,
    position: _Position,
    checkpoint: datetime,
    age: int,
    timelines: dict[tuple[int, int], CandidateTimeline],
    episode_indexes: Mapping[tuple[int, int], _EpisodeIndex],
    tape: SerialTape,
    sorted_price_ticks: Sequence[int],
) -> dict[str, Any]:
    checkpoint_event = _datetime_to_micros(checkpoint) * EVENT_ORDER_SCALE
    event_index = bisect_left(tape.events, checkpoint_event) - 1
    if event_index < 0:
        raise CapitalReleaseDiagnosticError("checkpoint has no strictly prior trade")
    current_tick = int(tape.price_ticks[event_index])
    current = _price_tick(current_tick, tape.tick_size)
    low_tick = _tick(position.low, tape.tick_size)
    high_tick = _tick(position.high, tape.tick_size)
    candidate = (low_tick, high_tick - low_tick)
    if candidate not in timelines:
        raise CapitalReleaseDiagnosticError("position band absent from canonical timelines")
    if candidate not in episode_indexes:
        raise CapitalReleaseDiagnosticError("position band absent from causal episode index")
    minimum_tick = _minimum_tick_between(
        tape,
        sorted_price_ticks,
        position.entry_event,
        checkpoint_event,
    )
    worst_mark = position.residual_cash + Decimal(minimum_tick) * tape.tick_size * position.quantity
    fee_buy = _rate(position.buy_fee, position.quantity * position.low)
    fee_sell = _rate(position.sell_fee, position.quantity * position.high)
    release_fee = fee_sell
    release_cash = position.residual_cash + position.quantity * current * (
        Decimal("1") - release_fee
    )
    target_cash = position.residual_cash + position.quantity * position.high * (
        Decimal("1") - fee_sell
    )
    loss_fraction = Decimal("1") - release_cash / position.cash_before_buy
    loss_usdt = position.cash_before_buy - release_cash
    _, eligible_distances, grid_multiple = _selection_grid(
        evidence.model,
        USDCUSDT_TICK_CATALOG,
        checkpoint_event,
        tape.tick_size,
        tape.observed_tick_evidence_event,
    )
    lookback = evidence.model.lookback_minutes * 60 * 1_000_000 * EVENT_ORDER_SCALE
    alternative = _select(
        timelines,
        evidence.model,
        checkpoint_event - lookback,
        checkpoint_event,
        eligible_distances=eligible_distances,
        grid_multiple=grid_multiple,
    )
    alt_timeline = timelines.get(alternative) if alternative is not None else None
    c1h = (
        alt_timeline.contained_cycles(checkpoint_event - _hour_events(), checkpoint_event)
        if alt_timeline
        else 0
    )
    c24h = (
        alt_timeline.contained_cycles(checkpoint_event - _day_events(), checkpoint_event)
        if alt_timeline
        else 0
    )
    cycles_per_hour = Decimal(c24h) / Decimal("24")
    rate_proxy = min(Decimal(c1h), cycles_per_hour)
    alt_low = _price_tick(alternative[0], tape.tick_size) if alternative else None
    alt_high = _price_tick(alternative[0] + alternative[1], tape.tick_size) if alternative else None
    alt_score = _score(
        alternative, timelines, evidence.model, checkpoint_event - lookback, checkpoint_event
    )
    net_edge = (
        alt_high * (Decimal("1") - fee_sell) / (alt_low * (Decimal("1") + fee_buy)) - Decimal("1")
        if alt_low is not None and alt_high is not None
        else Decimal("0")
    )
    n_b_ideal = _ideal_cycles(release_cash, position.cash_before_buy, net_edge)
    n_k_ideal = _ideal_cycles(release_cash, target_cash, net_edge)
    exact_b, exact_b_status = _exact_recovery(
        release_cash, position.cash_before_buy, alt_low, alt_high, fee_buy, fee_sell
    )
    exact_k, exact_k_status = _exact_recovery(
        release_cash, target_cash, alt_low, alt_high, fee_buy, fee_sell
    )
    fixed_destination_q, fixed_delta = _fixed_100_transform(alt_low, alt_high, fee_buy, fee_sell)
    fixed_original_q, fixed_residual, fixed_release, fixed_target = _fixed_position_values(
        position.low,
        position.high,
        current,
        fee_buy,
        fee_sell,
        release_fee,
    )
    fixed_b = _fixed_recovery_cycles(fixed_release, FIXED_RULER_CAPITAL, fixed_delta)
    fixed_k = _fixed_recovery_cycles(fixed_release, fixed_target, fixed_delta)
    survival = _same_band_survival_indexed(
        candidate,
        checkpoint_event,
        position.entry_event,
        age,
        episode_indexes[candidate],
    )
    first_cycle = _first_cycle_q90(alternative, checkpoint_event, timelines)
    q90 = (
        Decimal(str(first_cycle["q90_seconds"])) if first_cycle["q90_seconds"] is not None else None
    )
    recovery_time_k = (
        q90 + (Decimal(max(exact_k - 1, 0)) / rate_proxy * Decimal("3600"))
        if q90 is not None and exact_k is not None and rate_proxy > 0
        else None
    )
    original_rmst = (
        Decimal(str(survival["rmst24_seconds"])) if survival["rmst24_seconds"] is not None else None
    )
    rule_inputs = {
        "alternative_differs": alternative is not None and alternative != candidate,
        "survival_support_identified": survival["support"],
        "activity_support": c1h >= 30 and c24h >= 120,
        "loss_support": Decimal("0") < loss_fraction <= Decimal("0.0005"),
        "first_cycle_q90_support": first_cycle["support"],
        "exact_target_recovery_support": exact_k is not None,
        "strict_rmst_comparison": (
            recovery_time_k is not None
            and original_rmst is not None
            and recovery_time_k * Decimal("1.25") < original_rmst
        ),
    }
    would_release = all(rule_inputs.values())
    reason_code = _candidate_rule_reason(
        alternative=alternative,
        incumbent=candidate,
        survival_support=bool(survival["support"]),
        activity_support=bool(rule_inputs["activity_support"]),
        loss_fraction=loss_fraction,
        first_cycle_support=bool(first_cycle["support"]),
        exact_target_recovery=exact_k,
        strict_comparison=bool(rule_inputs["strict_rmst_comparison"]),
    )
    rule = {
        "status": "REPORT_ONLY_NOT_APPLIED",
        **rule_inputs,
        "recovery_time_k_seconds": _s(recovery_time_k),
        "original_rmst24_seconds": _s(original_rmst),
        "would_release": would_release,
        "reason_code": reason_code,
    }
    snapshot = {
        "protocol_version": PROTOCOL_VERSION,
        "model_id": MODEL_ID,
        "prefix_hash": canonical_hash(
            {
                "support_tape_hash": tape.tape_hash,
                "checkpoint_event_exclusive": checkpoint_event,
                "prefix_records": event_index + 1,
                "last_trade_event": int(tape.events[event_index]),
            }
        ),
        "position_index": position.index,
        "entry_event": position.entry_event,
        "entry_timestamp": position.entry_timestamp.isoformat(),
        "checkpoint_timestamp": checkpoint.isoformat(),
        "checkpoint_event": checkpoint_event,
        "age_seconds": age,
        "last_trade_event": int(tape.events[event_index]),
        "last_trade_timestamp": _event_to_datetime(int(tape.events[event_index])).isoformat(),
        "staleness_seconds": _s(
            Decimal(
                str(
                    (checkpoint - _event_to_datetime(int(tape.events[event_index]))).total_seconds()
                )
            )
        ),
        "B_cash_before_buy": _s(position.cash_before_buy),
        "quantity": _s(position.quantity),
        "residual_cash": _s(position.residual_cash),
        "low_tick": low_tick,
        "high_tick": high_tick,
        "current_tick": current_tick,
        "low": _s(position.low),
        "high": _s(position.high),
        "current_price": _s(current),
        "marked_equity": _s(position.residual_cash + position.quantity * current),
        "worst_marked_equity_prefix": _s(worst_mark),
        "worst_marked_loss_B_usdt": _s(position.cash_before_buy - worst_mark),
        "release_cash_R_T": _s(release_cash),
        "release_value_class": "THEORETICAL_PRICE_PATH_MARK_NOT_EXECUTABLE_FILL",
        "release_loss_B_usdt": _s(loss_usdt),
        "release_loss_B_fraction": _s(loss_fraction),
        "release_loss_B_bps": _s(loss_fraction * Decimal("10000")),
        "target_cash_K_at_high": _s(target_cash),
        "fee_buy_rate": _s(fee_buy),
        "fee_sell_rate": _s(fee_sell),
        "fee_release_rate": _s(release_fee),
        "alternative_relation": (
            "NO_CANDIDATE"
            if alternative is None
            else "SAME_CANDIDATE"
            if alternative == candidate
            else "DIFFERENT_CANDIDATE"
        ),
        "alternative_low_tick": None if alternative is None else alternative[0],
        "alternative_high_tick": None if alternative is None else alternative[0] + alternative[1],
        "alternative_low": _s(alt_low),
        "alternative_high": _s(alt_high),
        "alternative_score": _s(alt_score),
        "alternative_C1h": c1h,
        "alternative_C24h": c24h,
        "alternative_C_cycles_per_hour": _s(cycles_per_hour),
        "alternative_rate_proxy_nu": _s(rate_proxy),
        "alternative_net_edge": _s(net_edge),
        "recovery_cycles_B_ideal": n_b_ideal,
        "recovery_cycles_K_ideal": n_k_ideal,
        "recovery_cycles_B_exact": exact_b,
        "recovery_cycles_B_exact_status": exact_b_status,
        "recovery_cycles_K_exact": exact_k,
        "recovery_cycles_K_exact_status": exact_k_status,
        "recovery_time_rate_proxy_B_seconds": _s(_rate_time(exact_b, rate_proxy)),
        "recovery_time_rate_proxy_K_seconds": _s(_rate_time(exact_k, rate_proxy)),
        "fixed_100_original_quantity": _s(fixed_original_q),
        "fixed_100_residual_cash": _s(fixed_residual),
        "fixed_100_release_cash_R_T": _s(fixed_release),
        "fixed_100_target_cash_K_at_high": _s(fixed_target),
        "fixed_100_destination_quantity": _s(fixed_destination_q),
        "fixed_100_cycle_delta": _s(fixed_delta),
        "fixed_100_recovery_cycles_B": fixed_b,
        "fixed_100_recovery_cycles_K": fixed_k,
        "capital_lock_opportunity_proxy_24h_fixed_100": _s(
            rate_proxy * Decimal("24") * fixed_delta - (fixed_target - fixed_release)
        ),
        "capital_lock_opportunity_proxy_class": "CAUSAL_CONTINUITY_PROJECTION_ONLY",
        "break_even_release_loss_24h_fraction": _s(_break_even_24h(net_edge, rate_proxy)),
        "symmetric_break_even_fee_per_leg": _s(
            symmetric_break_even_fee(alt_low, alt_high)
            if alt_low is not None and alt_high is not None
            else None
        ),
        "remaining_hold": survival,
        "alternative_first_cycle_q90": first_cycle,
        "candidate_rule": rule,
        "executable_values": "UNKNOWN",
    }
    return snapshot


def _positions(evidence: _RunEvidence) -> tuple[_Position, ...]:
    cycles = evidence.replay.get("cycles")
    if not isinstance(cycles, list):
        raise CapitalReleaseDiagnosticError("M007 cycles are missing")
    cash = Decimal(str(evidence.replay["initial_quote"]))
    positions: list[_Position] = []
    for index, cycle in enumerate(cycles):
        if not isinstance(cycle, Mapping):
            raise CapitalReleaseDiagnosticError("cycle is not an object")
        low = Decimal(str(cycle["low"]))
        high = Decimal(str(cycle["high"]))
        quantity = Decimal(str(cycle["quantity"]))
        buy_fee = Decimal(str(cycle["buy_fee_quote"]))
        sell_fee = Decimal(str(cycle["sell_fee_quote"]))
        if buy_fee != 0 or sell_fee != 0:
            raise CapitalReleaseDiagnosticError("frozen M007 zero-fee scenario changed")
        residual = cash - quantity * low - buy_fee
        entry = int(cycle["entry_event"])
        exit_event = int(cycle["exit_event"])
        positions.append(
            _Position(
                index=index,
                entry_event=entry,
                entry_timestamp=_parse_dt(cycle["entry_timestamp"]),
                exit_event=exit_event,
                low=low,
                high=high,
                quantity=quantity,
                buy_fee=buy_fee,
                sell_fee=sell_fee,
                cash_before_buy=cash,
                residual_cash=residual,
            )
        )
        cash = residual + quantity * high - sell_fee
    if bool(evidence.replay.get("open_cycle_censored")):
        entry = int(evidence.replay["open_entry_event"])
        low = Decimal(str(evidence.replay["open_entry_price"]))
        quantity = Decimal(str(evidence.replay["final_inventory"]))
        buy_fee = Decimal(str(evidence.replay["open_buy_fee_quote"]))
        if buy_fee != 0:
            raise CapitalReleaseDiagnosticError("frozen M007 zero-fee scenario changed")
        residual_cash = cash - quantity * low - buy_fee
        positions.append(
            _Position(
                index=len(positions),
                entry_event=entry,
                entry_timestamp=_parse_dt(evidence.replay["open_entry_timestamp"]),
                exit_event=None,
                low=low,
                high=Decimal(str(evidence.replay.get("active_high", low))),
                quantity=quantity,
                buy_fee=buy_fee,
                sell_fee=Decimal("0"),
                cash_before_buy=cash,
                residual_cash=residual_cash,
                terminal=True,
            )
        )
        reconstructed_final_cash = residual_cash
    else:
        reconstructed_final_cash = cash
    if len(cycles) != int(evidence.replay["completed_cycles"]):
        raise CapitalReleaseDiagnosticError("M007 cycle count does not reconcile")
    if reconstructed_final_cash != Decimal(str(evidence.replay["final_cash"])):
        raise CapitalReleaseDiagnosticError("M007 cash ledger does not reconcile")
    return tuple(positions)


def _same_band_survival(
    candidate: tuple[int, int],
    checkpoint_event: int,
    focal_entry: int,
    age: int,
    timeline: CandidateTimeline,
) -> dict[str, Any]:
    return _same_band_survival_indexed(
        candidate,
        checkpoint_event,
        focal_entry,
        age,
        _EpisodeIndex.from_timeline(timeline),
    )


def _same_band_survival_indexed(
    candidate: tuple[int, int],
    checkpoint_event: int,
    focal_entry: int,
    age: int,
    index: _EpisodeIndex,
) -> dict[str, Any]:
    del candidate  # identity is bound by the caller's index lookup
    age_micros = age * 1_000_000
    causal_start_event = _datetime_to_micros(CAUSAL_START) * EVENT_ORDER_SCALE
    completed_limit = int(np.searchsorted(index.exits, checkpoint_event, side="left"))
    prefix_entries = index.entries[:completed_limit]
    prefix_durations = (
        index.exits[:completed_limit] // EVENT_ORDER_SCALE - prefix_entries // EVENT_ORDER_SCALE
    )
    eligible = (
        (prefix_entries >= causal_start_event)
        & (prefix_durations >= age_micros)
        & (prefix_entries != focal_entry)
    )
    selected_entries = prefix_entries[eligible]
    selected_residuals = prefix_durations[eligible] - age_micros
    residual_durations: list[Decimal] = []
    events: list[bool] = []
    entry_day_numbers = {
        int(entry) // EVENT_ORDER_SCALE // 1_000_000 // 86_400 for entry in selected_entries
    }
    for residual in selected_residuals:
        residual_durations.append(_micros_to_seconds(int(residual)))
        events.append(True)

    previous_exit = int(index.exits[completed_limit - 1]) if completed_limit else -1
    low_index = bisect_right(index.timeline.low_events, previous_exit)
    pending_entry = (
        int(index.timeline.low_events[low_index])
        if low_index < len(index.timeline.low_events)
        and int(index.timeline.low_events[low_index]) < checkpoint_event
        else None
    )
    if pending_entry is not None and pending_entry != focal_entry:
        elapsed_micros = _event_elapsed_micros(checkpoint_event, pending_entry)
        if pending_entry >= causal_start_event and elapsed_micros >= age_micros:
            residual_durations.append(_micros_to_seconds(elapsed_micros - age_micros))
            events.append(False)
            entry_day_numbers.add(pending_entry // EVENT_ORDER_SCALE // 1_000_000 // 86_400)

    focal_included = False
    if focal_entry >= causal_start_event and focal_entry < checkpoint_event:
        elapsed_micros = _event_elapsed_micros(checkpoint_event, focal_entry)
        if elapsed_micros >= age_micros:
            residual_durations.append(_micros_to_seconds(elapsed_micros - age_micros))
            events.append(False)
            entry_day_numbers.add(focal_entry // EVENT_ORDER_SCALE // 1_000_000 // 86_400)
            focal_included = True
    km = _kaplan_meier(residual_durations, events, RMST_CAP_SECONDS) if residual_durations else None
    followup = sum(duration >= RMST_CAP_SECONDS for duration in residual_durations)
    enough_observations = len(residual_durations) >= 30 and len(entry_day_numbers) >= 3
    support = enough_observations and km is not None and km.identified
    reasons: list[str] = []
    if len(residual_durations) < 30:
        reasons.append("RISK_SET_LT_30")
    if len(entry_day_numbers) < 3:
        reasons.append("ENTRY_DAYS_LT_3")
    if km is None or not km.identified:
        reasons.append("RMST_24H_NOT_IDENTIFIED")
    return {
        "risk_set": len(residual_durations),
        "entry_days": len(entry_day_numbers),
        "followup_24h_count": followup,
        "support": support,
        "support_reason": None if support else "+".join(reasons),
        "rmst24_seconds": _s(km.rmst if support and km else None),
        "rmst24_lower_bound_seconds": _s(km.lower_bound if km else None),
        "rmst24_upper_bound_seconds": _s(km.upper_bound if km else None),
        "maximum_supported_age_seconds": _s(km.maximum_time if km else None),
        "focal_included_as_right_censored": focal_included,
        "future_exit_values_contributed": False,
    }


def _prefix_serial_episodes(
    timeline: CandidateTimeline, checkpoint_event: int
) -> tuple[tuple[int, int | None], ...]:
    """Reconstruct serial episodes from arrays truncated strictly before T."""
    low_limit = bisect_left(timeline.low_events, checkpoint_event)
    high_limit = bisect_left(timeline.high_events, checkpoint_event)
    low_index = high_index = 0
    after = -1
    episodes: list[tuple[int, int | None]] = []
    while low_index < low_limit:
        low_index = bisect_right(timeline.low_events, after, lo=low_index, hi=low_limit)
        if low_index >= low_limit:
            break
        entry = int(timeline.low_events[low_index])
        high_index = bisect_right(
            timeline.high_events,
            entry,
            lo=high_index,
            hi=high_limit,
        )
        if high_index >= high_limit:
            episodes.append((entry, None))
            break
        exit_event = int(timeline.high_events[high_index])
        episodes.append((entry, exit_event))
        after = exit_event
        low_index += 1
        high_index += 1
    return tuple(episodes)


def _first_cycle_q90(
    candidate: tuple[int, int] | None,
    checkpoint_event: int,
    timelines: dict[tuple[int, int], CandidateTimeline],
) -> dict[str, Any]:
    if candidate is None or candidate not in timelines:
        return {"support": False, "reason": "NO_ALTERNATIVE_CANDIDATE", "q90_seconds": None}
    timeline = timelines[candidate]
    low_limit = bisect_left(timeline.low_events, checkpoint_event)
    high_limit = bisect_left(timeline.high_events, checkpoint_event)
    checkpoint = _event_to_datetime(checkpoint_event)
    window_start = checkpoint - timedelta(days=30)
    first_hour = window_start.replace(minute=0, second=0, microsecond=0)
    if first_hour < window_start:
        first_hour += timedelta(hours=1)
    durations: list[Decimal] = []
    observed: list[bool] = []
    days: set[str] = set()
    cursor = first_hour
    while cursor + timedelta(hours=1) <= checkpoint:
        origin_event = _datetime_to_micros(cursor) * EVENT_ORDER_SCALE
        low_index = bisect_left(timeline.low_events, origin_event, hi=low_limit)
        completion_event: int | None = None
        if low_index < low_limit:
            low_event = int(timeline.low_events[low_index])
            high_index = bisect_right(timeline.high_events, low_event, hi=high_limit)
            if high_index < high_limit:
                completion_event = int(timeline.high_events[high_index])
        end = completion_event if completion_event is not None else checkpoint_event
        duration = _event_elapsed_seconds(end, origin_event)
        durations.append(min(RMST_CAP_SECONDS, duration))
        observed.append(completion_event is not None and duration <= RMST_CAP_SECONDS)
        days.add(cursor.date().isoformat())
        cursor += timedelta(hours=1)
    q90 = kaplan_meier_q90(durations, observed, RMST_CAP_SECONDS) if durations else None
    support = len(durations) >= 30 and len(days) >= 3 and q90 is not None
    return {
        "support": support,
        "reason": None if support else "REQUIRES_30_ORIGINS_3_ENTRY_DAYS_AND_KM_Q90",
        "origins": len(durations),
        "origin_days": len(days),
        "q90_seconds": _s(q90),
        "future_event_values_read": False,
    }


def _exact_recovery_cycles(
    start: Decimal,
    target: Decimal,
    low: Decimal | None,
    high: Decimal | None,
    fee_buy: Decimal,
    fee_sell: Decimal,
) -> int | None:
    cycles, _status = _exact_recovery(start, target, low, high, fee_buy, fee_sell)
    return cycles


def _candidate_rule_reason(
    *,
    alternative: tuple[int, int] | None,
    incumbent: tuple[int, int],
    survival_support: bool,
    activity_support: bool,
    loss_fraction: Decimal,
    first_cycle_support: bool,
    exact_target_recovery: int | None,
    strict_comparison: bool,
) -> str:
    if alternative is None or alternative == incumbent:
        return "KEEP_NO_PRODUCTIVE_ALTERNATIVE"
    if not survival_support or not first_cycle_support:
        return "KEEP_INSUFFICIENT_CAUSAL_HISTORY"
    if not activity_support:
        return "KEEP_NO_PRODUCTIVE_ALTERNATIVE"
    if loss_fraction <= 0:
        return "KEEP_WAIT_EXPECTATION_FAVORABLE"
    if loss_fraction > Decimal("0.0005"):
        return "KEEP_LOSS_TOO_LARGE"
    if exact_target_recovery is None:
        return "KEEP_RECOVERY_TOO_SLOW"
    if not strict_comparison:
        return "KEEP_WAIT_EXPECTATION_FAVORABLE"
    return "CAPITAL_RELEASE_RECOVERY_ADVANTAGE"


def _exact_recovery(
    start: Decimal,
    target: Decimal,
    low: Decimal | None,
    high: Decimal | None,
    fee_buy: Decimal,
    fee_sell: Decimal,
) -> tuple[int | None, str]:
    if target <= start:
        return 0, "ALREADY_RECOVERED"
    if low is None or high is None or start <= 0:
        return None, "UNKNOWN_CANDIDATE_OR_CAPITAL"
    cash = start
    for count in range(1, 1_000_001):
        quantity = _rounded_quantity(cash, low, fee_buy)
        if quantity <= 0:
            return None, "UNRECOVERABLE_UNDER_ASSUMPTIONS"
        next_cash = (
            cash
            - quantity * low * (Decimal("1") + fee_buy)
            + quantity * high * (Decimal("1") - fee_sell)
        )
        if next_cash <= cash:
            return None, "UNRECOVERABLE_UNDER_ASSUMPTIONS"
        cash = next_cash
        if cash >= target:
            return count, "RECOVERABLE"
    return None, "COMPUTATION_LIMIT"


def _rounded_quantity(cash: Decimal, low: Decimal, fee_buy: Decimal) -> Decimal:
    if cash <= 0 or low <= 0:
        return Decimal("0")
    spendable = cash / (Decimal("1") + fee_buy)
    return (spendable / low / QUANTITY_STEP).to_integral_value(rounding=ROUND_DOWN) * QUANTITY_STEP


def _fixed_100_transform(
    low: Decimal | None, high: Decimal | None, fee_buy: Decimal, fee_sell: Decimal
) -> tuple[Decimal, Decimal]:
    if low is None or high is None:
        return Decimal("0"), Decimal("0")
    quantity = _rounded_quantity(FIXED_RULER_CAPITAL, low, fee_buy)
    delta = quantity * high * (Decimal("1") - fee_sell) - quantity * low * (Decimal("1") + fee_buy)
    return quantity, delta


def _fixed_position_values(
    low: Decimal,
    high: Decimal,
    current: Decimal,
    fee_buy: Decimal,
    fee_sell: Decimal,
    fee_release: Decimal,
) -> tuple[Decimal, Decimal, Decimal, Decimal]:
    quantity = _rounded_quantity(FIXED_RULER_CAPITAL, low, fee_buy)
    residual = FIXED_RULER_CAPITAL - quantity * low * (Decimal("1") + fee_buy)
    release = residual + quantity * current * (Decimal("1") - fee_release)
    target = residual + quantity * high * (Decimal("1") - fee_sell)
    return quantity, residual, release, target


def _fixed_recovery_cycles(start: Decimal, target: Decimal, delta: Decimal) -> int | None:
    if target <= start:
        return 0
    if delta <= 0:
        return None
    return int(((target - start) / delta).to_integral_value(rounding=ROUND_CEILING))


def _ideal_cycles(start: Decimal, target: Decimal, edge: Decimal) -> int | None:
    if target <= start:
        return 0
    if start <= 0 or edge <= 0:
        return None
    return max(
        0,
        int(
            ((target / start).ln() / (Decimal("1") + edge).ln()).to_integral_value(
                rounding=ROUND_CEILING
            )
        ),
    )


def _rate_time(count: int | None, rate: Decimal) -> Decimal | None:
    return None if count is None or rate <= 0 else Decimal(count) / rate * Decimal("3600")


def _break_even_24h(edge: Decimal, rate: Decimal) -> Decimal | None:
    if edge <= 0 or rate <= 0:
        return None
    cycles = int((rate * Decimal("24")).to_integral_value(rounding=ROUND_DOWN))
    return Decimal("1") - (Decimal("1") + edge) ** (-cycles)


def _checkpoint_ages() -> tuple[int, ...]:
    # The caller stops at each position's normal exit or physical cutoff.
    return INITIAL_AGES + tuple(range(259200, 366 * 86400, 86400))


def _summary(
    evidence: _RunEvidence,
    artifact_id: str,
    identity: Mapping[str, Any],
    positions: Sequence[_Position],
    snapshots: Sequence[Mapping[str, Any]],
    *,
    support_tape_manifest: TapeCacheManifest | None,
) -> dict[str, Any]:
    by_age: dict[str, int] = {}
    reasons: dict[str, int] = {}
    supported_remaining_hold = 0
    supported_first_cycle = 0
    would_release = 0
    for snapshot in snapshots:
        age = str(snapshot["age_seconds"])
        by_age[age] = by_age.get(age, 0) + 1
        remaining = snapshot["remaining_hold"]
        first_cycle = snapshot["alternative_first_cycle_q90"]
        rule = snapshot["candidate_rule"]
        assert isinstance(remaining, Mapping)
        assert isinstance(first_cycle, Mapping)
        assert isinstance(rule, Mapping)
        supported_remaining_hold += int(bool(remaining.get("support")))
        supported_first_cycle += int(bool(first_cycle.get("support")))
        would_release += int(bool(rule.get("would_release")))
        reason = str(rule.get("reason_code"))
        reasons[reason] = reasons.get(reason, 0) + 1
    return {
        "schema_version": PROTOCOL_VERSION,
        "status": "READY",
        "artifact_id": artifact_id,
        "identity": dict(identity),
        "source": {
            "model_id": evidence.model_id,
            "run_hash": evidence.run_hash,
            "evaluation_hash": evidence.evaluation_hash,
            "tape_hash": evidence.tape.tape_hash,
            "support_tape_hash": (
                support_tape_manifest.tape_hash if support_tape_manifest is not None else None
            ),
            "support_tape_cache_key": (
                support_tape_manifest.cache_key if support_tape_manifest is not None else None
            ),
            "physical_interval": evidence.run_manifest.get("interval"),
            "protections": evidence.run_manifest.get("run"),
        },
        "counts": {
            "positions": len(positions),
            "completed_positions": sum(not p.terminal for p in positions),
            "terminal_positions": sum(p.terminal for p in positions),
            "causal_snapshots": len(snapshots),
            "remaining_hold_supported": supported_remaining_hold,
            "alternative_first_cycle_supported": supported_first_cycle,
            "candidate_rule_would_release": would_release,
            "snapshots_by_age_seconds": by_age,
            "candidate_rule_reason_counts": reasons,
        },
        "outcomes": {
            "status": "NOT_COMPUTED",
            "reason": "CAUSAL_SNAPSHOT_PHASE_ONLY",
        },
        "known_parent_reference": {
            "completed_cycles": evidence.replay.get("completed_cycles"),
            "zero_cycle_days": evidence.replay.get("zero_cycle_days"),
            "final_marked_equity": evidence.replay.get("final_marked_equity"),
            "execution_class": evidence.replay.get("execution_class"),
        },
        "causal_snapshots_file": "causal-snapshots.jsonl",
    }


def _tick(value: Decimal, quantum: Decimal) -> int:
    result = value / quantum
    integral = result.to_integral_value()
    if result != integral:
        raise CapitalReleaseDiagnosticError("price is not representable on tape quantum")
    return int(integral)


def _minimum_tick_between(
    tape: SerialTape,
    sorted_price_ticks: Sequence[int],
    start_inclusive: int,
    end_exclusive: int,
) -> int:
    """Return a prefix minimum without materializing a multi-million-event slice."""
    for tick in sorted_price_ticks:
        occurrences = tape.occurrences[tick]
        index = bisect_left(occurrences, start_inclusive)
        if index < len(occurrences) and int(occurrences[index]) < end_exclusive:
            return int(tick)
    raise CapitalReleaseDiagnosticError("position prefix contains no observed trade")


def _price_tick(value: int, quantum: Decimal) -> Decimal:
    return Decimal(value) * quantum


def _hour_events() -> int:
    return 3_600 * 1_000_000 * EVENT_ORDER_SCALE


def _day_events() -> int:
    return 24 * _hour_events()


def _event_elapsed_micros(later: int, earlier: int) -> int:
    """Return elapsed wall-clock microseconds; event ordinals only break timestamp ties."""
    return later // EVENT_ORDER_SCALE - earlier // EVENT_ORDER_SCALE


def _micros_to_seconds(value: int) -> Decimal:
    return Decimal(value) / Decimal(1_000_000)


def _event_elapsed_seconds(later: int, earlier: int) -> Decimal:
    return _micros_to_seconds(_event_elapsed_micros(later, earlier))


def _rate(value: Decimal, notional: Decimal) -> Decimal:
    return Decimal("0") if notional == 0 else value / notional


def _parse_dt(value: Any) -> datetime:
    if not isinstance(value, str):
        raise CapitalReleaseDiagnosticError("timestamp must be ISO string")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise CapitalReleaseDiagnosticError("timestamp must be timezone-aware")
    return parsed.astimezone(UTC)


def _s(value: Any) -> str | None:
    return None if value is None else str(value)


def _git_sha() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], check=True, capture_output=True, text=True
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError) as error:
        raise CapitalReleaseDiagnosticError("cannot determine code SHA") from error


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, default=str) + "\n").encode()


def _jsonl_bytes(values: Sequence[Mapping[str, Any]]) -> bytes:
    return b"".join(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode() + b"\n"
        for value in values
    )


def _write_artifact(root: Path, artifact_id: str, files: Mapping[str, bytes]) -> None:
    root.parent.mkdir(parents=True, exist_ok=True)
    temp = Path(tempfile.mkdtemp(prefix=f".{artifact_id}.", dir=root.parent))
    try:
        descriptors: dict[str, Any] = {}
        for name, data in files.items():
            (temp / name).write_bytes(data)
            descriptors[name] = {"sha256": hashlib.sha256(data).hexdigest(), "size": len(data)}
        manifest = {
            "schema_version": PROTOCOL_VERSION,
            "status": "READY",
            "artifact_id": artifact_id,
            "files": descriptors,
            "content_hash": canonical_hash(descriptors),
        }
        (temp / "manifest.json").write_bytes(_json_bytes(manifest))
        try:
            os.replace(temp, root)
        except FileExistsError as error:
            raise CapitalReleaseDiagnosticError("diagnostic artifact race") from error
    finally:
        if temp.exists():
            for item in temp.iterdir():
                item.unlink()
            temp.rmdir()


def _validate_artifact(root: Path, artifact_id: str) -> None:
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("artifact_id") != artifact_id or manifest.get("status") != "READY":
        raise CapitalReleaseDiagnosticError("capital release artifact identity mismatch")
    for name, descriptor in manifest.get("files", {}).items():
        data = (root / name).read_bytes()
        if (
            len(data) != descriptor["size"]
            or hashlib.sha256(data).hexdigest() != descriptor["sha256"]
        ):
            raise CapitalReleaseDiagnosticError(f"capital release artifact corruption: {name}")


__all__ = [
    "CapitalReleaseDiagnosticError",
    "CapitalReleaseDiagnosticResult",
    "KaplanMeierResult",
    "build_capital_release_diagnostic",
    "build_capital_release_snapshots",
    "diagnose_capital_release",
    "kaplan_meier_q90",
    "kaplan_meier_rmst",
]
