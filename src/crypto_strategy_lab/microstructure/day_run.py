"""Fail-closed local orchestration for one frozen microstructure campaign.

The runner deliberately owns orchestration only.  It does not select a window,
download market data, create a model, or alter a strategy after seeing data.  The
only currently supported engine is the repository's deterministic CPU passive
L2/trade counterfactual simulator.  A new engine must be integrated explicitly rather than silently
changing the meaning of an existing campaign.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from collections import Counter
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager, suppress
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from itertools import pairwise
from pathlib import Path
from typing import Any, Literal, cast

import yaml
from pydantic import ValidationError

from crypto_strategy_lab.domain import canonical_hash, require_utc
from crypto_strategy_lab.microstructure.execution import (
    MicrostructureRunResult,
    PassiveExecutionSimulator,
)
from crypto_strategy_lab.microstructure.models import (
    BookDeltaEvent,
    BookSnapshotEvent,
    CancelRequest,
    FeedGapEvent,
    LiquidityRole,
    MarketEvent,
    OrderStatus,
    RiskHaltEvent,
    S0Config,
    Side,
    TradeEvent,
)
from crypto_strategy_lab.microstructure.oracle_acceleration import scan_oracle

STATUS_PATH = "RUN_STATUS.json"
SUMMARY_NAME = "SUMMARY.json"
AUDIT_NAME = "AUDIT.json"
JOB_SCHEMA = "crypto-lab-day-job-v1"
SPEC_SCHEMA = "crypto-lab-day-model-spec-v1"
TAPE_MANIFEST_SCHEMA = "crypto-lab-day-tape-manifest-v1"
RAW_EVENT_SOURCE_SCHEMA = "crypto-lab-day-raw-events-v1"
COUNTERFACTUAL_L2_QUEUE_ENVELOPE: Literal["COUNTERFACTUAL_L2_QUEUE_ENVELOPE"] = (
    "COUNTERFACTUAL_L2_QUEUE_ENVELOPE"
)
PUBLIC_L2_QUEUE_LIMITATION = (
    "INCONCLUSIVE_PUBLIC_L2_QUEUE_ESTIMATE_UNKNOWN_CAPTURE_ARRIVAL_AND_LATENCY_"
    "NO_OWN_ORDER_PRIORITY_OR_VENUE_RECEIPT"
)
_MODEL_ID = re.compile(r"^M(?P<number>[0-9]{3,})$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_GIT_COMMIT = re.compile(r"^[0-9a-f]{40,64}$")
_SCENARIO_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")


class DayRunError(ValueError):
    """Base class for expected day-run failures."""


class DayRunPreflightError(DayRunError):
    """Raised before a campaign can claim its one permitted execution."""


@dataclass(frozen=True)
class CampaignWindow:
    start: datetime
    end: datetime


@dataclass(frozen=True)
class Scenario:
    name: str
    fee_bps: Decimal
    mode: Literal["single", "parallel"]


@dataclass(frozen=True)
class OraclePlan:
    backend: Literal["cpu", "gpu", "auto"]
    candidates: tuple[tuple[int, int], ...]


@dataclass(frozen=True)
class Gates:
    min_l2_inferred_cycles: int
    max_negative_cycles: int
    capital_conservation: bool


@dataclass(frozen=True)
class CurrentStateBinding:
    """Exact authority values which must match CURRENT_STATE before a run."""

    next_campaign_status: str
    next_campaign_model_hash: str
    next_campaign_window: str


@dataclass(frozen=True)
class DayJob:
    day: str
    model_id: str
    parent: str
    windows: tuple[CampaignWindow, ...]
    scenarios: tuple[Scenario, ...]
    oracle: OraclePlan
    engine: Literal["causal_cpu"]
    gates: Gates
    output_dir: Path
    terminal_mark_max_age_seconds: int
    max_l2_update_age_seconds: int
    model_spec_sha256: str
    execution_authorized: bool
    state_binding: CurrentStateBinding
    contract_sha256: str


@dataclass(frozen=True)
class FrozenModelSpec:
    model_id: str
    parent: str
    identity: str
    classification: str
    status: str
    authorization_status: str
    symbol: str
    base_asset: str
    quote_asset: str
    evidence_class: Literal["COUNTERFACTUAL_L2_QUEUE_ENVELOPE"]
    execution_authorized: bool
    tape_path: Path
    tape_sha256: str | None
    tape_manifest_path: Path | None
    tape_manifest_sha256: str | None
    strategy_sha256: str
    job_contract_sha256: str
    execution_source_commit: str
    fee_provenance: TemporalProvenance | None
    rule_provenance: TemporalProvenance | None
    s0_config: S0Config
    sha256: str


@dataclass(frozen=True)
class DayRunOutcome:
    """Locations and immutable identity emitted by a completed campaign."""

    model_id: str
    status: str
    summary_path: Path
    audit_path: Path
    status_path: Path


@dataclass(frozen=True)
class ReportPaths:
    summary: Path
    audit: Path
    oracle: Path | None
    scenarios: tuple[Path, ...]


@dataclass(frozen=True)
class SourceBinding:
    commit: str
    branch: str
    source_tree_clean: bool


@dataclass(frozen=True)
class TemporalProvenance:
    """A locally hash-bound venue record valid throughout a frozen window.

    This is intentionally a narrow serialization adapter for the legacy S0
    day-run, not a second general venue-eligibility registry.  It requires the
    M034 historical-evidence properties and adds the S0-specific LIMIT_MAKER,
    raw-byte, and one-grid constraints; broader routing continues to use the
    canonical M034 venue models/registries.
    """

    record_id: str
    path: Path
    sha256: str
    venue: str
    symbol: str
    valid_from: datetime
    valid_until: datetime
    acquired_at: datetime
    counterfactual_sensitivity_bps: tuple[Decimal, ...] = ()
    rules: VenueRules | None = None


@dataclass(frozen=True)
class VenueRules:
    min_price: Decimal
    max_price: Decimal
    tick_size: Decimal
    min_quantity: Decimal
    max_quantity: Decimal
    step_size: Decimal
    min_notional: Decimal
    max_notional: Decimal | None


@dataclass(frozen=True)
class ScenarioExecution:
    scenario: Scenario
    config: S0Config
    result: MicrostructureRunResult
    metrics: dict[str, Any]


@dataclass(frozen=True)
class TerminalMark:
    """The reconstructed L2 mark and the source timestamp that makes it auditable."""

    mid: Decimal | None
    l2_timestamp: datetime | None


@dataclass(frozen=True)
class ClaimValidation:
    """Inputs re-read while the status claim lock is held."""

    source_binding: SourceBinding
    tape: Mapping[str, Any]
    oracle_payload: dict[str, Any] | None


def run_day_campaign(root: Path, campaign: Path) -> DayRunOutcome:
    """Run exactly one authorized, locally available campaign.

    Preflight failures never claim an execution.  Once preflight has succeeded,
    ``RUN_STATUS.json`` is created exclusively before the first event; a crash or
    post-claim failure therefore remains visible and cannot be rerun accidentally.
    """

    repository = root.resolve()
    campaign_dir = _campaign_directory(repository, campaign)
    status_path = campaign_dir / STATUS_PATH
    started_at = _now()
    job: DayJob | None = None
    spec: FrozenModelSpec | None = None
    source_binding: SourceBinding | None = None
    oracle_payload: dict[str, Any] | None = None

    _assert_prior_status_is_recoverable(status_path)
    finalization_started = False
    current_state_record_appended = False
    finalizing_status: dict[str, Any] | None = None
    try:
        job = _read_job(campaign_dir / "job.yaml", repository)
        spec = _read_model_spec(campaign_dir / "model_spec.json", repository)
        _validate_frozen_contracts(campaign_dir, job, spec)
        _validate_job_matches_spec(job, spec)
        _validate_campaign_day(campaign_dir, job)
        _validate_current_state(repository, job, spec)
        _validate_unique_campaign_identity(repository, campaign_dir, spec.model_id)
        _validate_output_directory(repository, job.output_dir)
        source_binding = _validate_execution_source(repository, spec)
        _validate_oracle_backend(job)
        tape_path = _resolve_under_root(repository, spec.tape_path, "execution.tape_path")
        tape: Mapping[str, Any] = _read_tape(repository, tape_path, spec, job)
        # Oracle calculation is advisory, but its inputs and requested backend still
        # belong to preflight.  A malformed tape or unavailable explicit backend must
        # not consume an otherwise unexecuted model identity.
        oracle_payload = _run_oracle(job, spec, tape)
    except DayRunPreflightError as error:
        _record_preflight_rejection(
            status_path,
            campaign_dir,
            error,
            started_at,
            model_id=job.model_id if job is not None else None,
        )
        raise

    claim_payload = {
        "schema_version": "crypto-lab-day-run-status-v1",
        "state": "RUNNING",
        "model_id": spec.model_id,
        "day": job.day,
        "identity": spec.identity,
        "evidence_class": spec.evidence_class,
        "economic_eligibility": PUBLIC_L2_QUEUE_LIMITATION,
        "started_at": started_at,
        "campaign": _relative(repository, campaign_dir),
        "rerun_allowed": False,
    }
    try:
        claim, final_inputs = _claim_execution(
            status_path,
            claim_payload,
            verifier=lambda: _revalidate_before_claim(
                repository,
                campaign_dir,
                job,
                spec,
            ),
        )
    except DayRunPreflightError as error:
        _record_preflight_rejection(
            status_path,
            campaign_dir,
            error,
            started_at,
            model_id=job.model_id,
        )
        raise
    source_binding = final_inputs.source_binding
    tape = final_inputs.tape
    oracle_payload = final_inputs.oracle_payload

    try:
        executions = _run_scenarios(job, spec, tape)
        scenario_payloads = [execution.metrics for execution in executions]
        gates = _evaluate_gates(job.gates, scenario_payloads)
        report_paths = _write_reports(
            repository,
            job,
            spec,
            tape,
            executions,
            gates,
            oracle_payload,
            campaign_dir,
            source_binding,
        )
        completed_at = _now()
        final_state = (
            "COMPLETED_GATE_FAIL" if gates["verdict"] == "FAIL" else "COMPLETED_INCONCLUSIVE"
        )
        final_status = {
            **claim,
            "state": final_state,
            "completed_at": completed_at,
            "verdict": gates["verdict"],
            "summary_path": _relative(repository, report_paths.summary),
            "audit_path": _relative(repository, report_paths.audit),
            "oracle_path": (
                None if report_paths.oracle is None else _relative(repository, report_paths.oracle)
            ),
            "scenario_evidence_paths": [
                _relative(repository, path) for path in report_paths.scenarios
            ],
        }
        # There is no cross-file atomic transaction for reports, status, and
        # CURRENT_STATE. Persist an explicit finalization phase before appending
        # authority so a filesystem failure is reviewable rather than resembling
        # a normal post-claim failure or a completed rerun invitation.
        finalizing_status = {
            **final_status,
            "state": "FINALIZING_CURRENT_STATE",
            "intended_final_state": final_state,
            "current_state_record_appended": False,
        }
        _write_json_atomic(status_path, finalizing_status)
        finalization_started = True
        _append_current_state_record(repository, job, spec, final_status)
        current_state_record_appended = True
        _write_json_atomic(status_path, final_status)
        return DayRunOutcome(
            model_id=spec.model_id,
            status=final_state,
            summary_path=report_paths.summary,
            audit_path=report_paths.audit,
            status_path=status_path,
        )
    except BaseException as error:
        failure_state = (
            "FINALIZATION_INCONSISTENT_REQUIRES_OPERATOR_REVIEW"
            if current_state_record_appended
            else "FAILED_AFTER_CLAIM"
        )
        _write_json_atomic(
            status_path,
            {
                **(finalizing_status if finalization_started and finalizing_status else claim),
                "state": failure_state,
                "failed_at": _now(),
                "error_type": type(error).__name__,
                "error": str(error),
                "current_state_record_appended": current_state_record_appended,
                "rerun_allowed": False,
            },
        )
        raise


def _campaign_directory(root: Path, campaign: Path) -> Path:
    path = campaign if campaign.is_absolute() else root / campaign
    resolved = path.resolve()
    campaigns_root = (root / "campaigns").resolve()
    if not resolved.is_dir() or not _is_relative_to(resolved, campaigns_root):
        raise DayRunPreflightError("CAMPAIGN_DIRECTORY_MUST_EXIST_UNDER_CAMPAIGNS")
    return resolved


def _read_job(path: Path, root: Path) -> DayJob:
    raw = _yaml_mapping(path, "job.yaml")
    if raw.get("schema_version", JOB_SCHEMA) != JOB_SCHEMA:
        raise DayRunPreflightError("DAY_JOB_SCHEMA_UNSUPPORTED")
    day = _string(raw, "day")
    _parse_day(day)
    model_id = _model_id(raw, "model_id")
    parent = _model_id(raw, "parent")
    windows = _windows(raw)
    scenarios_raw = _sequence(raw, "scenarios")
    scenarios = tuple(_scenario(item, index) for index, item in enumerate(scenarios_raw))
    if not scenarios:
        raise DayRunPreflightError("DAY_JOB_REQUIRES_SCENARIOS")
    if len({item.name for item in scenarios}) != len(scenarios):
        raise DayRunPreflightError("DAY_JOB_SCENARIO_NAMES_MUST_BE_UNIQUE")
    oracle = _oracle(_mapping(raw, "oracle"))
    engine = _string(raw, "engine")
    if engine != "causal_cpu":
        raise DayRunPreflightError("UNSUPPORTED_DAY_RUN_ENGINE")
    gates = _gates(_mapping(raw, "gates"))
    output_dir = _report_directory(root, _string(raw, "output_dir"))
    terminal_mark_max_age_seconds = _integer(
        raw.get("terminal_mark_max_age_seconds"), "terminal_mark_max_age_seconds"
    )
    if terminal_mark_max_age_seconds < 0:
        raise DayRunPreflightError("TERMINAL_MARK_MAX_AGE_MUST_BE_NON_NEGATIVE")
    max_l2_update_age_seconds = _integer(
        raw.get("max_l2_update_age_seconds"), "max_l2_update_age_seconds"
    )
    if max_l2_update_age_seconds <= 0:
        raise DayRunPreflightError("MAX_L2_UPDATE_AGE_MUST_BE_POSITIVE")
    state_binding = _current_state_binding(_mapping(raw, "current_state_binding"))
    contract = {key: value for key, value in raw.items() if key != "model_spec_sha256"}
    return DayJob(
        day=day,
        model_id=model_id,
        parent=parent,
        windows=windows,
        scenarios=scenarios,
        oracle=oracle,
        engine="causal_cpu",
        gates=gates,
        output_dir=output_dir,
        terminal_mark_max_age_seconds=terminal_mark_max_age_seconds,
        max_l2_update_age_seconds=max_l2_update_age_seconds,
        model_spec_sha256=_sha256_value(_string(raw, "model_spec_sha256"), "model_spec_sha256"),
        execution_authorized=_bool(raw, "execution_authorized"),
        state_binding=state_binding,
        contract_sha256=canonical_hash(contract),
    )


def _read_model_spec(path: Path, root: Path) -> FrozenModelSpec:
    raw = _json_mapping(path, "model_spec.json")
    if raw.get("schema_version") != SPEC_SCHEMA:
        raise DayRunPreflightError("MODEL_SPEC_SCHEMA_UNSUPPORTED")
    supplied_hash = _sha256_value(_string(raw, "spec_sha256"), "spec_sha256")
    unhashed = {key: value for key, value in raw.items() if key != "spec_sha256"}
    if canonical_hash(unhashed) != supplied_hash:
        raise DayRunPreflightError("MODEL_SPEC_HASH_MISMATCH")
    model_id = _model_id(raw, "model_id")
    parent = _model_id(raw, "parent_model_id")
    identity = _string(raw, "identity")
    if not identity.startswith(f"{model_id}_"):
        raise DayRunPreflightError("MODEL_SPEC_IDENTITY_MUST_BEGIN_WITH_MODEL_ID")
    status = _string(raw, "status")
    authorization = _mapping(raw, "authorization")
    authorization_status = _string(authorization, "status")
    symbol = _string(raw, "symbol").upper()
    if symbol != "USDCUSDT":
        raise DayRunPreflightError("DAY_RUN_ACCEPTS_ONLY_ACTIVE_USDCUSDT_SYMBOL")
    if _string(raw, "venue") != "BINANCE_SPOT":
        raise DayRunPreflightError("DAY_RUN_REQUIRES_BINANCE_SPOT_VENUE")
    _validate_invariants(_mapping(raw, "invariants"))
    execution = _mapping(raw, "execution")
    if _string(execution, "engine") != "causal_cpu":
        raise DayRunPreflightError("MODEL_SPEC_ENGINE_MISMATCH")
    evidence_class = _string(execution, "evidence_class")
    if evidence_class != COUNTERFACTUAL_L2_QUEUE_ENVELOPE:
        raise DayRunPreflightError("DAY_RUN_REQUIRES_COUNTERFACTUAL_L2_QUEUE_EVIDENCE_CLASS")
    tape_path = Path(_string(execution, "tape_path"))
    if tape_path.is_absolute():
        raise DayRunPreflightError("MODEL_SPEC_TAPE_PATH_MUST_BE_RELATIVE")
    tape_manifest_path = _optional_relative_path(
        execution.get("tape_manifest_path"), "execution.tape_manifest_path"
    )
    asset_mapping = _mapping(execution, "asset_mapping")
    base_asset = _string(asset_mapping, "base_asset").upper()
    quote_asset = _string(asset_mapping, "quote_asset").upper()
    if (base_asset, quote_asset) != ("USDC", "USDT"):
        raise DayRunPreflightError("DAY_RUN_REQUIRES_EXPLICIT_USDC_USDT_ASSET_MAPPING")
    if _string(asset_mapping, "adapter") != "legacy_s0_quote_base_v1":
        raise DayRunPreflightError("DAY_RUN_ASSET_ADAPTER_UNSUPPORTED")
    config_raw = _mapping(execution, "s0_config")
    _validate_s0_config_mapping(config_raw)
    try:
        config = S0Config.model_validate(config_raw)
    except ValidationError as error:
        raise DayRunPreflightError(f"MODEL_SPEC_S0_CONFIG_INVALID:{error}") from error
    _validate_s0_numeric_contract(config)
    if config.symbol.upper() != symbol:
        raise DayRunPreflightError("MODEL_SPEC_S0_SYMBOL_MISMATCH")
    if config.strategy_id != identity:
        raise DayRunPreflightError("MODEL_SPEC_STRATEGY_IDENTITY_MISMATCH")
    if config.fees.buy_fee_asset.value != "QUOTE" or config.fees.sell_fee_asset.value != "QUOTE":
        raise DayRunPreflightError("DAY_RUN_REQUIRES_QUOTE_DENOMINATED_FEES")
    execution_authorized = _bool(raw, "execution_authorized")
    tape_sha256 = _optional_sha256(execution.get("tape_sha256"), "execution.tape_sha256")
    tape_manifest_sha256 = _optional_sha256(
        execution.get("tape_manifest_sha256"), "execution.tape_manifest_sha256"
    )
    provenance = _mapping(raw, "provenance")
    strategy_sha256 = _sha256_value(
        _string(provenance, "strategy_sha256"), "provenance.strategy_sha256"
    )
    job_contract_sha256 = _sha256_value(
        _string(provenance, "job_contract_sha256"), "provenance.job_contract_sha256"
    )
    execution_source_commit = _string(provenance, "execution_source_commit")
    temporal_provenance = execution.get("temporal_provenance")
    fee_provenance = _read_temporal_provenance(
        root,
        path,
        tape_path,
        tape_manifest_path,
        temporal_provenance,
        "fee",
        symbol,
        config,
        required=execution_authorized,
    )
    rule_provenance = _read_temporal_provenance(
        root,
        path,
        tape_path,
        tape_manifest_path,
        temporal_provenance,
        "rule",
        symbol,
        config,
        required=execution_authorized,
    )
    if execution_authorized and (
        status != "AUTHORIZED"
        or authorization_status != "AUTHORIZED"
        or tape_sha256 is None
        or tape_manifest_path is None
        or tape_manifest_sha256 is None
        or _GIT_COMMIT.fullmatch(execution_source_commit) is None
        or fee_provenance is None
        or rule_provenance is None
    ):
        raise DayRunPreflightError(
            "AUTHORIZED_MODEL_SPEC_REQUIRES_PROVENANCE_SOURCE_AND_TAPE_MANIFEST"
        )
    _resolve_under_root(root, tape_path, "execution.tape_path", require_exists=False)
    if tape_manifest_path is not None:
        _resolve_under_root(
            root,
            tape_manifest_path,
            "execution.tape_manifest_path",
            require_exists=False,
        )
    return FrozenModelSpec(
        model_id=model_id,
        parent=parent,
        identity=identity,
        classification=_string(raw, "classification"),
        status=status,
        authorization_status=authorization_status,
        symbol=symbol,
        base_asset=base_asset,
        quote_asset=quote_asset,
        evidence_class=COUNTERFACTUAL_L2_QUEUE_ENVELOPE,
        execution_authorized=execution_authorized,
        tape_path=tape_path,
        tape_sha256=tape_sha256,
        tape_manifest_path=tape_manifest_path,
        tape_manifest_sha256=tape_manifest_sha256,
        strategy_sha256=strategy_sha256,
        job_contract_sha256=job_contract_sha256,
        execution_source_commit=execution_source_commit,
        fee_provenance=fee_provenance,
        rule_provenance=rule_provenance,
        s0_config=config,
        sha256=supplied_hash,
    )


def _read_temporal_provenance(
    root: Path,
    spec_path: Path,
    tape_path: Path,
    tape_manifest_path: Path | None,
    value: Any,
    kind: Literal["fee", "rule"],
    symbol: str,
    config: S0Config,
    *,
    required: bool,
) -> TemporalProvenance | None:
    """Validate one immutable, local, historical venue record for an authorized run."""

    if not required:
        return None
    container = _as_mapping(value, "execution.temporal_provenance")
    _require_exact_fields(
        container,
        {"fee_record", "rule_record"},
        "AUTHORIZED_TEMPORAL_PROVENANCE",
    )
    descriptor = _mapping(container, f"{kind}_record")
    _require_exact_fields(
        descriptor,
        {"path", "sha256", "venue", "symbol"},
        f"AUTHORIZED_{kind.upper()}_RECORD_DESCRIPTOR",
    )
    if _string(descriptor, "venue") != "BINANCE_SPOT":
        raise DayRunPreflightError("TEMPORAL_PROVENANCE_VENUE_MISMATCH")
    if _string(descriptor, "symbol").upper() != symbol:
        raise DayRunPreflightError("TEMPORAL_PROVENANCE_SYMBOL_MISMATCH")
    record_path_value = Path(_string(descriptor, "path"))
    if record_path_value.is_absolute():
        raise DayRunPreflightError("TEMPORAL_PROVENANCE_PATH_MUST_BE_RELATIVE")
    record_path = _resolve_under_root(root, record_path_value, "temporal_provenance.record")
    forbidden_paths = {
        spec_path.resolve(),
        (spec_path.parent / "job.yaml").resolve(),
        (spec_path.parent / "STRATEGY.md").resolve(),
        _resolve_under_root(root, tape_path, "execution.tape_path", require_exists=False),
    }
    if tape_manifest_path is not None:
        forbidden_paths.add(
            _resolve_under_root(
                root,
                tape_manifest_path,
                "execution.tape_manifest_path",
                require_exists=False,
            )
        )
    if record_path in forbidden_paths:
        raise DayRunPreflightError("TEMPORAL_PROVENANCE_MUST_NOT_SELF_ATTEST")
    provenance_record_paths = {
        _resolve_under_root(
            root,
            _relative_descriptor_path(container, "fee_record"),
            "temporal_provenance.record",
        ),
        _resolve_under_root(
            root,
            _relative_descriptor_path(container, "rule_record"),
            "temporal_provenance.record",
        ),
    }
    if len(provenance_record_paths) != 2:
        raise DayRunPreflightError("TEMPORAL_PROVENANCE_FEE_AND_RULE_RECORDS_MUST_DIFFER")
    digest = _sha256_value(_string(descriptor, "sha256"), "temporal_provenance.sha256")
    if _file_sha256(record_path) != digest:
        raise DayRunPreflightError("TEMPORAL_PROVENANCE_FILE_HASH_MISMATCH")
    record = _json_mapping(record_path, f"{kind} provenance record")
    expected_schema = f"crypto-lab-day-{kind}-record-v1"
    if record.get("schema_version") != expected_schema:
        raise DayRunPreflightError("TEMPORAL_PROVENANCE_RECORD_SCHEMA_UNSUPPORTED")
    valid_from, valid_until, acquired_at = _validate_common_temporal_record(
        root,
        record_path,
        record,
        symbol,
        forbidden_paths | provenance_record_paths,
        kind,
    )
    record_id = _string(record, "record_id")
    if kind == "fee":
        sensitivity_bps = _validate_fee_record(record, config)
        return TemporalProvenance(
            record_id=record_id,
            path=record_path,
            sha256=digest,
            venue="BINANCE_SPOT",
            symbol=symbol,
            valid_from=valid_from,
            valid_until=valid_until,
            acquired_at=acquired_at,
            counterfactual_sensitivity_bps=sensitivity_bps,
        )
    rules = _validate_rule_record(record, config)
    return TemporalProvenance(
        record_id=record_id,
        path=record_path,
        sha256=digest,
        venue="BINANCE_SPOT",
        symbol=symbol,
        valid_from=valid_from,
        valid_until=valid_until,
        acquired_at=acquired_at,
        rules=rules,
    )


def _validate_common_temporal_record(
    root: Path,
    record_path: Path,
    record: Mapping[str, Any],
    symbol: str,
    forbidden_source_paths: set[Path],
    kind: Literal["fee", "rule"],
) -> tuple[datetime, datetime, datetime]:
    for field in (
        "record_id",
        "venue",
        "symbol",
        "base_asset",
        "quote_asset",
        "evidence_status",
        "effective",
        "acquired_at",
        "sources",
    ):
        if field not in record:
            raise DayRunPreflightError(f"TEMPORAL_PROVENANCE_RECORD_FIELD_REQUIRED:{field}")
    if _string(record, "venue") != "BINANCE_SPOT":
        raise DayRunPreflightError("TEMPORAL_PROVENANCE_RECORD_VENUE_MISMATCH")
    if _string(record, "symbol").upper() != symbol:
        raise DayRunPreflightError("TEMPORAL_PROVENANCE_RECORD_SYMBOL_MISMATCH")
    if (_string(record, "base_asset").upper(), _string(record, "quote_asset").upper()) != (
        "USDC",
        "USDT",
    ):
        raise DayRunPreflightError("TEMPORAL_PROVENANCE_RECORD_ASSET_MAPPING_MISMATCH")
    if _string(record, "evidence_status") != "PROVEN_HISTORICAL":
        raise DayRunPreflightError("TEMPORAL_PROVENANCE_MUST_BE_PROVEN_HISTORICAL")
    effective = _mapping(record, "effective")
    _require_exact_fields(effective, {"start", "end"}, "TEMPORAL_PROVENANCE_EFFECTIVE")
    valid_from = _timestamp(_string(effective, "start"), "effective.start")
    valid_until = _timestamp(_string(effective, "end"), "effective.end")
    if valid_until <= valid_from:
        raise DayRunPreflightError("TEMPORAL_PROVENANCE_EFFECTIVE_RANGE_INVALID")
    acquired_at = _timestamp(_string(record, "acquired_at"), "acquired_at")
    _validate_provenance_sources(
        root,
        record_path,
        _sequence(record, "sources"),
        forbidden_source_paths,
        kind,
        record,
    )
    return valid_from, valid_until, acquired_at


def _validate_provenance_sources(
    root: Path,
    record_path: Path,
    sources: Sequence[Any],
    forbidden_paths: set[Path],
    kind: Literal["fee", "rule"],
    record: Mapping[str, Any],
) -> None:
    if not sources:
        raise DayRunPreflightError("TEMPORAL_PROVENANCE_REQUIRES_SOURCES")
    source_paths: set[Path] = set()
    for index, value in enumerate(sources):
        source = _as_mapping(value, f"temporal_provenance.sources[{index}]")
        _require_exact_fields(
            source,
            {"path", "sha256", "artifact_type", "reference", "locator", "provenance"},
            "TEMPORAL_PROVENANCE_SOURCE",
        )
        source_path_value = Path(_string(source, "path"))
        if source_path_value.is_absolute():
            raise DayRunPreflightError("TEMPORAL_PROVENANCE_SOURCE_PATH_MUST_BE_RELATIVE")
        source_path = _resolve_under_root(
            root,
            source_path_value,
            "temporal_provenance.source",
        )
        if (
            source_path == record_path
            or source_path in forbidden_paths
            or source_path in source_paths
        ):
            raise DayRunPreflightError("TEMPORAL_PROVENANCE_SOURCE_PATH_INVALID")
        source_paths.add(source_path)
        expected_hash = _sha256_value(
            _string(source, "sha256"),
            f"temporal_provenance.sources[{index}].sha256",
        )
        if _file_sha256(source_path) != expected_hash:
            raise DayRunPreflightError("TEMPORAL_PROVENANCE_SOURCE_FILE_HASH_MISMATCH")
        if _string(source, "artifact_type") != "IMMUTABLE_CAPTURE":
            raise DayRunPreflightError("TEMPORAL_PROVENANCE_SOURCE_ARTIFACT_TYPE_UNSUPPORTED")
        for field in ("reference", "locator", "provenance"):
            _string(source, field)
        _validate_capture_semantics(source_path, kind, record)


def _relative_descriptor_path(container: Mapping[str, Any], key: str) -> Path:
    descriptor = _mapping(container, key)
    path = Path(_string(descriptor, "path"))
    if path.is_absolute():
        raise DayRunPreflightError("TEMPORAL_PROVENANCE_PATH_MUST_BE_RELATIVE")
    return path


def _validate_capture_semantics(
    path: Path, kind: Literal["fee", "rule"], record: Mapping[str, Any]
) -> None:
    """Bind a local immutable capture to the exact fee/rule values it supports."""

    capture = _json_mapping(path, "temporal provenance capture")
    _require_exact_fields(
        capture,
        {"schema_version", "record_kind", "record_payload"},
        "TEMPORAL_PROVENANCE_CAPTURE",
    )
    if capture.get("schema_version") != "crypto-lab-day-venue-evidence-capture-v1":
        raise DayRunPreflightError("TEMPORAL_PROVENANCE_CAPTURE_SCHEMA_UNSUPPORTED")
    if _string(capture, "record_kind") != kind:
        raise DayRunPreflightError("TEMPORAL_PROVENANCE_CAPTURE_KIND_MISMATCH")
    captured_payload = _mapping(capture, "record_payload")
    expected_payload = {key: value for key, value in record.items() if key != "sources"}
    if canonical_hash(captured_payload) != canonical_hash(expected_payload):
        raise DayRunPreflightError("TEMPORAL_PROVENANCE_CAPTURE_SEMANTIC_MISMATCH")


def _validate_fee_record(record: Mapping[str, Any], config: S0Config) -> tuple[Decimal, ...]:
    for field in ("account_tier_context", "maker_rate", "taker_rate", "side_fee_semantics"):
        if field not in record:
            raise DayRunPreflightError(f"FEE_RECORD_FIELD_REQUIRED:{field}")
    _string(record, "account_tier_context")
    maker_rate = _decimal(record.get("maker_rate"), "fee_record.maker_rate")
    taker_rate = _decimal(record.get("taker_rate"), "fee_record.taker_rate")
    if maker_rate < 0 or taker_rate < 0:
        raise DayRunPreflightError("FEE_RECORD_RATE_MUST_BE_NON_NEGATIVE")
    if maker_rate != config.fees.maker_rate or taker_rate != config.fees.taker_rate:
        raise DayRunPreflightError("FEE_RECORD_RATES_DO_NOT_MATCH_FROZEN_CONFIG")
    if _string(record, "record_id") != config.fees.source:
        raise DayRunPreflightError("FEE_RECORD_ID_DOES_NOT_MATCH_FROZEN_CONFIG")
    semantics = _mapping(record, "side_fee_semantics")
    _require_exact_fields(semantics, {"BUY", "SELL"}, "FEE_RECORD_SIDE_FEE_SEMANTICS")
    if (
        _string(semantics, "BUY") != "QUOTE/SPENT_ASSET"
        or _string(semantics, "SELL") != "QUOTE/RECEIVED_ASSET"
    ):
        raise DayRunPreflightError("FEE_RECORD_SIDE_FEE_SEMANTICS_UNSUPPORTED")
    values = record.get("counterfactual_sensitivity_bps")
    if not isinstance(values, list):
        raise DayRunPreflightError("FEE_RECORD_COUNTERFACTUAL_SENSITIVITY_MUST_BE_A_LIST")
    bps = tuple(_decimal(value, "fee_record.counterfactual_sensitivity_bps") for value in values)
    if any(value < 0 for value in bps) or len(set(bps)) != len(bps):
        raise DayRunPreflightError("FEE_RECORD_COUNTERFACTUAL_SENSITIVITY_INVALID")
    return bps


def _validate_rule_record(record: Mapping[str, Any], config: S0Config) -> VenueRules:
    for field in (
        "trading_status",
        "order_capability",
        "filters",
        "raw_filter_types",
        "validated_filter_types",
        "unsupported_active_filter_types",
    ):
        if field not in record:
            raise DayRunPreflightError(f"RULE_RECORD_FIELD_REQUIRED:{field}")
    if _string(record, "trading_status") != "TRADING":
        raise DayRunPreflightError("RULE_RECORD_TRADING_STATUS_REQUIRED")
    capability = _mapping(record, "order_capability")
    _require_exact_fields(
        capability,
        {"order_type", "time_in_force", "post_only"},
        "RULE_RECORD_ORDER_CAPABILITY",
    )
    if (
        _string(capability, "order_type") != "LIMIT_MAKER"
        or _string(capability, "time_in_force") != "GTC"
        or _bool(capability, "post_only") is not True
    ):
        raise DayRunPreflightError("RULE_RECORD_LIMIT_MAKER_GTC_POST_ONLY_REQUIRED")
    raw_types = _string_list(record.get("raw_filter_types"), "rule_record.raw_filter_types")
    validated_types = _string_list(
        record.get("validated_filter_types"), "rule_record.validated_filter_types"
    )
    required_types = {"PRICE_FILTER", "LOT_SIZE", "MIN_NOTIONAL"}
    if set(raw_types) != required_types or set(validated_types) != required_types:
        raise DayRunPreflightError("RULE_RECORD_ACTIVE_FILTER_TYPES_UNSUPPORTED")
    unsupported = _string_list(
        record.get("unsupported_active_filter_types"),
        "rule_record.unsupported_active_filter_types",
    )
    if unsupported:
        raise DayRunPreflightError("RULE_RECORD_UNSUPPORTED_ACTIVE_FILTERS_PRESENT")
    filters = _mapping(record, "filters")
    _require_exact_fields(filters, {"price", "lot", "notional"}, "RULE_RECORD_FILTERS")
    price = _mapping(filters, "price")
    lot = _mapping(filters, "lot")
    notional = _mapping(filters, "notional")
    _require_exact_fields(price, {"min_price", "max_price", "tick_size"}, "RULE_RECORD_PRICE")
    _require_exact_fields(lot, {"min_quantity", "max_quantity", "step_size"}, "RULE_RECORD_LOT")
    _require_exact_fields(
        notional,
        {"min_notional", "max_notional", "applies_to_limit"},
        "RULE_RECORD_NOTIONAL",
    )
    rules = VenueRules(
        min_price=_decimal(price.get("min_price"), "rule_record.min_price"),
        max_price=_decimal(price.get("max_price"), "rule_record.max_price"),
        tick_size=_decimal(price.get("tick_size"), "rule_record.tick_size"),
        min_quantity=_decimal(lot.get("min_quantity"), "rule_record.min_quantity"),
        max_quantity=_decimal(lot.get("max_quantity"), "rule_record.max_quantity"),
        step_size=_decimal(lot.get("step_size"), "rule_record.step_size"),
        min_notional=_decimal(notional.get("min_notional"), "rule_record.min_notional"),
        max_notional=_optional_decimal(notional.get("max_notional"), "rule_record.max_notional"),
    )
    if _bool(notional, "applies_to_limit") is not True:
        raise DayRunPreflightError("RULE_RECORD_MIN_NOTIONAL_MUST_APPLY_TO_LIMIT")
    if (
        rules.min_price <= 0
        or rules.min_quantity <= 0
        or rules.min_notional <= 0
        or rules.tick_size <= 0
        or rules.step_size <= 0
        or rules.max_price < rules.min_price
        or rules.max_quantity < rules.min_quantity
        or (rules.max_notional is not None and rules.max_notional < rules.min_notional)
    ):
        raise DayRunPreflightError("RULE_RECORD_FILTER_BOUNDS_INVALID")
    _validate_s0_against_rules(config, rules)
    return rules


def _validate_s0_against_rules(config: S0Config, rules: VenueRules) -> None:
    # The legacy S0 engine exposes only one grid field.  An authorized
    # counterfactual campaign must therefore prove that it equals *both* exchange grids; otherwise
    # this adapter cannot faithfully represent the venue's separate tick/lot rules.
    if rules.tick_size != config.step_size or rules.step_size != config.step_size:
        raise DayRunPreflightError("RULE_RECORD_LEGACY_S0_REQUIRES_EQUAL_TICK_AND_LOT_STEP")
    for value in (config.lower, config.upper):
        if value < rules.min_price or value > rules.max_price:
            raise DayRunPreflightError("S0_PRICE_OUTSIDE_FROZEN_RULE_BOUNDS")
        _require_grid_multiple(value, rules.tick_size, "S0_PRICE_OFF_FROZEN_RULE_TICK")
    quantity = _frozen_entry_quantity(config)
    if quantity < rules.min_quantity or quantity > rules.max_quantity:
        raise DayRunPreflightError("S0_QUANTITY_OUTSIDE_FROZEN_RULE_BOUNDS")
    _require_grid_multiple(quantity, rules.step_size, "S0_QUANTITY_OFF_FROZEN_RULE_STEP")
    if config.min_quantity < rules.min_quantity or config.min_notional < rules.min_notional:
        raise DayRunPreflightError("S0_MINIMUMS_WEAKER_THAN_FROZEN_RULES")
    entry_notional = config.lower * quantity
    if entry_notional < rules.min_notional or (
        rules.max_notional is not None and entry_notional > rules.max_notional
    ):
        raise DayRunPreflightError("S0_ENTRY_NOTIONAL_OUTSIDE_FROZEN_RULE_BOUNDS")


def _validate_frozen_contracts(campaign_dir: Path, job: DayJob, spec: FrozenModelSpec) -> None:
    if job.contract_sha256 != spec.job_contract_sha256:
        raise DayRunPreflightError("DAY_JOB_CONTRACT_HASH_MISMATCH")
    strategy_path = campaign_dir / "STRATEGY.md"
    if not strategy_path.is_file():
        raise DayRunPreflightError("STRATEGY_MD_MISSING")
    if _file_sha256(strategy_path) != spec.strategy_sha256:
        raise DayRunPreflightError("STRATEGY_HASH_MISMATCH")


def _validate_job_matches_spec(job: DayJob, spec: FrozenModelSpec) -> None:
    if job.model_id != spec.model_id or job.parent != spec.parent:
        raise DayRunPreflightError("DAY_JOB_MODEL_LINEAGE_MISMATCH")
    if job.model_spec_sha256 != spec.sha256:
        raise DayRunPreflightError("DAY_JOB_MODEL_SPEC_HASH_MISMATCH")
    if job.execution_authorized is not spec.execution_authorized:
        raise DayRunPreflightError("DAY_JOB_MODEL_AUTHORIZATION_MISMATCH")
    if not job.execution_authorized:
        raise DayRunPreflightError("CAMPAIGN_EXECUTION_NOT_AUTHORIZED")
    if spec.status != "AUTHORIZED" or spec.authorization_status != "AUTHORIZED":
        raise DayRunPreflightError("CAMPAIGN_MODEL_SPEC_NOT_AUTHORIZED")
    _validate_authorized_temporal_provenance(job, spec)
    if any(item.mode != "single" for item in job.scenarios):
        raise DayRunPreflightError("CAUSAL_CPU_SINGLE_BOOK_ENGINE_REJECTS_PARALLEL_SCENARIO")
    if job.gates.max_negative_cycles != 0 or not job.gates.capital_conservation:
        raise DayRunPreflightError("DAY_RUN_REQUIRES_ZERO_LOSS_AND_CAPITAL_CONSERVATION_GATES")
    # The job contract itself is frozen into the model spec.  A literal sentinel
    # avoids an impossible self-referential hash while still requiring the active
    # state to name this exact, fully hashed spec below.
    if job.state_binding.next_campaign_model_hash != "MODEL_SPEC_SHA256":
        raise DayRunPreflightError("DAY_JOB_STATE_MODEL_HASH_BINDING_MISMATCH")
    if job.state_binding.next_campaign_window != _windows_token(job.windows):
        raise DayRunPreflightError("DAY_JOB_STATE_WINDOW_BINDING_MISMATCH")
    if not job.state_binding.next_campaign_status.startswith("AUTHORIZED_"):
        raise DayRunPreflightError("DAY_JOB_STATE_STATUS_MUST_BE_EXPLICITLY_AUTHORIZED")
    for scenario in job.scenarios:
        _validate_positive_exit_edge(scenario, spec)


def _validate_authorized_temporal_provenance(job: DayJob, spec: FrozenModelSpec) -> None:
    """Require one unambiguous, historical fee/rule record over every run window."""

    records = (spec.fee_provenance, spec.rule_provenance)
    if any(record is None for record in records):
        raise DayRunPreflightError("AUTHORIZED_MODEL_SPEC_REQUIRES_TEMPORAL_PROVENANCE")
    fee_record, rule_record = cast(tuple[TemporalProvenance, TemporalProvenance], records)
    for record in (fee_record, rule_record):
        if any(
            record.valid_from > window.start or record.valid_until < window.end
            for window in job.windows
        ):
            raise DayRunPreflightError("TEMPORAL_PROVENANCE_DOES_NOT_COVER_FROZEN_WINDOW")
    historical_maker_bps = spec.s0_config.fees.maker_rate * Decimal("10000")
    historical_taker_bps = spec.s0_config.fees.taker_rate * Decimal("10000")
    for scenario in job.scenarios:
        historical_rate = scenario.fee_bps == historical_maker_bps == historical_taker_bps
        if (
            not historical_rate
            and scenario.fee_bps not in fee_record.counterfactual_sensitivity_bps
        ):
            raise DayRunPreflightError("FEE_SCENARIO_NOT_PROVEN_OR_PREREGISTERED_SENSITIVITY")
    if rule_record.rules is None:  # Defensive: rule parser always supplies it.
        raise DayRunPreflightError("AUTHORIZED_MODEL_SPEC_REQUIRES_FROZEN_RULE_RECORD")


def _validate_campaign_day(campaign_dir: Path, job: DayJob) -> None:
    if campaign_dir.name != "TEMPLATE" and campaign_dir.name != job.day:
        raise DayRunPreflightError("CAMPAIGN_DIRECTORY_DATE_DOES_NOT_MATCH_JOB_DAY")
    day_start = datetime.combine(_parse_day(job.day), datetime.min.time(), tzinfo=UTC)
    day_end = day_start + timedelta(days=1)
    if any(window.start < day_start or window.end > day_end for window in job.windows):
        raise DayRunPreflightError("CAMPAIGN_WINDOWS_MUST_STAY_WITHIN_JOB_UTC_DAY")


def _validate_current_state(root: Path, job: DayJob, spec: FrozenModelSpec) -> None:
    state_path = root / "docs/research/CURRENT_STATE.md"
    if not state_path.is_file():
        raise DayRunPreflightError("CURRENT_STATE_MISSING")
    # A completed one-shot leaves an append-only record independent from mutable
    # campaign status/output files.  Search every authoritative record rather
    # than the first KEY=VALUE occurrence because the state reader intentionally
    # preserves the first value for ordinary bindings.
    state_head = state_path.read_text(encoding="utf-8").split("<!--", maxsplit=1)[0]
    prior_record = re.compile(
        rf"^## Day-run record — .+ / {re.escape(spec.model_id)}$", re.MULTILINE
    )
    if prior_record.search(state_head):
        raise DayRunPreflightError("MODEL_ID_ALREADY_CONSUMED_IN_CURRENT_STATE")
    current = _current_state_head(state_path)
    if current.get("ACTIVE_EXECUTION_CAMPAIGN") != "NONE":
        raise DayRunPreflightError("INCOMPATIBLE_ACTIVE_CAMPAIGN")
    for field in ("CAMPAIGN_ACTIVE_ENVELOPE", "CAMPAIGN_QUEUED_ENVELOPE"):
        if current.get(field) not in {None, "", "NONE"}:
            raise DayRunPreflightError(f"INCOMPATIBLE_{field}")
    if current.get("NEXT_CAMPAIGN_WINDOW") in {None, "", "UNAUTHORIZED"}:
        raise DayRunPreflightError("CURRENT_STATE_WINDOW_UNAUTHORIZED")
    required_state = {
        "NEXT_CAMPAIGN_STATUS": job.state_binding.next_campaign_status,
        "NEXT_CAMPAIGN_MODEL_HASH": spec.sha256,
        "NEXT_CAMPAIGN_WINDOW": job.state_binding.next_campaign_window,
    }
    for field, expected in required_state.items():
        if current.get(field) != expected:
            raise DayRunPreflightError(f"CURRENT_STATE_BINDING_MISMATCH:{field}")
    active_model = current.get("CURRENT_ACTIVE_RESEARCH_MODEL", "")
    active_match = _MODEL_ID.match(active_model.split("_", 1)[0])
    candidate_match = _MODEL_ID.match(spec.model_id)
    if (
        active_match
        and candidate_match
        and int(candidate_match["number"]) <= int(active_match["number"])
    ):
        raise DayRunPreflightError("MODEL_ID_NOT_NEWER_THAN_CURRENT_RESEARCH_MODEL")
    if current.get("NEXT_CAMPAIGN_STATUS", "").startswith("NO_RERUN") and job.model_id == "M035":
        raise DayRunPreflightError("CONSUMED_M035_CANNOT_BE_RERUN")


def _validate_execution_source(root: Path, spec: FrozenModelSpec) -> SourceBinding:
    """Bind an authorized run to the reviewed local source, not just a file hash."""

    top_level = Path(_git_output(root, "rev-parse", "--show-toplevel")).resolve()
    if top_level != root.resolve():
        raise DayRunPreflightError("EXECUTION_SOURCE_REPOSITORY_ROOT_MISMATCH")
    branch = _git_output(root, "branch", "--show-current")
    if branch != "main":
        raise DayRunPreflightError("EXECUTION_SOURCE_BRANCH_MUST_BE_MAIN")
    commit = _git_output(root, "rev-parse", "--verify", "HEAD")
    if _GIT_COMMIT.fullmatch(commit) is None:
        raise DayRunPreflightError("EXECUTION_SOURCE_HEAD_IS_NOT_A_FULL_COMMIT")
    if commit != spec.execution_source_commit:
        raise DayRunPreflightError("EXECUTION_SOURCE_COMMIT_DOES_NOT_MATCH_FROZEN_MODEL_SPEC")
    dirty = _git_output(
        root,
        "status",
        "--porcelain=v1",
        "--untracked-files=all",
        "--",
        "src/crypto_strategy_lab",
        "pyproject.toml",
        "uv.lock",
        ".python-version",
    )
    if dirty:
        raise DayRunPreflightError("EXECUTION_SOURCE_TREE_DIRTY")
    return SourceBinding(commit=commit, branch=branch, source_tree_clean=True)


def _revalidate_before_claim(
    root: Path,
    campaign_dir: Path,
    expected_job: DayJob,
    expected_spec: FrozenModelSpec,
) -> ClaimValidation:
    """Close the preflight-to-claim race using a fresh, in-memory frozen snapshot."""

    job = _read_job(campaign_dir / "job.yaml", root)
    spec = _read_model_spec(campaign_dir / "model_spec.json", root)
    if job != expected_job or spec != expected_spec:
        raise DayRunPreflightError("FROZEN_CAMPAIGN_CHANGED_DURING_PREFLIGHT")
    _validate_frozen_contracts(campaign_dir, job, spec)
    _validate_job_matches_spec(job, spec)
    _validate_campaign_day(campaign_dir, job)
    _validate_current_state(root, job, spec)
    _validate_unique_campaign_identity(root, campaign_dir, spec.model_id)
    _validate_output_directory(root, job.output_dir)
    source_binding = _validate_execution_source(root, spec)
    _validate_oracle_backend(job)
    tape_path = _resolve_under_root(root, spec.tape_path, "execution.tape_path")
    tape = _read_tape(root, tape_path, spec, job)
    oracle_payload = _run_oracle(job, spec, tape)
    return ClaimValidation(
        source_binding=source_binding,
        tape=tape,
        oracle_payload=oracle_payload,
    )


def _git_output(root: Path, *arguments: str) -> str:
    try:
        completed = subprocess.run(
            ["git", "-C", str(root), *arguments],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
    except OSError as error:
        raise DayRunPreflightError("GIT_REQUIRED_FOR_EXECUTION_SOURCE_BINDING") from error
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise DayRunPreflightError(f"EXECUTION_SOURCE_GIT_COMMAND_FAILED:{detail}")
    return completed.stdout.strip()


def _validate_oracle_backend(job: DayJob) -> None:
    """Fail early when an explicitly requested GPU cannot initialize locally."""

    if job.oracle.backend != "gpu":
        return
    try:
        # A non-empty probe reaches the CUDA device context, memory planner, and
        # kernels.  An empty candidate list returns before those runtime checks.
        scan_oracle((0,), ((0, 1),), backend="gpu")
    except Exception as error:
        message = f"EXPLICIT_GPU_ORACLE_UNAVAILABLE:{type(error).__name__}"
        raise DayRunPreflightError(message) from error


def _validate_invariants(raw: Mapping[str, Any]) -> None:
    expected = {
        "frozen_event_order_replay": True,
        "l2_inferred_fills_require_continuous_l2_and_individual_trades": True,
        "public_l2_queue_never_claims_own_queue_rank": True,
        "capture_arrival_and_latency_not_historical_proof": True,
        "decimal_exact": True,
        "capital_conservation": True,
        "zero_loss": True,
        "no_negative_ordinary_cycle_exit": True,
        "cancel_release_requires_ack": True,
        "live_testnet_closed": True,
        "llm_in_execution_loop": False,
    }
    if set(raw) != set(expected):
        raise DayRunPreflightError("MODEL_SPEC_INVARIANT_FIELDS_MUST_BE_EXACT")
    if any(raw[key] is not required for key, required in expected.items()):
        raise DayRunPreflightError("MODEL_SPEC_INVARIANTS_NOT_SATISFIED")


def _validate_s0_config_mapping(raw: Mapping[str, Any]) -> None:
    required = {
        "strategy_id",
        "symbol",
        "lower",
        "upper",
        "quantity_override",
        "initial_usdc",
        "lot_mode",
        "fixed_lot_usdc",
        "step_size",
        "min_quantity",
        "min_notional",
        "queue_model",
        "conservative_queue_multiplier",
        "latency",
        "fees",
    }
    _require_exact_fields(raw, required, "MODEL_SPEC_S0_CONFIG")
    _require_exact_fields(
        _mapping(raw, "latency"),
        {"market_data_ms", "decision_ms", "order_submit_ms", "cancel_ms"},
        "MODEL_SPEC_S0_LATENCY",
    )
    _require_exact_fields(
        _mapping(raw, "fees"),
        {
            "maker_rate",
            "taker_rate",
            "buy_fee_asset",
            "sell_fee_asset",
            "source",
        },
        "MODEL_SPEC_S0_FEES",
    )


def _require_exact_fields(raw: Mapping[str, Any], required: set[str], label: str) -> None:
    if set(raw) != required:
        raise DayRunPreflightError(f"{label}_FIELDS_MUST_BE_EXACT")


def _validate_s0_numeric_contract(config: S0Config) -> None:
    for label, value in (("lower", config.lower), ("upper", config.upper)):
        _require_grid_multiple(value, config.step_size, f"S0_{label.upper()}_OFF_TICK_GRID")
    quantity = _frozen_entry_quantity(config)
    if quantity <= 0:
        raise DayRunPreflightError("S0_FROZEN_ENTRY_QUANTITY_MUST_BE_POSITIVE")
    _require_grid_multiple(quantity, config.step_size, "S0_QUANTITY_OFF_STEP_GRID")
    if quantity < config.min_quantity:
        raise DayRunPreflightError("S0_QUANTITY_BELOW_MINIMUM")
    entry_notional = config.lower * quantity
    if entry_notional < config.min_notional:
        raise DayRunPreflightError("S0_ENTRY_NOTIONAL_BELOW_MINIMUM")
    buy_cost = entry_notional * (Decimal("1") + config.fees.maker_rate)
    if buy_cost > config.initial_usdc:
        raise DayRunPreflightError("S0_ENTRY_EXCEEDS_FROZEN_CAPITAL")


def _require_grid_multiple(value: Decimal, step: Decimal, error: str) -> None:
    quotient = value / step
    if quotient != quotient.to_integral_value():
        raise DayRunPreflightError(error)


def _frozen_entry_quantity(config: S0Config) -> Decimal:
    if config.quantity_override is not None:
        return config.quantity_override
    budget = (
        min(config.fixed_lot_usdc, config.initial_usdc)
        if config.lot_mode.value == "FIXED_LOT"
        else config.initial_usdc
    )
    if config.fees.buy_fee_asset.value == "QUOTE":
        budget /= Decimal("1") + config.fees.maker_rate
    return (budget / config.lower // config.step_size) * config.step_size


def _scenario_config(scenario: Scenario, spec: FrozenModelSpec) -> S0Config:
    rate = scenario.fee_bps / Decimal("10000")
    fees = spec.s0_config.fees.model_copy(update={"maker_rate": rate, "taker_rate": rate})
    config = spec.s0_config.model_copy(update={"fees": fees})
    _validate_s0_numeric_contract(config)
    return config


def _validate_positive_exit_edge(scenario: Scenario, spec: FrozenModelSpec) -> None:
    config = _scenario_config(scenario, spec)
    net_edge = config.fees.one_tick_net_quote(
        lower=config.lower,
        upper=config.upper,
        quantity=_frozen_entry_quantity(config),
        buy_role=LiquidityRole.MAKER,
        sell_role=LiquidityRole.MAKER,
    )
    if net_edge <= 0:
        raise DayRunPreflightError("POSITIVE_NET_EXIT_EDGE_REQUIRED_FOR_EACH_SCENARIO")


def _fee_interpretation(scenario: Scenario, spec: FrozenModelSpec) -> str:
    """Label fee sweeps honestly instead of presenting assumptions as history."""

    historical_maker_bps = spec.s0_config.fees.maker_rate * Decimal("10000")
    historical_taker_bps = spec.s0_config.fees.taker_rate * Decimal("10000")
    if scenario.fee_bps == historical_maker_bps == historical_taker_bps:
        return "HISTORICAL_PROVEN_RATE"
    return "COUNTERFACTUAL_PREREGISTERED_SENSITIVITY"


def _validate_unique_campaign_identity(root: Path, campaign_dir: Path, model_id: str) -> None:
    for candidate in (root / "campaigns").glob("*/model_spec.json"):
        if candidate.parent.resolve() == campaign_dir:
            continue
        try:
            payload = _json_mapping(candidate, "other campaign model_spec.json")
        except DayRunPreflightError:
            continue
        if payload.get("model_id") == model_id:
            raise DayRunPreflightError("MODEL_ID_ALREADY_PRESENT_IN_ANOTHER_CAMPAIGN")


def _validate_output_directory(root: Path, output_dir: Path) -> None:
    resolved = _resolve_under_root(root, output_dir, "output_dir", require_exists=False)
    if resolved.exists() and any(resolved.iterdir()):
        raise DayRunPreflightError("CAMPAIGN_OUTPUT_ALREADY_EXISTS")


def _read_tape(root: Path, tape_path: Path, spec: FrozenModelSpec, job: DayJob) -> dict[str, Any]:
    if not tape_path.is_file():
        raise DayRunPreflightError("LOCAL_TAPE_MISSING")
    raw = _json_mapping(tape_path, "tape")
    if _string(raw, "symbol").upper() != spec.symbol:
        raise DayRunPreflightError("TAPE_SYMBOL_MISMATCH")
    if _string(raw, "venue") != "BINANCE_SPOT":
        raise DayRunPreflightError("TAPE_VENUE_MISMATCH")
    if "config" in raw:
        tape_config_raw = _mapping(raw, "config")
        _validate_s0_config_mapping(tape_config_raw)
        try:
            tape_config = S0Config.model_validate(tape_config_raw)
        except ValidationError as error:
            raise DayRunPreflightError(f"TAPE_CONFIG_INVALID:{error}") from error
        _validate_s0_numeric_contract(tape_config)
        if tape_config.model_dump(mode="json") != spec.s0_config.model_dump(mode="json"):
            raise DayRunPreflightError("TAPE_CONFIG_DOES_NOT_MATCH_FROZEN_MODEL_SPEC")
    events = _parse_events(_sequence(raw, "events"))
    if not events:
        raise DayRunPreflightError("TAPE_EVENT_STREAM_EMPTY")
    _validate_event_order(events)
    for event in events:
        timestamp = require_utc(event.timestamp)
        if not _is_in_authorized_window(timestamp, job.windows):
            raise DayRunPreflightError("TAPE_EVENT_OUTSIDE_FROZEN_WINDOW")
    if any(isinstance(event, FeedGapEvent) for event in events):
        raise DayRunPreflightError("AUTHORIZED_DAY_RUN_REJECTS_FEED_GAPS")
    if any(isinstance(event, RiskHaltEvent) for event in events):
        raise DayRunPreflightError("AUTHORIZED_DAY_RUN_REJECTS_EXTERNAL_RISK_HALTS")
    _validate_l2_window_boundaries(events, job.windows)
    if not any(isinstance(event, (BookSnapshotEvent, BookDeltaEvent)) for event in events):
        raise DayRunPreflightError("TAPE_REQUIRES_L2_BOOK_EVENTS")
    if not any(isinstance(event, TradeEvent) for event in events):
        raise DayRunPreflightError("TAPE_REQUIRES_INDIVIDUAL_TRADE_EVENTS")
    _validate_tape_events_against_rules(events, spec)
    _validate_trade_id_continuity(events)
    _validate_l2_continuity(events)
    _validate_l2_update_coverage(events, job.windows, job.max_l2_update_age_seconds)
    _validate_terminal_l2_freshness(events, job.windows, job.terminal_mark_max_age_seconds)
    cancellations = _parse_cancellations(raw.get("cancellations", []))
    if cancellations:
        raise DayRunPreflightError("AUTHORIZED_DAY_RUN_REJECTS_EXTERNAL_CANCELLATIONS")
    _validate_tape_processing_cutoff(events, cancellations, job.windows, spec.s0_config)
    actual_sha256 = _file_sha256(tape_path)
    if spec.tape_sha256 is not None and spec.tape_sha256 != actual_sha256:
        raise DayRunPreflightError("TAPE_HASH_DOES_NOT_MATCH_FROZEN_MODEL_SPEC")
    manifest = _read_tape_manifest(root, tape_path, actual_sha256, spec, job, events)
    return {
        "path": tape_path,
        "sha256": actual_sha256,
        "events": events,
        "cancellations": cancellations,
        "manifest": manifest,
    }


def _run_oracle(
    job: DayJob,
    spec: FrozenModelSpec,
    tape: Mapping[str, Any],
) -> dict[str, Any] | None:
    if not job.oracle.candidates:
        return None
    events = cast(list[MarketEvent], tape["events"])
    prices: list[int] = []
    for event in events:
        if not isinstance(event, TradeEvent):
            continue
        ticks = event.price / spec.s0_config.step_size
        if ticks != ticks.to_integral_value():
            raise DayRunPreflightError("ORACLE_TRADE_PRICE_NOT_ON_FROZEN_TICK_GRID")
        prices.append(int(ticks))
    if not prices:
        raise DayRunPreflightError("ORACLE_REQUIRES_TRADE_PRICES")
    try:
        result = scan_oracle(prices, job.oracle.candidates, backend=job.oracle.backend)
    except Exception as error:
        raise DayRunPreflightError(
            f"ORACLE_EXECUTION_PRECHECK_FAILED:{type(error).__name__}"
        ) from error
    return {
        "schema_version": "crypto-lab-day-oracle-v1",
        "advisory_only": True,
        "model_id": spec.model_id,
        "backend_requested": job.oracle.backend,
        "backend_used": result.backend,
        "fallback_reason": result.fallback_reason,
        "events": result.events,
        "candidates": [asdict(candidate) for candidate in result.candidates],
    }


def _run_scenarios(
    job: DayJob, spec: FrozenModelSpec, tape: Mapping[str, Any]
) -> list[ScenarioExecution]:
    events = cast(list[MarketEvent], tape["events"])
    cancellations = cast(list[CancelRequest], tape["cancellations"])
    outputs: list[ScenarioExecution] = []
    for scenario in job.scenarios:
        config = _scenario_config(scenario, spec)
        result = PassiveExecutionSimulator(config).run(
            events,
            dataset_hash=cast(str, tape["sha256"]),
            cancel_requests=cancellations,
        )
        _validate_runtime_orders_against_rules(result, spec)
        _validate_runtime_timestamps(result, job.windows)
        outputs.append(
            ScenarioExecution(
                scenario=scenario,
                config=config,
                result=result,
                metrics=_scenario_metrics(
                    scenario,
                    config,
                    result,
                    events,
                    job.windows,
                    job.terminal_mark_max_age_seconds,
                    spec,
                ),
            )
        )
    return outputs


def _scenario_metrics(
    scenario: Scenario,
    config: S0Config,
    result: MicrostructureRunResult,
    events: Sequence[MarketEvent],
    windows: Sequence[CampaignWindow],
    terminal_mark_max_age_seconds: int,
    spec: FrozenModelSpec,
) -> dict[str, Any]:
    cycle_pnls = _l2_inferred_cycle_pnls(result)
    terminal = _terminal_mid(events)
    terminal_mark = terminal.mid
    terminal_age_seconds = (
        None
        if terminal.l2_timestamp is None
        else Decimal(
            str((max(window.end for window in windows) - terminal.l2_timestamp).total_seconds())
        )
    )
    if result.ledger.fdusd > 0 and terminal_mark is None:
        raise DayRunError("TERMINAL_MARK_REQUIRED_FOR_OPEN_INVENTORY")
    if (
        result.ledger.fdusd > 0
        and terminal_age_seconds is not None
        and terminal_age_seconds > Decimal(terminal_mark_max_age_seconds)
    ):
        raise DayRunError("TERMINAL_L2_MARK_TOO_STALE_AT_CUTOFF")
    if result.ledger.fdusd > 0 and not result.book_valid_at_end:
        raise DayRunError("VALID_L2_BOOK_REQUIRED_AT_CUTOFF_FOR_OPEN_INVENTORY")
    final_marked_equity = result.ledger.usdc + (
        result.ledger.fdusd * terminal_mark if terminal_mark is not None else Decimal("0")
    )
    terminal_unrealized = (
        Decimal("0")
        if result.ledger.fdusd == 0
        else result.ledger.fdusd * cast(Decimal, terminal_mark) - result.ledger.capital_locked_usdc
    )
    expected_equity = config.initial_usdc + result.ledger.realized_pnl_usdc + terminal_unrealized
    reconciled = _reconcile_fills(result, config)
    reservation_hours, inventory_hours = _committed_capital_hours(result, config, windows)
    capital_hours = reservation_hours + inventory_hours
    l2_inferred_cycles = len(cycle_pnls)
    engine_cycles = int(result.metrics["cycle_count"])
    if l2_inferred_cycles != engine_cycles:
        raise DayRunError("L2_INFERRED_CYCLE_RECONCILIATION_FAILED")
    if any(value < 0 for value in cycle_pnls):
        raise DayRunError("ZERO_LOSS_VIOLATION_DETECTED_IN_L2_INFERRED_CYCLE")
    marked_residual = final_marked_equity - expected_equity
    if final_marked_equity < config.initial_usdc:
        raise DayRunError("ZERO_LOSS_TERMINAL_EQUITY_VIOLATION")
    capital_conservation_pass = (
        reconciled["quote_balance_residual"] == 0
        and reconciled["base_balance_residual"] == 0
        and reconciled["locked_capital_residual"] == 0
        and marked_residual == 0
    )
    return {
        "scenario": scenario.name,
        "mode": scenario.mode,
        "fee_bps_per_leg": str(scenario.fee_bps),
        "fee_interpretation": _fee_interpretation(scenario, spec),
        "base_asset": spec.base_asset,
        "quote_asset": spec.quote_asset,
        "initial_equity_quote": str(config.initial_usdc),
        "final_marked_equity_quote": str(final_marked_equity),
        "marked_equity_residual_quote": str(marked_residual),
        "terminal_mark_quote_per_base": None if terminal_mark is None else str(terminal_mark),
        "terminal_l2_timestamp": (
            None if terminal.l2_timestamp is None else terminal.l2_timestamp.isoformat()
        ),
        "terminal_l2_age_seconds_at_cutoff": (
            None if terminal_age_seconds is None else str(terminal_age_seconds)
        ),
        "terminal_mark_max_age_seconds": terminal_mark_max_age_seconds,
        "terminal_unrealized_pnl_quote": str(terminal_unrealized),
        "engine_unrealized_pnl_quote": str(result.ledger.unrealized_pnl_usdc),
        "evidence_class": spec.evidence_class,
        "economic_eligibility": PUBLIC_L2_QUEUE_LIMITATION,
        "l2_inferred_cycles": l2_inferred_cycles,
        "negative_l2_inferred_cycles": sum(value < 0 for value in cycle_pnls),
        "l2_inferred_cycle_pnls_quote": [str(value) for value in cycle_pnls],
        "no_negative_l2_inferred_cycle": all(value >= 0 for value in cycle_pnls),
        "nonnegative_terminal_marked_equity": final_marked_equity >= config.initial_usdc,
        "modeled_zero_loss_pass": (
            all(value >= 0 for value in cycle_pnls) and final_marked_equity >= config.initial_usdc
        ),
        "pending_buy_reservation_hours_quote": str(reservation_hours),
        "inventory_cost_hours_quote": str(inventory_hours),
        "committed_capital_hours_quote": str(capital_hours),
        "net_realized_pnl_per_committed_capital_hour": (
            None if capital_hours == 0 else str(result.ledger.realized_pnl_usdc / capital_hours)
        ),
        "modeled_orders": len(result.orders),
        "l2_inferred_fills": len(result.fills),
        "book_invalidations": result.book_invalidations,
        "risk_halt": result.risk_halt,
        "terminal_inventory_base": str(result.ledger.fdusd),
        "fees_quote": str(result.ledger.fees_usdc),
        "quote_cash_balance_residual": str(reconciled["quote_balance_residual"]),
        "base_balance_residual": str(reconciled["base_balance_residual"]),
        "locked_capital_residual_quote": str(reconciled["locked_capital_residual"]),
        "capital_conservation_pass": capital_conservation_pass,
        "legacy_engine_metrics": {key: str(value) for key, value in result.metrics.items()},
    }


def _l2_inferred_cycle_pnls(result: MicrostructureRunResult) -> list[Decimal]:
    pending_buy: tuple[Decimal, Decimal] | None = None
    values: list[Decimal] = []
    for order in result.orders:
        if order.side == Side.BUY and order.status == OrderStatus.FILLED:
            if pending_buy is not None:
                raise DayRunError("OVERLAPPING_BUY_CYCLE")
            pending_buy = (
                order.filled_quantity,
                order.average_fill_price * order.filled_quantity + order.fees_quote,
            )
        elif order.side == Side.SELL and order.status == OrderStatus.FILLED:
            if pending_buy is None or order.filled_quantity != pending_buy[0]:
                raise DayRunError("UNPAIRED_OR_PARTIAL_L2_INFERRED_SELL")
            proceeds = order.average_fill_price * order.filled_quantity - order.fees_quote
            values.append(proceeds - pending_buy[1])
            pending_buy = None
    return values


def _reconcile_fills(result: MicrostructureRunResult, config: S0Config) -> dict[str, Decimal]:
    """Independently reconcile the engine's quote/base ledger from preserved fills."""

    expected_quote = config.initial_usdc
    expected_base = Decimal("0")
    for fill in result.fills:
        if fill.fee_asset.value != "QUOTE":
            raise DayRunError("DAY_RUN_REQUIRES_QUOTE_FEE_FILL_RECONCILIATION")
        if fill.side == Side.BUY:
            expected_quote -= fill.quote_value + fill.fee_quote_equivalent
            expected_base += fill.net_base_quantity
        else:
            expected_quote += fill.quote_value - fill.fee_quote_equivalent
            expected_base -= fill.gross_quantity
    if expected_base < 0:
        raise DayRunError("FILL_RECONCILIATION_NEGATIVE_BASE_BALANCE")
    expected_locked = result.ledger.average_cost_usdc * result.ledger.fdusd
    return {
        "quote_balance_residual": result.ledger.usdc - expected_quote,
        "base_balance_residual": result.ledger.fdusd - expected_base,
        "locked_capital_residual": result.ledger.capital_locked_usdc - expected_locked,
    }


