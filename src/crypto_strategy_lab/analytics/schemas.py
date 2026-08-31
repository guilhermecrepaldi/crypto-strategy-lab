from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ReportProvenance(BaseModel):
    model_config = ConfigDict(frozen=True)

    dataset_hash: str
    period_start: str
    period_end: str
    timeframe: str
    symbols: list[str]
    configuration: dict[str, Any]
    seed: int | None
    policy: str
    execution_costs: dict[str, str]
    code_version: str
    integrity_status: Literal["VALID", "INVALID"] = "VALID"
    source: str = "BINANCE_PUBLIC_DATA_SPOT_MONTHLY_KLINES"
    partition: Literal["TRAIN", "VALIDATION"]
    locked_test_accessed: bool = False


class CostBreakdownReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    schema_version: str = "cost-breakdown-v1"
    initial_equity_usdt: str
    final_equity_usdt: str
    costless_final_equity_usdt: str
    market_return_percent: dict[str, str]
    gross_pnl_usdt: str
    net_pnl_usdt: str
    loss_exclusively_from_costs_usdt: str
    direct_fees_usdt: str
    direct_spread_usdt: str
    direct_slippage_usdt: str
    direct_costs_usdt: str
    reconciliation_difference_usdt: str
    conservation_error_usdt: str
    per_asset_realized_pnl_usdt: dict[str, str]
    per_asset_costs_usdt: dict[str, str]
    ruin_reason: str | None


class TurnoverDiagnosticReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    schema_version: str = "turnover-diagnostic-v1"
    run_id: str
    provenance: ReportProvenance
    costs: CostBreakdownReport
    buys: int
    sells: int
    rotations: int
    operations: int
    avoided_operations: dict[str, int]
    total_turnover: str
    average_position_duration_steps: str
    average_exposure_ratio: str
    time_in_usdt_ratio: str
    max_drawdown: str
    terminated: bool
    truncated: bool
    warning: str
    transitions: list[dict[str, Any]] = Field(default_factory=list)


class DivergenceReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    schema_version: str = "divergence-report-v1"
    provenance: ReportProvenance
    alignment: dict[str, Any]
    pairwise: list[dict[str, Any]]
    rolling_context: dict[str, Any]
    strong_btc_events: dict[str, Any]
    relative_strength: dict[str, Any]
    causal_feature_contract: dict[str, Any]
    post_event_analysis: dict[str, Any]


class DashboardManifest(BaseModel):
    model_config = ConfigDict(frozen=True)

    schema_version: str = "dashboard-manifest-v1"
    run_id: str
    report_hash: str
    divergence_hash: str | None
    output_sha256: str
    sections: list[str]
    offline: bool = True
    external_resources: list[str] = Field(default_factory=list)
    warning: str


class LearningGateReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    schema_version: str = "learning-gates-v1"
    technical: str
    survival: str
    value: str
    classification: str
    reasons: dict[str, list[str]]


class ControlledTrainingReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    schema_version: str = "controlled-training-report-v1"
    phase: Literal["sanity", "development", "candidate"]
    dataset_hash: str
    partitions: dict[str, Any]
    action_mapping: dict[str, str]
    requested_timesteps_per_run: int
    seeds: list[int]
    algorithms: list[str]
    feature_variants: list[str]
    configuration_variants: list[str]
    runs: list[dict[str, Any]]
    internal_train_baselines: list[dict[str, Any]]
    validation_observed: bool = False
    locked_test_accessed: bool = False
    warning: str

    @model_validator(mode="after")
    def require_every_reported_seed(self) -> ControlledTrainingReport:
        run_seeds = {int(item["seed"]) for item in self.runs}
        if run_seeds != set(self.seeds):
            raise ValueError("all run seeds must be declared; best-seed filtering is forbidden")
        groups: dict[tuple[str, str, str], set[int]] = {}
        for item in self.runs:
            key = (
                str(item["algorithm"]),
                str(item["feature_variant"]),
                str(item["configuration_variant"]),
            )
            groups.setdefault(key, set()).add(int(item["seed"]))
        if any(group_seeds != set(self.seeds) for group_seeds in groups.values()):
            raise ValueError(
                "every algorithm/feature/configuration group must report every seed; "
                "best-seed filtering is forbidden"
            )
        identities = [
            (
                item["algorithm"],
                int(item["seed"]),
                item["feature_variant"],
                item["configuration_variant"],
            )
            for item in self.runs
        ]
        if len(identities) != len(set(identities)):
            raise ValueError("training report cannot contain duplicate run identities")
        expected_mapping = {
            "0": "USDT",
            "1": "BTCUSDT",
            "2": "ETHUSDT",
            "3": "SHIBUSDT",
            "4": "BNBUSDT",
        }
        if self.action_mapping != expected_mapping:
            raise ValueError("controlled report action mapping is immutable")
        return self


class ControlledValidationReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    schema_version: str = "controlled-validation-report-v1"
    source_training_phase: Literal["development", "candidate"]
    dataset_hash: str
    frozen_configuration_hash: str
    partition: dict[str, Any]
    runs: list[dict[str, Any]]
    baselines: list[dict[str, Any]]
    distributions: list[dict[str, Any]]
    gates: LearningGateReport
    validation_observed: bool = True
    locked_test_accessed: bool = False
    warning: str
