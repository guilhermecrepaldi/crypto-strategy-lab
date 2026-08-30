from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from crypto_strategy_lab.db.models import (
    AuditEvent,
    BaselineResult,
    EpisodeStep,
    EquityPoint,
    ExperimentEpisode,
    ExperimentRun,
    FeatureSet,
    FeatureSetVersion,
    ModelCheckpoint,
    ModelDefinition,
    NormalizerArtifact,
    OutboxEvent,
    PerformanceMetric,
    PortfolioSnapshot,
    RewardComponent,
    SimulatedFill,
    SimulatedOrder,
    TrainingMetric,
    TrainingRun,
)
from crypto_strategy_lab.domain import canonical_hash
from crypto_strategy_lab.ml.environment import CryptoRotationEnv
from crypto_strategy_lab.ml.evaluation import EvaluationResult
from crypto_strategy_lab.ml.features import FeatureNormalizer
from crypto_strategy_lab.ml.training import TrainingArtifact


def persist_ml_evaluation(
    database_url: str,
    *,
    env: CryptoRotationEnv,
    normalizer: FeatureNormalizer,
    evaluation: EvaluationResult,
    artifact: TrainingArtifact | None,
) -> tuple[UUID, bool]:
    identity = {
        "dataset_hash": env.dataset_hash,
        "partition": env.partition.model_dump(mode="json"),
        "policy": evaluation.policy,
        "seed": evaluation.seed,
        "actions": evaluation.actions,
        "checkpoint": artifact.checkpoint_hash if artifact else None,
    }
    run_id = uuid5(NAMESPACE_URL, canonical_hash(identity))
    engine = create_engine(database_url)
    with Session(engine) as session, session.begin():
        if session.scalar(select(ExperimentRun.id).where(ExperimentRun.id == run_id)):
            return run_id, False
        first_time = _dt(evaluation.transitions[0]["simulated_time"])
        last_time = _dt(evaluation.transitions[-1]["simulated_time"])
        feature_version_id, normalizer_id = _feature_authorities(
            session, env, normalizer, first_time
        )
        training_run_id = (
            _training_authorities(
                session,
                artifact,
                env,
                feature_version_id,
                normalizer_id,
                first_time,
                last_time,
            )
            if artifact
            else None
        )
        session.add(
            ExperimentRun(
                id=run_id,
                run_type="BLIND_EVALUATION"
                if env.partition.name == "LOCKED_TEST"
                else "LAB_REPLAY",
                status="COMPLETED",
                seed=evaluation.seed,
                dataset_hash=env.dataset_hash,
                policy_hash=artifact.checkpoint_hash
                if artifact
                else canonical_hash(evaluation.policy),
                started_at=first_time,
                completed_at=last_time,
                manifest={
                    "schema_version": "0002",
                    "partition": env.partition.model_dump(mode="json"),
                    "symbols": list(env.symbols),
                    "action_mapping": {
                        str(index): symbol or "USDT"
                        for index, symbol in enumerate(env.action_symbols)
                    },
                    "reward": _json_compatible(env.config.reward.__dict__),
                    "execution": _json_compatible(env.config.costs.__dict__),
                    "feature_version": env.pipeline.spec.version,
                    "normalizer": normalizer.manifest(),
                },
                created_at=first_time,
            )
        )
        session.flush()
        episode_id = uuid5(NAMESPACE_URL, f"{run_id}:episode:0")
        first = evaluation.transitions[0]
        session.add(
            ExperimentEpisode(
                id=episode_id,
                experiment_run_id=run_id,
                training_run_id=training_run_id,
                partition=str(first["partition"]),
                episode_start=_dt(first["episode_start"]),
                episode_end=_dt(first["episode_end"]),
                warmup_start=_dt(first["episode_start"]) - env.config.warmup,
                symbols=list(env.symbols),
                action_mapping=first["action_mapping"],
                environment_seed=evaluation.seed,
                termination_reason=str(evaluation.transitions[-1]["termination_reason"]),
                replay_hash=canonical_hash(evaluation.transitions),
                created_at=first_time,
            )
        )
        session.flush()
        for index, transition in enumerate(evaluation.transitions):
            time = _dt(transition["simulated_time"])
            step = EpisodeStep(
                experiment_episode_id=episode_id,
                step_index=index,
                simulated_time=time,
                available_data_until=_dt(transition["available_data_until"]),
                action=int(transition["action"]),
                target_symbol=str(transition["target_symbol"]),
                observation_hash=str(transition["observation_hash"]),
                reward=Decimal(str(transition["reward"]["total"])),
                equity_usdt=Decimal(str(transition["equity_usdt"])),
                terminated=bool(transition["terminated"]),
                truncated=bool(transition["truncated"]),
                info=transition,
                created_at=time,
            )
            session.add(step)
            session.flush()
            for component, value in transition["reward"].items():
                if component != "total":
                    session.add(
                        RewardComponent(
                            episode_step_id=step.id,
                            component=component,
                            value=Decimal(str(value)),
                            created_at=time,
                        )
                    )
            _persist_execution(session, run_id, step.id, transition, time)
            portfolio = transition["portfolio"]
            session.add_all(
                [
                    PortfolioSnapshot(
                        experiment_run_id=run_id,
                        simulated_time=time,
                        usdt_balance=Decimal(portfolio["usdt"]),
                        asset_symbol=None
                        if portfolio["asset_symbol"] == "None"
                        else portfolio["asset_symbol"],
                        asset_quantity=Decimal(portfolio["asset_quantity"]),
                        equity_usdt=Decimal(portfolio["equity_usdt"]),
                        realized_pnl=Decimal(portfolio["realized_pnl"]),
                        unrealized_pnl=Decimal(portfolio["unrealized_pnl"]),
                        fees=Decimal(portfolio["fees"]),
                        drawdown=Decimal(portfolio["drawdown"]),
                        created_at=time,
                    ),
                    EquityPoint(
                        experiment_run_id=run_id,
                        simulated_time=time,
                        equity_usdt=Decimal(str(transition["equity_usdt"])),
                        created_at=time,
                    ),
                ]
            )
        session.add(
            PerformanceMetric(
                experiment_run_id=run_id,
                name="final_equity_usdt",
                value=evaluation.final_equity_usdt,
                dimensions={"policy": evaluation.policy, "partition": env.partition.name},
                created_at=last_time,
            )
        )
        if artifact is None:
            session.add(
                BaselineResult(
                    experiment_run_id=run_id,
                    policy=evaluation.policy,
                    seed=evaluation.seed,
                    final_equity_usdt=evaluation.final_equity_usdt,
                    total_reward=evaluation.total_reward,
                    metrics={"steps": len(evaluation.transitions)},
                    created_at=last_time,
                )
            )
        audit_payload = {**identity, "run_id": str(run_id), "status": "COMPLETED"}
        audit_hash = canonical_hash(audit_payload)
        session.add_all(
            [
                AuditEvent(
                    experiment_run_id=run_id,
                    event_type="RL_EVALUATION_COMPLETED",
                    actor="crypto-rotation-env",
                    payload=audit_payload,
                    previous_hash=None,
                    event_hash=audit_hash,
                    created_at=last_time,
                ),
                OutboxEvent(
                    topic="rl.evaluation.completed",
                    aggregate_id=str(run_id),
                    payload={"run_id": str(run_id), "audit_hash": audit_hash},
                    published_at=None,
                    attempts=0,
                    created_at=last_time,
                ),
            ]
        )
    return run_id, True


