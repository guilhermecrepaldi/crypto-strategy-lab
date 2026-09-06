from __future__ import annotations

import csv
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from crypto_strategy_lab.ml.model_registry import (
    REQUIRED_CREATION_FILES,
    REQUIRED_EVALUATION_FILES,
    REQUIRED_EXECUTION_FILES,
    BackendSpec,
    Hypothesis,
    InvalidStatusTransition,
    ModelLineage,
    ModelRegistry,
    ModelSpec,
    ModelStatus,
    RunSpec,
    ScenarioSpec,
    compute_model_hash,
    compute_run_hash,
    evaluation_artifact_dir,
    run_artifact_dir,
)

AT = datetime(2026, 1, 1, tzinfo=UTC)


def spec(seed: int = 11) -> ModelSpec:
    return ModelSpec(
        model={"decision_rule": "caller-provided", "seed": seed},
        hypothesis=Hypothesis(
            observation="observed",
            hypothesis="hypothesis",
            change="change",
            expected_effect="effect",
            reason_for_new_model="reason",
        ),
        lineage=ModelLineage(change_category="INITIAL", change_summary="initial model"),
        status=ModelStatus.CREATED,
        registered_at=AT,
    )


def run_for(registry: ModelRegistry, model_id: str = "M001") -> tuple[str, str]:
    scenario = registry.append_scenario(
        model_id, ScenarioSpec(scenario={"name": "scenario"}), occurred_at=AT
    )
    scenario_hash = scenario["payload"]["SCENARIO_HASH"]
    run = RunSpec(
        scenario_hash=scenario_hash,
        dataset_hash="dataset-sha",
        campaign_snapshot_id="snapshot-1",
        interval={"start": "2026-01-01", "end": "2026-01-02"},
        code_commit="abc123",
        technical_revision="technical-1",
        backend=BackendSpec(backend="CPU"),
    )
    event = registry.append_run(model_id, run, occurred_at=AT)
    return scenario_hash, event["payload"]["RUN_HASH"]


def test_deterministic_hashes_layout_and_creation_files(tmp_path: Path) -> None:
    registry = ModelRegistry(tmp_path / "artifacts", tmp_path / "reports")
    record = registry.register(spec())
    assert record.model_id == "M001"
    assert record.model_hash == compute_model_hash(spec().model)
    directory = Path(record.artifacts.directory)
    assert directory == tmp_path / "artifacts" / "usdcusdt" / "models" / "M001"
    assert {path.name for path in directory.iterdir()} == set(REQUIRED_CREATION_FILES)
    model_card = (directory / "MODEL_SPEC.md").read_text(encoding="utf-8")
    for field in (
        "MODEL_ID",
        "PARENT",
        "CREATED_AT",
        "HYPOTHESIS",
        "PROBLEM_OBSERVED",
        "CHANGE_FROM_PARENT",
        "EXPECTED_IMPROVEMENT",
        "FULL_STRATEGY_SUMMARY",
        "FINAL_RESULT: pending",
        "DECISION: pending",
        "REASON",
    ):
        assert field in model_card
    assert registry.registry_projection_path.exists()
    assert registry.registry_csv_path.exists()


def test_duplicate_rules_and_divergent_hash_are_rejected(tmp_path: Path) -> None:
    registry = ModelRegistry(tmp_path / "artifacts", tmp_path / "reports")
    registry.register(spec())
    before = registry.registry_path.read_bytes()
    assert registry.register(spec()).model_id == "M001"
    assert registry.registry_path.read_bytes() == before
    with pytest.raises(ValueError, match="MODEL_HASH"):
        registry.register(spec(12).model_copy(update={"model_hash": "wrong"}))


