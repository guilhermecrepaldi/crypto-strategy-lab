from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

MONEY = Numeric(38, 18)
UTC_TS = DateTime(timezone=True)


class Base(DeclarativeBase):
    metadata = MetaData(
        naming_convention={
            "ix": "ix_%(column_0_label)s",
            "uq": "uq_%(table_name)s_%(column_0_name)s",
            "ck": "ck_%(table_name)s_%(constraint_name)s",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
            "pk": "pk_%(table_name)s",
        }
    )


class IdMixin:
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)


class CreatedMixin:
    created_at: Mapped[datetime] = mapped_column(UTC_TS, nullable=False)


class Venue(Base, IdMixin):
    __tablename__ = "venue"
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)


class Asset(Base, IdMixin):
    __tablename__ = "asset"
    symbol: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)


class Instrument(Base, IdMixin):
    __tablename__ = "instrument"
    venue_id: Mapped[int] = mapped_column(ForeignKey("venue.id"), nullable=False)
    base_asset_id: Mapped[int] = mapped_column(ForeignKey("asset.id"), nullable=False)
    quote_asset_id: Mapped[int] = mapped_column(ForeignKey("asset.id"), nullable=False)
    symbol: Mapped[str] = mapped_column(String(64), nullable=False)
    market_type: Mapped[str] = mapped_column(String(16), nullable=False, default="SPOT")
    __table_args__ = (UniqueConstraint("venue_id", "symbol"),)


class InstrumentRuleSnapshot(Base, IdMixin, CreatedMixin):
    __tablename__ = "instrument_rule_snapshot"
    instrument_id: Mapped[int] = mapped_column(ForeignKey("instrument.id"), nullable=False)
    valid_from: Mapped[datetime] = mapped_column(UTC_TS, nullable=False)
    available_at: Mapped[datetime] = mapped_column(UTC_TS, nullable=False)
    tick_size: Mapped[Decimal | None] = mapped_column(MONEY)
    step_size: Mapped[Decimal | None] = mapped_column(MONEY)
    min_notional: Mapped[Decimal | None] = mapped_column(MONEY)
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class MarketIngestRun(Base, IdMixin, CreatedMixin):
    __tablename__ = "market_ingest_run"
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(UTC_TS)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)


class DatasetManifest(Base, IdMixin, CreatedMixin):
    __tablename__ = "dataset_manifest"
    ingest_run_id: Mapped[int | None] = mapped_column(ForeignKey("market_ingest_run.id"))
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    local_path: Mapped[str] = mapped_column(Text, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    quarantined_reason: Mapped[str | None] = mapped_column(Text)
    __table_args__ = (UniqueConstraint("source_url", "sha256"),)


class MarketDataGap(Base, IdMixin, CreatedMixin):
    __tablename__ = "market_data_gap"
    instrument_id: Mapped[int | None] = mapped_column(ForeignKey("instrument.id"))
    symbol: Mapped[str] = mapped_column(String(64), nullable=False)
    gap_start: Mapped[datetime] = mapped_column(UTC_TS, nullable=False)
    gap_end: Mapped[datetime] = mapped_column(UTC_TS, nullable=False)
    interval_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)


class Candle5m(Base):
    __tablename__ = "candle_5m"
    instrument_id: Mapped[int] = mapped_column(
        ForeignKey("instrument.id"), primary_key=True, nullable=False
    )
    open_time: Mapped[datetime] = mapped_column(UTC_TS, primary_key=True, nullable=False)
    close_time: Mapped[datetime] = mapped_column(UTC_TS, nullable=False)
    available_at: Mapped[datetime] = mapped_column(UTC_TS, nullable=False)
    open: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    high: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    low: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    close: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    volume: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    quote_asset_volume: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    trade_count: Mapped[int] = mapped_column(BigInteger, nullable=False)
    source_manifest_id: Mapped[int | None] = mapped_column(ForeignKey("dataset_manifest.id"))
    __table_args__ = (Index("ix_candle_5m_available_at", "available_at"),)


class HistoricalUniverseSelection(Base, IdMixin, CreatedMixin):
    __tablename__ = "historical_universe_selection"
    effective_at: Mapped[datetime] = mapped_column(UTC_TS, nullable=False)
    lookback_start: Mapped[datetime] = mapped_column(UTC_TS, nullable=False)
    lookback_end: Mapped[datetime] = mapped_column(UTC_TS, nullable=False)
    symbols: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    ranking: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    criteria: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    provisional: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class Strategy(Base, IdMixin, CreatedMixin):
    __tablename__ = "strategy"
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)


