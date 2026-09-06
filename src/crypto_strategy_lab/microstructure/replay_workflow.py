"""Canonical full-replay workflow for the USDCUSDT model ladder."""

from __future__ import annotations

import json
import os
import subprocess
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
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
) -> tuple[dict[str, Any], ...]:
    """Replay every requested model to the one frozen physical cutoff, sequentially."""
    manifest = HistoryManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
    _validate_manifest(manifest)
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
    warmup_minutes = max(item.lookback_minutes for item in models)
    tape_start = REPLAY_START - timedelta(minutes=warmup_minutes)
    end_exclusive = manifest.last_timestamp + timedelta(microseconds=1)
    if manifest.first_timestamp > tape_start:
        raise ValueError("validated manifest lacks the causal warm-up before 2026-01-01")
    scenario = SerialScenarioConfig(
        scenario_id="PRICE_PATH_HISTORICAL_TICK_ZERO_FEE_V2",
        tick_size=SERIAL_TAPE_QUANTUM,
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
        market_profile = build_hourly_market_profile(
            manifest,
            start=REPLAY_START,
            end_exclusive=end_exclusive,
            tick_size=scenario.tick_size,
            tick_catalog=USDCUSDT_TICK_CATALOG,
        )
        profile_paths = write_hourly_market_profile(
            market_profile,
            artifact_root / "usdcusdt" / "market-profiles" / market_profile.profile_hash,
        )
        tape = load_serial_tape(
            manifest,
            tick_size=scenario.tick_size,
            start=tape_start,
            end_exclusive=end_exclusive,
            tick_catalog=USDCUSDT_TICK_CATALOG,
        )
        analysis_context = TemporalAnalysisContext(tape)
        records: list[dict[str, Any]] = [
            {
                "kind": "MARKET_HOURLY_PROFILE",
                "profile_hash": market_profile.profile_hash,
                "paths": {key: str(value) for key, value in profile_paths.items()},
            }
        ]
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
) -> tuple[dict[str, Any], TemporalReplayAnalysis | None]:
    status = registry.current_status(model.model_id)
    if status in {
        ModelStatus.EVALUATED,
        ModelStatus.PROMOTED,
        ModelStatus.REJECTED,
        ModelStatus.SUPERSEDED,
    }:
        return {"model_id": model.model_id, "status": status.value, "action": "SKIPPED"}, None
    if status == ModelStatus.INVALIDATED_TECHNICAL:
        return {
            "model_id": model.model_id,
            "status": status.value,
            "action": "SKIPPED_TERMINAL_INVALIDATION",
        }, None
    scenario_event = registry.append_scenario(
        model.model_id,
        ScenarioSpec(
            scenario=scenario.model_dump(mode="json", exclude={"scenario_id"}),
            scenario_hash=scenario.scenario_hash,
            label=scenario.scenario_id,
        ),
    )
    code_commit = _git_head()
    run_event = registry.append_run(
        model.model_id,
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
            run={
                "manifest": manifest.dataset_hash,
                "execution_class": scenario.execution_class,
                "validation_accessed": False,
                "locked_test_accessed": False,
                "live_accessed": False,
                "testnet_accessed": False,
            },
        ),
    )
    run_hash = str(run_event["payload"]["RUN_HASH"])
    if status == ModelStatus.CREATED:
        registry.transition(
            model.model_id,
            ModelStatus.RUNNING,
            reason="canonical full DEVELOPMENT replay started",
        )
    try:
        result = replay_serial_model(
            tape,
            model,
            scenario,
            start=REPLAY_START,
            end_exclusive=end_exclusive,
            tick_catalog=tick_catalog,
        )
        analysis = analyze_replay_temporally(
            result,
            tape,
            market_profile,
            analysis_context,
        )
        _record_evaluation(
            registry,
            model,
            scenario,
            result,
            analysis,
            snapshot_id=snapshot_id,
            run_hash=run_hash,
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


def _record_evaluation(
    registry: ModelRegistry,
    model: SerialModelConfig,
    scenario: SerialScenarioConfig,
    result: SerialReplayResult,
    analysis: TemporalReplayAnalysis,
    *,
    snapshot_id: str,
    run_hash: str,
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


__all__ = ["DEFAULT_MODEL_IDS", "REPLAY_START", "run_full_replay_campaign"]