def test_multiple_scenarios_and_runs_stay_under_one_model(tmp_path: Path) -> None:
    registry = ModelRegistry(tmp_path / "artifacts", tmp_path / "reports")
    registry.register(spec())
    first_scenario, first_run = run_for(registry)
    second = registry.append_scenario("M001", {"scenario": {"name": "other"}}, occurred_at=AT)
    assert second["payload"]["SCENARIO_HASH"] != first_scenario
    run = RunSpec(
        scenario_hash=second["payload"]["SCENARIO_HASH"],
        dataset_hash="dataset-sha-2",
        campaign_snapshot_id="snapshot-2",
        interval="2026-02",
        code_commit="abc123",
        technical_revision="technical-1",
        backend=BackendSpec(backend="CPU"),
    )
    second_run = registry.append_run("M001", run, occurred_at=AT)
    assert second_run["payload"]["RUN_HASH"] != first_run
    assert len(registry.entries()) == 1
    assert (
        run_artifact_dir("M001", first_run, tmp_path / "artifacts") / "run-manifest.json"
    ).exists()
    assert (
        run_artifact_dir("M001", second_run["payload"]["RUN_HASH"], tmp_path / "artifacts")
        / "run-manifest.json"
    ).exists()


def test_run_hash_requires_identity_and_is_deterministic(tmp_path: Path) -> None:
    registry = ModelRegistry(tmp_path / "artifacts", tmp_path / "reports")
    registry.register(spec())
    scenario_hash, _ = run_for(registry)
    with pytest.raises(ValueError):
        registry.append_run("M001", {"scenario_hash": scenario_hash, "dataset_hash": "d"})
    run = RunSpec(
        scenario_hash=scenario_hash,
        dataset_hash="dataset-sha",
        campaign_snapshot_id="snapshot-1",
        interval="2026-01",
        code_commit="abc123",
        technical_revision="technical-1",
        backend=BackendSpec(backend="CPU"),
    )
    expected = compute_run_hash(
        model_hash=registry.get("M001").model_hash,
        scenario_hash=scenario_hash,
        dataset_hash=run.dataset_hash,
        campaign_snapshot_id=run.campaign_snapshot_id,
        interval=run.interval,
        code_commit=run.code_commit,
        technical_revision=run.technical_revision,
        backend=run.backend,
    )
    assert registry.append_run("M001", run, occurred_at=AT)["payload"]["RUN_HASH"] == expected


def test_backend_provenance_is_required_and_cuda_is_complete() -> None:
    assert BackendSpec(backend="CPU").model_dump() == {
        "backend": "CPU",
        "device": None,
        "driver": None,
        "runtime": None,
        "library": None,
        "library_version": None,
        "batch_size": None,
        "benchmark_hash": None,
    }
    cuda = BackendSpec(
        backend="CUDA",
        device="cuda:0",
        driver="driver",
        runtime="cuda-runtime",
        library="torch",
        library_version="2.0",
        batch_size=64,
        benchmark_hash="a" * 64,
    )
    assert cuda.backend == "CUDA"
    with pytest.raises(ValueError, match="CUDA backend requires"):
        BackendSpec(backend="CUDA")
    with pytest.raises(ValueError, match="CPU backend forbids"):
        BackendSpec(backend="CPU", batch_size=64)
    with pytest.raises(ValueError, match="string_pattern_mismatch"):
        BackendSpec(
            backend="CUDA",
            device="RTX",
            driver="1",
            runtime="1",
            library="CuPy",
            library_version="1",
            batch_size=64,
            benchmark_hash="not-a-content-hash",
        )


def test_cpu_and_cuda_runs_have_distinct_hashes_without_new_model(tmp_path: Path) -> None:
    registry = ModelRegistry(tmp_path / "artifacts", tmp_path / "reports")
    registry.register(spec())
    scenario_hash, cpu_run_hash = run_for(registry)
    cuda_run = RunSpec(
        scenario_hash=scenario_hash,
        dataset_hash="dataset-sha",
        campaign_snapshot_id="snapshot-1",
        interval={"start": "2026-01-01", "end": "2026-01-02"},
        code_commit="abc123",
        technical_revision="technical-1",
        backend=BackendSpec(
            backend="CUDA",
            device="cuda:0",
            driver="driver",
            runtime="cuda-runtime",
            library="torch",
            library_version="2.0",
            batch_size=64,
            benchmark_hash="a" * 64,
        ),
    )
    cuda_event = registry.append_run("M001", cuda_run, occurred_at=AT)
    assert cuda_event["payload"]["RUN_HASH"] != cpu_run_hash
    assert len(registry.entries()) == 1
    manifest = Path(cuda_event["payload"]["artifact_directory"]) / "run-manifest.json"
    assert manifest.exists()
    assert '"backend": "CUDA"' in manifest.read_text(encoding="utf-8")


