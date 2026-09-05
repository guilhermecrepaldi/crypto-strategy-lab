from __future__ import annotations

import gzip
import hashlib
import inspect
import json
from collections.abc import Callable
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from statistics import median
from typing import Any

from crypto_strategy_lab.analytics.schemas import ControlledTrainingReport
from crypto_strategy_lab.data.history import HistoricalDatasetManifest, load_normalized_history
from crypto_strategy_lab.data.temporal import TemporalMarketData
from crypto_strategy_lab.domain import canonical_hash
from crypto_strategy_lab.ml.controls import TurnoverControlConfig
from crypto_strategy_lab.ml.environment import CryptoRotationEnv, EnvironmentConfig
from crypto_strategy_lab.ml.evaluation import EvaluationResult, EvaluationRunner
from crypto_strategy_lab.ml.features import FeaturePipeline, FeatureSetSpec, fit_train_normalizer
from crypto_strategy_lab.ml.partitions import PartitionName, TemporalPartition
from crypto_strategy_lab.ml.policies import (
    BuyAndHoldPolicy,
    CashPolicy,
    CostAwareMomentum24hPolicy,
    DiscretePolicy,
    MomentumPolicy,
)
from crypto_strategy_lab.ml.reward import RewardConfig

TRAIN_START = datetime.fromisoformat("2022-01-01T00:00:00+00:00")
TRAIN_END = datetime.fromisoformat("2022-04-01T00:00:00+00:00")
NORMALIZER_START = datetime.fromisoformat("2021-12-01T00:00:00+00:00")
SEEDS = (11, 29, 42)
PRIMARY_PERIODS = (
    ("TRAIN_30D_1", TRAIN_START, 30),
    ("TRAIN_30D_2", datetime.fromisoformat("2022-01-31T00:00:00+00:00"), 30),
    ("TRAIN_30D_3", datetime.fromisoformat("2022-03-02T00:00:00+00:00"), 30),
)
SENSITIVITY_PERIODS = (("TRAIN_90D", TRAIN_START, 90),)