def _committed_capital_hours(
    result: MicrostructureRunResult,
    config: S0Config,
    windows: Sequence[CampaignWindow],
) -> tuple[Decimal, Decimal]:
    """Integrate pending-BUY reservation and filled-inventory cost to the frozen cutoff.

    The legacy S0 engine stores an abstract quote wallet as ``usdc`` and abstract base
    inventory as ``fdusd``.  This reconstruction intentionally works from its preserved
    orders/fills and treats those values as the quote/base mapping frozen by the day spec.
    """

    changes: dict[datetime, list[Decimal]] = {}

    def add(
        timestamp: datetime,
        reservation: Decimal = Decimal("0"),
        inventory: Decimal = Decimal("0"),
    ) -> None:
        bucket = changes.setdefault(require_utc(timestamp), [Decimal("0"), Decimal("0")])
        bucket[0] += reservation
        bucket[1] += inventory

    fills_by_order: dict[str, list[Any]] = {}
    for fill in result.fills:
        fills_by_order.setdefault(fill.order_id, []).append(fill)
    for order in result.orders:
        if order.side != Side.BUY:
            continue
        reserve_per_unit = order.price * (Decimal("1") + config.fees.maker_rate)
        add(order.placed_at, reservation=order.quantity * reserve_per_unit)
        for fill in fills_by_order.get(order.order_id, []):
            add(
                fill.timestamp,
                reservation=-(fill.quote_value + fill.fee_quote_equivalent),
            )
        if order.remaining_quantity > 0:
            if order.status == OrderStatus.CANCELED:
                if order.cancel_effective_at is None:
                    raise DayRunError("CANCELED_BUY_MISSING_CANCEL_ACK_TIME")
                release_at = order.cancel_effective_at
            elif order.status in {
                OrderStatus.REJECTED_POST_ONLY,
                OrderStatus.REJECTED_NO_OBSERVED_QUEUE_COVERAGE,
            }:
                release_at = order.exchange_arrival_at
            elif order.status in {
                OrderStatus.PENDING,
                OrderStatus.OPEN,
                OrderStatus.PARTIALLY_FILLED,
                OrderStatus.CANCEL_PENDING,
            }:
                release_at = max(window.end for window in windows)
            else:
                raise DayRunError("BUY_RESERVATION_HAS_UNSUPPORTED_FINAL_STATUS")
            add(release_at, reservation=-(order.remaining_quantity * reserve_per_unit))

    inventory_base = Decimal("0")
    inventory_cost = Decimal("0")
    for fill in sorted(result.fills, key=lambda row: row.timestamp):
        if fill.side == Side.BUY:
            cost = fill.quote_value + fill.fee_quote_equivalent
            inventory_base += fill.net_base_quantity
            inventory_cost += cost
            add(fill.timestamp, inventory=cost)
            continue
        if inventory_base <= 0 or fill.gross_quantity > inventory_base:
            raise DayRunError("CAPITAL_HOURS_SELL_WITHOUT_OWNED_INVENTORY")
        released = inventory_cost * fill.gross_quantity / inventory_base
        inventory_base -= fill.gross_quantity
        inventory_cost -= released
        add(fill.timestamp, inventory=-released)
    if inventory_base != result.ledger.fdusd or (
        inventory_cost != result.ledger.average_cost_usdc * result.ledger.fdusd
    ):
        raise DayRunError("CAPITAL_HOURS_INVENTORY_RECONCILIATION_FAILED")

    reservation_hours, inventory_hours = _integrate_capital_changes(changes, windows)
    return reservation_hours, inventory_hours


