"""Published, single-writer M012 reality replay; no account or exchange access."""

from __future__ import annotations

import argparse
import hashlib
import inspect
import json
import os
import subprocess
import time
import traceback
from bisect import bisect_left
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

try:
    from scripts.run_b10_reality import AuditJournal, typed
except ModuleNotFoundError:
    from run_b10_reality import AuditJournal, typed

from crypto_strategy_lab.microstructure.b10_reality import (
    BookEnvelope,
    ExecutionProfile,
    SymbolRules,
    Trade,
)
from crypto_strategy_lab.microstructure.data import HistoryManifest, iter_history
from crypto_strategy_lab.microstructure.evolution_diagnostics import load_evaluated_run_evidence
from crypto_strategy_lab.microstructure.operator import frozen_m007_strategy
from crypto_strategy_lab.microstructure.recovery_reserve import (
    RecoveryReserveRuntime,
    ReserveConfig,
)
from crypto_strategy_lab.microstructure.recovery_reserve_study import (
    file_sha,
    published_sha,
    write_json,
)
from crypto_strategy_lab.microstructure.serial_replay import (
    EVENT_ORDER_SCALE,
    USDCUSDT_TICK_CATALOG,
    SerialScenarioConfig,
    _datetime_to_micros,
)
from crypto_strategy_lab.ml.model_registry import (
    BackendSpec,
    ModelRegistry,
    ModelStatus,
    RunSpec,
    compute_model_hash,
)

D = Decimal
SPEC = Path("docs/microstructure/M012_MODEL_SPEC.json")
PROFILE_CONFIG = Path("artifacts/binance/b10-reality-profiles.json")
PROFILE_CONFIG_SHA = "a77e0c67fdff8c618cbfc28fdd3d49d2fa831626560aed7fe1ec27007293537d"
PROFILE = "B_REALISTIC_CONSERVATIVE"
TAPE_HASH = "505fd6c31b010eac4e8da2d7e290137bb455d475b95409ac306d1ded7be55b6c"
PREREG = Path("docs/microstructure/M012_HIGH_UPTIME_RECOVERY_PREREGISTRATION.md")
REVIEW = Path("reports/usdcusdt/M012-preflight-independent-review.md")
KERNEL = Path("src/crypto_strategy_lab/microstructure/high_uptime_recovery.py")


def lf_sha(path):
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def validate_review(review_path, source_paths):
    lines = review_path.read_text(encoding="utf-8").splitlines()
    if "STATUS=PASS_CONDITIONAL_PRE_RUN" not in lines:
        raise ValueError("INDEPENDENT_PREFLIGHT_REVIEW_NOT_PASSED")
    for path in source_paths:
        binding = f"REVIEWED_SOURCE_SHA256_LF[{path.as_posix()}]={lf_sha(path)}"
        if binding not in lines:
            raise ValueError(f"INDEPENDENT_REVIEW_SOURCE_BINDING_MISMATCH:{path}")


def validate_registered_design(model, spec_path=SPEC, prereg_path=PREREG):
    design = json.loads(spec_path.read_bytes())
    expected = {
        **design,
        "preregistration_sha256_lf": lf_sha(prereg_path),
        "spec_sha256_lf": lf_sha(spec_path),
    }
    if dict(model.model) != expected or model.model_hash != compute_model_hash(expected):
        raise ValueError("REGISTERED_DESIGN_OR_PREREG_HASH_MISMATCH")
    if (
        design["capital_mode"] != "COMPOUNDING"
        or design["position_sizing"] != "USE_AVAILABLE_OPERATING_BANK"
    ):
        raise ValueError("OWNER_COMPOUNDING_REQUIRED")
    return {
        "model_spec_sha256_lf": lf_sha(spec_path),
        "preregistration_sha256_lf": lf_sha(prereg_path),
    }


def runtime_class_evidence(cls, expected_path=KERNEL):
    path = Path(inspect.getfile(cls)).resolve()
    if path != expected_path.resolve():
        raise ValueError("ACTUAL_RUNTIME_CLASS_SOURCE_MISMATCH")
    return {
        "class": cls.__module__ + "." + cls.__qualname__,
        "source_path": str(path),
        "source_sha256": file_sha(path),
        "mro": [c.__module__ + "." + c.__qualname__ for c in cls.__mro__],
    }


