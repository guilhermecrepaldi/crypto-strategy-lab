"""Published, single-writer weekly B10 reserve replay; no account or exchange access."""

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
from contextlib import contextmanager
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
SPEC = Path("docs/microstructure/M014_MODEL_SPEC.json")
PROFILE_CONFIG = Path("artifacts/binance/b10-reality-profiles.json")
PROFILE_CONFIG_SHA = "a77e0c67fdff8c618cbfc28fdd3d49d2fa831626560aed7fe1ec27007293537d"
PROFILE = "B_REALISTIC_CONSERVATIVE"
TAPE_HASH = "505fd6c31b010eac4e8da2d7e290137bb455d475b95409ac306d1ded7be55b6c"
PREREG = Path("docs/microstructure/M014_B10_RESERVE_PREREGISTRATION.md")
REVIEW = Path("reports/usdcusdt/M014-preflight-independent-review.md")
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


def validate_weekly_scope(design):
    start = datetime.fromisoformat(design["start"])
    end = datetime.fromisoformat(design["end_exclusive"])
    if (
        design.get("test_plan") != "WEEKLY_OWNER_GATED"
        or design.get("model_id") != "M014"
        or start != datetime(2026, 1, 1, tzinfo=UTC)
        or end != datetime(2026, 1, 8, tzinfo=UTC)
        or design.get("daily_positive_cycle_target") != 2000
    ):
        raise ValueError("OWNER_WEEK_1_SCOPE_REQUIRED; EXTENSION_NOT_AUTHORIZED")
    return start, end


@contextmanager
def campaign_writer_lock(root=Path("artifacts/usdcusdt/models")):
    """One campaign writer regardless of user-selected output directory."""
    root.mkdir(parents=True, exist_ok=True)
    with (root / ".campaign-writer.lock").open("a+b") as lock:
        if lock.tell() == 0:
            lock.write(b"0")
            lock.flush()
        lock.seek(0)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            lock.seek(0)
            if os.name == "nt":
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(lock, fcntl.LOCK_UN)


def run(output: Path):
    validate_weekly_scope(json.loads(SPEC.read_bytes()))
    with campaign_writer_lock():
        return _run_authorized_week(output)