def test_run_without_backend_fails_even_with_other_identity_fields(tmp_path: Path) -> None:
    registry = ModelRegistry(tmp_path / "artifacts", tmp_path / "reports")
    registry.register(spec())
    scenario_hash, _ = run_for(registry)
    with pytest.raises(ValueError, match="backend"):
        registry.append_run(
            "M001",
            {
                "scenario_hash": scenario_hash,
                "dataset_hash": "dataset-sha",
                "campaign_snapshot_id": "snapshot-1",
                "interval": "2026-01",
                "code_commit": "abc123",
                "technical_revision": "technical-1",
            },
        )


def test_promotion_requires_evaluation_and_decision_references(tmp_path: Path) -> None:
    registry = ModelRegistry(tmp_path / "artifacts", tmp_path / "reports")
    registry.register(spec())
    scenario_hash, run_hash = run_for(registry)
    registry.transition("M001", ModelStatus.RUNNING, reason="execute", occurred_at=AT)
    registry.transition("M001", ModelStatus.EVALUATED, reason="evaluate", occurred_at=AT)
    decision = {
        "scenario_hash": scenario_hash,
        "campaign_snapshot_id": "snapshot-1",
        "run_hash": run_hash,
        "comparison": {"baseline": "caller-provided"},
        "criteria": {"gate": "caller-provided"},
    }
    registry.promote("M001", decision, occurred_at=AT)
    assert registry.current_status("M001") == ModelStatus.PROMOTED
    assert registry.champion()["model_id"] == "M001"  # type: ignore[index]
    with pytest.raises(InvalidStatusTransition):
        registry.promote("M001", decision, occurred_at=AT)


def test_second_promotion_supersedes_first_and_invalidation_removes_champion(
    tmp_path: Path,
) -> None:
    registry = ModelRegistry(tmp_path / "artifacts", tmp_path / "reports")
    first = registry.register(spec())
    first_scenario, first_run = run_for(registry)
    registry.transition(first.model_id, ModelStatus.RUNNING, reason="execute", occurred_at=AT)
    registry.transition(first.model_id, ModelStatus.EVALUATED, reason="evaluate", occurred_at=AT)
    first_decision = {
        "scenario_hash": first_scenario,
        "campaign_snapshot_id": "snapshot-1",
        "run_hash": first_run,
        "comparison": {"baseline": "first"},
        "criteria": {"gate": "first"},
    }
    registry.promote(first.model_id, first_decision, occurred_at=AT)

    second = registry.register(
        spec(12).model_copy(
            update={
                "lineage": ModelLineage(
                    parent_model_id="M001",
                    ancestor_chain=("M001",),
                    change_category="FOLLOWUP",
                    change_summary="second model",
                )
            }
        )
    )
    second_scenario, second_run = run_for(registry, second.model_id)
    registry.transition(second.model_id, ModelStatus.RUNNING, reason="execute", occurred_at=AT)
    registry.transition(second.model_id, ModelStatus.EVALUATED, reason="evaluate", occurred_at=AT)
    second_decision = {
        "scenario_hash": second_scenario,
        "campaign_snapshot_id": "snapshot-1",
        "run_hash": second_run,
        "comparison": {"baseline": "second"},
        "criteria": {"gate": "second"},
    }
    registry.promote(second.model_id, second_decision, occurred_at=AT)
    assert registry.current_status("M001") == ModelStatus.SUPERSEDED
    assert registry.champion()["model_id"] == "M002"  # type: ignore[index]
    registry.transition("M002", ModelStatus.INVALIDATED_TECHNICAL, reason="bug", occurred_at=AT)
    assert registry.champion() is None


