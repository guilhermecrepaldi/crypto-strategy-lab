"""M013 frozen two-stage replay. Stage 2 is fail-closed behind audited Stage 1."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from bisect import bisect_left
from datetime import UTC, datetime
from decimal import Decimal
from itertools import pairwise
from pathlib import Path
from types import SimpleNamespace

from crypto_strategy_lab.microstructure.recovery_reserve_study import (
    file_sha,
    published_sha,
    write_json,
)
from scripts.run_b10_reality import AuditJournal, typed
from scripts.run_high_uptime_recovery import (
    PROFILE,
    PROFILE_CONFIG,
    PROFILE_CONFIG_SHA,
    due_boundaries,
    lf_sha,
    preserve_failure,
    published_bytes,
    runtime_class_evidence,
    validate_review,
)

START = datetime(2026, 1, 1, tzinfo=UTC)
STAGE_1_END = datetime(2026, 6, 1, tzinfo=UTC)
STAGE_2_END = datetime(2026, 9, 5, 23, 59, 59, 783644, tzinfo=UTC)
DAY_CHECKPOINTS = (1, 7, 30, 60, 90, 120)
MODEL_ID = "M013"
SPEC = Path("docs/microstructure/M013_MODEL_SPEC.json")
PREREG = Path("docs/microstructure/M013_CONTINUOUS_MULTI_QUEUE_PREREGISTRATION.md")
REVIEW = Path("reports/usdcusdt/M013-preflight-independent-review.md")
KERNEL = Path("src/crypto_strategy_lab/microstructure/continuous_multi_queue.py")
D = Decimal
WARMUP_START = datetime(2025, 12, 31, tzinfo=UTC)
SOURCE_TAPE = Path(
    "artifacts/usdcusdt/market-tape/"
    "22307d010fe179b2b834931f839376014423bde9a7751b4f453463de16bdcf18"
)
SOURCE_TAPE_HASH = "505fd6c31b010eac4e8da2d7e290137bb455d475b95409ac306d1ded7be55b6c"
SOURCE_MANIFEST_SHA = "9ab5db213673e5f0371c86b1aa35cff3d8925287e77af41cff2e54446c16d907"
EXECUTION_DEPENDENCIES = tuple(
    Path(name)
    for name in (
        "scripts/run_high_uptime_recovery.py",
        "scripts/run_b10_reality.py",
        "src/crypto_strategy_lab/microstructure/high_uptime_recovery.py",
        "src/crypto_strategy_lab/microstructure/b10_reality.py",
        "src/crypto_strategy_lab/microstructure/serial_replay.py",
        "src/crypto_strategy_lab/microstructure/recovery_reserve.py",
        "src/crypto_strategy_lab/microstructure/tape_cache.py",
        "src/crypto_strategy_lab/microstructure/data.py",
        "src/crypto_strategy_lab/microstructure/operator.py",
        "src/crypto_strategy_lab/microstructure/recovery_reserve_study.py",
        "src/crypto_strategy_lab/ml/model_registry.py",
    )
)


def prefix_archives(history, start=WARMUP_START, end=STAGE_1_END):
    from crypto_strategy_lab.microstructure.data import select_history_archives

    selected = select_history_archives(history, start=start, end_exclusive=end)
    if any(item.first_timestamp < start or item.last_timestamp >= end for item in selected):
        raise ValueError("ARCHIVE_CROSSES_SEALED_BOUNDARY")
    return selected


def load_stage1_tape(history, output):
    """Derive only the authorized physical prefix; never hash or scan sealed array suffixes."""
    import numpy as np

    from crypto_strategy_lab.microstructure.recovery_reserve_study import file_sha, write_json
    from crypto_strategy_lab.microstructure.serial_replay import (
        EVENT_ORDER_SCALE,
        USDCUSDT_TICK_CATALOG,
        SerialTape,
        _datetime_to_micros,
    )
    from crypto_strategy_lab.microstructure.tape_cache import (
        TapeCacheManifest,
        _first_observed_tick_evidence,
        load_or_build_tape,
    )

    selected = prefix_archives(history)
    archive_bindings = []
    for item in selected:
        path = Path(item.local_path)
        if path.stat().st_size != item.size_bytes or file_sha(path) != item.sha256:
            raise ValueError("STAGE_1_ARCHIVE_HASH_MISMATCH:" + str(path))
        archive_bindings.append({"path": str(path), "sha256": item.sha256})
    source_manifest_path = SOURCE_TAPE / "manifest.json"
    if file_sha(source_manifest_path) != SOURCE_MANIFEST_SHA:
        raise ValueError("PINNED_SOURCE_MANIFEST_HASH_MISMATCH")
    source = TapeCacheManifest.model_validate_json(source_manifest_path.read_bytes())
    if (
        source.tape_hash != SOURCE_TAPE_HASH
        or source.dataset_hash != history.dataset_hash
        or source.start != WARMUP_START
    ):
        raise ValueError("CANONICAL_SOURCE_TAPE_IDENTITY_MISMATCH")
    count = sum(item.record_count for item in selected)
    lower = _datetime_to_micros(WARMUP_START) * EVENT_ORDER_SCALE
    upper = _datetime_to_micros(STAGE_1_END) * EVENT_ORDER_SCALE

    def derive():
        arrays = {}
        for name in ("events", "price_ticks"):
            descriptor = source.files[name]
            path = SOURCE_TAPE / f"{name}.npy"
            if path.stat().st_size != descriptor.size:
                raise ValueError("CANONICAL_SOURCE_ARRAY_SIZE_MISMATCH")
            mapped = np.load(path, mmap_mode="r", allow_pickle=False)
            if mapped.dtype.str != descriptor.dtype or mapped.shape != descriptor.shape:
                raise ValueError("CANONICAL_SOURCE_ARRAY_FORMAT_MISMATCH")
            # Index derives exclusively from already hashed authorized archive counts.
            # No binary search into future timestamps and no full-file rehash.
            arrays[name] = mapped[:count]
        events, prices = arrays["events"], arrays["price_ticks"]
        if (
            len(events) != count
            or len(prices) != count
            or int(events[0]) < lower
            or int(events[-1]) >= upper
            or np.any(events[1:] <= events[:-1])
        ):
            raise ValueError("PHYSICAL_PREFIX_SCOPE_OR_ORDER_MISMATCH")
        ordering = np.argsort(prices, kind="stable")
        grouped_prices = prices[ordering]
        boundaries = np.flatnonzero(grouped_prices[1:] != grouped_prices[:-1]) + 1
        bounds = np.concatenate(([0], boundaries, [count]))
        occurrences = {
            int(grouped_prices[first]): np.array(events[ordering[first:last]])
            for first, last in pairwise(bounds)
        }
        quantum = D(source.quantum)
        observed = _first_observed_tick_evidence(events, prices, quantum, USDCUSDT_TICK_CATALOG)
        return SerialTape(
            quantum, occurrences, events, prices, int(events[-1]), int(prices[-1]), observed
        )

    result = load_or_build_tape(
        history,
        start=WARMUP_START,
        end_exclusive=STAGE_1_END,
        raw_loader=derive,
        progress=lambda name, percentage: print(f"M013_PREFIX_{name}={percentage}%", flush=True),
    )
    if result.manifest.records != count or result.manifest.end_exclusive != STAGE_1_END:
        raise ValueError("DERIVED_PREFIX_COUNT_OR_INTERVAL_MISMATCH")
    provenance = {
        "method": "AUTHORIZED_PREFIX_DERIVED_FROM_CANONICAL_MMAP",
        "source_manifest_sha256": file_sha(source_manifest_path),
        "source_tape_hash": SOURCE_TAPE_HASH,
        "source_full_array_hashes": "HISTORICAL_PROVENANCE_NOT_REHASHED_IN_STAGE_1",
        "prefix_tape_hash": result.tape.tape_hash,
        "prefix_cache_key": result.manifest.cache_key,
        "prefix_records_including_warmup": count,
        "archives_freshly_hashed": archive_bindings,
        "sealed_suffix_scanned": False,
        "raw_prefix_reconciliation": "REQUIRED_PER_EVENT_DURING_REPLAY_INCLUDING_WARMUP",
    }
    write_json(output / "prefix-data-provenance.json", provenance)
    return result.tape, provenance


def stage1_decision(score, audit, *, design=None):
    """Fail-closed economic gate; missing or unbound evidence cannot authorize extension."""
    if score.get("RUN_STATUS") != "COMPLETE" or score.get("STAGE") != "STAGE_1":
        return "PENDING"
    if (
        audit.get("status") != "PASS"
        or audit.get("run_id") != score.get("RUN_ID")
        or audit.get("checkpoint_sha256") != score.get("CHECKPOINT_SHA256")
        or audit.get("model_hash") != score.get("MODEL_HASH")
        or audit.get("execution_evidence_sufficient") is not True
        or audit.get("ordinary_samples", 0) < 100
        or audit.get("all_release_events_audited") is not True
        or audit.get("all_active_reserve_fills_audited") is not True
        or audit.get("all_traded_queues_represented") is not True
    ):
        return "INCONCLUSIVE"
    design = design if design is not None else json.loads(SPEC.read_bytes())
    config = design["gates"]
    if (
        score.get("CALENDAR_DAYS_PROCESSED") != design["stage_1_calendar_days"]
        or score.get("SIMULATION_TIMESTAMP") != design["stage_1_end_exclusive"]
    ):
        return "INCONCLUSIVE"
    for key in ("ACCOUNTING_VIOLATIONS", "FUTURE_LEAKAGE_EVENTS", "LIQUIDITY_DUPLICATION_EVENTS"):
        if score.get(key) != 0:
            return "INCONCLUSIVE"
    gates = (
        ("MOTOR_UPTIME", ">=", "motor_uptime_min"),
        ("CAPITAL_WEIGHTED_UPTIME", ">=", "capital_weighted_uptime_min"),
        ("DEPLOYABLE_CAPITAL_WEIGHTED_UPTIME", ">=", "deployable_capital_uptime_min"),
        ("FULL_STOP_DAYS", "<=", "full_stop_days_max"),
        ("ZERO_CYCLE_DAYS", "<=", "zero_cycle_days_max"),
        ("MAX_OPERATING_HOLD_HOURS", "<=", "operating_max_hold_hours"),
        ("MAX_ACTIVE_RESERVE_HOLD_HOURS", "<=", "active_max_hold_hours"),
        ("HARD_LOCK_VIOLATIONS", "<=", "hard_lock_violations_max"),
        ("RESERVE_MIN", ">", "reserve_min_exclusive"),
        ("RESERVE_DEPLETION_EVENTS", "<=", "reserve_depletion_events_max"),
        ("TOTAL_EQUITY", ">", "total_bid_marked_equity_min_exclusive"),
        ("NET_REALIZED_PNL", ">", "net_realized_pnl_min_exclusive"),
        ("CORE_RESERVE_VIOLATIONS", "<=", "core_and_active_share_violations_max"),
        ("OPERATING_RESTORATION_VIOLATIONS", "<=", "operating_recovery_coverage_violations_max"),
    )
    comparisons = {
        ">=": lambda a, b: a >= b,
        "<=": lambda a, b: a <= b,
        ">": lambda a, b: a > b,
        "==": lambda a, b: a == b,
    }
    outcomes = []
    try:
        for key, operator, threshold in gates:
            value = D(str(score[key]))
            if not value.is_finite():
                return "INCONCLUSIVE"
            outcomes.append(comparisons[operator](value, D(str(config[threshold]))))
        consumption = D(str(score["RESERVE_CONSUMPTION"])) + D(str(score["ACTIVE_RESERVE_LOSSES"]))
        if consumption > 0:
            sustainability = D(str(score["RESERVE_SELF_SUSTAINABILITY_RATIO"]))
            if not sustainability.is_finite():
                return "INCONCLUSIVE"
            outcomes.append(sustainability >= D(config["reserve_self_sustainability_min"]))
        elif consumption == 0:
            # Undefined 0-denominator is never fabricated as infinity or a numeric pass.
            outcomes.append(D(str(score["ACTIVE_RESERVE_NET_PNL"])) >= 0)
        else:
            return "INCONCLUSIVE"
    except (KeyError, ValueError, ArithmeticError):
        return "INCONCLUSIVE"
    return "PASS_TO_EXTENSION" if all(outcomes) else "FAIL"


def validate_extension_artifacts(folder: Path):
    """Call BEFORE reading any extension market data. Binds audit to immutable final state."""
    score_path = folder / "capital-checkpoints" / "FINAL_5_MONTH.json"
    score = json.loads(score_path.read_bytes())
    audit_path = folder / "stage1-independent-audit.json"
    audit = json.loads(audit_path.read_bytes())
    checkpoint = folder / "stage1-final-checkpoint.json"
    digest = hashlib.sha256(checkpoint.read_bytes()).hexdigest()
    if digest != score.get("CHECKPOINT_SHA256"):
        raise ValueError("STAGE_1_FINAL_CHECKPOINT_BINDING_MISMATCH")
    if stage1_decision(score, audit) != "PASS_TO_EXTENSION":
        raise ValueError("SEALED_EXTENSION_GATE_CLOSED")
    return score, audit, hashlib.sha256(audit_path.read_bytes()).hexdigest()


def validate_registered_design(model):
    from crypto_strategy_lab.ml.model_registry import compute_model_hash

    spec = json.loads(SPEC.read_bytes())
    expected = {
        **spec,
        "preregistration_sha256_lf": lf_sha(PREREG),
        "spec_sha256_lf": lf_sha(SPEC),
    }
    if dict(model.model) != expected or compute_model_hash(expected) != model.model_hash:
        raise ValueError("REGISTERED_DESIGN_OR_PREREG_HASH_MISMATCH")
    if spec.get("capital_mode") != "COMPOUNDING":
        raise ValueError("OWNER_COMPOUNDING_REQUIRED")
    return spec


def runtime_for(tape):
    from crypto_strategy_lab.microstructure.operator import frozen_m007_strategy
    from crypto_strategy_lab.microstructure.recovery_reserve import (
        RecoveryReserveRuntime,
        ReserveConfig,
    )
    from crypto_strategy_lab.microstructure.serial_replay import (
        USDCUSDT_TICK_CATALOG,
        SerialScenarioConfig,
    )

    parent, catalog = frozen_m007_strategy(), USDCUSDT_TICK_CATALOG
    scenario = SerialScenarioConfig(
        scenario_id="PRICE_PATH_HISTORICAL_TICK_ZERO_FEE_V2",
        tick_size=tape.tick_size,
        historical_tick_catalog_hash=catalog.catalog_hash,
        historical_tick_source_url=catalog.source_url,
        historical_tick_policy="CAUSAL_OBSERVED_GRID_THEN_OFFICIAL_COMPLETION_BOUND",
    )
    # Existing prefix selector infrastructure only; M013 owns all treasury/release policy.
    return RecoveryReserveRuntime(
        ReserveConfig(D("0.02"), 1, D(10)),
        parent,
        scenario,
        tape,
        tape.timelines(catalog.absolute_distances(parent.distances)),
        catalog,
    )


def prepare_only(output: Path):
    """Data preparation is not an economic run and cannot open the Stage 2 gate."""
    if MODEL_ID == "M013":
        raise ValueError("M013_RETIRED_TECHNICAL; WEEKLY_OWNER_GATED_REPLAY_REQUIRED")
    from crypto_strategy_lab.microstructure.data import HistoryManifest
    from crypto_strategy_lab.ml.model_registry import ModelRegistry

    source = published_sha()
    for path in (
        SPEC,
        PREREG,
        Path(__file__).resolve().relative_to(Path.cwd()),
        *EXECUTION_DEPENDENCIES,
    ):
        published_bytes(path, source)
    validate_registered_design(ModelRegistry().get(MODEL_ID))
    if file_sha(PROFILE_CONFIG) != PROFILE_CONFIG_SHA:
        raise ValueError("FROZEN_EXECUTION_PROFILE_MISMATCH")
    config = json.loads(PROFILE_CONFIG.read_bytes())
    manifest = Path(config["history_manifest"])
    if file_sha(manifest) != config["history_manifest_sha256"]:
        raise ValueError("PINNED_HISTORY_MANIFEST_MISMATCH")
    tape, provenance = load_stage1_tape(
        HistoryManifest.model_validate_json(manifest.read_bytes()), output
    )
    print(
        json.dumps(
            {
                "DATA_PREPARATION": "COMPLETE",
                "ECONOMIC_REPLAY_STARTED": False,
                "PREFIX_TAPE_HASH": tape.tape_hash,
                "PROVENANCE": provenance,
            }
        ),
        flush=True,
    )


def run(output: Path, *, extend=False):
    if MODEL_ID == "M013":
        raise ValueError("M013_RETIRED_TECHNICAL; WEEKLY_OWNER_GATED_REPLAY_REQUIRED")
    from crypto_strategy_lab.microstructure.b10_reality import (
        BookEnvelope,
        ExecutionProfile,
        SymbolRules,
    )
    from crypto_strategy_lab.microstructure.continuous_multi_queue import ContinuousMultiQueueReplay
    from crypto_strategy_lab.microstructure.data import HistoryManifest
    from crypto_strategy_lab.microstructure.serial_replay import (
        EVENT_ORDER_SCALE,
        USDCUSDT_TICK_CATALOG,
        _datetime_to_micros,
    )
    from crypto_strategy_lab.microstructure.tape_cache import load_tape_cache
    from crypto_strategy_lab.ml.model_registry import (
        BackendSpec,
        ModelRegistry,
        ModelStatus,
        RunSpec,
    )

    if not extend and any(
        (output / name).exists()
        for name in (
            "checkpoint.json",
            "run-manifest.json",
            "execution-audit.jsonl",
        )
    ):
        raise ValueError("EXISTING_RUN_PRESERVED")
    # Gate must precede even opening extension arrays or archives.
    extension_evidence = validate_extension_artifacts(output) if extend else None
    source_sha = published_sha()
    own_path = Path(__file__).resolve().relative_to(Path.cwd())
    sources = (KERNEL, own_path, Path("scripts/report_continuous_multi_queue.py"))
    for path in (
        SPEC,
        PREREG,
        REVIEW,
        *sources,
        *EXECUTION_DEPENDENCIES,
    ):
        published_bytes(path, source_sha)
    validate_review(REVIEW, sources)
    actual_runtime = runtime_class_evidence(ContinuousMultiQueueReplay, KERNEL)
    registry = ModelRegistry()
    model = registry.get(MODEL_ID)
    spec = validate_registered_design(model)
    if model.model.get("strategy") != "CONTINUOUS_MULTI_QUEUE_RECOVERY":
        raise ValueError("M013_REGISTERED_MODEL_MISMATCH")
    if not extend and registry.current_status(MODEL_ID) != ModelStatus.CREATED:
        raise ValueError("M013_FIRST_STAGE_ALREADY_REGISTERED")
    if file_sha(PROFILE_CONFIG) != PROFILE_CONFIG_SHA:
        raise ValueError("FROZEN_EXECUTION_PROFILE_MISMATCH")
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
    prefix_tape, provenance = load_stage1_tape(history, output)
    tape = prefix_tape
    start_us = _datetime_to_micros(START)
    end = STAGE_2_END if extend else STAGE_1_END
    end_us = _datetime_to_micros(end)
    begin = bisect_left(tape.events, start_us * EVENT_ORDER_SCALE)
    item = next(row for row in config["profiles"] if row["profile"]["name"] == PROFILE)
    profile = typed(ExecutionProfile, item["profile"])
    envelope = typed(BookEnvelope, item["envelope"])
    periods = [
        (int(row["start_us"]), int(row["end_us"]), typed(SymbolRules, row["rule"]))
        for row in config["rules"]
    ]

    def rules_at(timestamp):
        for first, last, rule in periods:
            if first <= timestamp < last:
                return rule
        raise ValueError("NO_RULE_FOR_EVENT")

    if not extend:
        scenario = registry.append_scenario(
            MODEL_ID,
            {
                "scenario": {
                    "name": "M013_REALITY_COMPOUNDING_TWO_STAGE",
                    "profile": item,
                    "profile_config_sha256": PROFILE_CONFIG_SHA,
                    "initial_quote": "100",
                    "initial_reserve": "10",
                    "capital_mode": "COMPOUNDING",
                    "stage1_tape_hash": tape.tape_hash,
                    "sealed_extension_source": SOURCE_TAPE_HASH,
                }
            },
        )
        run_event = registry.append_run(
            MODEL_ID,
            RunSpec(
                scenario_hash=scenario["payload"]["SCENARIO_HASH"],
                dataset_hash=history.dataset_hash,
                campaign_snapshot_id=tape.tape_hash,
                interval={"start": START.isoformat(), "end_exclusive": STAGE_1_END.isoformat()},
                code_commit=source_sha,
                technical_revision="M013_TWO_STAGE_REALITY_V1",
                backend=BackendSpec(backend="CPU"),
                capital_mode="COMPOUNDING",
                run={
                    "test_plan": "TWO_STAGE",
                    "runtime": actual_runtime,
                    "spec_sha256_lf": lf_sha(SPEC),
                    "preregistration_sha256_lf": lf_sha(PREREG),
                    "output": str(output),
                    "prefix_data_provenance": provenance,
                },
            ),
        )
        identity = {
            "capital_mode": "COMPOUNDING",
            "published_config_sha": source_sha,
            "model_id": MODEL_ID,
            "model_hash": model.model_hash,
            "run_hash": run_event["payload"]["RUN_HASH"],
            "stage": "STAGE_1",
            "model_spec_sha256": file_sha(SPEC),
            "spec_sha256_lf": lf_sha(SPEC),
            "preregistration_sha256_lf": lf_sha(PREREG),
            "runtime": actual_runtime,
            "profile_config_sha256": PROFILE_CONFIG_SHA,
            "data_manifest_sha256": config["history_manifest_sha256"],
            "prefix_tape_hash": tape.tape_hash,
            "expected_trade_count": len(tape.events) - begin,
            "expected_last_trade_us": int(tape.events[-1]) // EVENT_ORDER_SCALE,
            "start": START.isoformat(),
            "end_exclusive": end.isoformat(),
        }
        replay = ContinuousMultiQueueReplay(
            runtime_for(tape),
            profile,
            rules_at,
            envelope,
            start_us=start_us,
            end_us=end_us,
            identity=identity,
            spec=spec,
        )
        saved = None
        registry.transition(
            MODEL_ID,
            ModelStatus.RUNNING,
            reason="OWNER authorized frozen five-month Stage 1 after independent preflight review",
        )
        write_json(output / "run-manifest.json", identity)
    else:
        original_identity = json.loads((output / "run-manifest.json").read_bytes())
        if original_identity["model_hash"] != model.model_hash:
            raise ValueError("EXTENSION_MODEL_CHANGED")
        # Reporting-only newer commits cannot silently replace execution implementation.
        for path in (*sources, *EXECUTION_DEPENDENCIES):
            published_bytes(path, original_identity["published_config_sha"])
        source_sha = original_identity["published_config_sha"]
        saved = json.loads((output / "stage1-final-checkpoint.json").read_bytes())
        replay = ContinuousMultiQueueReplay(
            runtime_for(tape),
            profile,
            rules_at,
            envelope,
            start_us=start_us,
            end_us=_datetime_to_micros(STAGE_1_END),
            identity=original_identity,
            spec=spec,
        )
        replay.restore(saved["replay"])
        tape = load_tape_cache(SOURCE_TAPE, tick_catalog=USDCUSDT_TICK_CATALOG)
        if tape.tape_hash != SOURCE_TAPE_HASH:
            raise ValueError("EXTENSION_CANONICAL_TAPE_HASH_MISMATCH")
        for archive in prefix_archives(history, STAGE_1_END, STAGE_2_END):
            path = Path(archive.local_path)
            if path.stat().st_size != archive.size_bytes or file_sha(path) != archive.sha256:
                raise ValueError("EXTENSION_RAW_ARCHIVE_HASH_MISMATCH")
        import numpy as np

        if not np.array_equal(tape.events[: len(prefix_tape.events)], prefix_tape.events) or not (
            np.array_equal(tape.price_ticks[: len(prefix_tape.events)], prefix_tape.price_ticks)
        ):
            raise ValueError("EXTENSION_PREFIX_CHANGED")
        identity = {
            **original_identity,
            "stage": "STAGE_2",
            "end_exclusive": end.isoformat(),
            "expected_trade_count": len(tape.events) - begin,
            "expected_last_trade_us": int(tape.events[-1]) // EVENT_ORDER_SCALE,
            "extension_tape_hash": tape.tape_hash,
        }
        replay.extend_to(
            end_us, identity, "PASS_TO_EXTENSION", extension_evidence[2], runtime=runtime_for(tape)
        )
        write_json(output / "extension-manifest.json", identity)
    print(
        json.dumps(
            {
                "MODEL_ID": MODEL_ID,
                "MODEL_HASH": model.model_hash,
                "RUN_ID": identity["run_hash"],
                "STAGE": identity["stage"],
                "STAGE_1_CALENDAR_DAYS": 151,
                "EXECUTION_SOURCE_COMMIT": source_sha,
            }
        ),
        flush=True,
    )
    stream_stage(history, tape, begin, replay, identity, output, saved=saved)


def stream_stage(history, tape, begin, replay, identity, output, *, saved=None):
    from crypto_strategy_lab.microstructure.b10_reality import Trade
    from crypto_strategy_lab.microstructure.data import iter_history
    from crypto_strategy_lab.microstructure.serial_replay import (
        _datetime_to_micros,
    )

    stage = identity["stage"]
    start = START if stage == "STAGE_1" else STAGE_1_END
    end = STAGE_1_END if stage == "STAGE_1" else STAGE_2_END
    start_us, end_us = _datetime_to_micros(START), _datetime_to_micros(end)
    journal = AuditJournal(output / "execution-audit.jsonl", saved["audit"] if saved else None)
    curve = AuditJournal(output / "capital-curve.jsonl", saved["capital_curve"] if saved else None)
    milestones = [start_us + d * 86_400_000_000 for d in DAY_CHECKPOINTS] if not saved else []
    month_boundaries = {
        _datetime_to_micros(datetime(2026, month, 1, tzinfo=UTC)): f"2026-{month - 1:02}"
        for month in range(2 if not saved else 7, 7 if not saved else 10)
        if start < datetime(2026, month, 1, tzinfo=UTC) < end
    }
    day_boundaries = set(milestones)
    milestones = sorted(set(milestones) | set(month_boundaries))
    checkpoint_at = time.monotonic()
    previous_id = None
    previous_stamp = None
    ordinal = 0

    def reconcile(index, event):
        nonlocal previous_stamp, ordinal
        stamp = _datetime_to_micros(event.timestamp)
        ordinal = ordinal + 1 if stamp == previous_stamp else 0
        assert_raw_matches(tape, index, event, ordinal=ordinal)
        previous_stamp = stamp

    def checkpoint(reason, as_of_us=None):
        journal.drain(replay)
        binding = journal.durable()
        state = replay.checkpoint()
        score = replay.metrics(as_of_us=as_of_us)
        score.update(
            {
                "MODEL_ID": MODEL_ID,
                "MODEL_HASH": identity["model_hash"],
                "RUN_ID": identity["run_hash"],
                "STAGE": stage,
                "TEST_PLAN": "TWO_STAGE",
                "CAPITAL_MODE": "COMPOUNDING",
                "INITIAL_EQUITY": "110",
                "EXECUTION_SOURCE_COMMIT": identity["published_config_sha"],
                "CHECKPOINT_REASON": reason,
                "AUDIT_PREFIX": binding,
                "PROCESSED_TRADES": replay.processed_trades,
                "CANONICAL_CUTOFF_EVENT": int(tape.events[begin + replay.processed_trades - 1])
                if replay.processed_trades
                else None,
                "LAST_TRADE_TIMESTAMP_US": replay.last_us if replay.processed_trades else None,
                "STAGE_2_STATUS": "SEALED_NOT_AUTHORIZED_UNLESS_STAGE1_PASS"
                if stage == "STAGE_1"
                else "AUTHORIZED_BY_STAGE1_PASS",
                "VERDICT": "PENDING",
                "STAGE_1_DECISION": "PENDING_INDEPENDENT_AUDIT"
                if reason == "FINAL_5_MONTH"
                else "PASS_TO_EXTENSION"
                if stage == "STAGE_2"
                else "PENDING",
            }
        )
        if as_of_us in month_boundaries:
            score["MONTH_CLOSED"] = month_boundaries[as_of_us]
        elif reason == "FINAL_5_MONTH":
            score["MONTH_CLOSED"] = "2026-05"
        curve.drain(SimpleNamespace(audit=[score]))
        curve_binding = curve.durable()
        physical = {"replay": state, "audit": binding, "capital_curve": curve_binding}
        write_json(output / "checkpoint.json", physical)
        score["CHECKPOINT_SHA256"] = file_sha(output / "checkpoint.json")
        score["CAPITAL_CURVE_PREFIX"] = curve_binding
        write_json(output / "scoreboard.json", score)
        if reason.startswith(("DAY_", "MONTH_")) or reason in ("FINAL_5_MONTH", "FINAL_EXTENSION"):
            write_json(output / "capital-checkpoints" / f"{reason}.json", score)
        if reason == "FINAL_5_MONTH":
            write_json(output / "stage1-final-checkpoint.json", physical)
            if file_sha(output / "stage1-final-checkpoint.json") != score["CHECKPOINT_SHA256"]:
                raise ValueError("FINAL_CHECKPOINT_SERIALIZATION_CHANGED")
        print(json.dumps(score, default=str), flush=True)

    try:
        checkpoint("INITIAL" if not saved else "EXTENSION_START", _datetime_to_micros(start))
        # Warmup must also be reconciled; no strategy decision uses an unchecked pre-start tape.
        if not saved:
            index = 0
            for event in iter_history(history, start=WARMUP_START, end_exclusive=START):
                reconcile(index, event)
                if previous_id is not None and event.trade_id != previous_id + 1:
                    raise ValueError("WARMUP_UNDECLARED_TRADE_ID_GAP")
                previous_id = event.trade_id
                index += 1
            if index != begin:
                raise ValueError("WARMUP_RAW_PREFIX_COUNT_MISMATCH")
        else:
            previous_id = replay.last_trade_id
        for event in iter_history(history, start=start, end_exclusive=end):
            stamp = _datetime_to_micros(event.timestamp)
            for boundary in due_boundaries(milestones, stamp):
                replay.advance_to(boundary)
                reason = (
                    f"DAY_{(boundary - start_us) // 86_400_000_000}"
                    if boundary in day_boundaries
                    else "MONTH_" + month_boundaries[boundary]
                )
                checkpoint(reason, boundary)
            if previous_id is not None and event.trade_id != previous_id + 1:
                raise ValueError("UNDECLARED_RAW_TRADE_ID_GAP")
            previous_id = event.trade_id
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
            journal.drain(replay)
            if time.monotonic() - checkpoint_at >= 60:
                checkpoint("PERIODIC")
                checkpoint_at = time.monotonic()
        for boundary in due_boundaries(milestones, end_us):
            replay.advance_to(boundary)
            reason = (
                f"DAY_{(boundary - start_us) // 86_400_000_000}"
                if boundary in day_boundaries
                else "MONTH_" + month_boundaries[boundary]
            )
            checkpoint(reason, boundary)
        replay.finish()
        checkpoint("FINAL_5_MONTH" if not saved else "FINAL_EXTENSION", end_us)
    except BaseException as exc:
        preserve_failure(output, exc, identity)
        raise
    finally:
        journal.close()
        curve.close()


def assert_raw_matches(tape, index, event, *, ordinal):
    from crypto_strategy_lab.microstructure.serial_replay import (
        EVENT_ORDER_SCALE,
        _datetime_to_micros,
    )

    if index >= len(tape.events) or (
        ordinal >= EVENT_ORDER_SCALE
        or int(tape.events[index])
        != _datetime_to_micros(event.timestamp) * EVENT_ORDER_SCALE + ordinal
        or D(int(tape.price_ticks[index])) * tape.tick_size != event.price
    ):
        raise ValueError("RAW_FLOW_CANONICAL_PRICE_TAPE_MISMATCH")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output", type=Path, default=Path("artifacts/usdcusdt/models/M013/reality-primary")
    )
    parser.add_argument("--extend", action="store_true")
    parser.add_argument("--prepare-only", action="store_true")
    args = parser.parse_args()
    if args.extend and args.prepare_only:
        parser.error("--prepare-only never authorizes extension")
    args.output.mkdir(parents=True, exist_ok=True)
    with (args.output / "writer.lock").open("a+b") as lock:
        lock.seek(0)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if args.prepare_only:
            prepare_only(args.output)
        else:
            run(args.output, extend=args.extend)