def run_candidate_strategy(
    manifest_path: Path,
    *,
    development_report_path: Path,
    artifact_root: Path,
    output: Path,
) -> dict[str, Any]:
    manifest = HistoricalDatasetManifest.model_validate_json(manifest_path.read_text())
    development = ControlledTrainingReport.model_validate_json(development_report_path.read_text())
    _require_train_only_gate(manifest, development)
    candles = load_normalized_history(Path(manifest.normalized_path))
    market = TemporalMarketData(candles)
    symbols = ("BTCUSDT", "ETHUSDT", "SHIBUSDT", "BNBUSDT")
    if set(market.symbols) != set(symbols):
        raise ValueError("candidate requires the frozen four-asset development universe")

    partition = TemporalPartition(name=PartitionName.TRAIN, start=TRAIN_START, end=TRAIN_END)
    normalizer_partition = TemporalPartition(
        name=PartitionName.TRAIN,
        start=NORMALIZER_START,
        end=TRAIN_START,
    )
    feature_spec = FeatureSetSpec()
    normalizer = fit_train_normalizer(
        FeaturePipeline(market, symbols, feature_spec),
        normalizer_partition,
        Decimal("100"),
    )
    base_config = _candidate_environment_config(30)
    implementation_hash = hashlib.sha256(
        inspect.getsource(CostAwareMomentum24hPolicy).encode("utf-8")
    ).hexdigest()
    identity = {
        "schema_version": "strategy-candidate-identity-v1",
        "name": CostAwareMomentum24hPolicy.name,
        "implementation_sha256": implementation_hash,
        "dataset_hash": manifest.dataset_hash,
        "partition": {"name": "TRAIN", "start": TRAIN_START, "end": TRAIN_END},
        "normalizer_fit": {"start": NORMALIZER_START, "end": TRAIN_START},
        "symbols": symbols,
        "action_mapping": {
            "0": "USDT",
            "1": "BTCUSDT",
            "2": "ETHUSDT",
            "3": "SHIBUSDT",
            "4": "BNBUSDT",
        },
        "initial_capital_usdt": "100",
        "max_exposure": "0.75",
        "reserve_ratio": "0.25",
        "hurdle": "0.0056",
        "decision_hours_utc": [0, 4, 8, 12, 16, 20],
        "momentum_candles": 289,
        "momentum_intervals": 288,
        "costs": {key: str(value) for key, value in base_config.costs.__dict__.items()},
        "controls": {
            key: str(value) if isinstance(value, Decimal) else value
            for key, value in base_config.controls.__dict__.items()
        },
        "reward": {key: str(value) for key, value in base_config.reward.__dict__.items()},
        "seeds": SEEDS,
        "primary_periods": PRIMARY_PERIODS,
        "sensitivity_periods": SENSITIVITY_PERIODS,
    }
    identity_hash = canonical_hash(identity)
    run_root = artifact_root / identity_hash[:20]
    results: list[dict[str, Any]] = []
    for period_kind, periods in (
        ("PRIMARY_NON_OVERLAPPING", PRIMARY_PERIODS),
        ("OVERLAPPING_HORIZON_SENSITIVITY", SENSITIVITY_PERIODS),
    ):
        for period_name, episode_start, duration_days in periods:
            for seed in SEEDS:
                for policy_factory in _policy_factories(market):
                    env = CryptoRotationEnv(
                        candles,
                        partition,
                        normalizer,
                        _candidate_environment_config(duration_days),
                        dataset_hash=manifest.dataset_hash,
                        feature_spec=feature_spec,
                    )
                    policy = policy_factory()
                    evaluation = EvaluationRunner().run(
                        env,
                        policy,
                        seed=seed,
                        episode_start=episode_start.isoformat(),
                    )
                    artifact_path, artifact_hash = _write_evaluation_artifact(
                        run_root,
                        identity_hash,
                        period_name,
                        seed,
                        policy,
                        evaluation,
                    )
                    results.append(
                        _summarize(
                            evaluation,
                            period_name=period_name,
                            period_kind=period_kind,
                            artifact_path=artifact_path,
                            artifact_hash=artifact_hash,
                            candidate_decisions=getattr(policy, "decisions", []),
                        )
                    )

    primary = [item for item in results if item["period_kind"] == "PRIMARY_NON_OVERLAPPING"]
    distributions = _distributions(primary)
    candidate = [item for item in primary if item["policy"] == CostAwareMomentum24hPolicy.name]
    baseline_distributions = {
        key: value
        for key, value in distributions.items()
        if key != CostAwareMomentum24hPolicy.name and key != "cash"
    }
    best_baseline = max(
        baseline_distributions,
        key=lambda key: Decimal(str(baseline_distributions[key]["median_return_percent"])),
    )
    candidate_median = median(Decimal(item["return_percent"]) for item in candidate)
    cash_median = Decimal(str(distributions["cash"]["median_return_percent"]))
    best_baseline_median = Decimal(
        str(baseline_distributions[best_baseline]["median_return_percent"])
    )
    technical_gate = all(not item["ruined"] for item in candidate) and all(
        item["unavailable_decisions"] == 0 for item in candidate
    )
    edge_demonstrated = (
        technical_gate
        and candidate_median > cash_median
        and candidate_median > best_baseline_median
    )
    report = {
        "schema_version": "strategy-candidate-report-v1",
        "identity_hash": identity_hash,
        "identity": identity,
        "source_development_report": str(development_report_path),
        "source_development_complete": True,
        "validation_accessed": False,
        "locked_test_accessed": False,
        "binance_live_accessed": False,
        "testnet_accessed": False,
        "results": results,
        "primary_distributions": distributions,
        "decision": {
            "technical_gate": "PASS" if technical_gate else "FAIL",
            "best_non_cash_baseline": best_baseline,
            "candidate_median_return_percent": str(candidate_median),
            "cash_median_return_percent": str(cash_median),
            "best_baseline_median_return_percent": str(best_baseline_median),
            "primary_months_above_40_percent": sum(
                Decimal(item["return_percent"]) > 40 for item in candidate
            ),
            "edge_demonstrated": edge_demonstrated,
        },
        "independence_warning": (
            "Only the three 30-day TRAIN windows are non-overlapping. The 90-day window is "
            "horizon sensitivity and is excluded from gates. Deterministic policies repeat "
            "across seeds; those repetitions are not independent evidence."
        ),
        "warning": (
            "Historical TRAIN-only simulation with public Binance data. No VALIDATION, "
            "LOCKED_TEST, Testnet, live account, order, or profitability claim."
        ),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    return report


def _require_train_only_gate(
    manifest: HistoricalDatasetManifest,
    development: ControlledTrainingReport,
) -> None:
    if manifest.locked_test_accessed or development.locked_test_accessed:
        raise ValueError("LOCKED_TEST is forbidden")
    if development.validation_observed:
        raise ValueError("candidate specification requires an unopened VALIDATION partition")
    if development.phase != "development":
        raise ValueError("candidate requires the development report")
    if manifest.dataset_hash != development.dataset_hash:
        raise ValueError("candidate dataset must match the completed development campaign")
    if len(development.runs) != 12 or any(
        item["status"] != "COMPLETED" or int(item["completed_timesteps"]) != 100_000
        for item in development.runs
    ):
        raise ValueError("candidate requires 12 completed development identities")


def _candidate_environment_config(duration_days: int) -> EnvironmentConfig:
    return EnvironmentConfig(
        initial_capital=Decimal("100"),
        max_exposure=Decimal("0.75"),
        reserve_ratio=Decimal("0.25"),
        warmup=timedelta(days=31),
        episode_duration=timedelta(days=duration_days),
        controls=TurnoverControlConfig(
            enabled=True,
            minimum_hold_steps=4,
            cooldown_steps=4,
            minimum_edge_after_costs=Decimal("0.001"),
            minimum_notional_usdt=Decimal("10"),
        ),
        reward=RewardConfig(
            turnover_coefficient=Decimal("0.005"),
            rotation_coefficient=Decimal("0"),
            ruin_penalty=Decimal("0"),
        ),
    )


def _policy_factories(
    market: TemporalMarketData,
) -> tuple[Callable[[], DiscretePolicy], ...]:
    return (
        CashPolicy,
        *(lambda action=action: BuyAndHoldPolicy(action) for action in range(1, 5)),
        MomentumPolicy,
        lambda: CostAwareMomentum24hPolicy(market),
    )


def _write_evaluation_artifact(
    root: Path,
    identity_hash: str,
    period_name: str,
    seed: int,
    policy: DiscretePolicy,
    result: EvaluationResult,
) -> tuple[Path, str]:
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{period_name.lower()}-seed-{seed}-{result.policy}.json.gz"
    payload = {
        "identity_hash": identity_hash,
        "period": period_name,
        "policy": result.policy,
        "seed": seed,
        "episode_start": result.episode_start,
        "episode_end": result.episode_end,
        "actions": result.actions,
        "transitions": result.transitions,
        "candidate_decisions": getattr(policy, "decisions", []),
    }
    serialized = (
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str) + "\n"
    ).encode("utf-8")
    path.write_bytes(gzip.compress(serialized, mtime=0))
    return path, hashlib.sha256(path.read_bytes()).hexdigest()