def test_execution_and_evaluation_artifacts_are_explicit(tmp_path: Path) -> None:
    registry = ModelRegistry(tmp_path / "artifacts", tmp_path / "reports")
    registry.register(spec())
    scenario_hash, run_hash = run_for(registry)
    assert (
        run_artifact_dir("M001", run_hash, tmp_path / "artifacts") / REQUIRED_EXECUTION_FILES[0]
    ).exists()
    registry.append_evaluation(
        "M001",
        {
            "scenario_hash": scenario_hash,
            "campaign_snapshot_id": "snapshot-1",
            "run_hash": run_hash,
            "comparison": {"baseline": "caller-provided"},
            "criteria": {"gate": "caller-provided"},
            "metrics": {"result": "caller-provided"},
            "daily": [{"date": "2026-01-01", "value": "caller-provided"}],
            "monthly": [{"month": "2026-01", "value": "caller-provided"}],
        },
        occurred_at=AT,
    )
    evaluation = registry.journal()[-1]
    evaluation_directory = evaluation_artifact_dir(
        "M001",
        run_hash,
        evaluation["payload"]["EVALUATION_HASH"],
        tmp_path / "artifacts",
    )
    assert all((evaluation_directory / name).exists() for name in REQUIRED_EVALUATION_FILES)


def test_productivity_fingerprint_projection_is_empty_until_latest_evaluation(
    tmp_path: Path,
) -> None:
    registry = ModelRegistry(tmp_path / "artifacts", tmp_path / "reports")
    registry.register(spec())
    fields = (
        "BEST_1D_CYCLES",
        "BEST_7D_CYCLES",
        "BEST_30D_CYCLES",
        "BEST_MONTH",
        "BEST_REGIME",
        "WORST_MONTH",
        "LONGEST_HOT_STREAK",
        "LONGEST_COLD_STREAK",
        "HOT_PERIOD_COUNT",
    )
    before = json.loads(registry.registry_projection_path.read_text(encoding="utf-8"))["models"][0]
    assert all(before[field] is None for field in fields)
    with registry.registry_csv_path.open(encoding="utf-8", newline="") as handle:
        before_csv = next(csv.DictReader(handle))
    assert all(before_csv[field] == "" for field in fields)

    scenario_hash, run_hash = run_for(registry)
    fingerprint = {
        "BEST_1D_CYCLES": 3,
        "BEST_7D_CYCLES": 21,
        "BEST_30D_CYCLES": 90,
        "BEST_MONTH": "2026-01",
        "BEST_REGIME": "caller-regime",
        "WORST_MONTH": "2026-02",
        "LONGEST_HOT_STREAK": 8,
        "LONGEST_COLD_STREAK": 5,
        "HOT_PERIOD_COUNT": 2,
    }
    registry.append_evaluation(
        "M001",
        {
            "scenario_hash": scenario_hash,
            "campaign_snapshot_id": "snapshot-1",
            "run_hash": run_hash,
            "comparison": {"baseline": "caller-provided"},
            "criteria": {"gate": "caller-provided"},
            "metrics": {"productivity_fingerprint": fingerprint},
        },
        occurred_at=AT,
    )
    after = json.loads(registry.registry_projection_path.read_text(encoding="utf-8"))["models"][0]
    assert {field: after[field] for field in fields} == fingerprint
    with registry.registry_csv_path.open(encoding="utf-8", newline="") as handle:
        after_csv = next(csv.DictReader(handle))
    assert after_csv["BEST_1D_CYCLES"] == "3"
    assert after_csv["BEST_MONTH"] == "2026-01"
    assert after_csv["HOT_PERIOD_COUNT"] == "2"

    newer_fingerprint = {**fingerprint, "BEST_1D_CYCLES": 4, "BEST_MONTH": "2026-03"}
    registry.append_evaluation(
        "M001",
        {
            "scenario_hash": scenario_hash,
            "campaign_snapshot_id": "snapshot-1",
            "run_hash": run_hash,
            "comparison": {"baseline": "newer"},
            "criteria": {"gate": "newer"},
            "metrics": {"productivity_fingerprint": newer_fingerprint},
        },
        occurred_at=datetime(2026, 1, 2, tzinfo=UTC),
    )
    latest = json.loads(registry.registry_projection_path.read_text(encoding="utf-8"))["models"][0]
    assert latest["BEST_1D_CYCLES"] == 4
    assert latest["BEST_MONTH"] == "2026-03"