def _integrate_capital_changes(
    changes: Mapping[datetime, Sequence[Decimal]], windows: Sequence[CampaignWindow]
) -> tuple[Decimal, Decimal]:
    reservation = Decimal("0")
    inventory = Decimal("0")
    reservation_hours = Decimal("0")
    inventory_hours = Decimal("0")
    last: datetime | None = None
    cutoff = max(window.end for window in windows)
    for timestamp, delta in sorted(changes.items()):
        if last is not None:
            end = min(timestamp, cutoff)
            if end > last:
                duration = _authorized_hours_between(last, end, windows)
                reservation_hours += reservation * duration
                inventory_hours += inventory * duration
        if timestamp > cutoff:
            break
        reservation += delta[0]
        inventory += delta[1]
        if reservation < 0 or inventory < 0:
            raise DayRunError("CAPITAL_HOURS_ACCOUNTING_INVALID")
        last = timestamp
    if last is not None and cutoff > last:
        duration = _authorized_hours_between(last, cutoff, windows)
        reservation_hours += reservation * duration
        inventory_hours += inventory * duration
    return reservation_hours, inventory_hours


def _terminal_mid(events: Sequence[MarketEvent]) -> TerminalMark:
    bids: dict[Decimal, Decimal] = {}
    asks: dict[Decimal, Decimal] = {}
    valid = False
    update_id: int | None = None
    mid: Decimal | None = None
    latest_l2_timestamp: datetime | None = None
    for event in events:
        if isinstance(event, BookSnapshotEvent):
            bids = {row.price: row.quantity for row in event.bids if row.quantity > 0}
            asks = {row.price: row.quantity for row in event.asks if row.quantity > 0}
            update_id = event.update_id
            valid = True
            latest_l2_timestamp = require_utc(event.timestamp)
        elif isinstance(event, BookDeltaEvent):
            if (
                not valid
                or update_id is None
                or not (event.first_update_id <= update_id + 1 <= event.final_update_id)
            ):
                valid = False
                update_id = None
                mid = None
                continue
            for row in event.bids:
                if row.quantity == 0:
                    bids.pop(row.price, None)
                else:
                    bids[row.price] = row.quantity
            for row in event.asks:
                if row.quantity == 0:
                    asks.pop(row.price, None)
                else:
                    asks[row.price] = row.quantity
            update_id = event.final_update_id
            latest_l2_timestamp = require_utc(event.timestamp)
        elif isinstance(event, FeedGapEvent):
            valid = False
            update_id = None
            mid = None
        elif isinstance(event, TradeEvent):
            side = bids if event.buyer_is_maker else asks
            if event.price in side:
                side[event.price] = max(Decimal("0"), side[event.price] - event.quantity)
                if side[event.price] == 0:
                    del side[event.price]
        if valid and bids and asks:
            mid = (max(bids) + min(asks)) / Decimal("2")
    return TerminalMark(
        mid=mid if valid and bids and asks else None,
        l2_timestamp=latest_l2_timestamp if valid and bids and asks else None,
    )


