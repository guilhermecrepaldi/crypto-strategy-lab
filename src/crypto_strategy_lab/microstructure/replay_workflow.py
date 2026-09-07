"""Canonical full-replay workflow for the USDCUSDT model ladder."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from crypto_strategy_lab.domain import canonical_hash
from crypto_strategy_lab.microstructure.campaign import CAMPAIGN_ID
from crypto_strategy_lab.microstructure.data import HistoryManifest
from crypto_strategy_lab.microstructure.market_profile import (
    MarketHourlyProfile,
    build_hourly_market_profile,
    write_hourly_market_profile,
)
from crypto_strategy_lab.microstructure.serial_replay import (
    SERIAL_TAPE_QUANTUM,
    USDCUSDT_TICK_CATALOG,
    SerialModelConfig,
    SerialReplayResult,
    SerialScenarioConfig,
    SerialTape,
    TickCatalog,
    load_serial_tape,
    replay_serial_model,
)
from crypto_strategy_lab.microstructure.tape_cache import (
    CACHE_SCHEMA,
    load_or_build_tape,
    load_tape_cache,
    tape_cache_dir,
)
from crypto_strategy_lab.microstructure.temporal_analysis import (
    MarketProductivityRegime,
    TemporalAnalysisContext,
    TemporalReplayAnalysis,
    analyze_market_productivity_regime,
    analyze_replay_temporally,
)
from crypto_strategy_lab.microstructure.temporal_dashboard import write_temporal_dashboard
from crypto_strategy_lab.ml.model_registry import (
    BackendSpec,
    EvaluationSpec,
    ModelRegistry,
    ModelStatus,
    RunSpec,
    ScenarioSpec,
    run_artifact_dir,
)

REPLAY_START = datetime(2026, 1, 1, tzinfo=UTC)
TECHNICAL_REVISION = "full-replay-historical-tick-temporal-regimes-v2"
DEFAULT_MODEL_IDS = ("M005", "M006", "M007", "M008")


def run_full_replay_campaign(
    manifest_path: Path,
    *,
    artifact_root: Path = Path("artifacts"),
    report_root: Path = Path("reports"),
    model_ids: tuple[str, ...] = DEFAULT_MODEL_IDS,
    progress: Callable[[str, int], None] | None = None,
) -> tuple[dict[str, Any], ...]:
    """Replay every requested model to the one frozen physical cutoff, sequentially."""
    manifest = HistoryManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
    _validate_manifest(manifest)
    progress_callback = progress or (lambda milestone, percent: print(f"{milestone} {percent}"))
    registry = ModelRegistry(artifact_root=artifact_root, report_root=report_root)
    registrations = {item.model_id: item for item in registry.entries()}
    missing = [model_id for model_id in model_ids if model_id not in registrations]
    if missing:
        raise ValueError(f"models must be preregistered first: {', '.join(missing)}")
    models = tuple(
        SerialModelConfig.model_validate(
            {
                "model_id": model_id,
                "parent_model_id": registrations[model_id].lineage.parent_model_id,
                **registrations[model_id].model,
            }
        )
        for model_id in model_ids
    )
    release_support_tape = None
    if any(model.capital_release_protocol is not None for model in models):
        if manifest.dataset_hash != (
            "8cb436b68d6953573d8e7e5dc89eaf53e344e46bde18ce749b440abdd757dd91"
        ):
            raise ValueError("M010_FROZEN_DATASET_MISMATCH")
        parent = registrations["M007"]
        for model in models:
            expected = {
                **parent.model,
                "capital_release_protocol": "OWNER_EXPLORATORY_OVERRIDE_FROZEN_V1",
            }
            if registrations[model.model_id].model != expected:
                raise ValueError("M010_MUST_EQUAL_M007_PLUS_FROZEN_RELEASE")
        release_support_tape = load_tape_cache(
            tape_cache_dir(
                "c5c9ccb6910052cdfce5ad696500b2fb50b0a579a097c81d450de21a3e2b0327", artifact_root
            ),
            tick_catalog=USDCUSDT_TICK_CATALOG,
        )
        if (
            release_support_tape.tape_hash
            != "4a5af5dfaf18a4249f9b98c0a4c15d6b2185df68b5148325f23e09878c3ef24f"
        ):
            raise ValueError("M010_FROZEN_SUPPORT_TAPE_MISMATCH")
    warmup_minutes = max(item.lookback_minutes for item in models)
    tape_start = REPLAY_START - timedelta(minutes=warmup_minutes)
    end_exclusive = manifest.last_timestamp + timedelta(microseconds=1)
    if manifest.first_timestamp > tape_start:
        raise ValueError("validated manifest lacks the causal warm-up before 2026-01-01")
    scenario = SerialScenarioConfig(
        scenario_id="PRICE_PATH_HISTORICAL_TICK_ZERO_FEE_V2",
        tick_size=SERIAL_TAPE_QUANTUM,
        initial_quote=Decimal("100"),
        historical_tick_catalog_hash=USDCUSDT_TICK_CATALOG.catalog_hash,
        historical_tick_source_url=USDCUSDT_TICK_CATALOG.source_url,
        historical_tick_policy="CAUSAL_OBSERVED_GRID_THEN_OFFICIAL_COMPLETION_BOUND",
    )
    snapshot_id = canonical_hash(
        {
            "campaign": CAMPAIGN_ID,
            "dataset_hash": manifest.dataset_hash,
            "replay_start": REPLAY_START,
            "end_exclusive": end_exclusive,
        }
    )
    lock_path = artifact_root / "usdcusdt" / "models" / ".full-replay.lock"
    with _exclusive_lock(lock_path):
        market_profile, profile_paths, profile_reused = load_or_build_market_profile(
            manifest,
            artifact_root=artifact_root,
            start=REPLAY_START,
            end_exclusive=end_exclusive,
            tick_size=scenario.tick_size,
            tick_catalog=USDCUSDT_TICK_CATALOG,
        )
        tape_result = load_or_build_tape(
            manifest,
            start=tape_start,
            end_exclusive=end_exclusive,
            artifact_root=artifact_root,
            tick_size=scenario.tick_size,
            tick_catalog=USDCUSDT_TICK_CATALOG,
            raw_loader=lambda: load_serial_tape(
                manifest,
                tick_size=scenario.tick_size,
                start=tape_start,
                end_exclusive=end_exclusive,
                tick_catalog=USDCUSDT_TICK_CATALOG,
            ),
            progress=progress_callback,
        )
        tape = tape_result.tape
        if release_support_tape is not None and tape.tape_hash != (
            "505fd6c31b010eac4e8da2d7e290137bb455d475b95409ac306d1ded7be55b6c"
        ):
            raise ValueError("M010_FROZEN_EXECUTION_TAPE_MISMATCH")
        analysis_context = TemporalAnalysisContext(tape)
        records: list[dict[str, Any]] = [
            {
                "kind": "MARKET_HOURLY_PROFILE",
                "profile_hash": market_profile.profile_hash,
                "reused": profile_reused,
                "paths": {key: str(value) for key, value in profile_paths.items()},
            }
        ]
        records.insert(
            1,
            {
                "kind": "MARKET_TAPE_READY",
                "tape_hash": tape_result.manifest.tape_hash,
                "records": tape_result.manifest.records,
                "reused": tape_result.reused,
                "memory_footprint_bytes": tape_result.manifest.memory_footprint_bytes,
            },
        )
        analyses: list[TemporalReplayAnalysis] = []
        for model in models:
            record, analysis = _run_one(
                registry,
                model,
                scenario,
                tape,
                manifest,
                snapshot_id,
                end_exclusive,
                market_profile,
                analysis_context,
                USDCUSDT_TICK_CATALOG,
                release_support_tape,
            )
            records.append(record)
            if analysis is not None:
                analyses.append(analysis)
        cohort = _write_cohort_if_eligible(
            analyses,
            expected_model_ids=model_ids,
            manifest=manifest,
            scenario=scenario,
            report_root=report_root,
        )
        if cohort is not None:
            records.append(
                {
                    "kind": "MARKET_PRODUCTIVITY_REGIME",
                    "cohort_hash": cohort.cohort_hash,
                    "blocks": len(cohort.blocks),
                }
            )
        if analyses and {item.model_id for item in analyses} == set(model_ids):
            dashboard_path = report_root / "usdcusdt" / "temporal-productivity.html"
            records.append(
                {
                    "kind": "TEMPORAL_DASHBOARD",
                    "path": str(dashboard_path),
                    "sha256": write_temporal_dashboard(analyses, cohort, dashboard_path),
                }
            )
        return tuple(records)


def load_or_build_market_profile(
    manifest: HistoryManifest,
    *,
    artifact_root: Path,
    start: datetime,
    end_exclusive: datetime,
    tick_size: Any,
    tick_catalog: TickCatalog | None,
) -> tuple[MarketHourlyProfile, dict[str, Path], bool]:
    profile_root = artifact_root / "usdcusdt" / "market-profiles"
    expected_catalog_hash = tick_catalog.catalog_hash if tick_catalog else None
    for directory in sorted(profile_root.glob("*/")):
        json_path = directory / "market-hourly.json"
        csv_path = directory / "market-hourly.csv"
        manifest_path = directory / "market-hourly-manifest.json"
        if not json_path.is_file() or not csv_path.is_file() or not manifest_path.is_file():
            continue
        try:
            cache_metadata = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if (
            cache_metadata.get("dataset_hash") != manifest.dataset_hash
            or cache_metadata.get("profile_hash") != directory.name
        ):
            continue
        expected_metadata = {
            "start": start.isoformat().replace("+00:00", "Z"),
            "end_exclusive": end_exclusive.isoformat().replace("+00:00", "Z"),
            "tick_size": str(tick_size),
            "tick_catalog_hash": expected_catalog_hash,
        }
        declared_target = all(
            cache_metadata.get(key) == value for key, value in expected_metadata.items()
        )
        try:
            profile = MarketHourlyProfile.model_validate_json(json_path.read_text(encoding="utf-8"))
        except Exception:
            if declared_target:
                raise ValueError("matching market profile JSON is invalid") from None
            continue
        profile_matches = (
            profile.dataset_hash == manifest.dataset_hash
            and profile.start == start
            and profile.end_exclusive == end_exclusive
            and profile.tick_size == tick_size
            and profile.tick_catalog_hash == expected_catalog_hash
        )
        if not profile_matches:
            if declared_target:
                raise ValueError("market profile manifest and JSON identities disagree")
            continue
        identity = {
            "dataset_hash": profile.dataset_hash,
            "start": profile.start,
            "end_exclusive": profile.end_exclusive,
            "tick_size": profile.tick_size,
            "tick_catalog_hash": profile.tick_catalog_hash,
            "hours": [item.model_dump(mode="json") for item in profile.hours],
        }
        if canonical_hash(identity) != profile.profile_hash:
            raise ValueError("market profile cache hash validation failed")
        if profile.profile_hash != directory.name:
            raise ValueError("market profile directory does not match its semantic hash")
        actual_hashes = {
            "json_sha256": _file_sha256(json_path),
            "csv_sha256": _file_sha256(csv_path),
        }
        declared_hashes = {key: cache_metadata.get(key) for key in actual_hashes}
        if any(declared_hashes.values()) and declared_hashes != actual_hashes:
            raise ValueError("market profile file hash validation failed")
        for key, value in expected_metadata.items():
            declared = cache_metadata.get(key)
            if declared is not None and declared != value:
                raise ValueError("market profile manifest identity mismatch")
        if declared_hashes != actual_hashes or any(
            cache_metadata.get(key) != value for key, value in expected_metadata.items()
        ):
            upgraded = {**cache_metadata, **expected_metadata, **actual_hashes}
            temporary = manifest_path.with_suffix(".json.upgrading")
            temporary.write_text(
                json.dumps(upgraded, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            os.replace(temporary, manifest_path)
        return profile, {"json": json_path, "csv": csv_path, "manifest": manifest_path}, True
    profile = build_hourly_market_profile(
        manifest,
        start=start,
        end_exclusive=end_exclusive,
        tick_size=tick_size,
        tick_catalog=tick_catalog,
    )
    paths = write_hourly_market_profile(profile, profile_root / profile.profile_hash)
    return profile, paths, False


def _run_one(
    registry: ModelRegistry,
    model: SerialModelConfig,
    scenario: SerialScenarioConfig,
    tape: SerialTape,
    manifest: HistoryManifest,
    snapshot_id: str,
    end_exclusive: datetime,
    market_profile: MarketHourlyProfile,
    analysis_context: TemporalAnalysisContext,
    tick_catalog: TickCatalog,
    release_support_tape: SerialTape | None = None,
) -> tuple[dict[str, Any], TemporalReplayAnalysis | None]:
    status = registry.current_status(model.model_id)
    if status == ModelStatus.INCONCLUSIVE:
        events = registry.journal()
        runs = [
            item["payload"]
            for item in events
            if item["event_type"] == "RUN_REGISTERED"
            and item["payload"]["model_id"] == model.model_id
        ]
        evaluations = [
            item["payload"]
            for item in events
            if item["event_type"] == "EVALUATION_RECORDED"
            and item["payload"]["model_id"] == model.model_id
        ]
        if (
            runs
            and evaluations
            and evaluations[-1]["run_hash"] == runs[-1]["RUN_HASH"]
            and evaluations[-1]["decision"].get("full_replay_completed") is True
        ):
            return {
                "model_id": model.model_id,
                "status": status.value,
                "action": "SKIPPED_COMPLETED_INCONCLUSIVE",
            }, None
    if model.model_id == "M010" and status == ModelStatus.INVALIDATED_TECHNICAL:
        prior_runs = [
            event["payload"]
            for event in registry.journal()
            if event["event_type"] == "RUN_REGISTERED" and event["payload"]["model_id"] == "M010"
        ]
        if prior_runs:
            prior_run = prior_runs[-1]
            raw_path = (
                run_artifact_dir("M010", prior_run["RUN_HASH"], registry.artifact_root)
                / "completed-replay.json"
            )
            if raw_path.exists():
                return _recover_m010_postprocessing(
                    registry,
                    model,
                    scenario,
                    tape,
                    manifest,
                    snapshot_id,
                    end_exclusive,
                    market_profile,
                    analysis_context,
                    prior_run,
                    raw_path,
                )
    if status in {
        ModelStatus.EVALUATED,
        ModelStatus.PROMOTED,
        ModelStatus.REJECTED,
        ModelStatus.SUPERSEDED,
    }:
        return {"model_id": model.model_id, "status": status.value, "action": "SKIPPED"}, None
    if status == ModelStatus.INVALIDATED_TECHNICAL and model.capital_release_protocol is None:
        return {
            "model_id": model.model_id,
            "status": status.value,
            "action": "SKIPPED_TERMINAL_INVALIDATION",
        }, None
    code_commit = _git_head()
    if model.capital_release_protocol is not None:
        remote = subprocess.check_output(
            ["git", "ls-remote", "origin", "refs/heads/main"], text=True
        ).split()[0]
        if (
            remote != code_commit
            or subprocess.check_output(
                ["git", "status", "--porcelain", "--untracked-files=no"], text=True
            ).strip()
        ):
            raise ValueError("M010_REQUIRES_CLEAN_PUBLISHED_CODE_SHA")
    scenario_event = registry.append_scenario(
        model.model_id,
        ScenarioSpec(
            scenario=scenario.model_dump(mode="json", exclude={"scenario_id"}),
            scenario_hash=scenario.scenario_hash,
            label=scenario.scenario_id,
        ),
    )
    run_event = _append_or_retry_run(
        registry,
        model,
        status,
        RunSpec(
            scenario_hash=scenario_event["payload"]["SCENARIO_HASH"],
            dataset_hash=manifest.dataset_hash,
            campaign_snapshot_id=snapshot_id,
            interval={
                "start": REPLAY_START.isoformat(),
                "end_exclusive": end_exclusive.isoformat(),
                "full_replay": True,
                "early_stop": "TECHNICAL_INVALIDITY_ONLY",
            },
            code_commit=code_commit,
            technical_revision=TECHNICAL_REVISION,
            backend=BackendSpec(backend="CPU"),
            initial_capital=Decimal("100"),
            currency="USDT",
            capital_mode="COMPOUNDING",
            run={
                "manifest": manifest.dataset_hash,
                "execution_class": scenario.execution_class,
                "initial_capital": "100",
                "currency": "USDT",
                "capital_mode": "COMPOUNDING",
                "fixed_notional_auxiliary": {
                    "status": "AUXILIARY_ONLY",
                    "notional": "100",
                    "currency": "USDT",
                },
                "capital_release_authorization": (
                    "OWNER_EXPLORATORY_OVERRIDE" if model.capital_release_protocol else None
                ),
                "capital_release_support_tape_hash": (
                    release_support_tape.tape_hash if release_support_tape else None
                ),
                "validation_accessed": False,
                "locked_test_accessed": False,
                "live_accessed": False,
                "testnet_accessed": False,
                "tape_cache": {
                    "cache_key": tape.tape_cache_key,
                    "tape_hash": tape.tape_hash,
                    "schema_version": CACHE_SCHEMA,
                },
            },
        ),
    )
    run_hash = str(run_event["payload"]["RUN_HASH"])
    if status in {ModelStatus.CREATED, ModelStatus.INCONCLUSIVE}:
        registry.transition(
            model.model_id,
            ModelStatus.RUNNING,
            reason=(
                "canonical full DEVELOPMENT replay started"
                if status == ModelStatus.CREATED
                else "resuming canonical full DEVELOPMENT replay after inconclusive run"
            ),
        )
    try:
        print(f"REPLAY_START model={model.model_id} sha={code_commit}", flush=True)
        result = replay_serial_model(
            tape,
            model,
            scenario,
            start=REPLAY_START,
            end_exclusive=end_exclusive,
            tick_catalog=tick_catalog,
            release_support_tape=release_support_tape,
        )
        _persist_completed_replay(
            result,
            run_root=run_artifact_dir(model.model_id, run_hash, registry.artifact_root),
            provenance={
                "model_id": model.model_id,
                "run_hash": run_hash,
                "code_commit": code_commit,
                "scenario_hash": scenario.scenario_hash,
                "dataset_hash": manifest.dataset_hash,
                "campaign_snapshot_id": snapshot_id,
            },
        )
        print(
            f"REPLAY_COMPLETE model={model.model_id} cycles={result.completed_cycles}", flush=True
        )
        analysis = analyze_replay_temporally(
            result,
            tape,
            market_profile,
            analysis_context,
        )
        release_report = None
        if model.capital_release_protocol is not None:
            release_report = _capital_release_report(
                result,
                tape,
                analysis,
                market_profile,
                analysis_context,
                registry.artifact_root,
                scenario=scenario,
                parent_config=_registered_parent_config(registry),
                reconstruction_root=run_artifact_dir(
                    model.model_id, run_hash, registry.artifact_root
                ),
                code_commit=code_commit,
            )
            release_report["code_commit"] = code_commit
            release_report["run_hash"] = run_hash
        _record_evaluation(
            registry,
            model,
            scenario,
            result,
            analysis,
            snapshot_id=snapshot_id,
            run_hash=run_hash,
            release_report=release_report,
        )
        if release_report is not None:
            destination = registry.report_root / "usdcusdt" / "M010-capital-release.json"
            destination.write_text(
                json.dumps(release_report, indent=2, sort_keys=True, default=str) + "\n",
                encoding="utf-8",
            )
        registry.transition(
            model.model_id,
            ModelStatus.EVALUATED,
            reason="full physical interval completed; scientific decision pending",
        )
        return {
            "model_id": model.model_id,
            "status": ModelStatus.EVALUATED.value,
            "run_hash": run_hash,
            "completed_cycles": result.completed_cycles,
            "final_marked_equity": str(result.final_marked_equity),
            "open_cycle": result.open_cycle_censored,
        }, analysis
    except Exception as error:
        failure_path = run_artifact_dir(model.model_id, run_hash, registry.artifact_root) / (
            "technical-failure.json"
        )
        failure_path.write_text(
            json.dumps(
                {
                    "classification": "INVALIDATED_TECHNICAL",
                    "error_type": type(error).__name__,
                    "error": str(error),
                    "recorded_at": datetime.now(UTC).isoformat(),
                    "run_hash": run_hash,
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        registry.transition(
            model.model_id,
            ModelStatus.INVALIDATED_TECHNICAL,
            reason=f"{type(error).__name__}: {error}",
        )
        raise


def _registered_parent_config(registry: ModelRegistry) -> SerialModelConfig:
    parent = registry.get("M007")
    return SerialModelConfig.model_validate(
        {
            **parent.model,
            "model_id": parent.model_id,
            "parent_model_id": parent.lineage.parent_model_id,
        }
    )


def _recover_m010_postprocessing(
    registry: ModelRegistry,
    model: SerialModelConfig,
    scenario: SerialScenarioConfig,
    tape: SerialTape,
    manifest: HistoryManifest,
    snapshot_id: str,
    end_exclusive: datetime,
    market_profile: MarketHourlyProfile,
    analysis_context: TemporalAnalysisContext,
    prior_run: dict[str, Any],
    raw_path: Path,
) -> tuple[dict[str, Any], TemporalReplayAnalysis]:
    """Recover only the known identity-loading failure; never simulate M010 again."""
    analysis_sha = _git_head()
    remote_sha = subprocess.check_output(
        ["git", "ls-remote", "origin", "refs/heads/main"], text=True
    ).split()[0]
    if (
        remote_sha != analysis_sha
        or subprocess.check_output(
            ["git", "status", "--porcelain", "--untracked-files=no"], text=True
        ).strip()
    ):
        raise ValueError("M010_REQUIRES_CLEAN_PUBLISHED_ANALYSIS_SHA")
    raw = json.loads(raw_path.read_text(encoding="utf-8"))
    serialized = json.dumps(
        raw["result"], sort_keys=True, separators=(",", ":"), default=str
    ).encode()
    if raw["result_sha256"] != hashlib.sha256(serialized).hexdigest():
        raise ValueError("M010_COMPLETED_REPLAY_HASH_MISMATCH")
    failure = json.loads((raw_path.parent / "technical-failure.json").read_text())
    if failure["error_type"] != "ValidationError" or not all(
        text in failure["error"] for text in ("model_id", "parent_model_id", "Field required")
    ):
        raise ValueError("M010_POSTPROCESSING_FAILURE_NOT_RECOGNIZED")
    expected = {
        "model_id": "M010",
        "run_hash": prior_run["RUN_HASH"],
        "code_commit": prior_run["code_commit"],
        "scenario_hash": scenario.scenario_hash,
        "dataset_hash": manifest.dataset_hash,
        "campaign_snapshot_id": snapshot_id,
    }
    if raw["provenance"] != expected or raw["status"] != "COMPUTATION_COMPLETE_PENDING_VALIDATION":
        raise ValueError("M010_COMPLETED_REPLAY_PROVENANCE_MISMATCH")
    result = SerialReplayResult.model_validate(raw["result"])
    if (
        result.model_id,
        result.model_hash,
        result.initial_quote,
        result.start,
        result.end_exclusive,
        result.scenario_hash,
    ) != (
        "M010",
        model.model_hash,
        Decimal("100"),
        REPLAY_START,
        end_exclusive,
        scenario.scenario_hash,
    ):
        raise ValueError("M010_COMPLETED_REPLAY_IDENTITY_MISMATCH")
    print(
        f"M010_POSTPROCESSING_RECOVERY source_run={prior_run['RUN_HASH']} "
        f"analysis_sha={analysis_sha}",
        flush=True,
    )
    analysis = analyze_replay_temporally(result, tape, market_profile, analysis_context)
    report = _capital_release_report(
        result,
        tape,
        analysis,
        market_profile,
        analysis_context,
        registry.artifact_root,
        scenario=scenario,
        parent_config=_registered_parent_config(registry),
        reconstruction_root=raw_path.parent,
        code_commit=analysis_sha,
    )
    report.update(
        code_commit=prior_run["code_commit"],
        analysis_code_commit=analysis_sha,
        run_hash=prior_run["RUN_HASH"],
        computation_reused_without_replay=True,
        completed_replay_sha256=raw["result_sha256"],
    )
    _record_evaluation(
        registry,
        model,
        scenario,
        result,
        analysis,
        snapshot_id=snapshot_id,
        run_hash=prior_run["RUN_HASH"],
        release_report=report,
    )
    evaluation = [
        event["payload"]
        for event in registry.journal()
        if event["event_type"] == "EVALUATION_RECORDED" and event["payload"]["model_id"] == "M010"
    ][-1]
    registry.complete_m010_report_recovery(
        prior_run["RUN_HASH"], evaluation["EVALUATION_HASH"], analysis_sha
    )
    (registry.report_root / "usdcusdt" / "M010-capital-release.json").write_text(
        json.dumps(report, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8"
    )
    return {
        "model_id": "M010",
        "status": "EVALUATED",
        "run_hash": prior_run["RUN_HASH"],
        "action": "POSTPROCESSING_RECOVERED_NO_REPLAY",
        "completed_cycles": result.completed_cycles,
        "final_marked_equity": str(result.final_marked_equity),
    }, analysis


def _persist_completed_replay(
    result: SerialReplayResult,
    *,
    run_root: Path,
    provenance: dict[str, Any],
) -> Path:
    """Persist raw computation output before downstream validation can fail."""
    raw = result.model_dump(mode="json")
    raw_bytes = json.dumps(raw, sort_keys=True, separators=(",", ":"), default=str).encode()
    payload = {
        "status": "COMPUTATION_COMPLETE_PENDING_VALIDATION",
        "result_sha256": hashlib.sha256(raw_bytes).hexdigest(),
        "provenance": dict(provenance),
        "result": raw,
    }
    encoded = (json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n").encode()
    destination = run_root / "completed-replay.json"
    if destination.exists():
        if destination.read_bytes() != encoded:
            raise ValueError("completed-replay.json already exists with different content")
        return destination
    run_root.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(encoded)
    return destination


def _record_evaluation(
    registry: ModelRegistry,
    model: SerialModelConfig,
    scenario: SerialScenarioConfig,
    result: SerialReplayResult,
    analysis: TemporalReplayAnalysis,
    *,
    snapshot_id: str,
    run_hash: str,
    release_report: dict[str, Any] | None = None,
) -> None:
    horizons = [item.model_dump(mode="json") for item in analysis.horizons]
    registry.append_evaluation(
        model.model_id,
        EvaluationSpec(
            scenario_hash=scenario.scenario_hash,
            campaign_snapshot_id=snapshot_id,
            run_hash=run_hash,
            comparison={
                "model_ladder": "M005_TO_M008",
                "same_dataset_scenario_cutoff_required": True,
            },
            criteria={
                "promotion_guardrail": "docs/microstructure/USDCUSDT_EXPERIMENT_JOURNAL.md",
                "temporal_metrics_are_diagnostic_only": True,
                "early_stop_economic": False,
            },
            metrics={
                "completed_cycles": result.completed_cycles,
                "initial_quote": result.initial_quote,
                "initial_capital": result.initial_quote,
                "currency": "USDT",
                "capital_mode": "COMPOUNDING",
                "fixed_notional_auxiliary": {
                    "status": "AUXILIARY_ONLY",
                    "notional": Decimal("100"),
                    "currency": "USDT",
                },
                "final_marked_equity": result.final_marked_equity,
                "return_fraction": result.return_fraction,
                "realized_profit": result.realized_profit,
                "unrealized_profit": result.unrealized_profit,
                "fees_quote": result.total_fees,
                "open_cycle_censored": result.open_cycle_censored,
                "temporal_stability": analysis.temporal_stability,
                "concentration": analysis.concentration,
                "productivity_distribution": analysis.productivity_distribution,
                "productivity_fingerprint": analysis.productivity_fingerprint,
                "data_support": analysis.data_support,
                **({"capital_release": release_report} if release_report is not None else {}),
            },
            daily=analysis.daily,
            weekly=analysis.weekly,
            monthly=analysis.monthly,
            hour_of_day=analysis.hour_of_day,
            day_of_week=analysis.day_of_week,
            windows=horizons,
            regimes=analysis.regime_contrasts,
            replay=result.model_dump(mode="json"),
            decision={
                "status": "PENDING_SCIENTIFIC_REVIEW",
                "full_replay_completed": True,
                "early_stop": False,
                "execution_evidence": "INCONCLUSIVE_PRICE_PATH_ONLY",
            },
        ),
    )


def _append_or_retry_run(
    registry: ModelRegistry,
    model: SerialModelConfig,
    status: ModelStatus,
    run: RunSpec,
) -> dict[str, Any]:
    if status != ModelStatus.INVALIDATED_TECHNICAL:
        return registry.append_run(model.model_id, run)
    prior_runs = [
        event["payload"]
        for event in registry.journal()
        if event["event_type"] == "RUN_REGISTERED"
        and event["payload"]["model_id"] == model.model_id
    ]
    if not prior_runs or model.model_id != "M010":
        raise ValueError("NO_AUTHORIZED_TECHNICAL_RETRY")
    return registry.retry_m010_technical_failure(
        str(prior_runs[-1]["RUN_HASH"]),
        run,
        reason=(
            "Correct NumPy representation defects; exact reconstructed M007 comparison and "
            "legacy event-ID audit; frozen M010 scientific rule unchanged."
        ),
    )


def _capital_release_report(
    result: SerialReplayResult,
    tape: SerialTape,
    analysis: TemporalReplayAnalysis,
    market_profile: MarketHourlyProfile,
    context: TemporalAnalysisContext,
    artifact_root: Path,
    *,
    scenario: SerialScenarioConfig,
    parent_config: SerialModelConfig,
    reconstruction_root: Path,
    code_commit: str,
) -> dict[str, Any]:
    from crypto_strategy_lab.microstructure.capital_release import EVALUATION_HASH, REPLAY_HASH
    from crypto_strategy_lab.microstructure.capital_release_analysis import (
        analyze_capital_release,
        audit_legacy_m007_event_projection,
        compare_zero_release,
    )

    parent_path = (
        run_artifact_dir("M007", REPLAY_HASH, artifact_root)
        / "evaluations"
        / EVALUATION_HASH
        / "replay.json"
    )
    parent = SerialReplayResult.model_validate_json(parent_path.read_text(encoding="utf-8"))
    if (parent.start, parent.end_exclusive, parent.scenario_hash) != (
        result.start,
        result.end_exclusive,
        result.scenario_hash,
    ):
        raise ValueError("M010_PARENT_COMPARISON_IDENTITY_MISMATCH")
    print("M007_TECHNICAL_RECONSTRUCTION_START", flush=True)
    reconstructed_parent = replay_serial_model(
        tape,
        parent_config,
        scenario,
        start=parent.start,
        end_exclusive=parent.end_exclusive,
        tick_catalog=USDCUSDT_TICK_CATALOG,
    )
    _persist_completed_replay(
        reconstructed_parent,
        run_root=reconstruction_root / "M007-technical-reconstruction",
        provenance={
            "classification": "TECHNICAL_RECONSTRUCTION_NOT_NEW_EXPERIMENT",
            "code_commit": code_commit,
            "original_m007_artifact": str(parent_path),
            "original_m007_sha256": hashlib.sha256(parent_path.read_bytes()).hexdigest(),
            "execution_tape_hash": tape.tape_hash,
            "purpose": "Recover exact event IDs lost by legacy NumPy/Pydantic serialization",
        },
    )
    legacy_audit = audit_legacy_m007_event_projection(parent, reconstructed_parent)
    equivalence = compare_zero_release(reconstructed_parent, result)
    equivalence["legacy_m007_event_id_audit"] = legacy_audit
    print("M010_EQUIVALENCE_CHECK_COMPLETE", flush=True)
    parent_analysis = analyze_replay_temporally(reconstructed_parent, tape, market_profile, context)
    parent_metrics = analyze_capital_release(
        reconstructed_parent, tape, temporal_analysis=parent_analysis
    )
    metrics = analyze_capital_release(result, tape, temporal_analysis=analysis)
    print("M010_POST_MORTEM_COMPLETE", flush=True)
    return {
        "MODEL": "M010",
        "PARENT": "M007",
        "M010_AUTHORIZATION_CLASS": "OWNER_EXPLORATORY_OVERRIDE",
        "SCIENTIFIC_GATE_PASS": False,
        "HYPOTHESIS_RESULT": "PENDING_AUTOPSY",
        "start": result.start.isoformat(),
        "end_exclusive": result.end_exclusive.isoformat(),
        "execution_tape_hash": tape.tape_hash,
        "M007": parent_metrics,
        "M010": metrics,
        "equivalence": equivalence,
        "VALIDATION_ACCESSED": "NO",
        "LOCKED_TEST_ACCESSED": "NO",
        "BINANCE_LIVE_ACCESSED": "NO",
        "TESTNET_ACCESSED": "NO",
    }


def _write_cohort_if_eligible(
    analyses: list[TemporalReplayAnalysis],
    *,
    expected_model_ids: tuple[str, ...],
    manifest: HistoryManifest,
    scenario: SerialScenarioConfig,
    report_root: Path,
) -> MarketProductivityRegime | None:
    if len(analyses) < 3 or {item.model_id for item in analyses} != set(expected_model_ids):
        return None
    cohort = analyze_market_productivity_regime(
        analyses,
        dataset_hash=manifest.dataset_hash,
        scenario_hash=scenario.scenario_hash,
    )
    path = report_root / "usdcusdt" / "market-productivity-regime.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(cohort.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return cohort


def _validate_manifest(manifest: HistoryManifest) -> None:
    if manifest.symbol != "USDCUSDT" or manifest.kind != "trades":
        raise ValueError("canonical replay accepts only official USDCUSDT trades")
    if manifest.integrity_status != "VALID" or manifest.invalidity_reasons:
        raise ValueError("canonical replay requires a VALID manifest with no invalidity reasons")
    if manifest.last_timestamp < REPLAY_START:
        raise ValueError("validated dataset does not reach the standardized replay start")


@contextmanager
def _exclusive_lock(path: Path) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as error:
        raise RuntimeError(f"another canonical full replay owns {path}") from error
    try:
        os.write(descriptor, f"pid={os.getpid()}\n".encode())
        os.close(descriptor)
        yield
    finally:
        if path.exists():
            path.unlink()


def _git_head() -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, check=True, text=True
    )
    return completed.stdout.strip()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


__all__ = [
    "DEFAULT_MODEL_IDS",
    "REPLAY_START",
    "load_or_build_market_profile",
    "run_full_replay_campaign",
]