def _summarize(
    result: EvaluationResult,
    *,
    period_name: str,
    period_kind: str,
    artifact_path: Path,
    artifact_hash: str,
    candidate_decisions: list[dict[str, Any]],
) -> dict[str, Any]:
    transitions = result.transitions
    costs = sum((Decimal(str(item["costs_usdt"])) for item in transitions), Decimal(0))
    turnover = sum((Decimal(str(item["turnover"])) for item in transitions), Decimal(0))
    positions = [str(item["position"]) for item in transitions]
    failures = sum(bool(item["failures"]) for item in transitions)
    rejected = sum(item["requested_action"] != item["effective_action"] for item in transitions)
    unavailable = sum(
        decision["unavailable_reason"] is not None for decision in candidate_decisions
    )
    return {
        "period": period_name,
        "period_kind": period_kind,
        "policy": result.policy,
        "seed": result.seed,
        "episode_start": result.episode_start,
        "episode_end": result.episode_end,
        "steps": len(transitions),
        "final_equity_usdt": str(result.final_equity_usdt),
        "return_percent": str((result.final_equity_usdt / Decimal("100") - 1) * 100),
        "max_drawdown": str(max(Decimal(str(item["drawdown"])) for item in transitions)),
        "turnover": str(turnover),
        "costs_usdt": str(costs),
        "operations": sum(bool(item["fills"]) for item in transitions),
        "rotations": sum(len(item["fills"]) == 2 for item in transitions),
        "execution_failures": failures,
        "rejected_requests": rejected,
        "unavailable_decisions": unavailable,
        "time_in_usdt_ratio": str(Decimal(positions.count("USDT")) / Decimal(len(positions))),
        "position_distribution": {
            position: positions.count(position) / len(positions)
            for position in ("USDT", "BTCUSDT", "ETHUSDT", "SHIBUSDT", "BNBUSDT")
        },
        "ruined": result.terminated,
        "transition_hash": canonical_hash(transitions),
        "artifact_path": str(artifact_path),
        "artifact_sha256": artifact_hash,
    }


def _distributions(results: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    distributions: dict[str, dict[str, Any]] = {}
    for policy in sorted({str(item["policy"]) for item in results}):
        group = [item for item in results if item["policy"] == policy]
        returns = [Decimal(item["return_percent"]) for item in group]
        period_medians = {
            period: str(
                median(
                    Decimal(item["return_percent"]) for item in group if item["period"] == period
                )
            )
            for period in sorted({str(item["period"]) for item in group})
        }
        seed_medians = {
            str(seed): str(
                median(
                    Decimal(item["return_percent"]) for item in group if int(item["seed"]) == seed
                )
            )
            for seed in SEEDS
        }
        distributions[policy] = {
            "runs": len(group),
            "median_return_percent": str(median(returns)),
            "min_return_percent": str(min(returns)),
            "max_return_percent": str(max(returns)),
            "period_median_returns": period_medians,
            "seed_median_returns": seed_medians,
            "median_max_drawdown": str(median(Decimal(item["max_drawdown"]) for item in group)),
            "median_turnover": str(median(Decimal(item["turnover"]) for item in group)),
            "median_costs_usdt": str(median(Decimal(item["costs_usdt"]) for item in group)),
            "median_time_in_usdt_ratio": str(
                median(Decimal(item["time_in_usdt_ratio"]) for item in group)
            ),
            "ruins": sum(bool(item["ruined"]) for item in group),
        }
    return distributions