def _hours_between(start: datetime, end: datetime) -> Decimal:
    delta = require_utc(end) - require_utc(start)
    microseconds = Decimal(delta.days * 86_400 + delta.seconds) * Decimal("1000000") + Decimal(
        delta.microseconds
    )
    return microseconds / Decimal("3600000000")


def _authorized_hours_between(
    start: datetime, end: datetime, windows: Sequence[CampaignWindow]
) -> Decimal:
    if end <= start:
        return Decimal("0")
    total = Decimal("0")
    for window in windows:
        overlap_start = max(require_utc(start), window.start)
        overlap_end = min(require_utc(end), window.end)
        if overlap_end > overlap_start:
            total += _hours_between(overlap_start, overlap_end)
    return total


def _evaluate_gates(gates: Gates, scenarios: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for row in scenarios:
        cycles = int(row["l2_inferred_cycles"])
        negatives = int(row["negative_l2_inferred_cycles"])
        checks = {
            "min_l2_inferred_cycles": cycles >= gates.min_l2_inferred_cycles,
            "max_negative_l2_inferred_cycles": negatives <= gates.max_negative_cycles,
            "capital_conservation": (not gates.capital_conservation)
            or bool(row["capital_conservation_pass"]),
            "modeled_zero_loss": bool(row["modeled_zero_loss_pass"]),
        }
        rows.append(
            {
                "scenario": row["scenario"],
                "technical_checks": checks,
                "technical_passed": all(checks.values()),
                "economic_eligibility": PUBLIC_L2_QUEUE_LIMITATION,
            }
        )
    technical_passed = all(bool(row["technical_passed"]) for row in rows)
    return {
        "technical_passed": technical_passed,
        # Public L2 can bound displayed depth but cannot observe our queue rank,
        # order ACK, or venue fill.  It therefore never becomes an economic PASS.
        "passed": False,
        "verdict": "INCONCLUSIVE" if technical_passed else "FAIL",
        "economic_eligibility": PUBLIC_L2_QUEUE_LIMITATION,
        "scenarios": rows,
    }


def _write_reports(
    root: Path,
    job: DayJob,
    spec: FrozenModelSpec,
    tape: Mapping[str, Any],
    executions: Sequence[ScenarioExecution],
    gates: Mapping[str, Any],
    oracle: dict[str, Any] | None,
    campaign_dir: Path,
    source_binding: SourceBinding,
) -> ReportPaths:
    output = _resolve_under_root(root, job.output_dir, "output_dir", require_exists=False)
    output.mkdir(parents=True, exist_ok=True)
    summary = output / SUMMARY_NAME
    audit = output / AUDIT_NAME
    oracle_path = output / "ORACLE.json" if oracle is not None else None
    if summary.exists() or audit.exists() or (oracle_path is not None and oracle_path.exists()):
        raise DayRunError("OUTPUT_ARTIFACT_ALREADY_EXISTS")
    scenarios = [execution.metrics for execution in executions]
    scenario_paths = tuple(
        output / f"SCENARIO_{index:02d}_{execution.scenario.name}.json"
        for index, execution in enumerate(executions, start=1)
    )
    if any(path.exists() for path in scenario_paths):
        raise DayRunError("SCENARIO_EVIDENCE_ARTIFACT_ALREADY_EXISTS")
    for execution, path in zip(executions, scenario_paths, strict=True):
        _write_json_atomic(path, _scenario_evidence(execution, spec))
    fee_break_even = _fee_break_even(scenarios)
    summary_payload = {
        "schema_version": "crypto-lab-day-summary-v1",
        "status": "COMPLETE",
        "verdict": gates["verdict"],
        "model_id": spec.model_id,
        "identity": spec.identity,
        "parent": spec.parent,
        "day": job.day,
        "classification": spec.classification,
        "execution_engine": job.engine,
        "evidence_class": spec.evidence_class,
        "economic_eligibility": PUBLIC_L2_QUEUE_LIMITATION,
        "scenarios": scenarios,
        "fee_break_even": fee_break_even,
        "gates": gates,
        "not_live_claim": True,
        "not_oos_claim": True,
        "scenario_evidence": [_relative(root, path) for path in scenario_paths],
    }
    manifest = cast(Mapping[str, Any], tape["manifest"])
    audit_payload = {
        "schema_version": "crypto-lab-day-audit-v1",
        "status": "COMPLETE",
        "verdict": gates["verdict"],
        "model_id": spec.model_id,
        "identity": spec.identity,
        "job_sha256": _file_sha256(campaign_dir / "job.yaml"),
        "model_spec_sha256": spec.sha256,
        "job_contract_sha256": job.contract_sha256,
        "strategy_sha256": spec.strategy_sha256,
        "execution_source": asdict(source_binding),
        "fee_provenance": _temporal_provenance_audit(root, spec.fee_provenance),
        "rule_provenance": _temporal_provenance_audit(root, spec.rule_provenance),
        "evidence_class": spec.evidence_class,
        "economic_eligibility": PUBLIC_L2_QUEUE_LIMITATION,
        "tape_path": _relative(root, cast(Path, tape["path"])),
        "tape_sha256": tape["sha256"],
        "tape_manifest_path": manifest["path"],
        "tape_manifest_sha256": manifest["sha256"],
        "individual_trade_id_coverage": manifest["individual_trade_id_coverage"],
        "tape_source_files": manifest["source_files"],
        "current_state_sha256_before_day_run_record": _file_sha256(
            root / "docs/research/CURRENT_STATE.md"
        ),
        "windows": [
            {"start": window.start.isoformat(), "end": window.end.isoformat()}
            for window in job.windows
        ],
        "event_count": len(cast(list[MarketEvent], tape["events"])),
        "trade_count": sum(
            isinstance(event, TradeEvent) for event in cast(list[MarketEvent], tape["events"])
        ),
        "l2_event_count": sum(
            isinstance(event, (BookSnapshotEvent, BookDeltaEvent))
            for event in cast(list[MarketEvent], tape["events"])
        ),
        "max_l2_update_age_seconds": job.max_l2_update_age_seconds,
        "no_future_data": True,
        "capital_conservation": [
            {
                "scenario": row["scenario"],
                "quote_cash_balance_residual": row["quote_cash_balance_residual"],
                "base_balance_residual": row["base_balance_residual"],
                "locked_capital_residual_quote": row["locked_capital_residual_quote"],
                "marked_equity_residual_quote": row["marked_equity_residual_quote"],
                "capital_conservation_pass": row["capital_conservation_pass"],
                "negative_l2_inferred_cycles": row["negative_l2_inferred_cycles"],
            }
            for row in scenarios
        ],
        "scenario_evidence": [
            {
                "scenario": execution.scenario.name,
                "path": _relative(root, path),
                "sha256": _file_sha256(path),
                "run_id": execution.result.run_id,
                "modeled_orders": len(execution.result.orders),
                "l2_inferred_fills": len(execution.result.fills),
                "finished_at": execution.result.finished_at,
                "cancel_effective_at": [
                    order.cancel_effective_at
                    for order in execution.result.orders
                    if order.cancel_effective_at is not None
                ],
                "terminal_l2_timestamp": execution.metrics["terminal_l2_timestamp"],
                "terminal_l2_age_seconds_at_cutoff": execution.metrics[
                    "terminal_l2_age_seconds_at_cutoff"
                ],
            }
            for execution, path in zip(executions, scenario_paths, strict=True)
        ],
        "oracle_advisory_only": oracle is not None,
        "no_llm_or_network_data_access": True,
    }
    _write_json_atomic(summary, summary_payload)
    _write_json_atomic(audit, audit_payload)
    if oracle_path is not None and oracle is not None:
        _write_json_atomic(oracle_path, oracle)
    return ReportPaths(summary=summary, audit=audit, oracle=oracle_path, scenarios=scenario_paths)


def _scenario_evidence(execution: ScenarioExecution, spec: FrozenModelSpec) -> dict[str, Any]:
    """Write traceable counterfactual L2-queue evidence, never a venue-fill claim."""

    result = execution.result
    return {
        "schema_version": "crypto-lab-day-scenario-evidence-v1",
        "model_id": spec.model_id,
        "identity": spec.identity,
        "scenario": execution.scenario.name,
        "fee_bps_per_leg": str(execution.scenario.fee_bps),
        "engine": "PassiveExecutionSimulator",
        "evidence_class": spec.evidence_class,
        "economic_eligibility": PUBLIC_L2_QUEUE_LIMITATION,
        "queue_evidence": {
            "observed_at_order_price_required": True,
            "queue_ahead_interpretation": "KNOWN_DISPLAYED_AHEAD_ONLY",
            "time_priority": "UNKNOWN_WITHIN_EXISTING_LEVEL",
            "venue_order_ack_or_fill_receipt": False,
        },
        "asset_mapping": {
            "base_asset": spec.base_asset,
            "quote_asset": spec.quote_asset,
            "legacy_engine_cash_field": "usdc",
            "legacy_engine_inventory_field": "fdusd",
        },
        # These two blocks preserve implementation-level diagnostics.  Their
        # original ``usdc``/``fdusd`` labels are legacy engine fields, never a
        # statement about the physical USDC/USDT assets above.
        "legacy_engine_config": execution.config.model_dump(mode="json"),
        "metrics": execution.metrics,
        "result": {
            "run_id": result.run_id,
            "strategy_id": result.strategy_id,
            "dataset_hash": result.dataset_hash,
            "edge_status": result.edge_status,
            "queue_model": result.queue_model.value,
            "started_at": result.started_at,
            "finished_at": result.finished_at,
            "book_valid_at_end": result.book_valid_at_end,
            "book_invalidations": result.book_invalidations,
            "risk_halt": result.risk_halt,
            "risk_halt_reason": result.risk_halt_reason,
            "decisions": [item.model_dump(mode="json") for item in result.decisions],
            "modeled_orders": [item.model_dump(mode="json") for item in result.orders],
            "l2_inferred_fills": [item.model_dump(mode="json") for item in result.fills],
            "ledger": {
                "quote_balance": str(result.ledger.usdc),
                "base_balance": str(result.ledger.fdusd),
                "average_cost_quote_per_base": str(result.ledger.average_cost_usdc),
                "realized_pnl_quote": str(result.ledger.realized_pnl_usdc),
                "unrealized_pnl_quote": str(result.ledger.unrealized_pnl_usdc),
                "fees_quote": str(result.ledger.fees_usdc),
                "capital_locked_quote": str(result.ledger.capital_locked_usdc),
                "inventory_opened_at": result.ledger.inventory_opened_at,
                "inventory_age_seconds": str(result.ledger.inventory_age_seconds),
            },
            "legacy_engine_metrics": {key: str(value) for key, value in result.metrics.items()},
        },
    }


def _temporal_provenance_audit(
    root: Path, record: TemporalProvenance | None
) -> dict[str, Any] | None:
    if record is None:
        return None
    payload: dict[str, Any] = {
        "record_id": record.record_id,
        "path": _relative(root, record.path),
        "sha256": record.sha256,
        "venue": record.venue,
        "symbol": record.symbol,
        "effective": {
            "start": record.valid_from.isoformat(),
            "end": record.valid_until.isoformat(),
        },
        "acquired_at": record.acquired_at.isoformat(),
        "counterfactual_sensitivity_bps": [
            str(value) for value in record.counterfactual_sensitivity_bps
        ],
    }
    if record.rules is not None:
        payload["rules"] = {
            "min_price": str(record.rules.min_price),
            "max_price": str(record.rules.max_price),
            "tick_size": str(record.rules.tick_size),
            "min_quantity": str(record.rules.min_quantity),
            "max_quantity": str(record.rules.max_quantity),
            "step_size": str(record.rules.step_size),
            "min_notional": str(record.rules.min_notional),
            "max_notional": (
                None if record.rules.max_notional is None else str(record.rules.max_notional)
            ),
        }
    return payload


def _fee_break_even(scenarios: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    completed = [row for row in scenarios if int(row["l2_inferred_cycles"]) > 0]
    if not completed:
        return {"status": "NOT_ESTIMABLE_NO_COMPLETED_L2_INFERRED_CYCLE", "bps_per_leg": None}
    profitable = [
        row
        for row in completed
        if Decimal(str(row["final_marked_equity_quote"]))
        > Decimal(str(row["initial_equity_quote"]))
        and bool(row["modeled_zero_loss_pass"])
    ]
    if not profitable:
        return {
            "status": "NOT_ESTIMABLE_NO_PROFITABLE_L2_INFERRED_SCENARIO",
            "bps_per_leg": None,
        }
    highest = max(Decimal(str(row["fee_bps_per_leg"])) for row in profitable)
    return {
        "status": "COUNTERFACTUAL_LOWER_BOUND_FROM_L2_INFERRED_SCENARIOS",
        "bps_per_leg": str(highest),
    }


def _assert_prior_status_is_recoverable(path: Path) -> None:
    if not path.exists():
        return
    payload = _json_mapping(path, STATUS_PATH)
    if payload.get("state") != "PREFLIGHT_REJECTED":
        raise DayRunPreflightError("CAMPAIGN_ALREADY_CLAIMED_OR_COMPLETED")


def _record_preflight_rejection(
    status_path: Path,
    campaign_dir: Path,
    error: DayRunPreflightError,
    started_at: str,
    *,
    model_id: str | None,
) -> None:
    with _exclusive_status_lock(status_path):
        existing = _json_mapping(status_path, STATUS_PATH) if status_path.exists() else None
        # A malformed or terminal status is evidence, never an invitation to replace it.
        if existing is not None and existing.get("state") != "PREFLIGHT_REJECTED":
            return
        rejection = {
            "state": "PREFLIGHT_REJECTED",
            "started_at": started_at,
            "rejected_at": _now(),
            "error_type": type(error).__name__,
            "error": str(error),
        }
        history = _preflight_rejection_history(existing)
        _write_json_atomic(
            status_path,
            {
                "schema_version": "crypto-lab-day-run-status-v1",
                "state": "PREFLIGHT_REJECTED",
                "model_id": model_id,
                "campaign": str(campaign_dir),
                **rejection,
                "preflight_rejections": [*history, rejection],
                "rerun_allowed_after_preflight_correction": True,
            },
        )


def _claim_execution(
    path: Path,
    payload: Mapping[str, Any],
    *,
    verifier: Callable[[], ClaimValidation],
) -> tuple[dict[str, Any], ClaimValidation]:
    """Claim one execution while retaining any corrected-preflight history.

    A preflight rejection does not consume a model identity.  The exclusive lock
    serializes its transition to a real claim; all terminal states remain immutable.
    """

    with _exclusive_status_lock(path):
        prior_rejections: list[dict[str, Any]] = []
        if path.exists():
            prior = _json_mapping(path, STATUS_PATH)
            if prior.get("state") != "PREFLIGHT_REJECTED":
                raise DayRunPreflightError("CAMPAIGN_ALREADY_CLAIMED_OR_COMPLETED")
            prior_rejections = _preflight_rejection_history(prior)
            if not prior_rejections:
                prior_rejections = [
                    {
                        "state": "PREFLIGHT_REJECTED",
                        "started_at": prior.get("started_at"),
                        "rejected_at": prior.get("rejected_at"),
                        "error_type": prior.get("error_type"),
                        "error": prior.get("error"),
                    }
                ]
        validated = verifier()
        claimed = dict(payload)
        if prior_rejections:
            claimed["preflight_rejections"] = prior_rejections
        _write_json_atomic(path, claimed)
        return claimed, validated


@contextmanager
def _exclusive_status_lock(path: Path) -> Iterator[None]:
    """Serialize status writes; a leftover lock requires manual review, never retry."""

    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_name(f".{path.name}.claim.lock")
    try:
        descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
    except FileExistsError as error:
        raise DayRunPreflightError(
            "CAMPAIGN_STATUS_LOCK_EXISTS_REQUIRES_OPERATOR_REVIEW"
        ) from error
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(f"locked_at={_now()}\n")
            stream.flush()
            os.fsync(stream.fileno())
        yield
    finally:
        with suppress(FileNotFoundError):  # pragma: no cover - defensive filesystem race handling
            lock_path.unlink()


def _preflight_rejection_history(payload: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    if payload is None:
        return []
    value = payload.get("preflight_rejections")
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, Mapping)]


def _append_current_state_record(
    root: Path, job: DayJob, spec: FrozenModelSpec, status: Mapping[str, Any]
) -> None:
    path = root / "docs/research/CURRENT_STATE.md"
    status_binding = canonical_hash(
        {
            "model_id": spec.model_id,
            "day": job.day,
            "verdict": status["verdict"],
            "state": status["state"],
            "summary_path": status["summary_path"],
            "audit_path": status["audit_path"],
            "execution_source_commit": spec.execution_source_commit,
        }
    )
    record = (
        f"\n\nDAY_RUN_LAST_MODEL_ID={spec.model_id}\n"
        f"DAY_RUN_LAST_DAY={job.day}\n"
        f"DAY_RUN_LAST_VERDICT={status['verdict']}\n"
        f"DAY_RUN_LAST_STATUS={status['state']}\n"
        f"DAY_RUN_LAST_SUMMARY={status['summary_path']}\n"
        f"DAY_RUN_LAST_AUDIT={status['audit_path']}\n"
        f"DAY_RUN_LAST_SOURCE_COMMIT={spec.execution_source_commit}\n\n"
        f"DAY_RUN_LAST_STATUS_BINDING_SHA256={status_binding}\n\n"
        f"## Day-run record — {job.day} / {spec.model_id}\n\n"
        f"- Identity: `{spec.identity}`\n"
        f"- Verdict: `{status['verdict']}` ({status['state']})\n"
        f"- Summary: `{status['summary_path']}`\n"
        f"- Audit: `{status['audit_path']}`\n"
        f"- Status binding SHA-256: `{status_binding}`\n"
        "- This append-only runner record does not authorize LIVE, TESTNET, a rerun, or a "
        "subsequent model.\n"
    )
    original = path.read_text(encoding="utf-8")
    if f"## Day-run record — {job.day} / {spec.model_id}" in original:
        raise DayRunError("CURRENT_STATE_ALREADY_CONTAINS_DAY_RUN_RECORD")
    marker = original.find("<!--")
    updated = (
        original.rstrip() + record + "\n"
        if marker < 0
        else original[:marker].rstrip() + record + "\n" + original[marker:]
    )
    _write_text_atomic(path, updated)


def _parse_events(rows: Sequence[Any]) -> list[MarketEvent]:
    events: list[MarketEvent] = []
    for index, value in enumerate(rows):
        row = _as_mapping(value, f"events[{index}]")
        event_type = _string(row, "type")
        payload = {key: item for key, item in row.items() if key != "type"}
        try:
            if event_type == "snapshot":
                events.append(BookSnapshotEvent.model_validate(payload))
            elif event_type == "delta":
                events.append(BookDeltaEvent.model_validate(payload))
            elif event_type == "gap":
                events.append(FeedGapEvent.model_validate(payload))
            elif event_type == "halt":
                events.append(RiskHaltEvent.model_validate(payload))
            elif event_type == "trade":
                events.append(TradeEvent.model_validate(payload))
            else:
                raise DayRunPreflightError(f"UNKNOWN_TAPE_EVENT_TYPE:{event_type}")
        except ValidationError as error:
            raise DayRunPreflightError(f"INVALID_TAPE_EVENT:{index}:{error}") from error
    return events


def _validate_event_order(events: Sequence[MarketEvent]) -> None:
    previous: tuple[datetime, int] | None = None
    identities: set[tuple[datetime, int]] = set()
    trade_ids: set[int] = set()
    for event in events:
        identity = (require_utc(event.timestamp), event.sequence)
        if identity in identities or (previous is not None and identity <= previous):
            raise DayRunPreflightError("TAPE_EVENTS_MUST_BE_STRICTLY_ORDERED")
        identities.add(identity)
        previous = identity
        if isinstance(event, TradeEvent):
            if event.trade_id in trade_ids:
                raise DayRunPreflightError("TAPE_TRADE_IDS_MUST_BE_UNIQUE")
            trade_ids.add(event.trade_id)


def _validate_tape_processing_cutoff(
    events: Sequence[MarketEvent],
    cancellations: Sequence[CancelRequest],
    windows: Sequence[CampaignWindow],
    config: S0Config,
) -> None:
    """Ensure causal delivery, decision, and submission cannot spill past a cutoff."""

    action_delay = (
        config.latency.market_data + config.latency.decision + config.latency.order_submit
    )
    for event in events:
        window = _authorized_window_for(require_utc(event.timestamp), windows)
        if window is None:  # Kept defensive; caller has already checked event membership.
            raise DayRunPreflightError("TAPE_EVENT_OUTSIDE_FROZEN_WINDOW")
        if require_utc(event.timestamp) + action_delay >= window.end:
            raise DayRunPreflightError("TAPE_EVENT_TOO_CLOSE_TO_FROZEN_CUTOFF")
    for request in cancellations:
        window = _authorized_window_for(require_utc(request.requested_at), windows)
        if window is None:
            raise DayRunPreflightError("TAPE_CANCELLATION_OUTSIDE_FROZEN_WINDOW")
        if require_utc(request.requested_at) + config.latency.cancel >= window.end:
            raise DayRunPreflightError("TAPE_CANCELLATION_TOO_CLOSE_TO_FROZEN_CUTOFF")


def _validate_runtime_timestamps(
    result: MicrostructureRunResult, windows: Sequence[CampaignWindow]
) -> None:
    timestamps: list[tuple[str, datetime]] = [
        ("result.started_at", result.started_at),
        ("result.finished_at", result.finished_at),
    ]
    timestamps.extend(("decision", decision.decision_timestamp) for decision in result.decisions)
    for order in result.orders:
        timestamps.extend(
            (
                ("order.placed_at", order.placed_at),
                ("order.exchange_arrival_at", order.exchange_arrival_at),
            )
        )
        if order.cancel_requested_at is not None:
            timestamps.append(("order.cancel_requested_at", order.cancel_requested_at))
        if order.cancel_effective_at is not None:
            timestamps.append(("order.cancel_effective_at", order.cancel_effective_at))
    timestamps.extend(("fill", fill.timestamp) for fill in result.fills)
    for label, timestamp in timestamps:
        if _authorized_window_for(require_utc(timestamp), windows) is None:
            raise DayRunError(f"RUNTIME_TIMESTAMP_OUTSIDE_FROZEN_WINDOW:{label}")


def _validate_runtime_orders_against_rules(
    result: MicrostructureRunResult, spec: FrozenModelSpec
) -> None:
    record = spec.rule_provenance
    if record is None or record.rules is None:
        raise DayRunError("RUNTIME_RULE_PROVENANCE_MISSING")
    rules = record.rules
    for order in result.orders:
        if order.price < rules.min_price or order.price > rules.max_price:
            raise DayRunError("RUNTIME_ORDER_PRICE_OUTSIDE_FROZEN_RULE_BOUNDS")
        if order.quantity < rules.min_quantity or order.quantity > rules.max_quantity:
            raise DayRunError("RUNTIME_ORDER_QUANTITY_OUTSIDE_FROZEN_RULE_BOUNDS")
        _require_grid_multiple(order.price, rules.tick_size, "RUNTIME_ORDER_PRICE_OFF_FROZEN_TICK")
        _require_grid_multiple(
            order.quantity,
            rules.step_size,
            "RUNTIME_ORDER_QUANTITY_OFF_FROZEN_STEP",
        )
        notional = order.price * order.quantity
        if notional < rules.min_notional or (
            rules.max_notional is not None and notional > rules.max_notional
        ):
            raise DayRunError("RUNTIME_ORDER_NOTIONAL_OUTSIDE_FROZEN_RULE_BOUNDS")


def _validate_tape_events_against_rules(
    events: Sequence[MarketEvent], spec: FrozenModelSpec
) -> None:
    """Reject off-rule public L2/trade inputs before they affect fills or marks."""

    record = spec.rule_provenance
    if record is None or record.rules is None:
        raise DayRunPreflightError("TAPE_RULE_PROVENANCE_MISSING")
    rules = record.rules

    def validate_price(price: Decimal, label: str) -> None:
        if price < rules.min_price or price > rules.max_price:
            raise DayRunPreflightError(f"TAPE_PRICE_OUTSIDE_FROZEN_RULE_BOUNDS:{label}")
        _require_grid_multiple(price, rules.tick_size, f"TAPE_PRICE_OFF_FROZEN_RULE_TICK:{label}")

    def validate_book_quantity(quantity: Decimal, label: str) -> None:
        if quantity <= 0:
            raise DayRunPreflightError(f"TAPE_BOOK_QUANTITY_MUST_BE_POSITIVE:{label}")
        # L2 quantities are level aggregates, so an exchange per-order maximum
        # cannot be imposed on them.  They still must use the frozen lot step.
        _require_grid_multiple(
            quantity, rules.step_size, f"TAPE_BOOK_QUANTITY_OFF_RULE_STEP:{label}"
        )

    def validate_trade_quantity(quantity: Decimal, label: str) -> None:
        if quantity < rules.min_quantity or quantity > rules.max_quantity:
            raise DayRunPreflightError(f"TAPE_TRADE_QUANTITY_OUTSIDE_FROZEN_RULE_BOUNDS:{label}")
        _require_grid_multiple(
            quantity, rules.step_size, f"TAPE_TRADE_QUANTITY_OFF_RULE_STEP:{label}"
        )

    for event in events:
        if isinstance(event, (BookSnapshotEvent, BookDeltaEvent)):
            for side, levels in (("bids", event.bids), ("asks", event.asks)):
                for level in levels:
                    validate_price(level.price, side)
                    # Zero in a delta is a deletion marker, not an observed level.
                    if level.quantity == 0 and isinstance(event, BookDeltaEvent):
                        continue
                    validate_book_quantity(level.quantity, side)
        elif isinstance(event, TradeEvent):
            validate_price(event.price, "trade")
            validate_trade_quantity(event.quantity, "trade")


def _validate_trade_id_continuity(events: Sequence[MarketEvent]) -> None:
    """Require a complete native individual-trade stream, never sampled prints.

    A unique ID is insufficient for queue depletion: omitted public prints change
    the modeled queue.  The normalized source contract supports only contiguous
    native trade IDs; a provider whose IDs cannot prove that property is outside
    this narrow runner rather than silently treated as complete.
    """

    previous: int | None = None
    for event in events:
        if not isinstance(event, TradeEvent):
            continue
        if previous is not None and event.trade_id != previous + 1:
            raise DayRunPreflightError("TAPE_INDIVIDUAL_TRADE_IDS_NOT_CONTIGUOUS")
        previous = event.trade_id


def _validate_l2_update_coverage(
    events: Sequence[MarketEvent],
    windows: Sequence[CampaignWindow],
    max_age_seconds: int,
) -> None:
    """Reject an unobserved intra-window interval before it can carry an order.

    A fresh cutoff quote does not make an hours-long mid-window L2 hole safe.
    Every frozen window must have bounded snapshot/delta coverage, including its
    opening and cutoff intervals.  Feed gaps are rejected by ``_read_tape`` so a
    valid book never crosses a known disconnect in this v1 contract.
    """

    maximum = timedelta(seconds=max_age_seconds)
    last_l2_at: datetime | None = None
    for window in windows:
        updates = [
            event
            for event in events
            if window.start <= require_utc(event.timestamp) < window.end
            and isinstance(event, (BookSnapshotEvent, BookDeltaEvent))
        ]
        if not updates:
            raise DayRunPreflightError("TAPE_L2_COVERAGE_MISSING_IN_FROZEN_WINDOW")
        if last_l2_at is None and not isinstance(updates[0], BookSnapshotEvent):
            raise DayRunPreflightError("TAPE_L2_COVERAGE_REQUIRES_OPENING_SNAPSHOT")
        prior = window.start if last_l2_at is None else last_l2_at
        for event in updates:
            timestamp = require_utc(event.timestamp)
            if timestamp - prior > maximum:
                raise DayRunPreflightError("TAPE_L2_UPDATE_GAP_EXCEEDS_FROZEN_MAX_AGE")
            prior = timestamp
        if window.end - prior > maximum:
            raise DayRunPreflightError("TAPE_L2_CUTOFF_GAP_EXCEEDS_FROZEN_MAX_AGE")
        last_l2_at = prior


def _validate_l2_continuity(events: Sequence[MarketEvent]) -> None:
    """Require a continuous, non-crossed L2 book for every observed trade event."""

    update_id: int | None = None
    bids: dict[Decimal, Decimal] = {}
    asks: dict[Decimal, Decimal] = {}
    for event in events:
        if isinstance(event, BookSnapshotEvent):
            _validate_unique_l2_levels(event.bids, "snapshot.bids")
            _validate_unique_l2_levels(event.asks, "snapshot.asks")
            update_id = event.update_id
            bids = {level.price: level.quantity for level in event.bids if level.quantity > 0}
            asks = {level.price: level.quantity for level in event.asks if level.quantity > 0}
            if not bids or not asks or max(bids) >= min(asks):
                raise DayRunPreflightError("TAPE_L2_SNAPSHOT_INVALID")
        elif isinstance(event, BookDeltaEvent):
            _validate_unique_l2_levels(event.bids, "delta.bids")
            _validate_unique_l2_levels(event.asks, "delta.asks")
            contiguous = (
                update_id is not None
                and event.first_update_id <= update_id + 1 <= event.final_update_id
            )
            if not contiguous:
                raise DayRunPreflightError("TAPE_L2_SNAPSHOT_DELTA_CONTINUITY_INVALID")
            for level in event.bids:
                if level.quantity == 0:
                    bids.pop(level.price, None)
                else:
                    bids[level.price] = level.quantity
            for level in event.asks:
                if level.quantity == 0:
                    asks.pop(level.price, None)
                else:
                    asks[level.price] = level.quantity
            if not bids or not asks or max(bids) >= min(asks):
                raise DayRunPreflightError("TAPE_L2_BOOK_INVALID_AFTER_DELTA")
            update_id = event.final_update_id
        elif isinstance(event, FeedGapEvent):
            update_id = None
            bids = {}
            asks = {}
        elif isinstance(event, TradeEvent):
            if update_id is None or not bids or not asks or max(bids) >= min(asks):
                raise DayRunPreflightError("TAPE_TRADE_WITHOUT_CONTINUOUS_L2_BOOK")
            book = bids if event.buyer_is_maker else asks
            if event.price in book:
                book[event.price] = max(Decimal("0"), book[event.price] - event.quantity)
                if book[event.price] == 0:
                    del book[event.price]


def _validate_unique_l2_levels(levels: Sequence[Any], label: str) -> None:
    prices = [level.price for level in levels]
    if len(set(prices)) != len(prices):
        raise DayRunPreflightError(f"TAPE_DUPLICATE_L2_PRICE_LEVEL:{label}")


def _validate_l2_window_boundaries(
    events: Sequence[MarketEvent], windows: Sequence[CampaignWindow]
) -> None:
    """Do not carry a public L2 book across an unauthorized time discontinuity."""

    prior_window: CampaignWindow | None = None
    for window in windows:
        if prior_window is not None and window.start == prior_window.end:
            prior_window = window
            continue
        first_event = next(
            (
                event
                for event in events
                if window.start <= require_utc(event.timestamp) < window.end
            ),
            None,
        )
        if not isinstance(first_event, BookSnapshotEvent):
            raise DayRunPreflightError("TAPE_DISCONTIGUOUS_WINDOW_REQUIRES_L2_SNAPSHOT")
        prior_window = window


def _validate_terminal_l2_freshness(
    events: Sequence[MarketEvent],
    windows: Sequence[CampaignWindow],
    max_age_seconds: int,
) -> None:
    """Require a continuous, fresh reconstructed L2 mark at every frozen cutoff.

    The simulator may finish with an old book after all events are consumed.  That
    is not a mark at the cutoff, so replay the public L2/trade updates here and
    fail before claiming an identity when the final book is stale, invalid, or
    crossed.
    """

    bids: dict[Decimal, Decimal] = {}
    asks: dict[Decimal, Decimal] = {}
    update_id: int | None = None
    latest_l2_at: datetime | None = None
    event_index = 0

    def apply(event: MarketEvent) -> None:
        nonlocal asks, bids, latest_l2_at, update_id
        if isinstance(event, BookSnapshotEvent):
            bids = {level.price: level.quantity for level in event.bids if level.quantity > 0}
            asks = {level.price: level.quantity for level in event.asks if level.quantity > 0}
            update_id = event.update_id
            latest_l2_at = require_utc(event.timestamp)
        elif isinstance(event, BookDeltaEvent):
            for level in event.bids:
                if level.quantity == 0:
                    bids.pop(level.price, None)
                else:
                    bids[level.price] = level.quantity
            for level in event.asks:
                if level.quantity == 0:
                    asks.pop(level.price, None)
                else:
                    asks[level.price] = level.quantity
            update_id = event.final_update_id
            latest_l2_at = require_utc(event.timestamp)
        elif isinstance(event, FeedGapEvent):
            bids = {}
            asks = {}
            update_id = None
            latest_l2_at = None
        elif isinstance(event, TradeEvent):
            book = bids if event.buyer_is_maker else asks
            if event.price in book:
                book[event.price] = max(Decimal("0"), book[event.price] - event.quantity)
                if book[event.price] == 0:
                    del book[event.price]

    for window in windows:
        while event_index < len(events) and require_utc(events[event_index].timestamp) < window.end:
            apply(events[event_index])
            event_index += 1
        if (
            update_id is None
            or latest_l2_at is None
            or not bids
            or not asks
            or max(bids) >= min(asks)
        ):
            raise DayRunPreflightError("TAPE_TERMINAL_L2_BOOK_INVALID_AT_CUTOFF")
        age = window.end - latest_l2_at
        if age > timedelta(seconds=max_age_seconds):
            raise DayRunPreflightError("TAPE_TERMINAL_L2_MARK_TOO_STALE_AT_CUTOFF")


def _read_tape_manifest(
    root: Path,
    tape_path: Path,
    tape_sha256: str,
    spec: FrozenModelSpec,
    job: DayJob,
    tape_events: Sequence[MarketEvent],
) -> dict[str, Any]:
    if spec.tape_manifest_path is None or spec.tape_manifest_sha256 is None:
        raise DayRunPreflightError("AUTHORIZED_TAPE_MANIFEST_REQUIRED")
    manifest_path = _resolve_under_root(
        root, spec.tape_manifest_path, "execution.tape_manifest_path"
    )
    actual_manifest_sha256 = _file_sha256(manifest_path)
    if actual_manifest_sha256 != spec.tape_manifest_sha256:
        raise DayRunPreflightError("TAPE_MANIFEST_HASH_DOES_NOT_MATCH_FROZEN_MODEL_SPEC")
    raw = _json_mapping(manifest_path, "tape manifest")
    if raw.get("schema_version") != TAPE_MANIFEST_SCHEMA:
        raise DayRunPreflightError("TAPE_MANIFEST_SCHEMA_UNSUPPORTED")
    if _string(raw, "venue") != "BINANCE_SPOT":
        raise DayRunPreflightError("TAPE_MANIFEST_VENUE_MISMATCH")
    if _string(raw, "symbol").upper() != spec.symbol:
        raise DayRunPreflightError("TAPE_MANIFEST_SYMBOL_MISMATCH")
    manifest_tape = Path(_string(raw, "tape_path"))
    manifest_tape_path = _resolve_under_root(root, manifest_tape, "tape_manifest.tape_path")
    same_tape = _relative(root, manifest_tape_path) == _relative(root, tape_path)
    if manifest_tape.is_absolute() or not same_tape:
        raise DayRunPreflightError("TAPE_MANIFEST_TAPE_PATH_MISMATCH")
    if _sha256_value(_string(raw, "tape_sha256"), "tape_manifest.tape_sha256") != tape_sha256:
        raise DayRunPreflightError("TAPE_MANIFEST_TAPE_HASH_MISMATCH")
    manifest_windows = tuple(
        _window(_as_mapping(value, f"tape_manifest.windows[{index}]"))
        for index, value in enumerate(_sequence(raw, "windows"))
    )
    if not manifest_windows or _windows_token(manifest_windows) != _windows_token(job.windows):
        raise DayRunPreflightError("TAPE_MANIFEST_WINDOW_MISMATCH")
    if _string(raw, "l2_snapshot_delta_validation") != "PASS":
        raise DayRunPreflightError("TAPE_MANIFEST_L2_VALIDATION_NOT_PASS")
    if _string(raw, "individual_trade_binding") != "PASS":
        raise DayRunPreflightError("TAPE_MANIFEST_TRADE_BINDING_NOT_PASS")
    trade_coverage = _mapping(raw, "individual_trade_id_coverage")
    _require_exact_fields(
        trade_coverage,
        {"mode", "first_trade_id", "last_trade_id"},
        "TAPE_MANIFEST_TRADE_ID_COVERAGE",
    )
    if _string(trade_coverage, "mode") != "CONTIGUOUS_NATIVE_IDS":
        raise DayRunPreflightError("TAPE_MANIFEST_TRADE_ID_COVERAGE_UNSUPPORTED")
    trade_ids = [event.trade_id for event in tape_events if isinstance(event, TradeEvent)]
    if not trade_ids:
        raise DayRunPreflightError("TAPE_MANIFEST_TRADE_ID_COVERAGE_REQUIRES_TRADES")
    if (
        _integer(trade_coverage.get("first_trade_id"), "trade_id_coverage.first_trade_id")
        != trade_ids[0]
        or _integer(trade_coverage.get("last_trade_id"), "trade_id_coverage.last_trade_id")
        != trade_ids[-1]
    ):
        raise DayRunPreflightError("TAPE_MANIFEST_TRADE_ID_COVERAGE_MISMATCH")
    if _bool(raw, "no_future_data") is not True:
        raise DayRunPreflightError("TAPE_MANIFEST_FUTURE_DATA_NOT_REJECTED")
    source_files = _sequence(raw, "source_files")
    if not source_files:
        raise DayRunPreflightError("TAPE_MANIFEST_REQUIRES_SOURCE_FILES")
    required_roles = {"L2_SNAPSHOT_DELTA", "INDIVIDUAL_TRADES"}
    source_roles: set[str] = set()
    source_paths: set[Path] = set()
    source_events: Counter[str] = Counter()
    verified_sources: list[dict[str, Any]] = []
    for index, value in enumerate(source_files):
        source = _as_mapping(value, f"tape_manifest.source_files[{index}]")
        role = _string(source, "role")
        if role not in required_roles:
            raise DayRunPreflightError("TAPE_MANIFEST_SOURCE_ROLE_UNSUPPORTED")
        if role in source_roles:
            raise DayRunPreflightError("TAPE_MANIFEST_SOURCE_ROLE_MUST_BE_UNIQUE")
        source_roles.add(role)
        source_path_value = Path(_string(source, "path"))
        if source_path_value.is_absolute():
            raise DayRunPreflightError("TAPE_MANIFEST_SOURCE_PATH_MUST_BE_RELATIVE")
        source_path = _resolve_under_root(root, source_path_value, "tape_manifest.source_file")
        if source_path in {tape_path, manifest_path}:
            raise DayRunPreflightError("TAPE_MANIFEST_SOURCE_MUST_NOT_SELF_ATTEST")
        if source_path in source_paths:
            raise DayRunPreflightError("TAPE_MANIFEST_SOURCE_PATH_MUST_BE_UNIQUE")
        source_paths.add(source_path)
        source_sha256 = _sha256_value(
            _string(source, "sha256"), f"tape_manifest.source_files[{index}].sha256"
        )
        if _file_sha256(source_path) != source_sha256:
            raise DayRunPreflightError("TAPE_MANIFEST_SOURCE_FILE_HASH_MISMATCH")
        parsed_source_events = _read_normalized_event_source(source_path, role, spec.symbol)
        source_events.update(_event_fingerprint(event) for event in parsed_source_events)
        verified_sources.append(
            {
                "role": role,
                "path": _relative(root, source_path),
                "sha256": source_sha256,
                "event_count": len(parsed_source_events),
            }
        )
    if source_roles != required_roles:
        raise DayRunPreflightError("TAPE_MANIFEST_REQUIRES_L2_AND_INDIVIDUAL_TRADE_SOURCES")
    tape_fingerprints = Counter(_event_fingerprint(event) for event in tape_events)
    if source_events != tape_fingerprints:
        raise DayRunPreflightError("TAPE_MANIFEST_SOURCE_EVENTS_DO_NOT_MATCH_TAPE")
    return {
        "path": _relative(root, manifest_path),
        "sha256": actual_manifest_sha256,
        "individual_trade_id_coverage": trade_coverage,
        "source_files": verified_sources,
    }


def _read_normalized_event_source(path: Path, role: str, symbol: str) -> list[MarketEvent]:
    """Read one hash-bound local source projection and constrain its event role.

    An acquisition pipeline may normalize provider bytes into this schema, but it
    cannot simply self-attest arbitrary metadata: the parsed source-event multiset
    must exactly reconstruct the frozen tape in the manifest validator above.
    """

    raw = _json_mapping(path, "normalized event source")
    if raw.get("schema_version") != RAW_EVENT_SOURCE_SCHEMA:
        raise DayRunPreflightError("NORMALIZED_EVENT_SOURCE_SCHEMA_UNSUPPORTED")
    if _string(raw, "venue") != "BINANCE_SPOT":
        raise DayRunPreflightError("NORMALIZED_EVENT_SOURCE_VENUE_MISMATCH")
    if _string(raw, "symbol").upper() != symbol:
        raise DayRunPreflightError("NORMALIZED_EVENT_SOURCE_SYMBOL_MISMATCH")
    events = _parse_events(_sequence(raw, "events"))
    if not events:
        raise DayRunPreflightError("NORMALIZED_EVENT_SOURCE_MUST_NOT_BE_EMPTY")
    _validate_event_order(events)
    allowed_types: tuple[type[MarketEvent], ...]
    if role == "L2_SNAPSHOT_DELTA":
        allowed_types = (BookSnapshotEvent, BookDeltaEvent)
    else:
        allowed_types = (TradeEvent,)
    if any(not isinstance(event, allowed_types) for event in events):
        raise DayRunPreflightError("NORMALIZED_EVENT_SOURCE_ROLE_CONTENT_MISMATCH")
    return events


def _event_fingerprint(event: MarketEvent) -> str:
    if isinstance(event, BookSnapshotEvent):
        event_type = "snapshot"
    elif isinstance(event, BookDeltaEvent):
        event_type = "delta"
    elif isinstance(event, FeedGapEvent):
        event_type = "gap"
    elif isinstance(event, RiskHaltEvent):
        event_type = "halt"
    else:
        event_type = "trade"
    return canonical_hash({"type": event_type, **event.model_dump(mode="json")})


def _parse_cancellations(value: Any) -> list[CancelRequest]:
    rows = value if isinstance(value, list) else None
    if rows is None:
        raise DayRunPreflightError("TAPE_CANCELLATIONS_MUST_BE_A_LIST")
    try:
        return [CancelRequest.model_validate(_as_mapping(row, "cancellation")) for row in rows]
    except ValidationError as error:
        raise DayRunPreflightError(f"INVALID_TAPE_CANCELLATION:{error}") from error


def _window(raw: Mapping[str, Any]) -> CampaignWindow:
    start = _timestamp(_string(raw, "start"), "window.start")
    end = _timestamp(_string(raw, "end"), "window.end")
    if end <= start:
        raise DayRunPreflightError("WINDOW_END_MUST_FOLLOW_START")
    return CampaignWindow(start=start, end=end)


def _windows(raw: Mapping[str, Any]) -> tuple[CampaignWindow, ...]:
    has_window = "window" in raw
    has_windows = "windows" in raw
    if has_window == has_windows:
        raise DayRunPreflightError("DAY_JOB_REQUIRES_EXACTLY_ONE_OF_WINDOW_OR_WINDOWS")
    if has_window:
        return (_window(_mapping(raw, "window")),)
    values = _sequence(raw, "windows")
    windows = tuple(
        _window(_as_mapping(value, f"windows[{index}]")) for index, value in enumerate(values)
    )
    if not windows:
        raise DayRunPreflightError("DAY_JOB_WINDOWS_MUST_NOT_BE_EMPTY")
    if any(current.start != previous.end for previous, current in pairwise(windows)):
        raise DayRunPreflightError("DAY_RUN_WINDOWS_MUST_BE_CONTIGUOUS")
    return windows


def _is_in_authorized_window(timestamp: datetime, windows: Sequence[CampaignWindow]) -> bool:
    return _authorized_window_for(timestamp, windows) is not None


def _authorized_window_for(
    timestamp: datetime, windows: Sequence[CampaignWindow]
) -> CampaignWindow | None:
    return next(
        (window for window in windows if window.start <= require_utc(timestamp) < window.end),
        None,
    )


def _scenario(value: Any, index: int) -> Scenario:
    raw = _as_mapping(value, f"scenarios[{index}]")
    mode = _string(raw, "mode")
    if mode not in {"single", "parallel"}:
        raise DayRunPreflightError("SCENARIO_MODE_MUST_BE_SINGLE_OR_PARALLEL")
    fee_bps = _decimal(raw.get("fee_bps"), f"scenarios[{index}].fee_bps")
    if fee_bps < 0:
        raise DayRunPreflightError("SCENARIO_FEE_BPS_MUST_BE_NON_NEGATIVE")
    name = _string(raw, "name")
    if _SCENARIO_NAME.fullmatch(name) is None:
        raise DayRunPreflightError("SCENARIO_NAME_INVALID")
    return Scenario(name=name, fee_bps=fee_bps, mode=cast(Any, mode))


def _oracle(raw: Mapping[str, Any]) -> OraclePlan:
    backend = _string(raw, "backend")
    if backend not in {"cpu", "gpu", "auto"}:
        raise DayRunPreflightError("ORACLE_BACKEND_MUST_BE_CPU_GPU_OR_AUTO")
    candidates: list[tuple[int, int]] = []
    for index, value in enumerate(raw.get("candidates", [])):
        candidate = _as_mapping(value, f"oracle.candidates[{index}]")
        low_tick = _integer(candidate.get("low_tick"), "oracle low_tick")
        distance = _integer(candidate.get("distance"), "oracle distance")
        if distance <= 0:
            raise DayRunPreflightError("ORACLE_CANDIDATE_DISTANCE_MUST_BE_POSITIVE")
        candidates.append((low_tick, distance))
    if len(set(candidates)) != len(candidates):
        raise DayRunPreflightError("ORACLE_CANDIDATES_MUST_BE_UNIQUE")
    return OraclePlan(backend=cast(Any, backend), candidates=tuple(candidates))


def _gates(raw: Mapping[str, Any]) -> Gates:
    minimum = _integer(raw.get("min_l2_inferred_cycles"), "gates.min_l2_inferred_cycles")
    maximum = _integer(raw.get("max_negative_cycles"), "gates.max_negative_cycles")
    if minimum < 0 or maximum < 0:
        raise DayRunPreflightError("GATES_MUST_BE_NON_NEGATIVE")
    return Gates(
        min_l2_inferred_cycles=minimum,
        max_negative_cycles=maximum,
        capital_conservation=_bool(raw, "capital_conservation"),
    )


def _current_state_binding(raw: Mapping[str, Any]) -> CurrentStateBinding:
    return CurrentStateBinding(
        next_campaign_status=_string(raw, "next_campaign_status"),
        next_campaign_model_hash=_string(raw, "next_campaign_model_hash"),
        next_campaign_window=_string(raw, "next_campaign_window"),
    )


def _current_state_head(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("<!--"):
            break
        if "=" not in line or line.startswith("#"):
            continue
        key, value = line.split("=", 1)
        if re.fullmatch(r"[A-Z][A-Z0-9_]*", key):
            values.setdefault(key, value.strip())
    return values


def _report_directory(root: Path, value: str) -> Path:
    path = Path(value)
    output_path = (root / path).resolve()
    reports_root = (root / "reports").resolve()
    if path.is_absolute() or not _is_relative_to(output_path, reports_root):
        raise DayRunPreflightError("OUTPUT_DIR_MUST_BE_UNDER_REPORTS")
    return path


def _resolve_under_root(
    root: Path, value: Path, label: str, *, require_exists: bool = True
) -> Path:
    resolved = (root / value).resolve() if not value.is_absolute() else value.resolve()
    if not _is_relative_to(resolved, root):
        raise DayRunPreflightError(f"{label.upper().replace('.', '_')}_ESCAPES_REPOSITORY")
    if require_exists and not resolved.exists():
        raise DayRunPreflightError(f"{label.upper().replace('.', '_')}_MISSING")
    return resolved


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _relative(root: Path, path: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def _yaml_mapping(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise DayRunPreflightError(f"{label.upper().replace('.', '_')}_MISSING")
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as error:
        raise DayRunPreflightError(f"{label.upper().replace('.', '_')}_INVALID") from error
    return _as_mapping(raw, label)


def _json_mapping(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise DayRunPreflightError(f"{label.upper().replace('.', '_')}_MISSING")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise DayRunPreflightError(f"{label.upper().replace('.', '_')}_INVALID") from error
    return _as_mapping(raw, label)


def _as_mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise DayRunPreflightError(f"{label.upper().replace('.', '_')}_MUST_BE_AN_OBJECT")
    return cast(dict[str, Any], value)


def _mapping(raw: Mapping[str, Any], key: str) -> dict[str, Any]:
    if key not in raw:
        raise DayRunPreflightError(f"MISSING_REQUIRED_FIELD:{key}")
    return _as_mapping(raw[key], key)


def _sequence(raw: Mapping[str, Any], key: str) -> list[Any]:
    value = raw.get(key)
    if not isinstance(value, list):
        raise DayRunPreflightError(f"{key.upper()}_MUST_BE_A_LIST")
    return value


def _string(raw: Mapping[str, Any], key: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value.strip():
        raise DayRunPreflightError(f"MISSING_OR_INVALID_STRING:{key}")
    return value.strip()


def _bool(raw: Mapping[str, Any], key: str) -> bool:
    value = raw.get(key)
    if not isinstance(value, bool):
        raise DayRunPreflightError(f"MISSING_OR_INVALID_BOOLEAN:{key}")
    return value


def _integer(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise DayRunPreflightError(f"MISSING_OR_INVALID_INTEGER:{label}")
    return cast(int, value)


def _decimal(value: Any, label: str) -> Decimal:
    try:
        decimal = Decimal(str(value))
    except Exception as error:
        raise DayRunPreflightError(f"MISSING_OR_INVALID_DECIMAL:{label}") from error
    if not decimal.is_finite():
        raise DayRunPreflightError(f"MISSING_OR_INVALID_DECIMAL:{label}")
    return decimal


def _optional_decimal(value: Any, label: str) -> Decimal | None:
    if value is None:
        return None
    return _decimal(value, label)


def _string_list(value: Any, label: str) -> list[str]:
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item.strip() for item in value
    ):
        raise DayRunPreflightError(f"{label.upper()}_MUST_BE_A_STRING_LIST")
    return [item.strip() for item in value]


def _model_id(raw: Mapping[str, Any], key: str) -> str:
    value = _string(raw, key)
    if _MODEL_ID.fullmatch(value) is None:
        raise DayRunPreflightError(f"INVALID_MODEL_ID:{key}")
    return value


def _sha256_value(value: str, label: str) -> str:
    if _SHA256.fullmatch(value) is None:
        raise DayRunPreflightError(f"INVALID_SHA256:{label}")
    return value


def _optional_sha256(value: Any, label: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise DayRunPreflightError(f"INVALID_SHA256:{label}")
    return _sha256_value(value, label)


def _optional_relative_path(value: Any, label: str) -> Path | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise DayRunPreflightError(f"MISSING_OR_INVALID_RELATIVE_PATH:{label}")
    path = Path(value.strip())
    if path.is_absolute():
        raise DayRunPreflightError(f"RELATIVE_PATH_REQUIRED:{label}")
    return path


def _timestamp(value: str, label: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    try:
        timestamp = datetime.fromisoformat(normalized)
    except ValueError as error:
        raise DayRunPreflightError(f"INVALID_UTC_TIMESTAMP:{label}") from error
    if timestamp.tzinfo is None or timestamp.utcoffset() != UTC.utcoffset(timestamp):
        raise DayRunPreflightError(f"TIMESTAMP_MUST_BE_UTC:{label}")
    return timestamp.astimezone(UTC)


def _parse_day(value: str) -> date:
    if re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value) is None:
        raise DayRunPreflightError("DAY_MUST_USE_YYYY_MM_DD")
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise DayRunPreflightError("DAY_MUST_USE_YYYY_MM_DD") from error


def _utc_token(timestamp: datetime) -> str:
    return require_utc(timestamp).isoformat().replace("+00:00", "Z")


def _windows_token(windows: Sequence[CampaignWindow]) -> str:
    return ",".join(f"{_utc_token(window.start)}/{_utc_token(window.end)}" for window in windows)


def _file_sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _write_json_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(payload, stream, indent=2, sort_keys=True, default=str)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def _write_text_atomic(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(value)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def _now() -> str:
    return datetime.now(UTC).isoformat()


__all__ = ["DayRunError", "DayRunOutcome", "DayRunPreflightError", "run_day_campaign"]
