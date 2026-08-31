from __future__ import annotations

import json
import subprocess
from dataclasses import replace
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from statistics import mean
from typing import Any

from crypto_strategy_lab.analytics.diagnostics import build_turnover_diagnostic
from crypto_strategy_lab.analytics.schemas import ReportProvenance, TurnoverDiagnosticReport
from crypto_strategy_lab.data.history import HistoricalDatasetManifest, load_normalized_history
from crypto_strategy_lab.data.temporal import TemporalMarketData
from crypto_strategy_lab.domain import Candle, require_utc
from crypto_strategy_lab.ml.controls import TurnoverControlConfig
from crypto_strategy_lab.ml.environment import CryptoRotationEnv, EnvironmentConfig
from crypto_strategy_lab.ml.evaluation import EvaluationRunner, evaluate_action_sequence
from crypto_strategy_lab.ml.features import FeaturePipeline, fit_train_normalizer
from crypto_strategy_lab.ml.partitions import PartitionName, TemporalPartition
from crypto_strategy_lab.ml.policies import (
    BuyAndHoldPolicy,
    CashPolicy,
    DiscretePolicy,
    MomentumPolicy,
    RandomPolicy,
    StableBaselinesPolicy,
)
from crypto_strategy_lab.ml.reward import RewardConfig
from crypto_strategy_lab.ml.training import StableBaselinesTrainer
from crypto_strategy_lab.simulation.portfolio import ExecutionCosts