def due_boundaries(milestones, timestamp):
    """Consume every boundary before/equal to the next raw trade, never after that trade."""
    while milestones and milestones[0] <= timestamp:
        yield milestones.pop(0)


def preserve_failure(output, exception, identity):
    checkpoint_path = output / "checkpoint.json"
    valid_sha = file_sha(checkpoint_path) if checkpoint_path.exists() else None
    write_json(
        output / "failure.json",
        {
            "status": "INTERRUPTED_OPERATOR"
            if isinstance(exception, KeyboardInterrupt)
            else "TECHNICAL_ERROR",
            "occurred_at": datetime.now(UTC).isoformat(),
            "error_type": type(exception).__name__,
            "error": str(exception),
            "traceback": traceback.format_exc(),
            "identity": identity,
            "last_durable_checkpoint_sha256": valid_sha,
            "last_durable_checkpoint_path": str(checkpoint_path) if valid_sha else None,
            "economic_scope": "Last hash-bound checkpoint preserved; current uncheckpointed "
            "suffix untrusted. No automatic economic invalidation or restart.",
        },
    )


def published_bytes(path, sha):
    raw = subprocess.check_output(["git", "show", f"{sha}:{path.as_posix()}"])
    if raw.replace(b"\r\n", b"\n") != path.read_bytes().replace(b"\r\n", b"\n"):
        raise ValueError(f"SOURCE_NOT_PUBLISHED:{path}")