def _feature_authorities(
    session: Session,
    env: CryptoRotationEnv,
    normalizer: FeatureNormalizer,
    created_at: datetime,
) -> tuple[int, int]:
    feature_set = session.scalar(
        select(FeatureSet).where(FeatureSet.name == env.pipeline.spec.name)
    )
    if feature_set is None:
        feature_set = FeatureSet(
            name=env.pipeline.spec.name,
            description="Small causal market and portfolio observation vector",
            created_at=created_at,
        )
        session.add(feature_set)
        session.flush()
    version = session.scalar(
        select(FeatureSetVersion).where(
            FeatureSetVersion.feature_set_id == feature_set.id,
            FeatureSetVersion.version == env.pipeline.spec.version,
        )
    )
    definition = env.pipeline.spec.__dict__
    if version is None:
        version = FeatureSetVersion(
            feature_set_id=feature_set.id,
            version=env.pipeline.spec.version,
            definition=definition,
            definition_hash=canonical_hash(definition),
            created_at=created_at,
        )
        session.add(version)
        session.flush()
    parameters = normalizer.manifest()
    artifact_hash = canonical_hash(parameters)
    normalizer_row = session.scalar(
        select(NormalizerArtifact).where(NormalizerArtifact.artifact_hash == artifact_hash)
    )
    if normalizer_row is None:
        normalizer_row = NormalizerArtifact(
            feature_set_version_id=version.id,
            fitted_partition="TRAIN",
            parameters=parameters,
            artifact_hash=artifact_hash,
            created_at=created_at,
        )
        session.add(normalizer_row)
        session.flush()
    return version.id, normalizer_row.id