def _run_authorized_week(output: Path):
    # Gates precede even loading the historical data. No resume/extension in this gate.
    design = json.loads(SPEC.read_bytes())
    start, end = validate_weekly_scope(design)
    if any(
        (output / name).exists()
        for name in ("checkpoint.json", "execution-audit.jsonl", "run-manifest.json")
    ):
        raise ValueError("EXISTING_RUN_PRESERVED")
    source_sha = published_sha()
    sources = (
        KERNEL,
        Path("src/crypto_strategy_lab/microstructure/b10_reality.py"),
        Path(__file__).resolve().relative_to(Path.cwd()),
        Path("scripts/run_continuous_multi_queue.py"),
    )
    dependencies = (
        Path("scripts/run_b10_reality.py"),
        Path("src/crypto_strategy_lab/microstructure/recovery_reserve.py"),
        Path("src/crypto_strategy_lab/microstructure/serial_replay.py"),
        Path("src/crypto_strategy_lab/microstructure/tape_cache.py"),
        Path("src/crypto_strategy_lab/microstructure/data.py"),
        Path("src/crypto_strategy_lab/microstructure/operator.py"),
        Path("src/crypto_strategy_lab/microstructure/recovery_reserve_study.py"),
        Path("src/crypto_strategy_lab/ml/model_registry.py"),
    )
    for path in (SPEC, PREREG, REVIEW, *sources, *dependencies):
        published_bytes(path, source_sha)
    validate_review(REVIEW, sources)
    from crypto_strategy_lab.microstructure.high_uptime_recovery import B10ReserveReplay
    from scripts.run_continuous_multi_queue import load_stage1_tape

    actual_runtime = runtime_class_evidence(B10ReserveReplay)
    registry = ModelRegistry()
    model = registry.get("M014")
    design_binding = validate_registered_design(model)
    if registry.current_status("M014") != ModelStatus.CREATED:
        raise ValueError("M014_FIRST_WEEK_ALREADY_REGISTERED")
    if any(
        registry.current_status(item.model_id) == ModelStatus.RUNNING for item in registry.entries()
    ):
        raise ValueError("ANOTHER_CANONICAL_MODEL_RUNNING")
    if file_sha(PROFILE_CONFIG) != PROFILE_CONFIG_SHA:
        raise ValueError("FROZEN_EXECUTION_EVIDENCE_MISMATCH")
    config = json.loads(PROFILE_CONFIG.read_bytes())
    for key in ("history_manifest", "calibration_manifest", "official_rule_manifest"):
        if file_sha(Path(config[key])) != config[key + "_sha256"]:
            raise ValueError("PINNED_INPUT_HASH_MISMATCH:" + key)
    history = HistoryManifest.model_validate_json(Path(config["history_manifest"]).read_bytes())
    if (
        history.symbol != "USDCUSDT"
        or history.kind != "trades"
        or history.integrity_status != "VALID"
    ):
        raise ValueError("VALID_USDCUSDT_RAW_TRADES_REQUIRED")
    print("M014_LOADING_AUTHORIZED_WEEK_1_PREFIX", flush=True)
    tape, provenance = load_stage1_tape(history, output, end=end)
    start_us, end_us = _datetime_to_micros(start), _datetime_to_micros(end)
    begin = bisect_left(tape.events, start_us * EVENT_ORDER_SCALE)
    if len(tape.events) - begin != 2489204:
        raise ValueError("WEEK_1_PHYSICAL_TRADE_COUNT_MISMATCH")
    parent, catalog = frozen_m007_strategy(), USDCUSDT_TICK_CATALOG
    scenario = SerialScenarioConfig(
        scenario_id="PRICE_PATH_HISTORICAL_TICK_ZERO_FEE_V2",
        tick_size=tape.tick_size,
        historical_tick_catalog_hash=catalog.catalog_hash,
        historical_tick_source_url=catalog.source_url,
        historical_tick_policy="CAUSAL_OBSERVED_GRID_THEN_OFFICIAL_COMPLETION_BOUND",
    )
    runtime = RecoveryReserveRuntime(
        ReserveConfig(D("0.02"), 1, D(10), D("2.5")),
        parent,
        scenario,
        tape,
        tape.timelines(catalog.absolute_distances(parent.distances)),
        catalog,
    )
    item = next(row for row in config["profiles"] if row["profile"]["name"] == PROFILE)
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
        "M014",
        {
            "scenario": {
                "name": "B10_F25_OWNER_RESERVE_WEEK_1",
                "profile": item,
                "profile_config_sha256": PROFILE_CONFIG_SHA,
                "initial_operating": "100",
                "initial_reserve": "10",
                "capital_mode": "COMPOUNDING",
                "prefix_tape_hash": tape.tape_hash,
            }
        },
    )
    run_event = registry.append_run(
        "M014",
        RunSpec(
            scenario_hash=scenario_event["payload"]["SCENARIO_HASH"],
            dataset_hash=history.dataset_hash,
            campaign_snapshot_id=tape.tape_hash,
            interval={"start": start.isoformat(), "end_exclusive": end.isoformat()},
            code_commit=source_sha,
            technical_revision="B10_F25_OWNER_RESERVE_WEEKLY",
            backend=BackendSpec(backend="CPU"),
            capital_mode="COMPOUNDING",
            run={
                "output": str(output),
                "runtime": actual_runtime,
                "prefix_data_provenance": provenance,
                **design_binding,
            },
        ),
    )
    identity = {
        "capital_mode": "COMPOUNDING",
        "published_config_sha": source_sha,
        "model_id": "M014",
        "model_hash": model.model_hash,
        "run_hash": run_event["payload"]["RUN_HASH"],
        "model_spec_sha256": file_sha(SPEC),
        **design_binding,
        "runtime": actual_runtime,
        "profile_config_sha256": PROFILE_CONFIG_SHA,
        "data_manifest_sha256": config["history_manifest_sha256"],
        "prefix_tape_hash": tape.tape_hash,
        "expected_last_trade_us": int(tape.events[-1]) // EVENT_ORDER_SCALE,
        "expected_trade_count": len(tape.events) - begin,
        "start": start.isoformat(),
        "end_exclusive": end.isoformat(),
        "week": 1,
        "automatic_extension": False,
    }
    replay = B10ReserveReplay(
        runtime, profile, rules_at, envelope, start_us=start_us, end_us=end_us, identity=identity
    )
    registry.transition(
        "M014",
        ModelStatus.RUNNING,
        reason="OWNER authorized only Jan1-7 B10 reconstruction with enhanced reserve",
    )
    write_json(output / "run-manifest.json", identity)
    try:
        stream_week(history, tape, begin, replay, identity, output)
    except BaseException:
        registry.transition(
            "M014",
            ModelStatus.INVALIDATED_TECHNICAL,
            reason="See immutable failure.json and last hash-bound checkpoint",
        )
        raise
    registry.transition(
        "M014",
        ModelStatus.INCONCLUSIVE,
        reason="Week1 complete; independent economic audit and OWNER extension approval pending",
    )