def run(output: Path):
    source_sha = published_sha()
    for path in (
        SPEC,
        PREREG,
        REVIEW,
        Path(__file__).resolve().relative_to(Path.cwd()),
        KERNEL,
        Path("scripts/run_b10_reality.py"),
        Path("src/crypto_strategy_lab/microstructure/b10_reality.py"),
    ):
        published_bytes(path, source_sha)
    validate_review(REVIEW, (KERNEL, Path(__file__).resolve().relative_to(Path.cwd())))
    from crypto_strategy_lab.microstructure.high_uptime_recovery import HighUptimeRecoveryReplay

    actual_runtime = runtime_class_evidence(HighUptimeRecoveryReplay)
    if file_sha(PROFILE_CONFIG) != PROFILE_CONFIG_SHA:
        raise ValueError("FROZEN_EXECUTION_EVIDENCE_MISMATCH")
    config = json.loads(PROFILE_CONFIG.read_bytes())
    registry = ModelRegistry()
    model = registry.get("M012")
    if model.model.get("strategy") != "HIGH_UPTIME_DYNAMIC_RECOVERY":
        raise ValueError("M012_REGISTERED_MODEL_MISMATCH")
    design_binding = validate_registered_design(model)
    if registry.current_status("M012") != ModelStatus.CREATED:
        raise ValueError("M012_FIRST_RUN_ONLY; resume requires separate provenance review")
    for key in (
        "history_manifest",
        "physical_archive_audit",
        "calibration_manifest",
        "official_rule_manifest",
    ):
        if file_sha(Path(config[key])) != config[key + "_sha256"]:
            raise ValueError(f"PINNED_INPUT_HASH_MISMATCH:{key}")
    audit = json.loads(Path(config["physical_archive_audit"]).read_bytes())
    if not audit["coverage_exact"] or any(
        audit["fresh_aggregate"][key] != audit["archive_count"]
        for key in (
            "existing_count",
            "manifest_hash_match_count",
            "manifest_size_match_count",
            "sidecar_hash_match_count",
            "zip_test_ok_count",
        )
    ):
        raise ValueError("PHYSICAL_ARCHIVE_AUDIT_INCOMPLETE")
    history = HistoryManifest.model_validate_json(Path(config["history_manifest"]).read_bytes())
    if (
        history.symbol != "USDCUSDT"
        or history.kind != "trades"
        or history.integrity_status != "VALID"
    ):
        raise ValueError("VALID_USDCUSDT_RAW_TRADES_REQUIRED")
    start, end = (
        datetime.fromisoformat(config["start"]),
        datetime.fromisoformat(config["end_exclusive"]),
    )
    if (
        start.isoformat() != "2026-01-01T00:00:00+00:00"
        or end.isoformat() != "2026-09-05T23:59:59.783644+00:00"
    ):
        raise ValueError("FROZEN_DEVELOPMENT_INTERVAL_MISMATCH")
    start_us, end_us = _datetime_to_micros(start), _datetime_to_micros(end)
    print("M012_LOADING_FROZEN_CANONICAL_TAPE", flush=True)
    evidence = load_evaluated_run_evidence("M007")
    tape, parent, catalog = evidence.tape, frozen_m007_strategy(), USDCUSDT_TICK_CATALOG
    if history.dataset_hash != evidence.tape_manifest.dataset_hash or tape.tape_hash != TAPE_HASH:
        raise ValueError("CANONICAL_DATASET_TAPE_MISMATCH")
    begin = bisect_left(tape.events, start_us * EVENT_ORDER_SCALE)
    stop = bisect_left(tape.events, end_us * EVENT_ORDER_SCALE)
    scenario = SerialScenarioConfig(
        scenario_id="PRICE_PATH_HISTORICAL_TICK_ZERO_FEE_V2",
        tick_size=tape.tick_size,
        historical_tick_catalog_hash=catalog.catalog_hash,
        historical_tick_source_url=catalog.source_url,
        historical_tick_policy="CAUSAL_OBSERVED_GRID_THEN_OFFICIAL_COMPLETION_BOUND",
    )
    runtime = RecoveryReserveRuntime(
        ReserveConfig(D("0.02"), 1, D(10)),
        parent,
        scenario,
        tape,
        tape.timelines(catalog.absolute_distances(parent.distances)),
        catalog,
    )
    # Runtime provides M007 selector infrastructure; M012 owns release/funding rules.
    item = next(item for item in config["profiles"] if item["profile"]["name"] == PROFILE)
    profile, envelope = (
        typed(ExecutionProfile, item["profile"]),
        typed(BookEnvelope, item["envelope"]),
    )
    periods = [
        (int(row["start_us"]), int(row["end_us"]), typed(SymbolRules, row["rule"]))
        for row in config["rules"]
    ]

    def rules_at(timestamp):
        for first, last, rule in periods:
            if first <= timestamp < last:
                return rule
        raise ValueError("NO_RULE_FOR_EVENT")

    scenario_event = registry.append_scenario(
        "M012",
        {
            "scenario": {
                "name": "M012_REALITY_COMPOUNDING_PRIMARY",
                "profile": item,
                "profile_config_sha256": PROFILE_CONFIG_SHA,
                "initial_quote": "100",
                "initial_reserve": "5",
                "capital_mode": "COMPOUNDING",
                "tape_hash": TAPE_HASH,
            }
        },
    )
    run_event = registry.append_run(
        "M012",
        RunSpec(
            scenario_hash=scenario_event["payload"]["SCENARIO_HASH"],
            dataset_hash=history.dataset_hash,
            campaign_snapshot_id=TAPE_HASH,
            interval={"start": start.isoformat(), "end_exclusive": end.isoformat()},
            code_commit=source_sha,
            technical_revision="M012_REALITY_V1",
            backend=BackendSpec(backend="CPU"),
            capital_mode="COMPOUNDING",
            run={
                "model_spec_sha256": file_sha(SPEC),
                **design_binding,
                "runtime": actual_runtime,
                "output": str(output),
            },
        ),
    )
    identity = {
        "capital_mode": "COMPOUNDING",
        "published_config_sha": source_sha,
        "model_id": "M012",
        "model_hash": model.model_hash,
        "run_hash": run_event["payload"]["RUN_HASH"],
        "model_spec_sha256": file_sha(SPEC),
        **design_binding,
        "runtime": actual_runtime,
        "profile_config_sha256": PROFILE_CONFIG_SHA,
        "data_manifest_sha256": config["history_manifest_sha256"],
        "expected_last_trade_us": int(tape.events[stop - 1]) // EVENT_ORDER_SCALE,
        "expected_trade_count": stop - begin,
        "start": start.isoformat(),
        "end_exclusive": end.isoformat(),
    }
    replay = HighUptimeRecoveryReplay(
        runtime, profile, rules_at, envelope, start_us=start_us, end_us=end_us, identity=identity
    )
    journal = AuditJournal(output / "execution-audit.jsonl")
    capital_curve = AuditJournal(output / "capital-curve.jsonl")
    registry.transition(
        "M012",
        ModelStatus.RUNNING,
        reason="OWNER authorized compounding reality replay after published prereg/review/tests",
    )
    write_json(output / "run-manifest.json", identity)
    print(
        json.dumps({"MODEL_ID": "M012", "RUN_ID": identity["run_hash"], "SOURCE_SHA": source_sha}),
        flush=True,
    )
    checkpoint_at = time.monotonic()
    milestones = [start_us + days * 86_400_000_000 for days in (1, 7, 30, 90)]
    previous_id = None
    last_violation_count = 0

    def checkpoint(reason, as_of_us=None):
        journal.drain(replay.execution)
        binding = journal.durable()
        saved_replay = replay.checkpoint()
        metrics = replay.metrics(as_of_us=as_of_us)
        cutoff = (
            int(tape.events[begin + replay.processed_trades - 1])
            if replay.processed_trades
            else None
        )
        metrics.update(
            {
                "CHECKPOINT_REASON": reason,
                "RUN_ID": identity["run_hash"],
                "EXECUTION_SOURCE_COMMIT": source_sha,
                "AUDIT_PREFIX": binding,
                "CANONICAL_CUTOFF_EVENT": cutoff,
                "PROCESSED_TRADES": replay.processed_trades,
                "LAST_TRADE_TIMESTAMP_US": replay.last_us if replay.processed_trades else None,
                "REPLAY_CHECKPOINT_SHA256": saved_replay["sha256"],
                "CAPITAL_BOUNDARY_SEMANTICS": "TIMESTAMP_STRICTLY_LESS_THAN_BOUNDARY"
                if as_of_us is not None
                else "INCLUSIVE_LAST_PROCESSED_EVENT",
            }
        )
        capital_curve.drain(SimpleNamespace(audit=[metrics]))
        curve_binding = capital_curve.durable()
        write_json(
            output / "checkpoint.json",
            {"replay": saved_replay, "audit": binding, "capital_curve": curve_binding},
        )
        metrics["CHECKPOINT_SHA256"] = file_sha(output / "checkpoint.json")
        metrics["CAPITAL_CURVE_PREFIX"] = curve_binding
        write_json(output / "scoreboard.json", metrics)
        if reason.startswith("DAY_") or reason == "COMPLETE":
            label = reason if reason.startswith("DAY_") else "FINAL"
            write_json(output / "capital-checkpoints" / f"{label}.json", metrics)
        print(json.dumps(metrics, default=str), flush=True)

    try:
        checkpoint("INITIAL", start_us)
        for event in iter_history(history, start=start, end_exclusive=end):
            stamp = _datetime_to_micros(event.timestamp)
            for boundary in due_boundaries(milestones, stamp):
                replay.advance_to(boundary)
                checkpoint(f"DAY_{(boundary - start_us) // 86_400_000_000}", boundary)
            if previous_id is not None and event.trade_id != previous_id + 1:
                raise ValueError("UNDECLARED_RAW_TRADE_ID_GAP")
            previous_id = event.trade_id
            canonical_event = int(tape.events[begin + replay.processed_trades])
            if (
                canonical_event // EVENT_ORDER_SCALE != stamp
                or D(int(tape.price_ticks[begin + replay.processed_trades])) * tape.tick_size
                != event.price
            ):
                raise ValueError("RAW_FLOW_CANONICAL_PRICE_TAPE_MISMATCH")
            replay.step(
                Trade(
                    stamp,
                    event.trade_id,
                    event.price,
                    event.quantity,
                    event.buyer_is_maker,
                    canonical_event,
                )
            )
            journal.drain(replay.execution)
            violation_count = replay.execution.counts.get("HARD_LOCK_VIOLATIONS", 0)
            reason = None
            if violation_count > last_violation_count:
                reason = "HARD_LOCK_VIOLATION"
                last_violation_count = violation_count
            if reason or time.monotonic() - checkpoint_at >= 60:
                checkpoint(reason or "PERIODIC")
                checkpoint_at = time.monotonic()
        replay.finish()
        checkpoint("COMPLETE")
    except BaseException as exc:
        preserve_failure(output, exc, identity)
        raise
    finally:
        journal.close()
        capital_curve.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output", type=Path, default=Path("artifacts/usdcusdt/models/M012/reality-primary")
    )
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    if (args.output / "checkpoint.json").exists() or (
        args.output / "execution-audit.jsonl"
    ).exists():
        raise ValueError("EXISTING_RUN_PRESERVED; do not overwrite or restart")
    with (args.output / "writer.lock").open("a+b") as lock:
        lock.seek(0)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        run(args.output)