def run_turnover_study(
    manifest_path: Path,
    *,
    start: datetime,
    end: datetime,
    seeds: tuple[int, ...],
    timesteps: int,
    artifact_dir: Path,
    output_dir: Path,
) -> dict[str, Any]:
    start, end = require_utc(start), require_utc(end)
    manifest = HistoricalDatasetManifest.model_validate_json(manifest_path.read_text())
    if manifest.locked_test_accessed:
        raise ValueError("LOCKED_TEST is forbidden")
    if end - start != timedelta(days=30):
        raise ValueError("turnover study is intentionally restricted to a 30-day TRAIN smoke")
    candles = load_normalized_history(Path(manifest.normalized_path))
    partition = TemporalPartition(name=PartitionName.TRAIN, start=start, end=end)
    market = TemporalMarketData(candles)
    normalizer = fit_train_normalizer(
        FeaturePipeline(market, market.symbols), partition, Decimal("80")
    )
    scenarios = predefined_scenarios()
    runner = EvaluationRunner()
    reports: list[TurnoverDiagnosticReport] = []
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "runs").mkdir(parents=True, exist_ok=True)
    for scenario_name, config in scenarios.items():
        for seed in seeds:
            policies: list[DiscretePolicy] = [
                CashPolicy(),
                BuyAndHoldPolicy((None, *market.symbols).index("BTCUSDT")),
                MomentumPolicy(),
                RandomPolicy(seed),
            ]
            training_env = _environment(
                candles, partition, normalizer, config, manifest.dataset_hash
            )
            artifact = StableBaselinesTrainer("PPO").train(
                training_env,
                total_timesteps=timesteps,
                seed=seed,
                artifact_dir=artifact_dir / scenario_name,
            )
            policies.append(
                StableBaselinesPolicy(artifact.model, "ppo-smoke-insufficiently-trained")
            )
            for policy in policies:
                evaluation_config = (
                    replace(config, controls=TurnoverControlConfig())
                    if isinstance(policy, (CashPolicy, BuyAndHoldPolicy))
                    else config
                )
                env = _environment(
                    candles,
                    partition,
                    normalizer,
                    evaluation_config,
                    manifest.dataset_hash,
                )
                result = runner.run(env, policy, seed=seed, episode_start=start.isoformat())
                zero_config = replace(
                    config,
                    costs=ExecutionCosts(Decimal("0"), Decimal("0"), Decimal("0")),
                    controls=TurnoverControlConfig(),
                )
                costless = evaluate_action_sequence(
                    _environment(
                        candles, partition, normalizer, zero_config, manifest.dataset_hash
                    ),
                    [int(item["effective_action"]) for item in result.transitions],
                    seed=seed,
                    episode_start=start.isoformat(),
                )
                policy_name = (
                    f"buy-and-hold-{env.action_symbols[policy.action]}"
                    if isinstance(policy, BuyAndHoldPolicy)
                    else policy.name
                )
                provenance = ReportProvenance(
                    dataset_hash=manifest.dataset_hash,
                    period_start=start.isoformat(),
                    period_end=end.isoformat(),
                    timeframe="15m",
                    symbols=list(env.symbols),
                    configuration={"scenario": scenario_name, **env.configuration_manifest()},
                    seed=seed,
                    policy=policy_name,
                    execution_costs={
                        key: str(value) for key, value in config.costs.__dict__.items()
                    },
                    code_version=_git_version(),
                    partition="TRAIN",
                )
                report = build_turnover_diagnostic(
                    result,
                    costless,
                    provenance=provenance,
                    market_return_percent=_market_returns(candles, start, end),
                )
                reports.append(report)
                (output_dir / "runs" / f"{report.run_id}.json").write_text(
                    json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
    payload = {
        "schema_version": "turnover-sensitivity-v1",
        "dataset_hash": manifest.dataset_hash,
        "partition": "TRAIN",
        "period": {"start": start.isoformat(), "end": end.isoformat()},
        "seeds": list(seeds),
        "scenarios": {name: _config_payload(config) for name, config in scenarios.items()},
        "runs": [report.model_dump(mode="json", exclude={"transitions"}) for report in reports],
        "distributions": _distributions(reports),
        "selection_rule": "all predefined scenarios and seeds reported; no best-seed selection",
        "locked_test_accessed": False,
    }
    (output_dir / "turnover-sensitivity.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return payload


def predefined_scenarios() -> dict[str, EnvironmentConfig]:
    penalty = RewardConfig(
        turnover_coefficient=Decimal("0.005"), rotation_coefficient=Decimal("0.002")
    )
    conservative = TurnoverControlConfig(
        enabled=True,
        minimum_hold_steps=4,
        cooldown_steps=0,
        minimum_edge_after_costs=Decimal("0.001"),
        minimum_notional_usdt=Decimal("10"),
    )

    def configuration(
        reward: RewardConfig, controls: TurnoverControlConfig | None = None
    ) -> EnvironmentConfig:
        return EnvironmentConfig(
            warmup=timedelta(minutes=30),
            episode_duration=timedelta(days=30),
            reward=reward,
            controls=controls or TurnoverControlConfig(),
        )

    return {
        "penalties-off": configuration(RewardConfig(turnover_coefficient=Decimal("0"))),
        "penalties-conservative": configuration(penalty),
        "controls-no-cooldown": configuration(penalty, conservative),
        "controls-with-cooldown": configuration(penalty, replace(conservative, cooldown_steps=4)),
    }


def _environment(
    candles: list[Candle],
    partition: TemporalPartition,
    normalizer: Any,
    config: EnvironmentConfig,
    dataset_hash: str,
) -> CryptoRotationEnv:
    return CryptoRotationEnv(candles, partition, normalizer, config, dataset_hash=dataset_hash)


def _market_returns(candles: list[Candle], start: datetime, end: datetime) -> dict[str, Decimal]:
    result: dict[str, Decimal] = {}
    for symbol in sorted({item.symbol for item in candles}):
        values = [
            item for item in candles if item.symbol == symbol and start <= item.open_time < end
        ]
        result[symbol] = (values[-1].close / values[0].open - 1) * Decimal("100")
    return result


def _config_payload(config: EnvironmentConfig) -> dict[str, Any]:
    return {
        "costs": {key: str(value) for key, value in config.costs.__dict__.items()},
        "reward": {key: str(value) for key, value in config.reward.__dict__.items()},
        "controls": {
            key: str(value) if isinstance(value, Decimal) else value
            for key, value in config.controls.__dict__.items()
        },
    }


def _distributions(reports: list[TurnoverDiagnosticReport]) -> list[dict[str, Any]]:
    keys = sorted(
        {(item.provenance.configuration["scenario"], item.provenance.policy) for item in reports}
    )
    result = []
    for scenario, policy in keys:
        group = [
            item
            for item in reports
            if item.provenance.configuration["scenario"] == scenario
            and item.provenance.policy == policy
        ]
        returns = [
            Decimal(item.costs.net_pnl_usdt) / Decimal(item.costs.initial_equity_usdt) * 100
            for item in group
        ]
        result.append(
            {
                "scenario": scenario,
                "policy": policy,
                "seed_count": len(group),
                "return_percent": {
                    "min": str(min(returns)),
                    "mean": str(mean(returns)),
                    "max": str(max(returns)),
                },
                "operations_mean": str(mean(item.operations for item in group)),
                "turnover_mean": str(mean(Decimal(item.total_turnover) for item in group)),
                "cost_loss_mean_usdt": str(
                    mean(Decimal(item.costs.loss_exclusively_from_costs_usdt) for item in group)
                ),
                "final_equity_mean_usdt": str(
                    mean(Decimal(item.costs.final_equity_usdt) for item in group)
                ),
                "terminated_count": sum(item.terminated for item in group),
            }
        )
    return result


def _git_version() -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, check=False, text=True
    )
    return completed.stdout.strip() or "UNKNOWN"
