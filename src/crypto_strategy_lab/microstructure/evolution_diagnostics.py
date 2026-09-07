"""Offline, causal diagnostics for two evaluated USDCUSDT model runs.

This module consumes only immutable registry artifacts and a READY tape cache.  It
does not replay a model or make a scientific decision.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import shutil
import tempfile
from bisect import bisect_left, bisect_right
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Final, cast

from crypto_strategy_lab.domain import canonical_hash
from crypto_strategy_lab.microstructure.serial_replay import (
    EVENT_ORDER_SCALE,
    USDCUSDT_TICK_CATALOG,
    CandidateTimeline,
    SerialModelConfig,
    SerialTape,
    _datetime_to_micros,
    _event_to_datetime,
    _score,
    _select,
    _selection_grid,
)
from crypto_strategy_lab.microstructure.tape_cache import (
    CACHE_SCHEMA,
    TapeCacheManifest,
    load_tape_cache,
    tape_cache_dir,
)
from crypto_strategy_lab.ml.model_registry import (
    ModelRegistry,
    evaluation_artifact_dir,
    run_artifact_dir,
)

SCHEMA_VERSION: Final = "usdcusdt-evolution-diagnostic-v2"
_HOUR_EVENTS: Final = 3_600 * 1_000_000 * EVENT_ORDER_SCALE
_DAY_EVENTS: Final = 24 * _HOUR_EVENTS
_ACTIVITY_SIGNALS: Final = ("UNKNOWN", "CONTRACTING", "NOT_CONTRACTING")
_PROTECTION_KEYS: Final = {
    "validation_accessed",
    "locked_test_accessed",
    "testnet_accessed",
}
_LIVE_PROTECTION_KEYS: Final = {"binance_live_accessed", "live_accessed"}
_LEGACY_PROTECTION_KEYS: Final = {"live_accessed", "validation", "locked_test", "testnet"}


class EvolutionDiagnosticError(ValueError):
    """Raised when diagnostic provenance or causal reconstruction is invalid."""


@dataclass(frozen=True, slots=True)
class EvolutionDiagnosticResult:
    artifact_id: str
    artifact_dir: Path
    report_path: Path
    summary: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class _RunEvidence:
    model_id: str
    model_hash: str
    run_hash: str
    evaluation_hash: str
    model: SerialModelConfig
    replay: Mapping[str, Any]
    run_manifest: Mapping[str, Any]
    evaluation: Mapping[str, Any]
    tape: SerialTape
    tape_manifest: TapeCacheManifest


@dataclass(slots=True)
class _CohortAccumulator:
    count: int = 0
    signals: dict[str, list[Decimal]] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        self.signals = {
            field: []
            for field in (
                "selection_age_seconds",
                "prior_high_age_seconds",
                "canonical_lookback_cycles",
                "canonical_lookback_score",
            )
        }

    def add(self, item: Mapping[str, Any]) -> None:
        self.count += 1
        for field, values in self.signals.items():
            value = item.get(field)
            if value is not None:
                values.append(Decimal(str(value)))

    def result(self) -> dict[str, Any]:
        return {
            "count": self.count,
            "signals": {name: _quantiles(sorted(values)) for name, values in self.signals.items()},
        }


def diagnose_evolution(
    *,
    parent_model_id: str,
    challenger_model_id: str,
    artifact_root: str | Path = Path("artifacts"),
    report_root: str | Path = Path("reports"),
) -> EvolutionDiagnosticResult:
    """Write an idempotent causal diagnostic for two evaluated model runs."""
    if parent_model_id == challenger_model_id:
        raise EvolutionDiagnosticError("parent and challenger must be distinct")
    if (parent_model_id, challenger_model_id) != ("M007", "M009"):
        raise EvolutionDiagnosticError(
            "activity contraction diagnostic requires M007 as primary and M009 as dependent"
        )
    registry = ModelRegistry(artifact_root=artifact_root, report_root=report_root)
    parent = _load_run_evidence(registry, parent_model_id, Path(artifact_root))
    challenger = _load_run_evidence(registry, challenger_model_id, Path(artifact_root))
    _validate_pair(parent, challenger)
    artifact_id = canonical_hash(
        {
            "schema_version": SCHEMA_VERSION,
            "models": [
                {
                    "model_id": parent.model_id,
                    "model_hash": parent.model_hash,
                    "run_hash": parent.run_hash,
                    "evaluation_hash": parent.evaluation_hash,
                },
                {
                    "model_id": challenger.model_id,
                    "model_hash": challenger.model_hash,
                    "run_hash": challenger.run_hash,
                    "evaluation_hash": challenger.evaluation_hash,
                },
            ],
            "tape_cache_key": _tape_cache_key(parent.run_manifest),
            "tape_hash": parent.tape_manifest.tape_hash,
        }
    )
    root = Path(artifact_root) / "usdcusdt" / "evolution-diagnostics" / artifact_id
    report_path = (
        Path(report_root)
        / "usdcusdt"
        / (f"evolution-diagnostic-{parent_model_id}-{challenger_model_id}.json")
    )
    if root.exists():
        summary = _validate_existing(root, artifact_id)
        _write_report(report_path, summary)
        return EvolutionDiagnosticResult(artifact_id, root, report_path, summary)
    summary, files = _build_summary(parent, challenger, artifact_id)
    _write_artifact(root, artifact_id, summary, files)
    _write_report(report_path, summary)
    return EvolutionDiagnosticResult(artifact_id, root, report_path, summary)


run_evolution_diagnostic = diagnose_evolution


def _load_run_evidence(registry: ModelRegistry, model_id: str, artifact_root: Path) -> _RunEvidence:
    registration = registry.get(model_id)
    events = registry.journal()
    evaluations = [
        event
        for event in events
        if event.get("event_type") == "EVALUATION_RECORDED"
        and event.get("payload", {}).get("model_id") == model_id
    ]
    if not evaluations:
        raise EvolutionDiagnosticError(f"no evaluated run for {model_id}")
    evaluation_event = evaluations[-1]
    evaluation_payload = evaluation_event["payload"]
    run_hash = str(evaluation_payload.get("run_hash", ""))
    evaluation_hash = str(evaluation_payload.get("EVALUATION_HASH", ""))
    if not run_hash or not evaluation_hash:
        raise EvolutionDiagnosticError(f"evaluation identity is incomplete for {model_id}")
    run_events = [
        event
        for event in events
        if event.get("event_type") == "RUN_REGISTERED"
        and event.get("payload", {}).get("model_id") == model_id
        and event.get("payload", {}).get("RUN_HASH") == run_hash
    ]
    if len(run_events) != 1:
        raise EvolutionDiagnosticError(f"run identity is ambiguous for {model_id}")
    run_payload = run_events[0]["payload"]
    run_path = run_artifact_dir(model_id, run_hash, artifact_root) / "run-manifest.json"
    eval_path = (
        evaluation_artifact_dir(model_id, run_hash, evaluation_hash, artifact_root) / "replay.json"
    )
    try:
        run_manifest = json.loads(run_path.read_text(encoding="utf-8"))
        replay = json.loads(eval_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise EvolutionDiagnosticError(f"cannot read immutable artifacts for {model_id}") from error
    _validate_protections(run_manifest)
    _validate_run_identity(
        registration.model_hash,
        model_id,
        run_hash,
        evaluation_payload,
        run_payload,
        run_manifest,
        replay,
    )
    cache_key = _tape_cache_key(run_manifest)
    cache_manifest_path = tape_cache_dir(cache_key, artifact_root) / "manifest.json"
    try:
        cache_manifest = TapeCacheManifest.model_validate_json(
            cache_manifest_path.read_text(encoding="utf-8")
        )
    except (OSError, ValueError) as error:
        raise EvolutionDiagnosticError(f"invalid tape cache manifest for {model_id}") from error
    interval = _interval(run_manifest)
    if cache_manifest.dataset_hash != run_manifest["dataset_hash"]:
        raise EvolutionDiagnosticError("tape dataset does not match run")
    if (
        cache_manifest.end_exclusive.isoformat()
        != _parse_datetime(interval["end_exclusive"]).isoformat()
    ):
        raise EvolutionDiagnosticError("tape cutoff does not match run cutoff")
    if cache_manifest.cache_key != cache_key:
        raise EvolutionDiagnosticError("tape cache key does not match run")
    if _tape_hash_from_manifest(run_manifest) != cache_manifest.tape_hash:
        raise EvolutionDiagnosticError("tape hash does not match run")
    try:
        tape = load_tape_cache(
            tape_cache_dir(cache_key, artifact_root),
            expected_identity={
                "schema_version": CACHE_SCHEMA,
                "dataset_hash": cache_manifest.dataset_hash,
                "tick_catalog_hash": cache_manifest.tick_catalog_hash,
                "tick_source_policy": cache_manifest.tick_source_policy,
                "tick_source_url": cache_manifest.tick_source_url,
                "start": cache_manifest.start,
                "end_exclusive": cache_manifest.end_exclusive,
                "quantum": cache_manifest.quantum,
            },
            tick_catalog=USDCUSDT_TICK_CATALOG,
        )
    except (OSError, ValueError) as error:
        raise EvolutionDiagnosticError(f"tape cache integrity failure for {model_id}") from error
    config_path = artifact_root / "usdcusdt" / "models" / model_id / "config.json"
    try:
        config_payload = json.loads(config_path.read_text(encoding="utf-8"))
        model_config = SerialModelConfig.model_validate(
            {
                "model_id": model_id,
                "parent_model_id": registration.lineage.parent_model_id,
                **config_payload["model"],
            }
        )
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise EvolutionDiagnosticError(f"invalid model config for {model_id}") from error
    if config_payload.get("MODEL_HASH") != registration.model_hash:
        raise EvolutionDiagnosticError(f"model hash mismatch for {model_id}")
    return _RunEvidence(
        model_id=model_id,
        model_hash=registration.model_hash,
        run_hash=run_hash,
        evaluation_hash=evaluation_hash,
        model=model_config,
        replay=replay,
        run_manifest=run_manifest,
        evaluation=evaluation_payload,
        tape=tape,
        tape_manifest=cache_manifest,
    )


def load_evaluated_run_evidence(
    model_id: str,
    *,
    artifact_root: str | Path = Path("artifacts"),
    report_root: str | Path = Path("reports"),
) -> _RunEvidence:
    """Load one immutable evaluated run through the canonical diagnostic loader.

    Consumers that need read-only evidence must use this entry point instead of
    reconstructing registry, run, evaluation, and tape validation independently.
    """
    registry = ModelRegistry(artifact_root=artifact_root, report_root=report_root)
    return _load_run_evidence(registry, model_id, Path(artifact_root))


def _validate_pair(parent: _RunEvidence, challenger: _RunEvidence) -> None:
    fields = ("dataset_hash", "SCENARIO_HASH", "campaign_snapshot_id")
    for field in fields:
        if parent.run_manifest.get(field) != challenger.run_manifest.get(field):
            raise EvolutionDiagnosticError(f"models do not share {field}")
    if _interval(parent.run_manifest) != _interval(challenger.run_manifest):
        raise EvolutionDiagnosticError("models do not share interval/cutoff")
    if _tape_cache_key(parent.run_manifest) != _tape_cache_key(challenger.run_manifest):
        raise EvolutionDiagnosticError("models do not share tape cache key")
    if parent.tape_manifest.tape_hash != challenger.tape_manifest.tape_hash:
        raise EvolutionDiagnosticError("models do not share tape hash")


def _build_summary(
    parent: _RunEvidence, challenger: _RunEvidence, artifact_id: str
) -> tuple[dict[str, Any], dict[str, bytes]]:
    parent_data = _diagnose_model(parent)
    challenger_data = _diagnose_model(
        challenger, excluded_entry_events=parent_data["entry_event_ids"]
    )
    summary = {
        "schema_version": SCHEMA_VERSION,
        "status": "READY",
        "artifact_id": artifact_id,
        "identity": {
            "parent_model_id": parent.model_id,
            "challenger_model_id": challenger.model_id,
            "parent_model_hash": parent.model_hash,
            "challenger_model_hash": challenger.model_hash,
            "parent_run_hash": parent.run_hash,
            "challenger_run_hash": challenger.run_hash,
            "parent_evaluation_hash": parent.evaluation_hash,
            "challenger_evaluation_hash": challenger.evaluation_hash,
            "dataset_hash": parent.run_manifest["dataset_hash"],
            "scenario_hash": parent.run_manifest["SCENARIO_HASH"],
            "campaign_snapshot_id": parent.run_manifest["campaign_snapshot_id"],
            "interval": _interval(parent.run_manifest),
            "tape_cache_key": _tape_cache_key(parent.run_manifest),
            "tape_hash": parent.tape_manifest.tape_hash,
            "tape_content_hash": parent.tape_manifest.content_hash,
            "protections": {
                "validation_accessed": False,
                "locked_test_accessed": False,
                "binance_live_accessed": False,
                "testnet_accessed": False,
            },
        },
        "models": {
            parent.model_id: parent_data["summary"],
            challenger.model_id: challenger_data["summary"],
        },
        "cohorts": {
            parent.model_id: parent_data["cohorts"],
            challenger.model_id: challenger_data["cohorts"],
        },
        "entry_event_overlap": {
            "primary_model_id": parent.model_id,
            "dependent_model_id": challenger.model_id,
            "shared_count": len(
                parent_data["entry_event_ids"] & challenger_data["entry_event_ids"]
            ),
            "unique_counts": {
                parent.model_id: len(
                    parent_data["entry_event_ids"] - challenger_data["entry_event_ids"]
                ),
                challenger.model_id: len(
                    challenger_data["entry_event_ids"] - parent_data["entry_event_ids"]
                ),
            },
        },
        "dependent_verification": {
            "model_id": challenger.model_id,
            "shared_events_excluded": len(
                parent_data["entry_event_ids"] & challenger_data["entry_event_ids"]
            ),
            "activity_contraction_on_unique_events": challenger_data["dependent_unique_activity"],
        },
    }
    files: dict[str, bytes] = {}
    long_holds: dict[str, Any] = {}
    aggregates: dict[str, Any] = {}
    aggregate_rows: list[dict[str, Any]] = []
    for evidence, data in ((parent, parent_data), (challenger, challenger_data)):
        long_holds[evidence.model_id] = data["long_holds"]
        aggregates[evidence.model_id] = data["aggregates"]
        aggregate_rows.extend(
            {"model_id": evidence.model_id, **row} for row in data["aggregate_rows"]
        )
    files["long-holds.json"] = _json_bytes(long_holds)
    files["aggregates.json"] = _json_bytes(aggregates)
    files["aggregates.csv"] = _csv_bytes(aggregate_rows)
    return summary, files


def _diagnose_model(
    evidence: _RunEvidence, *, excluded_entry_events: set[int] | None = None
) -> dict[str, Any]:
    replay = evidence.replay
    initial = _decimal(replay, "initial_quote")
    cash = initial
    cycles = replay.get("cycles")
    if not isinstance(cycles, list):
        raise EvolutionDiagnosticError(f"cycles missing for {evidence.model_id}")
    timelines = _timelines(evidence)
    selections = _selection_points(evidence, cycles)
    long_holds: list[dict[str, Any]] = []
    cohort_accumulators = {
        "LONG_HOLD": _CohortAccumulator(),
        "OTHER": _CohortAccumulator(),
    }
    entry_count = 0
    entry_event_ids: set[int] = set()
    activity_stats = _new_activity_stats()
    dependent_unique_stats = _new_activity_stats()
    dependent_unique_count = 0
    realized_total = Decimal("0")
    sum_logs = Decimal("0")
    aggregates: dict[str, dict[str, dict[str, Decimal | int]]] = defaultdict(dict)
    for cycle in cycles:
        if not isinstance(cycle, Mapping):
            raise EvolutionDiagnosticError("cycle is not an object")
        item, cash = _cycle_entry(evidence, cycle, cash, timelines, selections)
        entry_count += 1
        entry_event_ids.add(int(item["entry_event"]))
        _record_activity(activity_stats, item)
        is_dependent_unique = (
            excluded_entry_events is not None
            and int(item["entry_event"]) not in excluded_entry_events
        )
        if is_dependent_unique:
            dependent_unique_count += 1
            _record_activity(dependent_unique_stats, item)
        realized_total += Decimal(item["realized"])
        cohort_accumulators[item["cohort"]].add(item)
        if item["cohort"] == "LONG_HOLD":
            long_holds.append(item)
        sum_logs += Decimal(item["log_return"])
        _aggregate(aggregates, "exit_month", item["exit_timestamp"][:7], item)
        _aggregate(aggregates, "entry_month", item["entry_timestamp"][:7], item)
        _aggregate(aggregates, "low", item["low"], item)
        _aggregate(aggregates, "high", item["high"], item)
        _aggregate(aggregates, "level", f"{item['low']}->{item['high']}", item)
        _aggregate(aggregates, "selection_tick", item["tick_at_selection"], item)
        _aggregate(aggregates, "entry_tick", item["tick_at_entry"], item)
        _aggregate(aggregates, "activity_signal", item["activity_signal"], item)
        _aggregate(aggregates, "cohort", item["cohort"], item)
        breakdown_key = (
            f"{item['entry_timestamp'][:7]}|"
            f"selection_tick={item['tick_at_selection'] or 'UNKNOWN'}|"
            f"signal={item['activity_signal']}|cohort={item['cohort']}"
        )
        _aggregate(aggregates, "activity_breakdown", breakdown_key, item)
        if is_dependent_unique:
            _aggregate(aggregates, "dependent_unique_activity_breakdown", breakdown_key, item)
    final_cash = _decimal(replay, "final_cash")
    open_censored = bool(replay.get("open_cycle_censored"))
    terminal_context: dict[str, Any] = {}
    if open_censored:
        open_inventory = _decimal(replay, "final_inventory")
        open_price = _decimal(replay, "open_entry_price")
        open_fee = _decimal(replay, "open_buy_fee_quote")
        if final_cash + open_inventory * open_price + open_fee != cash:
            raise EvolutionDiagnosticError(
                f"open position does not reconcile for {evidence.model_id}"
            )
        marked = _decimal(replay, "final_marked_equity")
        terminal_log = (marked / cash).ln()
        terminal_context = _terminal_context(evidence, timelines, selections)
    else:
        if final_cash != cash:
            raise EvolutionDiagnosticError(
                f"terminal cash does not reconcile for {evidence.model_id}"
            )
        marked = final_cash
        terminal_log = Decimal("0")
    initial_to_flat = (cash / initial).ln()
    initial_to_marked = (marked / initial).ln()
    terminal = {
        "last_flat_cash": _string(cash),
        "open_cycle_censored": open_censored,
        "terminal_final_cash": _string(final_cash),
        "terminal_marked_equity": _string(marked),
        "terminal_marked_ratio": _string(marked / cash),
        "terminal_log": _string(terminal_log),
        "sum_cycle_logs": _string(sum_logs),
        "ln_last_flat_over_initial": _string(initial_to_flat),
        "ln_marked_over_initial": _string(initial_to_marked),
        "log_reconciliation_error": _string(sum_logs + terminal_log - initial_to_marked),
        "open_entry_timestamp": replay.get("open_entry_timestamp"),
        "open_holding_seconds": replay.get("open_holding_seconds"),
        "completed_duration_seconds": None,
        "observed_censor_age_seconds": replay.get("open_holding_seconds"),
        "causal_entry": terminal_context,
    }
    aggregate_rows = [
        {
            "dimension": dimension,
            "key": key,
            **{name: _string(value) for name, value in values.items()},
        }
        for dimension, grouped in aggregates.items()
        for key, values in grouped.items()
    ]
    activity_summary = _activity_summary(activity_stats, entry_count)
    dependent_unique_activity = (
        _activity_summary(dependent_unique_stats, dependent_unique_count)
        if excluded_entry_events is not None
        else None
    )
    return {
        "summary": {
            "initial_quote": _string(initial),
            "completed_cycles": entry_count,
            "all_entries_evaluated": entry_count,
            "final_marked_equity": _string(marked),
            "realized_total": _string(realized_total),
            "long_hold_count": len(long_holds),
            "activity_contraction": activity_summary,
            "terminal": terminal,
        },
        "entries": (),
        "long_holds": {
            "completed": long_holds,
            "terminal_censored": [terminal] if open_censored else [],
        },
        "aggregates": {dimension: dict(grouped) for dimension, grouped in aggregates.items()},
        "aggregate_rows": aggregate_rows,
        "entry_event_ids": entry_event_ids,
        "dependent_unique_activity": dependent_unique_activity,
        "cohorts": {
            name: accumulator.result() for name, accumulator in cohort_accumulators.items()
        },
    }


def _cycle_entry(
    evidence: _RunEvidence,
    cycle: Mapping[str, Any],
    cash: Decimal,
    timelines: dict[tuple[int, int], CandidateTimeline],
    selections: _SelectionHistory,
) -> tuple[dict[str, Any], Decimal]:
    low = _decimal(cycle, "low")
    high = _decimal(cycle, "high")
    quantity = _decimal(cycle, "quantity")
    buy_fee = _decimal(cycle, "buy_fee_quote")
    sell_fee = _decimal(cycle, "sell_fee_quote")
    entry = int(cycle["entry_event"])
    exit_event = int(cycle["exit_event"])
    entry_index = bisect_left(evidence.tape.events, entry)
    exit_index = bisect_left(evidence.tape.events, exit_event)
    if (
        entry_index >= len(evidence.tape.events)
        or int(evidence.tape.events[entry_index]) != entry
        or exit_index >= len(evidence.tape.events)
        or int(evidence.tape.events[exit_index]) != exit_event
        # One price-path event may cross LOW and HIGH and therefore complete a
        # cycle at the same event ordinal.  The canonical replay deliberately
        # records those as zero-duration cycles.
        or entry > exit_event
    ):
        raise EvolutionDiagnosticError("cycle events are absent or out of order")
    current = _tick_candidate(low, high, evidence.tape.tick_size)
    selection = selections.at(entry)
    if selection is None or selection[1] != current:
        raise EvolutionDiagnosticError(
            f"active endpoints do not match cycle for {evidence.model_id}"
        )
    _, _, selection_tick, selection_timestamp = selection
    entry_timestamp = _event_to_datetime(entry)
    exit_timestamp = _event_to_datetime(exit_event)
    if "entry_timestamp" in cycle and _parse_datetime(cycle["entry_timestamp"]) != entry_timestamp:
        raise EvolutionDiagnosticError("cycle entry timestamp does not match event")
    if "exit_timestamp" in cycle and _parse_datetime(cycle["exit_timestamp"]) != exit_timestamp:
        raise EvolutionDiagnosticError("cycle exit timestamp does not match event")
    timeline = timelines.get(current)
    if timeline is None:
        raise EvolutionDiagnosticError("cycle candidate is absent from canonical timelines")
    high_index = bisect_left(timeline.high_events, entry)
    if high_index == 0:
        prior_high_age = None
    else:
        prior_high_age = _seconds(
            entry_timestamp - _event_to_datetime(timeline.high_events[high_index - 1])
        )
    lookback = evidence.model.lookback_minutes * 60 * 1_000_000 * EVENT_ORDER_SCALE
    lookback_cycles = timeline.contained_cycles(entry - lookback, entry)
    lookback_score = _score(current, timelines, evidence.model, entry - lookback, entry)
    activity = _activity_contraction(timeline, entry)
    tick_at_entry, eligible, grid_multiple = _selection_grid(
        evidence.model,
        USDCUSDT_TICK_CATALOG if evidence.model.distance_semantics is not None else None,
        entry,
        evidence.tape.tick_size,
        evidence.tape.observed_tick_evidence_event,
    )
    hold_seconds = _seconds(exit_timestamp - entry_timestamp)
    alternative = None
    alternative_score: Decimal | None = None
    if hold_seconds >= Decimal("86400"):
        alternative = _select(
            timelines,
            evidence.model,
            entry - lookback,
            entry,
            eligible_distances=eligible,
            grid_multiple=grid_multiple,
            excluded_candidate=current,
        )
        alternative_score = _score(alternative, timelines, evidence.model, entry - lookback, entry)
    cash_before = cash
    notional = quantity * low
    residual = cash_before - notional - buy_fee
    proceeds = quantity * high
    cash_after = residual + proceeds - sell_fee
    realized = proceeds - sell_fee - (notional + buy_fee)
    if cash_after <= 0 or cash_before <= 0:
        raise EvolutionDiagnosticError("non-positive cash in cycle reconstruction")
    fee_free = buy_fee == 0 and sell_fee == 0
    full_edge = cash_before * (high / low - Decimal("1")) if fee_free else None
    residual_drag = full_edge - realized if full_edge is not None else None
    item: dict[str, Any] = {
        "model_id": evidence.model_id,
        "run_hash": evidence.run_hash,
        "evaluation_hash": evidence.evaluation_hash,
        "entry_event": entry,
        "entry_timestamp": entry_timestamp.isoformat(),
        "exit_timestamp": exit_timestamp.isoformat(),
        "hold_seconds": _string(hold_seconds),
        "low": _string(low),
        "high": _string(high),
        "quantity": _string(quantity),
        "cash_before": _string(cash_before),
        "buy_notional": _string(notional),
        "buy_fee_quote": _string(buy_fee),
        "residual_cash_after_buy": _string(residual),
        "sell_proceeds": _string(proceeds),
        "sell_fee_quote": _string(sell_fee),
        "cash_after": _string(cash_after),
        "realized": _string(realized),
        "return_fraction": _string(cash_after / cash_before - Decimal("1")),
        "log_return": _string((cash_after / cash_before).ln()),
        "full_capital_gross_edge": _string(full_edge),
        "rounding_residual_drag": _string(residual_drag),
        "selection_timestamp": selection_timestamp.isoformat(),
        "selection_age_seconds": _string(_seconds(entry_timestamp - selection_timestamp)),
        "prior_high_age_seconds": None if prior_high_age is None else _string(prior_high_age),
        "canonical_lookback_cycles": lookback_cycles,
        "canonical_lookback_score": _string(lookback_score),
        "activity_c1h": activity["C1h"],
        "activity_c24h": activity["C24h"],
        "activity_ratio": activity["R"],
        "activity_signal": activity["signal"],
        "C1h": activity["C1h"],
        "C24h": activity["C24h"],
        "R": activity["R"],
        "tick_at_selection": _string(selection_tick),
        "tick_at_entry": None if tick_at_entry is None else _string(tick_at_entry),
        "selection_tick_regime": _string(selection_tick),
        "entry_tick_regime": None if tick_at_entry is None else _string(tick_at_entry),
        "alternative_low": None
        if alternative is None
        else _string(_price_tick(alternative[0], evidence.tape.tick_size)),
        "alternative_high": None
        if alternative is None
        else _string(_price_tick(alternative[0] + alternative[1], evidence.tape.tick_size)),
        "alternative_score": _string(alternative_score),
        "cohort": "LONG_HOLD" if hold_seconds >= Decimal("86400") else "OTHER",
    }
    return item, cash_after


def _terminal_context(
    evidence: _RunEvidence,
    timelines: dict[tuple[int, int], CandidateTimeline],
    selections: _SelectionHistory,
) -> dict[str, Any]:
    replay = evidence.replay
    try:
        entry = int(replay["open_entry_event"])
    except (KeyError, TypeError, ValueError) as error:
        raise EvolutionDiagnosticError("censored position lacks open_entry_event") from error
    low = _decimal(replay, "open_entry_price")
    active_high = replay.get("active_high")
    if active_high in (None, ""):
        selection = selections.at(entry)
        active = None if selection is None else selection[1]
        if active is None:
            raise EvolutionDiagnosticError("censored position lacks active endpoints")
        current = active
    else:
        current = _tick_candidate(low, Decimal(str(active_high)), evidence.tape.tick_size)
    selection = selections.at(entry)
    if selection is None or selection[1] != current:
        raise EvolutionDiagnosticError("censored position endpoints do not match selection history")
    lookback = evidence.model.lookback_minutes * 60 * 1_000_000 * EVENT_ORDER_SCALE
    timeline = timelines.get(current)
    if timeline is None:
        raise EvolutionDiagnosticError("censored candidate is absent from canonical timelines")
    entry_timestamp = _event_to_datetime(entry)
    high_index = bisect_left(timeline.high_events, entry)
    prior_high_age = (
        None
        if high_index == 0
        else _seconds(entry_timestamp - _event_to_datetime(timeline.high_events[high_index - 1]))
    )
    lookback_cycles = timeline.contained_cycles(entry - lookback, entry)
    lookback_score = _score(current, timelines, evidence.model, entry - lookback, entry)
    activity = _activity_contraction(timeline, entry)
    tick, eligible, grid_multiple = _selection_grid(
        evidence.model,
        USDCUSDT_TICK_CATALOG if evidence.model.distance_semantics is not None else None,
        entry,
        evidence.tape.tick_size,
        evidence.tape.observed_tick_evidence_event,
    )
    alternative = _select(
        timelines,
        evidence.model,
        entry - lookback,
        entry,
        eligible_distances=eligible,
        grid_multiple=grid_multiple,
        excluded_candidate=current,
    )
    return {
        "entry_event": entry,
        "entry_timestamp": entry_timestamp.isoformat(),
        "selection_timestamp": selection[3].isoformat(),
        "selection_age_seconds": _string(_seconds(entry_timestamp - selection[3])),
        "prior_high_age_seconds": _string(prior_high_age),
        "canonical_lookback_cycles": lookback_cycles,
        "canonical_lookback_score": _string(lookback_score),
        "activity_c1h": activity["C1h"],
        "activity_c24h": activity["C24h"],
        "activity_ratio": activity["R"],
        "activity_signal": activity["signal"],
        "C1h": activity["C1h"],
        "C24h": activity["C24h"],
        "R": activity["R"],
        "low": _string(_price_tick(current[0], evidence.tape.tick_size)),
        "high": _string(_price_tick(current[0] + current[1], evidence.tape.tick_size)),
        "tick_at_selection": _string(selection[2]),
        "tick_at_entry": None if tick is None else _string(tick),
        "selection_tick_regime": _string(selection[2]),
        "entry_tick_regime": None if tick is None else _string(tick),
        "alternative_low": None
        if alternative is None
        else _string(_price_tick(alternative[0], evidence.tape.tick_size)),
        "alternative_high": None
        if alternative is None
        else _string(_price_tick(alternative[0] + alternative[1], evidence.tape.tick_size)),
        "alternative_score": _string(
            _score(alternative, timelines, evidence.model, entry - lookback, entry)
        ),
    }


def _activity_contraction(timeline: CandidateTimeline, entry: int) -> dict[str, int | str | None]:
    """Classify the selected candidate's activity before an entry event.

    Both windows are end-exclusive, matching ``CandidateTimeline``'s causal
    counting contract.  The ratio is deliberately fixed by the protocol.
    """
    c1h = timeline.contained_cycles(entry - _HOUR_EVENTS, entry)
    c24h = timeline.contained_cycles(entry - _DAY_EVENTS, entry)
    if c24h == 0:
        ratio: str | None = None
        signal = "UNKNOWN"
    else:
        ratio_decimal = Decimal(24 * c1h) / Decimal(c24h)
        ratio = _string(ratio_decimal)
        signal = "CONTRACTING" if ratio_decimal < 1 else "NOT_CONTRACTING"
    return {"C1h": c1h, "C24h": c24h, "R": ratio, "signal": signal}


def _new_activity_stats() -> dict[str, dict[str, Decimal | int]]:
    return {
        signal: {
            "entries": 0,
            "long_holds_completed": 0,
            "other_entries": 0,
            "sum_log_return": Decimal("0"),
        }
        for signal in _ACTIVITY_SIGNALS
    }


def _record_activity(stats: dict[str, dict[str, Decimal | int]], item: Mapping[str, Any]) -> None:
    signal = str(item["activity_signal"])
    bucket = stats[signal]
    bucket["entries"] = int(bucket["entries"]) + 1
    cohort_field = "long_holds_completed" if item["cohort"] == "LONG_HOLD" else "other_entries"
    bucket[cohort_field] = int(bucket[cohort_field]) + 1
    bucket["sum_log_return"] = Decimal(bucket["sum_log_return"]) + Decimal(str(item["log_return"]))


def _rate(numerator: int, denominator: int) -> str | None:
    return None if denominator == 0 else _string(Decimal(numerator) / Decimal(denominator))


def _activity_summary(
    stats: dict[str, dict[str, Decimal | int]], total_entries: int
) -> dict[str, Any]:
    total_long = sum(int(bucket["long_holds_completed"]) for bucket in stats.values())
    total_other = sum(int(bucket["other_entries"]) for bucket in stats.values())
    known_long = total_long - int(stats["UNKNOWN"]["long_holds_completed"])
    known_other = total_other - int(stats["UNKNOWN"]["other_entries"])
    contracting_long = int(stats["CONTRACTING"]["long_holds_completed"])
    contracting_other = int(stats["CONTRACTING"]["other_entries"])
    return {
        "entries": total_entries,
        "counts_by_signal": {signal: int(stats[signal]["entries"]) for signal in _ACTIVITY_SIGNALS},
        "rates_by_signal": {
            signal: _rate(int(stats[signal]["entries"]), total_entries)
            for signal in _ACTIVITY_SIGNALS
        },
        "by_signal": {
            signal: {
                key: _string(value) if isinstance(value, Decimal) else value
                for key, value in stats[signal].items()
            }
            for signal in _ACTIVITY_SIGNALS
        },
        "contracting_long_hold_capture_rate_all": _rate(contracting_long, total_long),
        "contracting_long_hold_capture_rate_known": _rate(contracting_long, known_long),
        "contracting_other_entry_fraction_all": _rate(contracting_other, total_other),
        "contracting_other_entry_fraction_known": _rate(contracting_other, known_other),
    }


@dataclass(frozen=True, slots=True)
class _SelectionHistory:
    events: tuple[int, ...]
    points: tuple[tuple[int, tuple[int, int] | None, Decimal | None, datetime], ...]

    def at(self, event: int) -> tuple[int, tuple[int, int] | None, Decimal | None, datetime] | None:
        if not self.events:
            return None
        index = bisect_right(self.events, event) - 1
        return self.points[index] if index >= 0 else None


def _selection_points(evidence: _RunEvidence, cycles: Sequence[Any]) -> _SelectionHistory:
    replay = evidence.replay
    start_event = (
        _datetime_to_micros(_parse_datetime(_interval(evidence.run_manifest)["start"]))
        * EVENT_ORDER_SCALE
    )
    changes = replay.get("selection_changes", [])
    points: list[tuple[int, tuple[int, int] | None, Decimal | None, datetime]] = []
    current: tuple[int, int] | None = None
    initial_tick: Decimal | None = None
    if changes:
        first = changes[0]
        current = _candidate_from_values(
            first.get("previous_low"), first.get("previous_high"), evidence.tape.tick_size
        )
        initial_tick = _optional_decimal(first.get("previous_tick_at_selection"))
    elif cycles:
        first_cycle = cycles[0]
        current = _candidate_from_values(
            first_cycle.get("low"), first_cycle.get("high"), evidence.tape.tick_size
        )
        initial_tick = _optional_decimal(first_cycle.get("tick_at_selection"))
    else:
        current = _candidate_from_values(
            replay.get("active_low"), replay.get("active_high"), evidence.tape.tick_size
        )
    if current is None and not changes:
        return _SelectionHistory(
            (start_event,), ((start_event, None, None, _event_to_datetime(start_event)),)
        )
    if current is not None and initial_tick is None:
        initial_tick = _selection_tick(evidence, start_event)
    points.append((start_event, current, initial_tick, _event_to_datetime(start_event)))
    previous_event = start_event
    for change in changes:
        event = int(change["event"])
        if event < previous_event:
            raise EvolutionDiagnosticError("selection changes are not strictly chronological")
        previous = _candidate_from_values(
            change.get("previous_low"), change.get("previous_high"), evidence.tape.tick_size
        )
        if previous != current:
            raise EvolutionDiagnosticError("selection change previous endpoint is inconsistent")
        selected = _candidate_from_values(
            change.get("selected_low"), change.get("selected_high"), evidence.tape.tick_size
        )
        tick = _optional_decimal(change.get("selected_tick_at_selection"))
        if selected is not None and tick is None:
            tick = _selection_tick(evidence, event)
        points.append((event, selected, tick, _event_to_datetime(event)))
        current = selected
        previous_event = event
    return _SelectionHistory(tuple(item[0] for item in points), tuple(points))


def _timelines(evidence: _RunEvidence) -> dict[tuple[int, int], CandidateTimeline]:
    distances = (
        USDCUSDT_TICK_CATALOG.absolute_distances(evidence.model.distances)
        if evidence.model.distance_semantics is not None
        else evidence.model.distances
    )
    return evidence.tape.timelines(distances)


def _selection_tick(evidence: _RunEvidence, event: int) -> Decimal:
    tick, _, _ = _selection_grid(
        evidence.model,
        USDCUSDT_TICK_CATALOG if evidence.model.distance_semantics is not None else None,
        event,
        evidence.tape.tick_size,
        evidence.tape.observed_tick_evidence_event,
    )
    return tick or evidence.tape.tick_size


def _aggregate(
    target: dict[str, dict[str, dict[str, Decimal | int]]],
    dimension: str,
    key: str | None,
    item: Mapping[str, Any],
) -> None:
    if key is None:
        return
    bucket = target.setdefault(dimension, {}).setdefault(
        key,
        {
            "cycles": 0,
            "realized": Decimal("0"),
            "log_return": Decimal("0"),
            "rounding_residual_drag": Decimal("0"),
            "full_capital_gross_edge": Decimal("0"),
        },
    )
    bucket["cycles"] = int(bucket["cycles"]) + 1
    bucket["realized"] = Decimal(bucket["realized"]) + Decimal(str(item["realized"]))
    for field in ("log_return", "rounding_residual_drag", "full_capital_gross_edge"):
        value = item.get(field)
        if value is not None:
            bucket[field] = Decimal(bucket[field]) + Decimal(str(value))


def _quantiles(values: list[Decimal]) -> dict[str, str | None]:
    if not values:
        return {"p10": None, "p50": None, "p90": None}

    def at(fraction: Decimal) -> Decimal:
        position = fraction * (len(values) - 1)
        low = int(position)
        high = min(low + 1, len(values) - 1)
        return values[low] + (values[high] - values[low]) * (position - low)

    return {
        name: _string(at(fraction))
        for name, fraction in (
            ("p10", Decimal("0.1")),
            ("p50", Decimal("0.5")),
            ("p90", Decimal("0.9")),
        )
    }


def _validate_protections(value: Mapping[str, Any]) -> None:
    run_value = value.get("run")
    protection_scope = run_value if isinstance(run_value, Mapping) else value
    missing = sorted(key for key in _PROTECTION_KEYS if key not in protection_scope)
    if missing:
        raise EvolutionDiagnosticError(
            "run manifest protection keys are missing: " + ", ".join(missing)
        )
    for key in _PROTECTION_KEYS:
        if protection_scope[key] is not False:
            raise EvolutionDiagnosticError(f"protected partition flag is not false: {key}")
    live_keys = sorted(key for key in _LIVE_PROTECTION_KEYS if key in protection_scope)
    if not live_keys:
        raise EvolutionDiagnosticError(
            "run manifest protection key is missing: binance_live_accessed/live_accessed"
        )
    for key in live_keys:
        if protection_scope[key] is not False:
            raise EvolutionDiagnosticError(f"protected partition flag is not false: {key}")

    def visit(item: Any) -> None:
        if isinstance(item, Mapping):
            for key, child in item.items():
                if (
                    str(key).lower()
                    in _PROTECTION_KEYS | _LIVE_PROTECTION_KEYS | _LEGACY_PROTECTION_KEYS
                    and child is not False
                    and child is not None
                ):
                    raise EvolutionDiagnosticError(f"protected partition flag is not false: {key}")
                visit(child)
        elif isinstance(item, list):
            for child in item:
                visit(child)

    visit(value)


def _validate_run_identity(
    model_hash: str,
    model_id: str,
    run_hash: str,
    evaluation: Mapping[str, Any],
    run_payload: Mapping[str, Any],
    manifest: Mapping[str, Any],
    replay: Mapping[str, Any],
) -> None:
    for value, expected, name in (
        (manifest.get("MODEL_HASH"), model_hash, "MODEL_HASH"),
        (manifest.get("RUN_HASH"), run_hash, "RUN_HASH"),
        (manifest.get("model_id"), model_id, "model_id"),
        (evaluation.get("run_hash"), run_hash, "evaluation run_hash"),
        (replay.get("model_id"), model_id, "replay model_id"),
        (replay.get("model_hash"), model_hash, "replay model_hash"),
        (replay.get("scenario_hash"), manifest.get("SCENARIO_HASH"), "replay scenario_hash"),
    ):
        if value != expected:
            raise EvolutionDiagnosticError(f"{name} mismatch")
    if run_payload.get("RUN_HASH") != run_hash:
        raise EvolutionDiagnosticError("journal/run manifest hash mismatch")


def _interval(manifest: Mapping[str, Any]) -> dict[str, Any]:
    interval = manifest.get("interval")
    if (
        not isinstance(interval, Mapping)
        or not interval.get("start")
        or not interval.get("end_exclusive")
    ):
        raise EvolutionDiagnosticError("run interval/cutoff is incomplete")
    return {"start": interval["start"], "end_exclusive": interval["end_exclusive"]}


def _tape_cache_key(manifest: Mapping[str, Any]) -> str:
    value = manifest.get("run", {}).get("tape_cache", {}).get("cache_key")
    if not isinstance(value, str) or len(value) != 64:
        raise EvolutionDiagnosticError("run does not bind a tape cache key")
    return value


def _tape_hash_from_manifest(manifest: Mapping[str, Any]) -> str:
    value = manifest.get("run", {}).get("tape_cache", {}).get("tape_hash")
    if not isinstance(value, str) or len(value) != 64:
        raise EvolutionDiagnosticError("run does not bind a tape hash")
    return value


def _validate_existing(root: Path, artifact_id: str) -> dict[str, Any]:
    manifest_path = root / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("status") != "READY" or manifest.get("artifact_id") != artifact_id:
            raise EvolutionDiagnosticError("diagnostic artifact is not READY")
        files = manifest["files"]
        if manifest.get("content_hash") != canonical_hash(files):
            raise EvolutionDiagnosticError("diagnostic artifact content hash mismatch")
        for name, descriptor in files.items():
            path = root / name
            data = path.read_bytes()
            if (
                len(data) != descriptor["size"]
                or hashlib.sha256(data).hexdigest() != descriptor["sha256"]
            ):
                raise EvolutionDiagnosticError(f"diagnostic artifact corruption: {name}")
        summary = json.loads((root / "summary.json").read_text(encoding="utf-8"))
        return cast(dict[str, Any], summary)
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        if isinstance(error, EvolutionDiagnosticError):
            raise
        raise EvolutionDiagnosticError("diagnostic artifact integrity failure") from error


def _write_artifact(
    root: Path, artifact_id: str, summary: Mapping[str, Any], files: Mapping[str, bytes]
) -> None:
    root.parent.mkdir(parents=True, exist_ok=True)
    temp = Path(tempfile.mkdtemp(prefix=f".{artifact_id}.", dir=root.parent))
    try:
        payloads = {"summary.json": _json_bytes(summary), **files}
        descriptors: dict[str, Any] = {}
        for name, data in payloads.items():
            (temp / name).write_bytes(data)
            descriptors[name] = {"sha256": hashlib.sha256(data).hexdigest(), "size": len(data)}
        manifest = {
            "schema_version": SCHEMA_VERSION,
            "status": "READY",
            "artifact_id": artifact_id,
            "files": descriptors,
            "content_hash": canonical_hash(descriptors),
        }
        (temp / "manifest.json").write_bytes(_json_bytes(manifest))
        try:
            os.replace(temp, root)
        except FileExistsError as error:
            raise EvolutionDiagnosticError(
                "diagnostic artifact race; validate existing artifact"
            ) from error
    finally:
        if temp.exists():
            shutil.rmtree(temp)


def _write_report(path: Path, summary: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_json_bytes(summary))


def _csv_bytes(rows: Sequence[Mapping[str, Any]]) -> bytes:
    from io import StringIO

    output = StringIO(newline="")
    fields = sorted({key for row in rows for key in row})
    writer = csv.DictWriter(output, fieldnames=fields)
    writer.writeheader()
    writer.writerows({key: row.get(key) for key in fields} for row in rows)
    return output.getvalue().encode()


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, default=str) + "\n").encode()


def _parse_datetime(value: Any) -> datetime:
    if not isinstance(value, str):
        raise EvolutionDiagnosticError("timestamp must be an ISO string")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise EvolutionDiagnosticError("timestamp must be timezone-aware")
    return parsed.astimezone(UTC)


def _seconds(value: Any) -> Decimal:
    return Decimal(str(value.total_seconds()))


def _decimal(mapping: Mapping[str, Any], key: str) -> Decimal:
    try:
        return Decimal(str(mapping[key]))
    except (KeyError, TypeError, ValueError) as error:
        raise EvolutionDiagnosticError(f"missing decimal field: {key}") from error


def _optional_decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    return Decimal(str(value))


def _string(value: Any) -> str | None:
    return None if value is None else str(value)


def _tick_candidate(low: Decimal, high: Decimal, quantum: Decimal) -> tuple[int, int]:
    return (_tick(low, quantum), _tick(high, quantum) - _tick(low, quantum))


def _candidate_from_values(low: Any, high: Any, quantum: Decimal) -> tuple[int, int] | None:
    if low in (None, "") or high in (None, ""):
        return None
    return _tick_candidate(Decimal(str(low)), Decimal(str(high)), quantum)


def _tick(price: Decimal, quantum: Decimal) -> int:
    result = price / quantum
    integral = result.to_integral_value()
    if result != integral:
        raise EvolutionDiagnosticError("price is not representable on tape quantum")
    return int(integral)


def _price_tick(tick: int, quantum: Decimal) -> Decimal:
    return Decimal(tick) * quantum


__all__ = [
    "EvolutionDiagnosticError",
    "EvolutionDiagnosticResult",
    "diagnose_evolution",
    "load_evaluated_run_evidence",
    "run_evolution_diagnostic",
]