def _training_authorities(
    session: Session,
    artifact: TrainingArtifact,
    env: CryptoRotationEnv,
    feature_version_id: int,
    normalizer_id: int,
    started_at: datetime,
    completed_at: datetime,
) -> UUID:
    definition_hash = canonical_hash(
        {"algorithm": artifact.algorithm, "hyperparameters": artifact.hyperparameters}
    )
    definition = session.scalar(
        select(ModelDefinition).where(ModelDefinition.definition_hash == definition_hash)
    )
    if definition is None:
        definition = ModelDefinition(
            name=f"{artifact.algorithm}-discrete-rotation",
            algorithm=artifact.algorithm,
            hyperparameters=artifact.hyperparameters,
            definition_hash=definition_hash,
            created_at=started_at,
        )
        session.add(definition)
        session.flush()
    checkpoint = session.scalar(
        select(ModelCheckpoint).where(ModelCheckpoint.artifact_hash == artifact.checkpoint_hash)
    )
    if checkpoint is None:
        checkpoint = ModelCheckpoint(
            model_definition_id=definition.id,
            status="TRAINED",
            artifact_path=str(artifact.checkpoint_path),
            artifact_hash=artifact.checkpoint_hash,
            training_steps=artifact.total_timesteps,
            created_at=completed_at,
        )
        session.add(checkpoint)
        session.flush()
    training_run_id = uuid5(NAMESPACE_URL, f"training:{artifact.model_id}")
    if not session.scalar(select(TrainingRun.id).where(TrainingRun.id == training_run_id)):
        session.add(
            TrainingRun(
                id=training_run_id,
                model_definition_id=definition.id,
                model_checkpoint_id=checkpoint.id,
                feature_set_version_id=feature_version_id,
                normalizer_artifact_id=normalizer_id,
                partition="TRAIN",
                global_seed=artifact.seed,
                environment_seed=artifact.seed,
                algorithm_seed=artifact.seed,
                status="TRAINED",
                dataset_hash=artifact.dataset_hash,
                config={
                    "total_timesteps": artifact.total_timesteps,
                    "hyperparameters": artifact.hyperparameters,
                },
                completed_at=completed_at,
                created_at=started_at,
            )
        )
        session.flush()
        session.add(
            TrainingMetric(
                training_run_id=training_run_id,
                step=artifact.total_timesteps,
                name="completed_timesteps",
                value=Decimal(artifact.total_timesteps),
                created_at=completed_at,
            )
        )
    return training_run_id


def _json_compatible(values: dict[str, object]) -> dict[str, object]:
    return {
        key: str(value) if isinstance(value, Decimal) else value for key, value in values.items()
    }


def _persist_execution(
    session: Session,
    run_id: UUID,
    step_id: int,
    transition: dict[str, Any],
    time: datetime,
) -> None:
    action = int(transition["action"])
    order = SimulatedOrder(
        experiment_run_id=run_id,
        decision_event_id=None,
        simulated_time=time,
        symbol=str(transition["target_symbol"]),
        action=f"TARGET_{action}",
        side="HOLD" if not transition["fills"] else "ROTATE",
        status="REJECTED" if transition["failures"] else "FILLED",
        requested_quote=None,
        requested_quantity=None,
        reason=f"episode_step:{step_id}",
        created_at=time,
    )
    session.add(order)
    session.flush()
    for raw_fill in transition["fills"]:
        session.add(
            SimulatedFill(
                simulated_order_id=order.id,
                experiment_run_id=run_id,
                simulated_time=_dt(raw_fill["simulated_time"]),
                symbol=raw_fill["symbol"],
                side=raw_fill["side"],
                price=Decimal(raw_fill["price"]),
                quantity=Decimal(raw_fill["quantity"]),
                quote_value=Decimal(raw_fill["quote_value"]),
                fee_asset="USDT",
                fee_amount=Decimal(raw_fill["fee"]),
                spread_cost=Decimal(raw_fill["spread_cost"]),
                slippage_cost=Decimal(raw_fill["slippage_cost"]),
                realized_pnl=Decimal(raw_fill["realized_pnl"]),
                created_at=time,
            )
        )


def _dt(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value.astimezone(UTC)
    if isinstance(value, str):
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
    raise TypeError(f"cannot parse datetime from {type(value).__name__}")