def stream_week(history, tape, begin, replay, identity, output):
    from scripts.run_continuous_multi_queue import WARMUP_START, assert_raw_matches

    start = datetime.fromisoformat(identity["start"])
    end = datetime.fromisoformat(identity["end_exclusive"])
    start_us, end_us = _datetime_to_micros(start), _datetime_to_micros(end)
    if start != datetime(2026, 1, 1, tzinfo=UTC) or end != datetime(2026, 1, 8, tzinfo=UTC):
        raise ValueError("OWNER_WEEK_1_SCOPE_REQUIRED")
    journal = AuditJournal(output / "execution-audit.jsonl")
    curve = AuditJournal(output / "capital-curve.jsonl")
    milestones = [start_us + day * 86400000000 for day in range(1, 8)]
    previous_id = previous_stamp = None
    ordinal = 0
    checkpoint_at = time.monotonic()

    def reconcile(index, event):
        nonlocal previous_id, previous_stamp, ordinal
        stamp = _datetime_to_micros(event.timestamp)
        if previous_id is not None and event.trade_id != previous_id + 1:
            raise ValueError("UNDECLARED_RAW_TRADE_ID_GAP")
        ordinal = ordinal + 1 if stamp == previous_stamp else 0
        assert_raw_matches(tape, index, event, ordinal=ordinal)
        previous_id, previous_stamp = event.trade_id, stamp

    def checkpoint(reason, boundary=None):
        journal.drain(replay.execution)
        audit_binding = journal.durable()
        state = replay.checkpoint()
        score = replay.metrics(as_of_us=boundary)
        score.update(
            {
                "MODEL_ID": "M014",
                "MODEL_HASH": identity["model_hash"],
                "RUN_ID": identity["run_hash"],
                "EXECUTION_SOURCE_COMMIT": identity["published_config_sha"],
                "CHECKPOINT_REASON": reason,
                "AUDIT_PREFIX": audit_binding,
                "PROCESSED_TRADES": replay.processed_trades,
                "CANONICAL_CUTOFF_EVENT": int(tape.events[begin + replay.processed_trades - 1])
                if replay.processed_trades
                else None,
                "LAST_TRADE_TIMESTAMP_US": replay.last_us if replay.processed_trades else None,
                "WEEK": 1,
                "CALENDAR_DAYS_TOTAL": 7,
                "DAILY_TARGET": 2000,
                "NEXT_WEEK_AUTHORIZED": False,
                "EXTENSION_STATUS": "AWAITING_OWNER_APPROVAL"
                if reason == "FINAL_WEEK_1"
                else "NOT_AUTHORIZED",
                "VERDICT": "PENDING_INDEPENDENT_AUDIT" if reason == "FINAL_WEEK_1" else "PENDING",
            }
        )
        curve.drain(SimpleNamespace(audit=[score]))
        curve_binding = curve.durable()
        physical = {"replay": state, "audit": audit_binding, "capital_curve": curve_binding}
        write_json(output / "checkpoint.json", physical)
        score["CHECKPOINT_SHA256"] = file_sha(output / "checkpoint.json")
        score["CAPITAL_CURVE_PREFIX"] = curve_binding
        write_json(output / "scoreboard.json", score)
        if reason.startswith("DAY_") or reason == "FINAL_WEEK_1":
            write_json(output / "capital-checkpoints" / (reason + ".json"), score)
        print(
            json.dumps(
                {
                    key: score.get(key)
                    for key in (
                        "MODEL_ID",
                        "SIMULATION_TIMESTAMP",
                        "RUN_STATUS",
                        "CHECKPOINT_REASON",
                        "OPERATING_BANK",
                        "RESERVE",
                        "TOTAL_EQUITY",
                        "FULL_FILL_CYCLES",
                        "NET_POSITIVE_CYCLES",
                        "RELEASE_FILLED",
                        "VERDICT",
                    )
                }
            ),
            flush=True,
        )

    try:
        checkpoint("INITIAL", start_us)
        count = 0
        for event in iter_history(history, start=WARMUP_START, end_exclusive=start):
            reconcile(count, event)
            count += 1
        if count != begin:
            raise ValueError("WARMUP_RAW_PREFIX_COUNT_MISMATCH")
        for event in iter_history(history, start=start, end_exclusive=end):
            stamp = _datetime_to_micros(event.timestamp)
            if not start_us <= stamp < end_us:
                raise ValueError("READER_CROSSED_WEEK_BOUNDARY")
            for boundary in due_boundaries(milestones, stamp):
                replay.advance_to(boundary)
                checkpoint("DAY_" + str((boundary - start_us) // 86400000000), boundary)
            index = begin + replay.processed_trades
            reconcile(index, event)
            replay.step(
                Trade(
                    stamp,
                    event.trade_id,
                    event.price,
                    event.quantity,
                    event.buyer_is_maker,
                    int(tape.events[index]),
                )
            )
            journal.drain(replay.execution)
            if time.monotonic() - checkpoint_at >= 60:
                checkpoint("PERIODIC")
                checkpoint_at = time.monotonic()
        for boundary in due_boundaries(milestones, end_us):
            replay.advance_to(boundary)
            checkpoint("DAY_" + str((boundary - start_us) // 86400000000), boundary)
        replay.finish()
        checkpoint("FINAL_WEEK_1", end_us)
    except BaseException as exc:
        preserve_failure(output, exc, identity)
        raise
    finally:
        journal.close()
        curve.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output", type=Path, default=Path("artifacts/usdcusdt/models/M014/reality-primary")
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