class StrategyVersion(Base, IdMixin, CreatedMixin):
    __tablename__ = "strategy_version"
    strategy_id: Mapped[int] = mapped_column(ForeignKey("strategy.id"), nullable=False)
    version: Mapped[str] = mapped_column(String(64), nullable=False)
    policy: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    policy_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    __table_args__ = (UniqueConstraint("strategy_id", "version"),)


class AdaptiveStateCheckpoint(Base, IdMixin, CreatedMixin):
    __tablename__ = "adaptive_state_checkpoint"
    strategy_version_id: Mapped[int | None] = mapped_column(ForeignKey("strategy_version.id"))
    experiment_run_id: Mapped[UUID | None] = mapped_column(ForeignKey("experiment_run.id"))
    simulated_time: Mapped[datetime] = mapped_column(UTC_TS, nullable=False)
    state: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    state_hash: Mapped[str] = mapped_column(String(64), nullable=False)


class ExperimentRun(Base, CreatedMixin):
    __tablename__ = "experiment_run"
    id: Mapped[UUID] = mapped_column(primary_key=True)
    run_type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    seed: Mapped[int] = mapped_column(BigInteger, nullable=False)
    dataset_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    policy_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    started_at: Mapped[datetime] = mapped_column(UTC_TS, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(UTC_TS)
    manifest: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class ExperimentScenario(Base, IdMixin, CreatedMixin):
    __tablename__ = "experiment_scenario"
    experiment_run_id: Mapped[UUID] = mapped_column(ForeignKey("experiment_run.id"))
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    parameters: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class DecisionEvent(Base, IdMixin, CreatedMixin):
    __tablename__ = "decision_event"
    experiment_run_id: Mapped[UUID] = mapped_column(ForeignKey("experiment_run.id"))
    simulated_time: Mapped[datetime] = mapped_column(UTC_TS, nullable=False)
    available_data_until: Mapped[datetime] = mapped_column(UTC_TS, nullable=False)
    provider: Mapped[str] = mapped_column(String(128), nullable=False)
    model: Mapped[str | None] = mapped_column(String(128))
    prompt_version: Mapped[str] = mapped_column(String(64), nullable=False)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    input_payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    raw_response: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    normalized_response: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    replayed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class SimulatedOrder(Base, IdMixin, CreatedMixin):
    __tablename__ = "simulated_order"
    experiment_run_id: Mapped[UUID] = mapped_column(ForeignKey("experiment_run.id"))
    decision_event_id: Mapped[int | None] = mapped_column(ForeignKey("decision_event.id"))
    simulated_time: Mapped[datetime] = mapped_column(UTC_TS, nullable=False)
    symbol: Mapped[str] = mapped_column(String(64), nullable=False)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    side: Mapped[str] = mapped_column(String(8), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    requested_quote: Mapped[Decimal | None] = mapped_column(MONEY)
    requested_quantity: Mapped[Decimal | None] = mapped_column(MONEY)
    reason: Mapped[str | None] = mapped_column(Text)


class SimulatedFill(Base, IdMixin, CreatedMixin):
    __tablename__ = "simulated_fill"
    simulated_order_id: Mapped[int | None] = mapped_column(ForeignKey("simulated_order.id"))
    experiment_run_id: Mapped[UUID] = mapped_column(ForeignKey("experiment_run.id"))
    simulated_time: Mapped[datetime] = mapped_column(UTC_TS, nullable=False)
    symbol: Mapped[str] = mapped_column(String(64), nullable=False)
    side: Mapped[str] = mapped_column(String(8), nullable=False)
    price: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    quantity: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    quote_value: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    fee_asset: Mapped[str] = mapped_column(String(32), nullable=False)
    fee_amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    spread_cost: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    slippage_cost: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    realized_pnl: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=Decimal("0"))


class SimulatedPosition(Base, IdMixin, CreatedMixin):
    __tablename__ = "simulated_position"
    experiment_run_id: Mapped[UUID] = mapped_column(ForeignKey("experiment_run.id"))
    simulated_time: Mapped[datetime] = mapped_column(UTC_TS, nullable=False)
    symbol: Mapped[str] = mapped_column(String(64), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    average_cost: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    realized_pnl: Mapped[Decimal] = mapped_column(MONEY, nullable=False)


class PortfolioSnapshot(Base, IdMixin, CreatedMixin):
    __tablename__ = "portfolio_snapshot"
    experiment_run_id: Mapped[UUID] = mapped_column(ForeignKey("experiment_run.id"))
    simulated_time: Mapped[datetime] = mapped_column(UTC_TS, nullable=False)
    usdt_balance: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    asset_symbol: Mapped[str | None] = mapped_column(String(64))
    asset_quantity: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    equity_usdt: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    realized_pnl: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    unrealized_pnl: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    fees: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    drawdown: Mapped[Decimal] = mapped_column(MONEY, nullable=False)


class PerformanceMetric(Base, IdMixin, CreatedMixin):
    __tablename__ = "performance_metric"
    experiment_run_id: Mapped[UUID] = mapped_column(ForeignKey("experiment_run.id"))
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    value: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    dimensions: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)


class EquityPoint(Base, IdMixin, CreatedMixin):
    __tablename__ = "equity_point"
    experiment_run_id: Mapped[UUID] = mapped_column(ForeignKey("experiment_run.id"))
    simulated_time: Mapped[datetime] = mapped_column(UTC_TS, nullable=False)
    equity_usdt: Mapped[Decimal] = mapped_column(MONEY, nullable=False)


class PatternOccurrence(Base, IdMixin, CreatedMixin):
    __tablename__ = "pattern_occurrence"
    experiment_run_id: Mapped[UUID] = mapped_column(ForeignKey("experiment_run.id"))
    simulated_time: Mapped[datetime] = mapped_column(UTC_TS, nullable=False)
    pattern_name: Mapped[str] = mapped_column(String(128), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class NewsEvent(Base, IdMixin, CreatedMixin):
    __tablename__ = "news_event"
    published_at: Mapped[datetime] = mapped_column(UTC_TS, nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(UTC_TS, nullable=False)
    source: Mapped[str] = mapped_column(String(128), nullable=False)
    canonical_url: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    relevance: Mapped[Decimal | None] = mapped_column(MONEY)
    novelty: Mapped[Decimal | None] = mapped_column(MONEY)
    quality: Mapped[Decimal | None] = mapped_column(MONEY)
    sentiment: Mapped[Decimal | None] = mapped_column(MONEY)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    dedup_key: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)


class NewsAssetLink(Base):
    __tablename__ = "news_asset_link"
    news_event_id: Mapped[int] = mapped_column(ForeignKey("news_event.id"), primary_key=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("asset.id"), primary_key=True)


class ExternalMarketSignal(Base, IdMixin, CreatedMixin):
    __tablename__ = "external_market_signal"
    provider: Mapped[str] = mapped_column(String(128), nullable=False)
    signal_type: Mapped[str] = mapped_column(String(128), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(UTC_TS, nullable=False)
    available_at: Mapped[datetime] = mapped_column(UTC_TS, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class AuditEvent(Base, IdMixin, CreatedMixin):
    __tablename__ = "audit_event"
    experiment_run_id: Mapped[UUID | None] = mapped_column(ForeignKey("experiment_run.id"))
    event_type: Mapped[str] = mapped_column(String(128), nullable=False)
    actor: Mapped[str] = mapped_column(String(128), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    previous_hash: Mapped[str | None] = mapped_column(String(64))
    event_hash: Mapped[str] = mapped_column(String(64), nullable=False)


class OutboxEvent(Base, IdMixin, CreatedMixin):
    __tablename__ = "outbox_event"
    topic: Mapped[str] = mapped_column(String(128), nullable=False)
    aggregate_id: Mapped[str] = mapped_column(String(128), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(UTC_TS)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class FeatureSet(Base, IdMixin, CreatedMixin):
    __tablename__ = "feature_set"
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)


class FeatureSetVersion(Base, IdMixin, CreatedMixin):
    __tablename__ = "feature_set_version"
    feature_set_id: Mapped[int] = mapped_column(ForeignKey("feature_set.id"), nullable=False)
    version: Mapped[str] = mapped_column(String(64), nullable=False)
    definition: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    definition_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    __table_args__ = (UniqueConstraint("feature_set_id", "version"),)


class NormalizerArtifact(Base, IdMixin, CreatedMixin):
    __tablename__ = "normalizer_artifact"
    feature_set_version_id: Mapped[int] = mapped_column(
        ForeignKey("feature_set_version.id"), nullable=False
    )
    fitted_partition: Mapped[str] = mapped_column(String(32), nullable=False)
    parameters: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    artifact_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)


class ModelDefinition(Base, IdMixin, CreatedMixin):
    __tablename__ = "model_definition"
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    algorithm: Mapped[str] = mapped_column(String(32), nullable=False)
    hyperparameters: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    definition_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)


class ModelCheckpoint(Base, IdMixin, CreatedMixin):
    __tablename__ = "model_checkpoint"
    model_definition_id: Mapped[int] = mapped_column(ForeignKey("model_definition.id"))
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    artifact_path: Mapped[str] = mapped_column(Text, nullable=False)
    artifact_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    training_steps: Mapped[int] = mapped_column(BigInteger, nullable=False)


class TrainingRun(Base, CreatedMixin):
    __tablename__ = "training_run"
    id: Mapped[UUID] = mapped_column(primary_key=True)
    model_definition_id: Mapped[int] = mapped_column(ForeignKey("model_definition.id"))
    model_checkpoint_id: Mapped[int | None] = mapped_column(ForeignKey("model_checkpoint.id"))
    feature_set_version_id: Mapped[int] = mapped_column(ForeignKey("feature_set_version.id"))
    normalizer_artifact_id: Mapped[int] = mapped_column(ForeignKey("normalizer_artifact.id"))
    partition: Mapped[str] = mapped_column(String(32), nullable=False)
    global_seed: Mapped[int] = mapped_column(BigInteger, nullable=False)
    environment_seed: Mapped[int] = mapped_column(BigInteger, nullable=False)
    algorithm_seed: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    dataset_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    config: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(UTC_TS)


class TrainingMetric(Base, IdMixin, CreatedMixin):
    __tablename__ = "training_metric"
    training_run_id: Mapped[UUID] = mapped_column(ForeignKey("training_run.id"))
    step: Mapped[int] = mapped_column(BigInteger, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    value: Mapped[Decimal] = mapped_column(MONEY, nullable=False)


class ExperimentEpisode(Base, CreatedMixin):
    __tablename__ = "experiment_episode"
    id: Mapped[UUID] = mapped_column(primary_key=True)
    experiment_run_id: Mapped[UUID] = mapped_column(ForeignKey("experiment_run.id"))
    training_run_id: Mapped[UUID | None] = mapped_column(ForeignKey("training_run.id"))
    partition: Mapped[str] = mapped_column(String(32), nullable=False)
    episode_start: Mapped[datetime] = mapped_column(UTC_TS, nullable=False)
    episode_end: Mapped[datetime] = mapped_column(UTC_TS, nullable=False)
    warmup_start: Mapped[datetime] = mapped_column(UTC_TS, nullable=False)
    symbols: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    action_mapping: Mapped[dict[str, str]] = mapped_column(JSON, nullable=False)
    environment_seed: Mapped[int] = mapped_column(BigInteger, nullable=False)
    termination_reason: Mapped[str] = mapped_column(String(64), nullable=False)
    replay_hash: Mapped[str] = mapped_column(String(64), nullable=False)


class EpisodeStep(Base, IdMixin, CreatedMixin):
    __tablename__ = "episode_step"
    experiment_episode_id: Mapped[UUID] = mapped_column(ForeignKey("experiment_episode.id"))
    step_index: Mapped[int] = mapped_column(Integer, nullable=False)
    simulated_time: Mapped[datetime] = mapped_column(UTC_TS, nullable=False)
    available_data_until: Mapped[datetime] = mapped_column(UTC_TS, nullable=False)
    action: Mapped[int] = mapped_column(Integer, nullable=False)
    target_symbol: Mapped[str] = mapped_column(String(64), nullable=False)
    observation_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    reward: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    equity_usdt: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    terminated: Mapped[bool] = mapped_column(Boolean, nullable=False)
    truncated: Mapped[bool] = mapped_column(Boolean, nullable=False)
    info: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    __table_args__ = (UniqueConstraint("experiment_episode_id", "step_index"),)


class RewardComponent(Base, IdMixin, CreatedMixin):
    __tablename__ = "reward_component"
    episode_step_id: Mapped[int] = mapped_column(ForeignKey("episode_step.id"))
    component: Mapped[str] = mapped_column(String(64), nullable=False)
    value: Mapped[Decimal] = mapped_column(MONEY, nullable=False)


class BaselineResult(Base, IdMixin, CreatedMixin):
    __tablename__ = "baseline_result"
    experiment_run_id: Mapped[UUID] = mapped_column(ForeignKey("experiment_run.id"))
    policy: Mapped[str] = mapped_column(String(128), nullable=False)
    seed: Mapped[int] = mapped_column(BigInteger, nullable=False)
    final_equity_usdt: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    total_reward: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
