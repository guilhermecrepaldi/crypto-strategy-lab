"""Append-only experiment registry for the preregistered USDCUSDT model campaign."""

from __future__ import annotations

import csv
import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from pathlib import Path
from typing import Any, Final, Literal, Self

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, model_validator

from crypto_strategy_lab.domain import canonical_hash, require_utc

PAIR: Final = "USDCUSDT"
REGISTRY_SCHEMA_VERSION: Final = "usdcusdt-model-registry-v2"
MODEL_ID_PATTERN: Final = re.compile(r"^M[0-9]{3,}$")
REQUIRED_CREATION_FILES: Final = ("MODEL_SPEC.md", "config.json", "hypothesis.json", "lineage.json")
REQUIRED_EXECUTION_FILES: Final = ("run-manifest.json",)
REQUIRED_EVALUATION_FILES: Final = (
    "metrics.json",
    "daily.csv",
    "weekly.csv",
    "monthly.csv",
    "hour-of-day.csv",
    "day-of-week.csv",
    "windows.json",
    "regimes.json",
    "replay.json",
    "decision.json",
)
PROJECTION_FIELDS: Final = (
    "model_id",
    "status",
    "initial_capital",
    "currency",
    "capital_mode",
    "capital_evidence",
    "MODEL_HASH",
    "parent",
    "created_at",
    "HYPOTHESIS",
    "PROBLEM_OBSERVED",
    "CHANGE_FROM_PARENT",
    "EXPECTED_IMPROVEMENT",
    "FULL_STRATEGY_SUMMARY",
    "FINAL_RESULT",
    "DECISION",
    "REASON",
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


class ModelStatus(StrEnum):
    CREATED = "CREATED"
    RUNNING = "RUNNING"
    EVALUATED = "EVALUATED"
    PROMOTED = "PROMOTED"
    REJECTED = "REJECTED"
    INCONCLUSIVE = "INCONCLUSIVE"
    INVALIDATED_TECHNICAL = "INVALIDATED_TECHNICAL"
    SUPERSEDED = "SUPERSEDED"


ALLOWED_STATUSES: Final = frozenset(ModelStatus)
ALLOWED_STATUS_TRANSITIONS: Final[dict[ModelStatus, frozenset[ModelStatus]]] = {
    ModelStatus.CREATED: frozenset(
        {ModelStatus.RUNNING, ModelStatus.REJECTED, ModelStatus.SUPERSEDED}
    ),
    ModelStatus.RUNNING: frozenset(
        {ModelStatus.EVALUATED, ModelStatus.INCONCLUSIVE, ModelStatus.INVALIDATED_TECHNICAL}
    ),
    ModelStatus.EVALUATED: frozenset(
        {
            ModelStatus.PROMOTED,
            ModelStatus.REJECTED,
            ModelStatus.INCONCLUSIVE,
            ModelStatus.INVALIDATED_TECHNICAL,
        }
    ),
    ModelStatus.PROMOTED: frozenset({ModelStatus.SUPERSEDED, ModelStatus.INVALIDATED_TECHNICAL}),
    ModelStatus.REJECTED: frozenset(),
    ModelStatus.INCONCLUSIVE: frozenset({ModelStatus.RUNNING, ModelStatus.REJECTED}),
    ModelStatus.INVALIDATED_TECHNICAL: frozenset(),
    ModelStatus.SUPERSEDED: frozenset(),
}


class DuplicateConfigurationError(ValueError):
    pass


class ArtifactConflictError(ValueError):
    pass


class InvalidStatusTransition(ValueError):
    pass


class Hypothesis(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    observation: str = Field(min_length=1)
    hypothesis: str = Field(min_length=1)
    change: str = Field(min_length=1)
    expected_effect: str = Field(min_length=1)
    reason_for_new_model: str = Field(min_length=1)


class ModelLineage(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True)

    parent_model_id: str | None = None
    ancestor_chain: tuple[str, ...] = ()
    change_category: str = Field(min_length=1)
    change_summary: str = Field(min_length=1)
    parent_run_hash: str | None = None
    references: dict[str, Any] = Field(default_factory=dict)


class ModelSpec(BaseModel):
    """Creation-time specification; model is the sole source of decision rules."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    model_id: str | None = None
    pair: str = PAIR
    model: dict[str, Any] = Field(min_length=1)
    hypothesis: Hypothesis
    lineage: ModelLineage
    status: ModelStatus
    model_hash: str | None = Field(
        default=None, validation_alias=AliasChoices("model_hash", "MODEL_HASH")
    )
    scenario_hash: str | None = Field(
        default=None, validation_alias=AliasChoices("scenario_hash", "SCENARIO_HASH")
    )
    run_hash: str | None = Field(
        default=None, validation_alias=AliasChoices("run_hash", "RUN_HASH")
    )
    registered_at: datetime | None = None

    @model_validator(mode="after")
    def validate_spec(self) -> Self:
        if self.pair != PAIR:
            raise ValueError(f"model registry only {PAIR} is accepted")
        if self.status != ModelStatus.CREATED:
            raise ValueError("new model status must be CREATED")
        if self.model_id is not None:
            _validate_model_id(self.model_id)
        if self.registered_at is not None:
            require_utc(self.registered_at)
        return self

    def identity_payload(self) -> dict[str, Any]:
        return {"pair": self.pair, "model": self.model}


class ScenarioSpec(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True)

    scenario: dict[str, Any] = Field(min_length=1)
    scenario_hash: str | None = Field(
        default=None, validation_alias=AliasChoices("scenario_hash", "SCENARIO_HASH")
    )
    label: str | None = None


class BackendSpec(BaseModel):
    """Reproducible backend provenance for every execution."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    backend: Literal["CPU", "CUDA"]
    device: str | None = None
    driver: str | None = None
    runtime: str | None = None
    library: str | None = None
    library_version: str | None = None
    batch_size: int | None = Field(default=None, gt=0)
    benchmark_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_backend_provenance(self) -> Self:
        required = (
            "device",
            "driver",
            "runtime",
            "library",
            "library_version",
            "batch_size",
            "benchmark_hash",
        )
        if self.backend == "CUDA":
            missing = [name for name in required if getattr(self, name) in (None, "")]
            if missing:
                raise ValueError(f"CUDA backend requires: {', '.join(missing)}")
        elif self.batch_size is not None:
            raise ValueError("CPU backend forbids CUDA batch_size")
        return self


class RunSpec(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True)

    scenario_hash: str = Field(
        min_length=1, validation_alias=AliasChoices("scenario_hash", "SCENARIO_HASH")
    )
    dataset_hash: str = Field(min_length=1)
    campaign_snapshot_id: str = Field(min_length=1)
    interval: Any
    code_commit: str = Field(min_length=1)
    technical_revision: str = Field(min_length=1)
    backend: BackendSpec
    initial_capital: Decimal = Field(default=Decimal("100"), gt=0)
    currency: Literal["USDT"] = "USDT"
    capital_mode: Literal["COMPOUNDING"] = "COMPOUNDING"
    run: dict[str, Any] = Field(default_factory=dict)
    run_hash: str | None = Field(
        default=None, validation_alias=AliasChoices("run_hash", "RUN_HASH")
    )

    @model_validator(mode="after")
    def validate_interval(self) -> Self:
        if self.interval is None or self.interval == "" or self.interval == {}:
            raise ValueError("interval is required")
        if self.initial_capital != Decimal("100"):
            raise ValueError(
                "INITIAL_CAPITAL_INVARIANT_VIOLATION: canonical USDCUSDT run "
                "requires initial_capital=100 USDT"
            )
        return self


class EvaluationSpec(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True)

    scenario_hash: str = Field(min_length=1)
    campaign_snapshot_id: str = Field(min_length=1)
    run_hash: str = Field(min_length=1)
    comparison: Any
    criteria: Any
    metrics: dict[str, Any] = Field(default_factory=dict)
    daily: Sequence[Mapping[str, Any]] = ()
    weekly: Sequence[Mapping[str, Any]] = ()
    monthly: Sequence[Mapping[str, Any]] = ()
    hour_of_day: Sequence[Mapping[str, Any]] = ()
    day_of_week: Sequence[Mapping[str, Any]] = ()
    windows: Any = Field(default_factory=dict)
    regimes: Any = Field(default_factory=dict)
    replay: Any = Field(default_factory=dict)
    decision: dict[str, Any] = Field(default_factory=dict)


class ArtifactReferences(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    directory: str
    model_spec: str
    config: str
    hypothesis: str
    lineage: str
    run_manifest: str | None = None
    metrics: str | None = None
    daily: str | None = None
    monthly: str | None = None
    decision: str | None = None


class ModelRegistration(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = REGISTRY_SCHEMA_VERSION
    model_id: str
    pair: str = PAIR
    status: ModelStatus
    model_hash: str = Field(validation_alias=AliasChoices("model_hash", "MODEL_HASH"))
    hypothesis: Hypothesis
    model: dict[str, Any]
    lineage: ModelLineage
    artifacts: ArtifactReferences
    created_at: datetime

    @model_validator(mode="before")
    @classmethod
    def normalize_protocol_hash(cls, value: Any) -> Any:
        if isinstance(value, Mapping):
            normalized = dict(value)
            if "model_hash" not in normalized and "MODEL_HASH" in normalized:
                normalized["model_hash"] = normalized["MODEL_HASH"]
            normalized.pop("MODEL_HASH", None)
            return normalized
        return value

    @property
    def MODEL_HASH(self) -> str:
        return self.model_hash

    def protocol_payload(self) -> dict[str, Any]:
        payload = self.model_dump(mode="json")
        payload["MODEL_HASH"] = payload["model_hash"]
        return payload


def compute_model_hash(model: Mapping[str, Any]) -> str:
    return canonical_hash(dict(model))


def compute_scenario_hash(scenario: Mapping[str, Any]) -> str:
    return canonical_hash(dict(scenario))


def compute_run_hash(
    *,
    model_hash: str,
    scenario_hash: str,
    dataset_hash: str,
    campaign_snapshot_id: str,
    interval: Any,
    code_commit: str,
    technical_revision: str,
    backend: BackendSpec | Mapping[str, Any],
) -> str:
    backend_spec = (
        backend if isinstance(backend, BackendSpec) else BackendSpec.model_validate(backend)
    )
    return canonical_hash(
        {
            "MODEL_HASH": model_hash,
            "SCENARIO_HASH": scenario_hash,
            "dataset_hash": dataset_hash,
            "campaign_snapshot_id": campaign_snapshot_id,
            "interval": interval,
            "code_commit": code_commit,
            "technical_revision": technical_revision,
            "backend": backend_spec.model_dump(mode="json"),
        }
    )


def compute_configuration_hash(spec: ModelSpec) -> str:
    return compute_model_hash(spec.model)


def model_artifact_dir(model_id: str, artifact_root: str | Path = Path("artifacts")) -> Path:
    _validate_model_id(model_id)
    return Path(artifact_root) / PAIR.lower() / "models" / model_id


def required_artifact_paths(
    model_id: str, artifact_root: str | Path = Path("artifacts")
) -> dict[str, Path]:
    directory = model_artifact_dir(model_id, artifact_root)
    return {name: directory / name for name in REQUIRED_CREATION_FILES}


def run_artifact_dir(
    model_id: str, run_hash: str, artifact_root: str | Path = Path("artifacts")
) -> Path:
    if not run_hash:
        raise ValueError("run_hash is required")
    return model_artifact_dir(model_id, artifact_root) / "runs" / run_hash


def run_artifact_paths(
    model_id: str, run_hash: str, artifact_root: str | Path = Path("artifacts")
) -> dict[str, Path]:
    directory = run_artifact_dir(model_id, run_hash, artifact_root)
    return {name: directory / name for name in REQUIRED_EXECUTION_FILES}


def evaluation_artifact_dir(
    model_id: str,
    run_hash: str,
    evaluation_hash: str,
    artifact_root: str | Path = Path("artifacts"),
) -> Path:
    if not evaluation_hash:
        raise ValueError("evaluation_hash is required")
    return run_artifact_dir(model_id, run_hash, artifact_root) / "evaluations" / evaluation_hash


def evaluation_artifact_paths(
    model_id: str,
    run_hash: str,
    evaluation_hash: str,
    artifact_root: str | Path = Path("artifacts"),
) -> dict[str, Path]:
    directory = evaluation_artifact_dir(model_id, run_hash, evaluation_hash, artifact_root)
    return {name: directory / name for name in REQUIRED_EVALUATION_FILES}


class ModelRegistry:
    """Canonical append-only event registry and report projections."""

    def __init__(
        self,
        artifact_root: str | Path = Path("artifacts"),
        report_root: str | Path = Path("reports"),
    ) -> None:
        self.artifact_root = Path(artifact_root)
        self.report_root = Path(report_root)
        self.root = self.artifact_root / PAIR.lower() / "models"
        self.registry_path = self.root / "registry.jsonl"
        self.journal_path = self.registry_path
        self.registry_projection_path = self.report_root / PAIR.lower() / "model-registry.json"
        self.registry_csv_path = self.report_root / PAIR.lower() / "model-registry.csv"
        self.champion_history_path = self.report_root / PAIR.lower() / "champion-history.csv"

    def entries(self) -> tuple[ModelRegistration, ...]:
        return tuple(
            ModelRegistration.model_validate(event["payload"])
            for event in self._events("MODEL_CREATED")
        )

    def get(self, model_id: str) -> ModelRegistration:
        for item in self.entries():
            if item.model_id == model_id:
                return item
        raise KeyError(f"unknown model id {model_id}")

    def register(self, spec: ModelSpec | Mapping[str, Any]) -> ModelRegistration:
        value = _coerce_spec(spec)
        calculated = compute_model_hash(value.model)
        _reject_divergent(value.model_hash, calculated, "MODEL_HASH")
        existing = next((item for item in self.entries() if item.model_hash == calculated), None)
        if existing is not None:
            if value.model_id is not None and value.model_id != existing.model_id:
                raise DuplicateConfigurationError(
                    f"MODEL_HASH already registered as {existing.model_id}"
                )
            self._ensure_creation_artifacts(existing)
            self._project()
            return existing
        expected = _next_model_id(self.entries())
        model_id = value.model_id or expected
        if model_id != expected:
            raise ValueError(f"model ids must be append-only; expected {expected}, got {model_id}")
        directory = model_artifact_dir(model_id, self.artifact_root)
        registration = self._registration(model_id, value, calculated)
        if directory.exists():
            if not _directory_matches_model(directory, calculated):
                raise ArtifactConflictError(f"artifact directory already exists: {directory}")
            self._append_event(
                "MODEL_CREATED", registration.protocol_payload(), registration.created_at
            )
        else:
            self._append_event(
                "MODEL_CREATED", registration.protocol_payload(), registration.created_at
            )
        self._ensure_creation_artifacts(registration)
        self._project()
        return registration

    def append_scenario(
        self,
        model_id: str,
        scenario: ScenarioSpec | Mapping[str, Any],
        *,
        occurred_at: datetime | None = None,
    ) -> dict[str, Any]:
        self.get(model_id)
        value = (
            scenario
            if isinstance(scenario, ScenarioSpec)
            else ScenarioSpec.model_validate(scenario)
        )
        calculated = compute_scenario_hash(value.scenario)
        _reject_divergent(value.scenario_hash, calculated, "SCENARIO_HASH")
        for event in self._events("SCENARIO_REGISTERED"):
            if (
                event["payload"]["model_id"] == model_id
                and event["payload"]["SCENARIO_HASH"] == calculated
            ):
                return event
        event = self._append_event(
            "SCENARIO_REGISTERED",
            {
                "model_id": model_id,
                "SCENARIO_HASH": calculated,
                "scenario": value.scenario,
                "label": value.label,
            },
            occurred_at,
        )
        self._project()
        return event

    def append_run(
        self,
        model_id: str,
        run: RunSpec | Mapping[str, Any],
        *,
        occurred_at: datetime | None = None,
    ) -> dict[str, Any]:
        model = self.get(model_id)
        value = run if isinstance(run, RunSpec) else RunSpec.model_validate(run)
        if not any(
            event["payload"]["model_id"] == model_id
            and event["payload"]["SCENARIO_HASH"] == value.scenario_hash
            for event in self._events("SCENARIO_REGISTERED")
        ):
            raise ValueError("run references an unregistered scenario")
        calculated = compute_run_hash(
            model_hash=model.model_hash,
            scenario_hash=value.scenario_hash,
            dataset_hash=value.dataset_hash,
            campaign_snapshot_id=value.campaign_snapshot_id,
            interval=value.interval,
            code_commit=value.code_commit,
            technical_revision=value.technical_revision,
            backend=value.backend,
        )
        _reject_divergent(value.run_hash, calculated, "RUN_HASH")
        for event in self._events("RUN_REGISTERED"):
            if (
                event["payload"]["model_id"] == model_id
                and event["payload"]["RUN_HASH"] == calculated
            ):
                return event
        payload = {
            "model_id": model_id,
            "MODEL_HASH": model.model_hash,
            "SCENARIO_HASH": value.scenario_hash,
            "RUN_HASH": calculated,
            **value.model_dump(mode="json", exclude={"run_hash", "scenario_hash"}),
        }
        payload["artifact_directory"] = str(
            run_artifact_dir(model_id, calculated, self.artifact_root)
        )
        event = self._append_event("RUN_REGISTERED", payload, occurred_at)
        self._write_run_manifest(model_id, calculated, payload)
        self._project()
        return event

    def retry_m010_numpy_failure(
        self,
        failed_run_hash: str,
        replacement_run: RunSpec,
        reason: str,
        *,
        occurred_at: datetime | None = None,
    ) -> dict[str, Any]:
        """Authorize the single, evidence-bound retry of the failed M010 run.

        This is deliberately narrower than :meth:`transition`: a technical retry
        is valid only for the recorded numpy/Decimal failure and reopens no other
        model or scientific state.
        """
        if not reason or not reason.strip():
            raise ValueError("retry reason is required")
        if not isinstance(replacement_run, RunSpec):
            raise TypeError("replacement_run must be a RunSpec")
        model = self.get("M010")
        if model.model.get("capital_release_protocol") != "OWNER_EXPLORATORY_OVERRIDE_FROZEN_V1":
            raise ValueError("M010 retry requires the frozen capital-release protocol")
        if model.lineage.model_dump(mode="json").get("authorization_class") != (
            "OWNER_EXPLORATORY_OVERRIDE"
        ):
            raise ValueError("M010 retry requires OWNER_EXPLORATORY_OVERRIDE lineage authorization")
        if self.current_status("M010") != ModelStatus.INVALIDATED_TECHNICAL:
            raise InvalidStatusTransition(
                "M010 retry requires current INVALIDATED_TECHNICAL status"
            )

        m010_runs = [
            event
            for event in self._events("RUN_REGISTERED")
            if event["payload"].get("model_id") == "M010"
        ]
        if not m010_runs or m010_runs[-1]["payload"].get("RUN_HASH") != failed_run_hash:
            raise ValueError("failed_run_hash must match the latest M010 run")
        old_payload = m010_runs[-1]["payload"]
        if old_payload.get("MODEL_HASH") != model.model_hash:
            raise ValueError("latest M010 run model hash does not match M010")
        if replacement_run.code_commit == old_payload.get("code_commit"):
            raise ValueError("M010 retry requires a different code_commit")
        if replacement_run.scenario_hash != old_payload.get("SCENARIO_HASH"):
            raise ValueError("M010 retry cannot change scenario_hash")
        for field, old_key in (
            ("dataset_hash", "dataset_hash"),
            ("campaign_snapshot_id", "campaign_snapshot_id"),
            ("interval", "interval"),
            ("backend", "backend"),
            ("initial_capital", "initial_capital"),
            ("currency", "currency"),
            ("capital_mode", "capital_mode"),
            ("run", "run"),
        ):
            old_value = old_payload.get(old_key)
            new_value = getattr(replacement_run, field)
            if field == "backend":
                old_value = BackendSpec.model_validate(old_value).model_dump(mode="json")
                new_value = new_value.model_dump(mode="json")
            elif field == "initial_capital":
                old_value = Decimal(str(old_value))
            if old_value != new_value:
                raise ValueError(f"M010 retry cannot change {field}")

        replacement_hash = compute_run_hash(
            model_hash=model.model_hash,
            scenario_hash=replacement_run.scenario_hash,
            dataset_hash=replacement_run.dataset_hash,
            campaign_snapshot_id=replacement_run.campaign_snapshot_id,
            interval=replacement_run.interval,
            code_commit=replacement_run.code_commit,
            technical_revision=replacement_run.technical_revision,
            backend=replacement_run.backend,
        )
        _reject_divergent(replacement_run.run_hash, replacement_hash, "RUN_HASH")

        failure_path = run_artifact_dir("M010", failed_run_hash, self.artifact_root) / (
            "technical-failure.json"
        )
        if not failure_path.is_file():
            raise ValueError("M010 technical-failure.json is missing")
        try:
            failure = json.loads(failure_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ValueError("M010 technical-failure.json is unreadable") from error
        if (
            failure.get("classification") != "INVALIDATED_TECHNICAL"
            or failure.get("error_type") != "TypeError"
            or failure.get("error") != "conversion from numpy.int64 to Decimal is not supported"
            or failure.get("run_hash") != failed_run_hash
        ):
            raise ValueError("M010 technical-failure evidence does not match numpy failure")
        evaluations = [
            event
            for event in self._events("EVALUATION_RECORDED")
            if event["payload"].get("model_id") == "M010"
        ]
        evaluation_root = (
            run_artifact_dir("M010", failed_run_hash, self.artifact_root) / "evaluations"
        )
        if (
            evaluations
            or (evaluation_root.exists() and any(evaluation_root.iterdir()))
            or any(failure_path.parent.rglob("replay.json"))
        ):
            raise ValueError("M010 retry is forbidden after evaluation artifacts")
        status_events = [
            event
            for event in self._events("STATUS_CHANGED")
            if event["payload"].get("model_id") == "M010"
        ]
        if not status_events or status_events[-1]["payload"] != {
            **status_events[-1]["payload"],
            "from": ModelStatus.RUNNING.value,
            "to": ModelStatus.INVALIDATED_TECHNICAL.value,
        }:
            raise ValueError("latest M010 status must be RUNNING -> INVALIDATED_TECHNICAL")

        old_failure_sha = hashlib.sha256(failure_path.read_bytes()).hexdigest()
        retry_payload = {
            "model_id": "M010",
            "failed_run_hash": failed_run_hash,
            "failure_file_sha256": old_failure_sha,
            "old_code_commit": old_payload.get("code_commit"),
            "new_code_commit": replacement_run.code_commit,
            "replacement_run_hash": replacement_hash,
            "reason": reason,
            "authorization": "OWNER_EXPLORATORY_OVERRIDE",
        }
        self._append_event("TECHNICAL_RETRY_AUTHORIZED", retry_payload, occurred_at)
        run_event = self.append_run("M010", replacement_run, occurred_at=occurred_at)
        self._append_event(
            "STATUS_CHANGED",
            {
                "model_id": "M010",
                "from": ModelStatus.INVALIDATED_TECHNICAL.value,
                "to": ModelStatus.RUNNING.value,
                "reason": reason,
                "retry_run_hash": run_event["payload"]["RUN_HASH"],
            },
            occurred_at,
        )
        self._project()
        return run_event

    def append_evaluation(
        self,
        model_id: str,
        evaluation: EvaluationSpec | Mapping[str, Any],
        *,
        occurred_at: datetime | None = None,
    ) -> dict[str, Any]:
        self.get(model_id)
        value = (
            evaluation
            if isinstance(evaluation, EvaluationSpec)
            else EvaluationSpec.model_validate(evaluation)
        )
        run_event = next(
            (
                event
                for event in self._events("RUN_REGISTERED")
                if event["payload"]["model_id"] == model_id
                and event["payload"]["RUN_HASH"] == value.run_hash
            ),
            None,
        )
        if run_event is None:
            raise ValueError("evaluation references an unregistered run")
        run_payload = run_event["payload"]
        if value.scenario_hash != run_payload["SCENARIO_HASH"]:
            raise ValueError("evaluation scenario does not match run")
        if value.campaign_snapshot_id != run_payload["campaign_snapshot_id"]:
            raise ValueError("evaluation snapshot does not match run")
        decision = {
            **value.decision,
            "scenario_hash": value.scenario_hash,
            "campaign_snapshot_id": value.campaign_snapshot_id,
            "run_hash": value.run_hash,
            "comparison": value.comparison,
            "criteria": value.criteria,
        }
        evidence_hash = canonical_hash(
            {
                "metrics": value.metrics,
                "daily": value.daily,
                "weekly": value.weekly,
                "monthly": value.monthly,
                "hour_of_day": value.hour_of_day,
                "day_of_week": value.day_of_week,
                "windows": value.windows,
                "regimes": value.regimes,
                "replay": value.replay,
                "decision": decision,
            }
        )
        payload = {
            "model_id": model_id,
            "scenario_hash": value.scenario_hash,
            "campaign_snapshot_id": value.campaign_snapshot_id,
            "run_hash": value.run_hash,
            "comparison": value.comparison,
            "criteria": value.criteria,
            "metrics": value.metrics,
            "decision": decision,
            "EVIDENCE_HASH": evidence_hash,
        }
        evaluation_hash = canonical_hash(payload)
        payload["EVALUATION_HASH"] = evaluation_hash
        for event in self._events("EVALUATION_RECORDED"):
            if event["payload"] == payload:
                return event
        payload["artifact_directory"] = str(
            evaluation_artifact_dir(model_id, value.run_hash, evaluation_hash, self.artifact_root)
        )
        event = self._append_event("EVALUATION_RECORDED", payload, occurred_at)
        self._write_evaluation_artifacts(model_id, value, decision, evaluation_hash)
        self._project()
        return event

    def transition(
        self,
        model_id: str,
        status: ModelStatus | str,
        *,
        reason: str,
        occurred_at: datetime | None = None,
    ) -> dict[str, Any]:
        current = self.current_status(model_id)
        target = ModelStatus(status)
        if target == ModelStatus.PROMOTED:
            raise InvalidStatusTransition("PROMOTED requires promote() decision references")
        if target not in ALLOWED_STATUS_TRANSITIONS[current]:
            raise InvalidStatusTransition(f"cannot transition {model_id}: {current} -> {target}")
        event = self._append_event(
            "STATUS_CHANGED",
            {"model_id": model_id, "from": current.value, "to": target.value, "reason": reason},
            occurred_at,
        )
        self._project()
        return event

    def current_status(self, model_id: str) -> ModelStatus:
        current = self.get(model_id).status
        for event in self._events("STATUS_CHANGED", "PROMOTION_RECORDED"):
            payload = event["payload"]
            if payload.get("model_id") == model_id and "to" in payload:
                current = ModelStatus(payload["to"])
        return current

    def promote(
        self,
        model_id: str,
        decision: Mapping[str, Any],
        *,
        occurred_at: datetime | None = None,
    ) -> dict[str, Any]:
        required = ("scenario_hash", "campaign_snapshot_id", "run_hash", "comparison", "criteria")
        missing = [key for key in required if key not in decision]
        if missing:
            raise ValueError(f"promotion decision missing: {', '.join(missing)}")
        if self.current_status(model_id) != ModelStatus.EVALUATED:
            raise InvalidStatusTransition(f"only EVALUATED models can be promoted: {model_id}")
        run_event = next(
            (
                event
                for event in self._events("RUN_REGISTERED")
                if event["payload"]["model_id"] == model_id
                and event["payload"]["RUN_HASH"] == decision["run_hash"]
            ),
            None,
        )
        if run_event is None:
            raise ValueError("promotion references an unregistered run")
        run_payload = run_event["payload"]
        if decision["scenario_hash"] != run_payload["SCENARIO_HASH"]:
            raise ValueError("promotion scenario does not match run")
        if decision["campaign_snapshot_id"] != run_payload["campaign_snapshot_id"]:
            raise ValueError("promotion snapshot does not match run")
        prior = self.champion()
        if prior is not None and prior["model_id"] == model_id:
            raise InvalidStatusTransition(f"model already is the champion: {model_id}")
        if prior is not None:
            self._append_event(
                "STATUS_CHANGED",
                {
                    "model_id": prior["model_id"],
                    "from": ModelStatus.PROMOTED.value,
                    "to": ModelStatus.SUPERSEDED.value,
                    "reason": f"superseded by {model_id}",
                },
                occurred_at,
            )
        payload = {
            "model_id": model_id,
            "to": ModelStatus.PROMOTED.value,
            "decision": dict(decision),
            "previous_model_id": None if prior is None else prior["model_id"],
        }
        event = self._append_event("PROMOTION_RECORDED", payload, occurred_at)
        self._append_event("CHAMPION_RECORDED", payload, occurred_at)
        self._project()
        return event

    def champion(self) -> dict[str, Any] | None:
        candidates = [event["payload"] for event in self._events("CHAMPION_RECORDED")]
        for candidate in reversed(candidates):
            model_id = str(candidate["model_id"])
            if self.current_status(model_id) == ModelStatus.PROMOTED:
                return dict(candidate)
        return None

    def journal(self) -> tuple[dict[str, Any], ...]:
        return _read_jsonl(self.registry_path)

    def _registration(self, model_id: str, spec: ModelSpec, model_hash: str) -> ModelRegistration:
        lineage = spec.lineage
        if lineage.parent_model_id is None:
            if lineage.ancestor_chain:
                raise ValueError("ancestor_chain requires parent_model_id")
        else:
            _validate_model_id(lineage.parent_model_id)
            parent = next(
                (item for item in self.entries() if item.model_id == lineage.parent_model_id),
                None,
            )
            if parent is None:
                raise ValueError(f"unknown parent model: {lineage.parent_model_id}")
            expected_chain = (*parent.lineage.ancestor_chain, parent.model_id)
            if lineage.ancestor_chain != expected_chain:
                raise ValueError("ancestor_chain must equal parent ancestors followed by parent")
        if len(set(lineage.ancestor_chain)) != len(lineage.ancestor_chain):
            raise ValueError("ancestor_chain cannot contain duplicates")
        for ancestor in lineage.ancestor_chain:
            _validate_model_id(ancestor)
            if not any(item.model_id == ancestor for item in self.entries()):
                raise ValueError(f"unknown ancestor model: {ancestor}")
        directory = model_artifact_dir(model_id, self.artifact_root)
        return ModelRegistration(
            model_id=model_id,
            status=spec.status,
            model_hash=model_hash,
            hypothesis=spec.hypothesis,
            model=spec.model,
            lineage=spec.lineage,
            artifacts=ArtifactReferences(
                directory=str(directory),
                model_spec=str(directory / "MODEL_SPEC.md"),
                config=str(directory / "config.json"),
                hypothesis=str(directory / "hypothesis.json"),
                lineage=str(directory / "lineage.json"),
            ),
            created_at=spec.registered_at or datetime.now(UTC),
        )

    def _ensure_creation_artifacts(self, registration: ModelRegistration) -> None:
        directory = Path(registration.artifacts.directory)
        directory.mkdir(parents=True, exist_ok=True)
        files = {
            "MODEL_SPEC.md": (
                f"# {registration.model_id}\n\n"
                f"MODEL_ID: `{registration.model_id}`\n"
                f"PARENT: `{registration.lineage.parent_model_id or 'NONE'}`\n"
                f"CREATED_AT: `{registration.created_at.isoformat()}`\n"
                f"HYPOTHESIS: {registration.hypothesis.hypothesis}\n"
                f"PROBLEM_OBSERVED: {registration.hypothesis.observation}\n"
                f"CHANGE_FROM_PARENT: {registration.hypothesis.change}\n"
                f"EXPECTED_IMPROVEMENT: {registration.hypothesis.expected_effect}\n"
                "FULL_STRATEGY_SUMMARY: "
                f"`{json.dumps(registration.model, sort_keys=True, default=str)}`\n"
                "FINAL_RESULT: pending\n"
                "DECISION: pending\n"
                f"REASON: {registration.hypothesis.reason_for_new_model}\n"
            ),
            "config.json": _json_text(
                {"MODEL_HASH": registration.model_hash, "model": registration.model}
            ),
            "hypothesis.json": _json_text(registration.hypothesis.model_dump(mode="json")),
            "lineage.json": _json_text(registration.lineage.model_dump(mode="json")),
        }
        for name, content in files.items():
            path = directory / name
            if not path.exists():
                path.write_text(content, encoding="utf-8")

    def _write_run_manifest(self, model_id: str, run_hash: str, payload: Mapping[str, Any]) -> None:
        directory = run_artifact_dir(model_id, run_hash, self.artifact_root)
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "run-manifest.json").write_text(_json_text(dict(payload)), encoding="utf-8")

    def _write_evaluation_artifacts(
        self,
        model_id: str,
        evaluation: EvaluationSpec,
        decision: Mapping[str, Any],
        evaluation_hash: str,
    ) -> None:
        directory = evaluation_artifact_dir(
            model_id, evaluation.run_hash, evaluation_hash, self.artifact_root
        )
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "metrics.json").write_text(_json_text(evaluation.metrics), encoding="utf-8")
        _write_csv(directory / "daily.csv", evaluation.daily)
        _write_csv(directory / "weekly.csv", evaluation.weekly)
        _write_csv(directory / "monthly.csv", evaluation.monthly)
        _write_csv(directory / "hour-of-day.csv", evaluation.hour_of_day)
        _write_csv(directory / "day-of-week.csv", evaluation.day_of_week)
        (directory / "windows.json").write_text(_json_text(evaluation.windows), encoding="utf-8")
        (directory / "regimes.json").write_text(_json_text(evaluation.regimes), encoding="utf-8")
        (directory / "replay.json").write_text(_json_text(evaluation.replay), encoding="utf-8")
        (directory / "decision.json").write_text(_json_text(dict(decision)), encoding="utf-8")

    def _append_event(
        self, event_type: str, payload: Mapping[str, Any], occurred_at: datetime | None
    ) -> dict[str, Any]:
        event = _event(event_type, payload, occurred_at)
        _append_jsonl(self.registry_path, event)
        return event

    def _events(self, *event_types: str) -> tuple[dict[str, Any], ...]:
        return tuple(
            event
            for event in _read_jsonl(self.registry_path)
            if event.get("event_type") in event_types
        )

    def _project(self) -> None:
        events = self.journal()
        models = [item.model_dump(mode="json") for item in self.entries()]
        model_projections = [
            {
                **model,
                "status": self.current_status(model["model_id"]).value,
                **_capital_fields(model["model_id"], events),
                **_productivity_fields(model["model_id"], events),
            }
            for model in models
        ]
        projection = {
            "schema_version": REGISTRY_SCHEMA_VERSION,
            "pair": PAIR,
            "models": model_projections,
            "events": events,
        }
        self.registry_projection_path.parent.mkdir(parents=True, exist_ok=True)
        self.registry_projection_path.write_text(_json_text(projection), encoding="utf-8")
        rows = [
            {
                "model_id": model["model_id"],
                "status": self.current_status(model["model_id"]).value,
                **_capital_fields(model["model_id"], events),
                "MODEL_HASH": model["model_hash"],
                "parent": model["lineage"].get("parent_model_id"),
                "created_at": model["created_at"],
                "HYPOTHESIS": model["hypothesis"]["hypothesis"],
                "PROBLEM_OBSERVED": model["hypothesis"]["observation"],
                "CHANGE_FROM_PARENT": model["hypothesis"]["change"],
                "EXPECTED_IMPROVEMENT": model["hypothesis"]["expected_effect"],
                "FULL_STRATEGY_SUMMARY": _json_text(model["model"]).strip(),
                "FINAL_RESULT": _latest_evaluation_result(model["model_id"], events),
                "DECISION": _latest_evaluation_decision(model["model_id"], events),
                "REASON": model["hypothesis"]["reason_for_new_model"],
                **_productivity_fields(model["model_id"], events),
            }
            for model in models
        ]
        _write_csv(self.registry_csv_path, rows, fields=PROJECTION_FIELDS)
        _write_csv(
            self.champion_history_path,
            [event["payload"] for event in self._events("CHAMPION_RECORDED")],
        )


def register_model(
    spec: ModelSpec | Mapping[str, Any],
    *,
    artifact_root: str | Path = Path("artifacts"),
    report_root: str | Path = Path("reports"),
) -> ModelRegistration:
    return ModelRegistry(artifact_root, report_root).register(spec)


ExperimentSpec = ModelSpec
ExperimentRegistry = ModelRegistry
RegistryRecord = ModelRegistration


def _coerce_spec(spec: ModelSpec | Mapping[str, Any]) -> ModelSpec:
    return spec if isinstance(spec, ModelSpec) else ModelSpec.model_validate(dict(spec))


def _validate_model_id(model_id: str) -> None:
    if MODEL_ID_PATTERN.fullmatch(model_id) is None:
        raise ValueError("model_id must use the Mxxx format")


def _next_model_id(records: Sequence[ModelRegistration]) -> str:
    numbers = [
        int(item.model_id[1:]) for item in records if MODEL_ID_PATTERN.fullmatch(item.model_id)
    ]
    return f"M{max(numbers, default=0) + 1:03d}"


def _reject_divergent(caller_hash: str | None, calculated: str, name: str) -> None:
    if caller_hash is not None and caller_hash != calculated:
        raise ValueError(f"caller-provided {name} diverges from canonical hash")


def _directory_model_hash(directory: Path) -> str | None:
    path = directory / "config.json"
    if not path.exists():
        return None
    try:
        return str(json.loads(path.read_text(encoding="utf-8"))["MODEL_HASH"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None


def _directory_matches_model(directory: Path, model_hash: str) -> bool:
    if _directory_model_hash(directory) == model_hash:
        return True
    model_spec = directory / "MODEL_SPEC.md"
    return model_spec.exists() and f"MODEL_HASH: `{model_hash}`" in model_spec.read_text(
        encoding="utf-8"
    )


def _event(
    event_type: str, payload: Mapping[str, Any], occurred_at: datetime | None
) -> dict[str, Any]:
    timestamp = occurred_at or datetime.now(UTC)
    require_utc(timestamp)
    return {
        "event_type": event_type,
        "occurred_at": timestamp.astimezone(UTC).isoformat(),
        "payload": dict(payload),
    }


def _append_jsonl(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str) + "\n")


def _read_jsonl(path: Path) -> tuple[dict[str, Any], ...]:
    if not path.exists():
        return ()
    return tuple(
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    )


def _json_text(payload: Any) -> str:
    return json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n"


def _latest_evaluation_result(model_id: str, events: Sequence[Mapping[str, Any]]) -> str | None:
    evaluations = [
        event["payload"]
        for event in events
        if event.get("event_type") == "EVALUATION_RECORDED"
        and event.get("payload", {}).get("model_id") == model_id
    ]
    return _json_text(evaluations[-1]["metrics"]).strip() if evaluations else None


def _latest_evaluation_decision(model_id: str, events: Sequence[Mapping[str, Any]]) -> str | None:
    evaluations = [
        event["payload"]
        for event in events
        if event.get("event_type") == "EVALUATION_RECORDED"
        and event.get("payload", {}).get("model_id") == model_id
    ]
    return _json_text(evaluations[-1]["decision"]).strip() if evaluations else None


_PRODUCTIVITY_FIELDS: Final = (
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


def _productivity_fields(model_id: str, events: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    evaluations = [
        event["payload"]
        for event in events
        if event.get("event_type") == "EVALUATION_RECORDED"
        and event.get("payload", {}).get("model_id") == model_id
    ]
    metrics = evaluations[-1].get("metrics", {}) if evaluations else {}
    fingerprint_value = (
        metrics.get("productivity_fingerprint", {}) if isinstance(metrics, Mapping) else {}
    )
    fingerprint = fingerprint_value if isinstance(fingerprint_value, Mapping) else {}
    return {field: fingerprint.get(field) for field in _PRODUCTIVITY_FIELDS}


def _capital_fields(model_id: str, events: Sequence[Mapping[str, Any]]) -> dict[str, str]:
    runs = [
        event["payload"]
        for event in events
        if event.get("event_type") == "RUN_REGISTERED"
        and event.get("payload", {}).get("model_id") == model_id
    ]
    if not runs:
        return {
            "initial_capital": "100",
            "currency": "USDT",
            "capital_mode": "COMPOUNDING",
            "capital_evidence": "PLANNED_CANONICAL_CONTRACT",
        }
    latest = runs[-1]
    run_hash = latest.get("RUN_HASH")
    scenario_hash = latest.get("SCENARIO_HASH")
    observed: list[Decimal] = []
    for value in (
        latest.get("initial_capital"),
        latest.get("run", {}).get("initial_capital"),
    ):
        if value is not None:
            observed.append(Decimal(str(value)))
    for event in events:
        payload = event.get("payload", {})
        if (
            event.get("event_type") == "SCENARIO_REGISTERED"
            and payload.get("model_id") == model_id
            and payload.get("SCENARIO_HASH") == scenario_hash
        ):
            value = payload.get("scenario", {}).get("initial_quote")
            if value is not None:
                observed.append(Decimal(str(value)))
        if (
            event.get("event_type") == "EVALUATION_RECORDED"
            and payload.get("model_id") == model_id
            and payload.get("run_hash") == run_hash
        ):
            metrics = payload.get("metrics", {})
            for key in ("initial_capital", "initial_quote"):
                value = metrics.get(key)
                if value is not None:
                    observed.append(Decimal(str(value)))
    if not observed:
        return {
            "initial_capital": "UNKNOWN",
            "currency": str(latest.get("currency", "USDT")),
            "capital_mode": str(latest.get("capital_mode", "COMPOUNDING")),
            "capital_evidence": "MISSING_EXECUTION_EVIDENCE",
        }
    if any(value != Decimal("100") for value in observed):
        raise ValueError(
            "INITIAL_CAPITAL_INVARIANT_VIOLATION: registered execution evidence "
            f"for {model_id} does not start from 100 USDT"
        )
    return {
        "initial_capital": "100",
        "currency": str(latest.get("currency", "USDT")),
        "capital_mode": str(latest.get("capital_mode", "COMPOUNDING")),
        "capital_evidence": (
            "RUN_MANIFEST"
            if latest.get("initial_capital") is not None
            else "HISTORICAL_LINKED_EVIDENCE"
        ),
    }


def _write_csv(
    path: Path, rows: Sequence[Mapping[str, Any]], *, fields: Sequence[str] | None = None
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    materialized = [dict(row) for row in rows]
    csv_fields = (
        list(fields) if fields is not None else sorted({key for row in materialized for key in row})
    )
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=csv_fields)
        if csv_fields:
            writer.writeheader()
            writer.writerows(materialized)


__all__ = [
    "ALLOWED_STATUSES",
    "ALLOWED_STATUS_TRANSITIONS",
    "PAIR",
    "REQUIRED_CREATION_FILES",
    "REQUIRED_EVALUATION_FILES",
    "REQUIRED_EXECUTION_FILES",
    "ArtifactConflictError",
    "ArtifactReferences",
    "BackendSpec",
    "DuplicateConfigurationError",
    "EvaluationSpec",
    "ExperimentRegistry",
    "ExperimentSpec",
    "Hypothesis",
    "InvalidStatusTransition",
    "ModelLineage",
    "ModelRegistration",
    "ModelRegistry",
    "ModelSpec",
    "ModelStatus",
    "RegistryRecord",
    "RunSpec",
    "ScenarioSpec",
    "compute_configuration_hash",
    "compute_model_hash",
    "compute_run_hash",
    "compute_scenario_hash",
    "evaluation_artifact_dir",
    "evaluation_artifact_paths",
    "model_artifact_dir",
    "register_model",
    "required_artifact_paths",
    "run_artifact_dir",
    "run_artifact_paths",
]
