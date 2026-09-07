"""Offline reserve study using the canonical serial engine, never the operator."""

from __future__ import annotations

import gzip
import hashlib
import json
import subprocess
import time
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from crypto_strategy_lab.domain import canonical_hash
from crypto_strategy_lab.microstructure.recovery_reserve import (
    RecoveryReserveRuntime,
    ReserveConfig,
)
from crypto_strategy_lab.microstructure.serial_replay import (
    EVENT_ORDER_SCALE,
    CandidateTimeline,
    SerialCycle,
    SerialModelConfig,
    SerialReplayResult,
    SerialScenarioConfig,
    SerialTape,
    TickCatalog,
    _advance,
    _datetime_to_micros,
    _decision,
    _event_to_datetime,
    _minutes_to_events,
    _result,
    _select,
    _selection_grid,
    _State,
)

D = Decimal


def file_sha(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write_json(path: Path, value: Any) -> None:
    """Atomic publication: partial writes never masquerade as completed results."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, sort_keys=True, default=str) + "\n", encoding="utf-8")
    temporary.replace(path)


def _state_snapshot(state: _State) -> dict[str, Any]:
    return {
        key: [cycle.model_dump(mode="json") for cycle in value]
        if key in {"cycles", "release_closures"}
        else value
        for key, value in vars(state).items()
    }


def _restore_state(raw: dict[str, Any]) -> _State:
    values = dict(raw)
    for key in ("cash", "inventory", "inventory_cost", "fees", "realized_profit"):
        values[key] = D(values[key])
    for key in ("candidate", "idle_challenger"):
        values[key] = tuple(values[key]) if values[key] is not None else None
    if values["candidate_tick_size"] is not None:
        values["candidate_tick_size"] = D(values["candidate_tick_size"])
    for key in ("cycles", "release_closures"):
        values[key] = [SerialCycle.model_validate(item) for item in values[key]]
    values["changes"] = [
        (
            event,
            tuple(old) if old else None,
            D(ot) if ot else None,
            tuple(new) if new else None,
            D(nt) if nt else None,
        )
        for event, old, ot, new, nt in values["changes"]
    ]
    return _State(**values)


def run_scenario(
    tape: SerialTape,
    timelines: dict[tuple[int, int], CandidateTimeline],
    parent: SerialModelConfig,
    scenario: SerialScenarioConfig,
    reserve_config: ReserveConfig,
    *,
    start: datetime,
    end: datetime,
    catalog: TickCatalog | None,
    checkpoint: Path | None = None,
    identity: dict[str, Any] | None = None,
) -> tuple[SerialReplayResult, RecoveryReserveRuntime]:
    """One causal pass. Shared immutable indexes do not share bank or reserve state."""
    if scenario.initial_quote != D(100):
        raise ValueError("INITIAL_CAPITAL_INVARIANT_VIOLATION")
    start_event = _datetime_to_micros(start) * EVENT_ORDER_SCALE
    end_event = _datetime_to_micros(end) * EVENT_ORDER_SCALE
    if start >= end or end_event > (tape.last_event // EVENT_ORDER_SCALE + 1) * EVENT_ORDER_SCALE:
        raise ValueError("INVALID_PHYSICAL_REPLAY_INTERVAL")
    runtime = RecoveryReserveRuntime(reserve_config, parent, scenario, tape, timelines, catalog)
    state = _State(cash=scenario.initial_quote, flat_since=start_event)
    cursor = start_event
    lookback = _minutes_to_events(parent.lookback_minutes)
    tick, distances, multiple = _selection_grid(
        parent, catalog, start_event, tape.tick_size, tape.observed_tick_evidence_event
    )
    state.candidate = _select(
        timelines,
        parent,
        start_event - lookback,
        start_event,
        eligible_distances=distances,
        grid_multiple=multiple,
    )
    state.candidate_tick_size = tick if state.candidate is not None else None
    if checkpoint is not None and checkpoint.exists():
        saved = json.loads(checkpoint.read_text(encoding="utf-8"))
        payload = saved["payload"]
        if canonical_hash(payload) != saved["sha256"] or payload["identity"] != identity:
            raise ValueError("RESERVE_CHECKPOINT_IDENTITY_OR_HASH_MISMATCH")
        state = _restore_state(payload["state"])
        runtime.restore(payload["reserve"])
        cursor = int(payload["cursor"])
        if not start_event <= cursor <= end_event:
            raise ValueError("RESERVE_CHECKPOINT_CURSOR_INVALID")
    interval = _minutes_to_events(parent.decision_interval_minutes or 1)
    checkpoint_at = last_progress = time.monotonic()
    while cursor < end_event:
        boundary = min(cursor + interval, end_event)
        _advance(
            state,
            timelines,
            parent,
            scenario,
            cursor,
            boundary,
            recalculate_after_exit=True,
            tick_catalog=catalog,
            tape_quantum=tape.tick_size,
            observed_tick_evidence_event=tape.observed_tick_evidence_event,
            release_decision=runtime,
            release_schedule=runtime.schedule,
            cycle_settled=runtime.cycle_settled,
        )
        if boundary < end_event:
            _decision(
                state,
                timelines,
                parent,
                boundary,
                lookback,
                tick_catalog=catalog,
                tape_quantum=tape.tick_size,
                observed_tick_evidence_event=tape.observed_tick_evidence_event,
            )
        cursor = boundary
        now = time.monotonic()
        if now - last_progress >= 30:
            print(
                json.dumps(
                    {
                        "scenario": reserve_config.scenario_id,
                        "timestamp": _event_to_datetime(cursor).isoformat(),
                        "cycles": len(state.cycles),
                        "releases": len(runtime.releases),
                        "reserve": str(runtime.reserve),
                    }
                ),
                flush=True,
            )
            last_progress = now
        if checkpoint is not None and (now - checkpoint_at >= 300 or cursor == end_event):
            payload = json.loads(
                json.dumps(
                    {
                        "identity": identity,
                        "cursor": cursor,
                        "state": _state_snapshot(state),
                        "reserve": runtime.snapshot(),
                    },
                    default=str,
                )
            )
            write_json(checkpoint, {"payload": payload, "sha256": canonical_hash(payload)})
            checkpoint_at = now
    return _result(state, tape, parent, scenario, start, end, end_event), runtime


def write_replay(path: Path, result: SerialReplayResult) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    with (
        temporary.open("wb") as raw,
        gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as out,
    ):
        out.write(result.model_dump_json().encode())
    temporary.replace(path)
    return file_sha(path)


def published_sha() -> str:
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    remote = subprocess.check_output(
        ["git", "ls-remote", "origin", "refs/heads/main"], text=True
    ).split()[0]
    if head != remote:
        raise ValueError("PRE_RUN_CODE_NOT_PUBLISHED")
    if subprocess.check_output(["git", "diff", "--name-only", "HEAD"], text=True).strip():
        raise ValueError("PRE_RUN_TRACKED_CODE_DIRTY")
    return head


def run_study() -> dict[str, Any]:
    """Only this entry point reads physical DEVELOPMENT artifacts. No market connection."""
    from crypto_strategy_lab.microstructure.capital_release_analysis import (
        audit_legacy_m007_event_projection,
    )
    from crypto_strategy_lab.microstructure.evolution_diagnostics import load_evaluated_run_evidence
    from crypto_strategy_lab.microstructure.hold_risk import EXACT_PARENT
    from crypto_strategy_lab.microstructure.operator import frozen_m007_strategy
    from crypto_strategy_lab.microstructure.recovery_reserve import grid_configs
    from crypto_strategy_lab.microstructure.recovery_reserve_audit import audit_ledger
    from crypto_strategy_lab.microstructure.recovery_reserve_metrics import (
        robust_regions,
        summarize_replay,
    )
    from crypto_strategy_lab.microstructure.serial_replay import USDCUSDT_TICK_CATALOG

    sha = published_sha()
    print("RECOVERY_RESERVE_VERIFY_PHYSICAL_M007", flush=True)
    evidence = load_evaluated_run_evidence("M007")
    exact = json.loads(EXACT_PARENT.read_text(encoding="utf-8"))
    if canonical_hash(exact["result"]) != exact["result_sha256"]:
        raise ValueError("EXACT_PARENT_HASH_MISMATCH")
    baseline_result = SerialReplayResult.model_validate(exact["result"])
    projection = audit_legacy_m007_event_projection(
        SerialReplayResult.model_validate(evidence.replay), baseline_result
    )
    parent = frozen_m007_strategy()
    scenario = SerialScenarioConfig(
        scenario_id="PRICE_PATH_HISTORICAL_TICK_ZERO_FEE_V2",
        tick_size=evidence.tape.tick_size,
        historical_tick_catalog_hash=USDCUSDT_TICK_CATALOG.catalog_hash,
        historical_tick_source_url=USDCUSDT_TICK_CATALOG.source_url,
        historical_tick_policy="CAUSAL_OBSERVED_GRID_THEN_OFFICIAL_COMPLETION_BOUND",
    )
    if (
        parent.model_hash != baseline_result.model_hash
        or scenario.scenario_hash != baseline_result.scenario_hash
    ):
        raise ValueError("PARENT_OR_ECONOMIC_SCENARIO_CHANGED")
    identity = {
        "schema": "recovery-reserve-study-1",
        "git_commit_sha": sha,
        "protocol_sha256": file_sha(Path("docs/microstructure/RECOVERY_RESERVE_PROTOCOL.md")),
        "parent_model": "M007",
        "parent_hash": parent.model_hash,
        "parent_exact_sha256": file_sha(EXACT_PARENT),
        "dataset_hash": evidence.tape_manifest.dataset_hash,
        "tape_hash": evidence.tape.tape_hash,
        "scenario_hash": scenario.scenario_hash,
        "start": baseline_result.start.isoformat(),
        "end": baseline_result.end_exclusive.isoformat(),
        "initial_capital": "100",
        "initial_recovery_reserve": "5",
        "total_initial_equity": "105",
        "currency": "USDT",
        "capital_mode": "COMPOUNDING",
        "phase": "DEVELOPMENT",
        "grid": [config.payload() for config in grid_configs()],
        "model_id": "NOT_REGISTERED_PHASE_A",
        "trading_enabled": False,
    }
    root = Path("artifacts/usdcusdt/recovery-reserve") / canonical_hash(identity)
    root.mkdir(parents=True, exist_ok=True)
    write_json(root / "identity.json", identity)
    write_json(root / "parent-event-projection-audit.json", projection)
    print("RECOVERY_RESERVE_BASELINE_EXACT_LEDGER", flush=True)
    baseline_audit = audit_ledger(baseline_result, evidence.tape, D(0), D(5), [])
    baseline = summarize_replay(
        baseline_result, D(5), D(5), D(0), [], D(baseline_audit["maximum_drawdown"])
    )
    baseline["integrity_pass"] = True
    write_json(root / "baseline.json", baseline)
    write_json(root / "baseline-ledger.json", baseline_audit)
    print("RECOVERY_RESERVE_BUILD_SHARED_CANONICAL_TIMELINES", flush=True)
    started = time.monotonic()
    timelines = evidence.tape.timelines(USDCUSDT_TICK_CATALOG.absolute_distances(parent.distances))
    print(
        json.dumps({"timelines": len(timelines), "build_seconds": time.monotonic() - started}),
        flush=True,
    )
    rows: list[dict[str, Any]] = []
    for config in grid_configs():
        path = root / config.scenario_id
        config_identity = {**identity, "reserve_config": config.payload()}
        completion = path / "completed.json"
        if completion.exists():
            saved = json.loads(completion.read_text(encoding="utf-8"))
            payload_hash = saved.pop("payload_sha256")
            if canonical_hash(saved) != payload_hash:
                raise ValueError("COMPLETED_SCENARIO_SUMMARY_HASH_MISMATCH")
            if (
                saved["identity"] != config_identity
                or file_sha(path / "replay.json.gz") != saved["replay_sha256"]
            ):
                raise ValueError("COMPLETED_SCENARIO_IDENTITY_MISMATCH")
            for filename, expected in saved["artifact_hashes"].items():
                if file_sha(path / filename) != expected:
                    raise ValueError("COMPLETED_SCENARIO_ARTIFACT_HASH_MISMATCH")
            rows.append(saved["summary"])
            print(f"RECOVERY_RESERVE_REUSE_COMPLETED {config.scenario_id}", flush=True)
            continue
        print(f"RECOVERY_RESERVE_START {config.scenario_id}", flush=True)
        began = time.monotonic()
        result, runtime = run_scenario(
            evidence.tape,
            timelines,
            parent,
            scenario,
            config,
            start=baseline_result.start,
            end=baseline_result.end_exclusive,
            catalog=USDCUSDT_TICK_CATALOG,
            checkpoint=path / "checkpoint.json",
            identity=config_identity,
        )
        result = result.model_copy(
            update={
                "model_id": "RECOVERY_RESERVE_PHASE_A",
                "model_hash": canonical_hash(
                    {"parent": parent.model_hash, "logic_protocol": identity["protocol_sha256"]}
                ),
                "scenario_id": config.scenario_id,
                "scenario_hash": canonical_hash(
                    {
                        "economic_reference": scenario.scenario_hash,
                        "reserve_config": config.payload(),
                    }
                ),
            }
        )
        audit = audit_ledger(
            result, evidence.tape, config.skim_rate, runtime.reserve, runtime.releases
        )
        row = summarize_replay(
            result,
            runtime.reserve,
            D(audit["min_reserve_balance"]),
            runtime.total_skim,
            runtime.releases,
            D(audit["maximum_drawdown"]),
        )
        consumed = D(audit["total_release_loss"])
        holds = [
            D(_datetime_to_micros(c.exit_timestamp) - _datetime_to_micros(c.entry_timestamp))
            / 3_600_000_000
            for c in (*result.cycles, *result.release_closures)
        ]
        if result.open_entry_timestamp is not None:
            holds.append(
                D(
                    _datetime_to_micros(result.end_exclusive)
                    - _datetime_to_micros(result.open_entry_timestamp)
                )
                / 3_600_000_000
            )
        threshold_lock = sum((max(D(0), duration - config.lock_hours) for duration in holds), D(0))
        interval_hours = (
            D(_datetime_to_micros(result.end_exclusive) - _datetime_to_micros(result.start))
            / 3_600_000_000
        )
        row.update(
            {
                "scenario_id": config.scenario_id,
                "skim_rate": str(config.skim_rate),
                "lock_hours_threshold": config.lock_hours,
                "max_loss_bps": str(config.max_loss_bps),
                "integrity_pass": True,
                "elapsed_seconds": time.monotonic() - began,
                "lock_hours_avoided": baseline["lock_hours"] - row["lock_hours"],
                "total_release_loss": consumed,
                "threshold_specific_lock_hours": threshold_lock,
                "threshold_specific_operating_uptime": 1 - threshold_lock / interval_hours,
                "additional_profit_attributable_to_released_capital": (
                    result.realized_profit + consumed - baseline_result.realized_profit
                ),
                "reserve_dollars_consumed": consumed,
                "reserve_depletion_events": audit["reserve_depletion_events"],
                "reserve_empty_fraction": audit["reserve_empty_fraction"],
                "longest_reserve_empty_hours": audit["longest_reserve_empty_hours"],
                "decision_counts": dict(runtime.evaluations),
                "efficiency_classification": (
                    "RETROSPECTIVE_POLICY_COMPARISON_PROXY_NOT_IDENTIFIED_CAUSAL_EFFECT"
                ),
                "reserve_efficiency": (
                    result.realized_profit + consumed - baseline_result.realized_profit
                )
                / consumed
                if consumed
                else None,
                "additional_cycles_per_reserve_dollar": D(
                    result.completed_cycles - baseline_result.completed_cycles
                )
                / consumed
                if consumed
                else None,
                "net_equity_gain_per_reserve_dollar": (
                    row["total_final_equity"] - baseline["total_final_equity"]
                )
                / consumed
                if consumed
                else None,
            }
        )
        replay_hash = write_replay(path / "replay.json.gz", result)
        write_json(path / "audit.json", audit)
        write_json(path / "runtime.json", runtime.snapshot())
        completion_payload = json.loads(
            json.dumps(
                {
                    "identity": config_identity,
                    "replay_sha256": replay_hash,
                    "summary": row,
                    "artifact_hashes": {
                        filename: file_sha(path / filename)
                        for filename in ("audit.json", "runtime.json")
                    },
                },
                default=str,
            )
        )
        write_json(
            completion, {**completion_payload, "payload_sha256": canonical_hash(completion_payload)}
        )
        rows.append(row)
        write_json(
            root / "progress.json",
            {"completed": len(rows), "total": 27, "last_scenario": config.scenario_id},
        )
        print(
            json.dumps(
                {
                    "SCENARIO_COMPLETE": config.scenario_id,
                    "COMPLETED": len(rows),
                    "CYCLES": result.completed_cycles,
                    "RELEASES": len(runtime.releases),
                }
            ),
            flush=True,
        )
    report = {
        "identity": identity,
        "artifact_root": str(root),
        "baseline": baseline,
        "scenarios": rows,
        "robustness": robust_regions(rows, baseline),
        "scientific_review": "PENDING_ASTRA",
        "current_champion": "M007",
        "executable_edge": "UNKNOWN",
        "VALIDATION_ACCESSED": "NO",
        "LOCKED_TEST_ACCESSED": "NO",
        "TESTNET_ACCESSED": "NO",
        "LIVE_ACCESSED": "NO",
        "ORDERS_SENT": 0,
    }
    write_json(Path("reports/usdcusdt/recovery-reserve-scenarios.json"), report)
    import csv

    csv_path = Path("reports/usdcusdt/recovery-reserve-scenarios.csv")
    with csv_path.open("w", encoding="utf-8", newline="") as stream:
        columns = [key for key, value in rows[0].items() if not isinstance(value, dict)]
        writer = csv.DictWriter(stream, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return report
