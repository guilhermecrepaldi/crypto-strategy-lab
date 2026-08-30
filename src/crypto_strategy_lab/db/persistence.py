from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from crypto_strategy_lab.data.binance import DownloadManifest
from crypto_strategy_lab.db.models import (
    AdaptiveStateCheckpoint,
    AuditEvent,
    DatasetManifest,
    DecisionEvent,
    EquityPoint,
    ExperimentRun,
    MarketIngestRun,
    OutboxEvent,
    PerformanceMetric,
    PortfolioSnapshot,
    SimulatedFill,
    SimulatedOrder,
)
from crypto_strategy_lab.domain import canonical_hash
from crypto_strategy_lab.simulation.engine import SimulationResult


def _decimal(value: Any) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value))


def persist_result(database_url: str, result: SimulationResult) -> bool:
    """Persist one immutable run. Returns False when that deterministic run already exists."""
    engine = create_engine(database_url)
    with Session(engine) as session, session.begin():
        if session.scalar(select(ExperimentRun.id).where(ExperimentRun.id == result.run_id)):
            return False
        started_at = _time(result.equity[0]["simulated_time"])
        completed_at = _time(result.equity[-1]["simulated_time"])
        run = ExperimentRun(
            id=result.run_id,
            run_type=result.config.run_type,
            status="COMPLETED",
            seed=result.config.seed,
            dataset_hash=result.dataset_hash,
            policy_hash=result.policy_hash,
            started_at=started_at,
            completed_at=completed_at,
            created_at=started_at,
            manifest={
                "initial_capital": str(result.config.initial_capital),
                "symbols": list(result.symbols),
                "offline": True,
            },
        )
        session.add(run)
        session.flush()
        decision_ids: list[int] = []
        for decision in result.decisions:
            event = DecisionEvent(
                experiment_run_id=result.run_id,
                simulated_time=_time(decision["simulated_time"]),
                available_data_until=_time(decision["available_data_until"]),
                provider=str(decision["provider"]),
                model=None,
                prompt_version=str(decision["prompt_version"]),
                input_hash=str(decision["input_hash"]),
                input_payload=decision["input_payload"],
                raw_response=decision["raw_response"],
                normalized_response=decision["normalized_response"],
                replayed=False,
                created_at=_time(decision["simulated_time"]),
            )
            session.add(event)
            session.flush()
            decision_ids.append(event.id)
            adaptive_state = decision["input_payload"].get("adaptive_memory", {})
            session.add(
                AdaptiveStateCheckpoint(
                    strategy_version_id=None,
                    experiment_run_id=result.run_id,
                    simulated_time=_time(decision["simulated_time"]),
                    state=adaptive_state,
                    state_hash=canonical_hash(adaptive_state),
                    created_at=_time(decision["simulated_time"]),
                )
            )

        for order in result.orders:
            decision_index = int(order["decision_index"])
            session.add(
                SimulatedOrder(
                    experiment_run_id=result.run_id,
                    decision_event_id=decision_ids[decision_index],
                    simulated_time=_time(order["simulated_time"]),
                    symbol=str(order["to_symbol"] or order["from_symbol"] or "USDT"),
                    action=str(order["action"]),
                    side=_order_side(str(order["action"])),
                    status=str(order["status"]),
                    requested_quote=None,
                    requested_quantity=None,
                    reason=str(order["reason"]),
                    created_at=_time(order["simulated_time"]),
                )
            )
        for fill in result.fills:
            session.add(
                SimulatedFill(
                    simulated_order_id=None,
                    experiment_run_id=result.run_id,
                    simulated_time=fill.simulated_time,
                    symbol=fill.symbol,
                    side=fill.side,
                    price=fill.price,
                    quantity=fill.quantity,
                    quote_value=fill.quote_value,
                    fee_asset="USDT",
                    fee_amount=fill.fee,
                    spread_cost=fill.spread_cost,
                    slippage_cost=fill.slippage_cost,
                    realized_pnl=fill.realized_pnl,
                    created_at=fill.simulated_time,
                )
            )
        for point in result.equity:
            time = _time(point["simulated_time"])
            session.add_all(
                [
                    PortfolioSnapshot(
                        experiment_run_id=result.run_id,
                        simulated_time=time,
                        usdt_balance=_decimal(point["usdt"]),
                        asset_symbol=point["asset_symbol"],
                        asset_quantity=_decimal(point["asset_quantity"]),
                        equity_usdt=_decimal(point["equity_usdt"]),
                        realized_pnl=_decimal(point["realized_pnl"]),
                        unrealized_pnl=_decimal(point["unrealized_pnl"]),
                        fees=_decimal(point["fees"]),
                        drawdown=_decimal(point["drawdown"]),
                        created_at=time,
                    ),
                    EquityPoint(
                        experiment_run_id=result.run_id,
                        simulated_time=time,
                        equity_usdt=_decimal(point["equity_usdt"]),
                        created_at=time,
                    ),
                ]
            )
        for name, value in result.metrics.items():
            session.add(
                PerformanceMetric(
                    experiment_run_id=result.run_id,
                    name=name,
                    value=value,
                    dimensions={},
                    created_at=completed_at,
                )
            )
        audit_payload = {
            "run_id": str(result.run_id),
            "dataset_hash": result.dataset_hash,
            "policy_hash": result.policy_hash,
            "decision_count": len(result.decisions),
            "order_count": len(result.orders),
            "fill_count": len(result.fills),
            "status": "COMPLETED",
        }
        event_hash = canonical_hash(audit_payload)
        session.add_all(
            [
                AuditEvent(
                    experiment_run_id=result.run_id,
                    event_type="EXPERIMENT_COMPLETED",
                    actor="simulation-engine",
                    payload=audit_payload,
                    previous_hash=None,
                    event_hash=event_hash,
                    created_at=completed_at,
                ),
                OutboxEvent(
                    topic="experiment.completed",
                    aggregate_id=str(result.run_id),
                    payload={**audit_payload, "audit_hash": event_hash},
                    published_at=None,
                    attempts=0,
                    created_at=completed_at,
                ),
            ]
        )
    return True


def persist_download_manifest(database_url: str, manifest: DownloadManifest) -> bool:
    engine = create_engine(database_url)
    with Session(engine) as session, session.begin():
        existing = session.scalar(
            select(DatasetManifest.id).where(
                DatasetManifest.source_url == manifest.source_url,
                DatasetManifest.sha256 == manifest.sha256,
            )
        )
        if existing:
            return False
        run = MarketIngestRun(
            status="COMPLETED",
            source="BINANCE_PUBLIC_DATA",
            completed_at=manifest.ingested_at,
            details={"archive_count": 1},
            created_at=manifest.ingested_at,
        )
        session.add(run)
        session.flush()
        session.add(
            DatasetManifest(
                ingest_run_id=run.id,
                source_url=manifest.source_url,
                local_path=str(manifest.local_path),
                sha256=manifest.sha256,
                size_bytes=manifest.size_bytes,
                status=manifest.status,
                quarantined_reason=None,
                created_at=manifest.ingested_at,
            )
        )
    return True


def _time(value: Any) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"expected datetime, received {type(value).__name__}")
    return value


def _order_side(action: str) -> str:
    if action == "BUY_FROM_USDT":
        return "BUY"
    if action == "SELL_TO_USDT":
        return "SELL"
    return "ROTATE" if action == "ROTATE_ASSET" else "HOLD"
