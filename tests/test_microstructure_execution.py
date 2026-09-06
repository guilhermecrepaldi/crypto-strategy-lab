from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from pydantic import ValidationError

from crypto_strategy_lab.microstructure.execution import PassiveExecutionSimulator
from crypto_strategy_lab.microstructure.models import (
    BookDeltaEvent,
    BookSnapshotEvent,
    CancelRequest,
    DecisionAudit,
    FeedGapEvent,
    FeeModel,
    LatencyConfig,
    LiquidityRole,
    OrderStatus,
    PriceLevel,
    QueueModel,
    RiskHaltEvent,
    S0Config,
    TradeEvent,
)

START = datetime(2026, 9, 5, tzinfo=UTC)


def _snapshot(
    *,
    at: datetime = START,
    sequence: int = 1,
    update_id: int = 100,
    bid: Decimal = Decimal("0.9988"),
    bid_qty: Decimal = Decimal("10"),
    ask: Decimal = Decimal("0.9989"),
    ask_qty: Decimal = Decimal("10"),
) -> BookSnapshotEvent:
    return BookSnapshotEvent(
        timestamp=at,
        sequence=sequence,
        update_id=update_id,
        bids=(PriceLevel(price=bid, quantity=bid_qty),),
        asks=(PriceLevel(price=ask, quantity=ask_qty),),
    )


def _trade(
    seconds: int,
    *,
    sequence: int,
    trade_id: int,
    price: Decimal,
    quantity: Decimal,
    buyer_is_maker: bool,
) -> TradeEvent:
    return TradeEvent(
        timestamp=START + timedelta(seconds=seconds),
        sequence=sequence,
        trade_id=trade_id,
        price=price,
        quantity=quantity,
        buyer_is_maker=buyer_is_maker,
    )


def test_price_presence_without_aggressor_trade_is_not_a_fill() -> None:
    result = PassiveExecutionSimulator(S0Config()).run([_snapshot()], dataset_hash="fixture")

    assert result.metrics["fill_count"] == 0
    assert result.orders[0].status == OrderStatus.OPEN
    assert result.ledger.fdusd == 0


def test_realistic_queue_is_consumed_before_partial_own_fill() -> None:
    events = [
        _snapshot(),
        _trade(
            1,
            sequence=2,
            trade_id=1,
            price=Decimal("0.9988"),
            quantity=Decimal("7"),
            buyer_is_maker=True,
        ),
        _trade(
            2,
            sequence=3,
            trade_id=2,
            price=Decimal("0.9988"),
            quantity=Decimal("4"),
            buyer_is_maker=True,
        ),
    ]

    result = PassiveExecutionSimulator(S0Config(quantity_override=Decimal("2"))).run(
        events, dataset_hash="fixture"
    )

    buy = result.orders[0]
    assert buy.queue_ahead == 0
    assert buy.filled_quantity == Decimal("1")
    assert buy.remaining_quantity == Decimal("1")
    assert buy.status == OrderStatus.PARTIALLY_FILLED
    assert result.ledger.fdusd == Decimal("1")
    assert len(result.orders) == 1


def test_trade_before_exchange_arrival_cannot_fill_order() -> None:
    config = S0Config(
        queue_model=QueueModel.OPTIMISTIC,
        latency=LatencyConfig(order_submit_ms=1_000),
    )
    events = [
        _snapshot(),
        _trade(
            0,
            sequence=2,
            trade_id=1,
            price=Decimal("0.9988"),
            quantity=Decimal("100"),
            buyer_is_maker=True,
        ),
    ]
    # Give the second event a later exchange ordering without using future information.
    events[1] = events[1].model_copy(update={"timestamp": START + timedelta(milliseconds=500)})

    result = PassiveExecutionSimulator(config).run(events, dataset_hash="fixture")

    assert result.metrics["fill_count"] == 0
    assert result.orders[0].exchange_arrival_at == START + timedelta(seconds=1)


def test_cancel_in_flight_does_not_prevent_fill_before_effective_time() -> None:
    config = S0Config(
        queue_model=QueueModel.OPTIMISTIC,
        latency=LatencyConfig(cancel_ms=1_000),
        quantity_override=Decimal("2"),
    )
    events = [
        _snapshot(),
        _trade(
            1,
            sequence=2,
            trade_id=1,
            price=Decimal("0.9988"),
            quantity=Decimal("1"),
            buyer_is_maker=True,
        ),
    ]
    cancel = CancelRequest(
        order_id="order-000001", requested_at=START + timedelta(milliseconds=500)
    )

    result = PassiveExecutionSimulator(config).run(
        events, dataset_hash="fixture", cancel_requests=[cancel]
    )

    buy = result.orders[0]
    assert buy.filled_quantity == Decimal("1")
    assert buy.status == OrderStatus.CANCELED
    assert buy.cancel_effective_at == START + timedelta(milliseconds=1500)


def test_post_only_order_crossing_at_arrival_is_rejected() -> None:
    result = PassiveExecutionSimulator(
        S0Config(lower=Decimal("0.9988"), upper=Decimal("0.9990"))
    ).run(
        [_snapshot(bid=Decimal("0.9987"), ask=Decimal("0.9988"))],
        dataset_hash="fixture",
    )

    assert result.orders[0].status == OrderStatus.REJECTED_POST_ONLY
    assert result.metrics["fill_count"] == 0


def test_full_buy_is_required_before_one_sell_lot_and_cycle_restart() -> None:
    config = S0Config(
        queue_model=QueueModel.OPTIMISTIC,
        quantity_override=Decimal("2"),
    )
    events = [
        _snapshot(bid_qty=Decimal("100"), ask_qty=Decimal("100")),
        _trade(
            1,
            sequence=2,
            trade_id=1,
            price=Decimal("0.9988"),
            quantity=Decimal("2"),
            buyer_is_maker=True,
        ),
        _trade(
            2,
            sequence=3,
            trade_id=2,
            price=Decimal("0.9989"),
            quantity=Decimal("2"),
            buyer_is_maker=False,
        ),
    ]

    result = PassiveExecutionSimulator(config).run(events, dataset_hash="fixture")

    assert [order.side.value for order in result.orders] == ["BUY", "SELL", "BUY"]
    assert result.metrics["cycle_count"] == 1
    assert result.ledger.fdusd == 0
    assert result.ledger.realized_pnl_usdc == Decimal("0.0002")


def test_partial_fill_notice_cannot_reveal_a_later_fill_early() -> None:
    config = S0Config(
        queue_model=QueueModel.OPTIMISTIC,
        quantity_override=Decimal("2"),
        latency=LatencyConfig(market_data_ms=100),
    )
    events = [
        _snapshot(bid_qty=Decimal("100"), ask_qty=Decimal("100")),
        TradeEvent(
            timestamp=START + timedelta(seconds=1),
            sequence=2,
            trade_id=1,
            price=Decimal("0.9988"),
            quantity=Decimal("1"),
            buyer_is_maker=True,
        ),
        TradeEvent(
            timestamp=START + timedelta(seconds=1, milliseconds=50),
            sequence=3,
            trade_id=2,
            price=Decimal("0.9988"),
            quantity=Decimal("1"),
            buyer_is_maker=True,
        ),
    ]

    result = PassiveExecutionSimulator(config).run(events, dataset_hash="fixture")

    assert result.fills[0].completes_order is False
    assert result.fills[1].completes_order is True
    sell_decisions = [item for item in result.decisions if item.action == "PLACE_SELL"]
    assert len(sell_decisions) == 1
    assert sell_decisions[0].decision_timestamp == START + timedelta(seconds=1, milliseconds=150)


def test_structural_depeg_halts_new_cycles_without_forced_liquidation() -> None:
    config = S0Config(
        queue_model=QueueModel.OPTIMISTIC,
        quantity_override=Decimal("2"),
    )
    events = [
        _snapshot(bid_qty=Decimal("100"), ask_qty=Decimal("100")),
        RiskHaltEvent(
            timestamp=START + timedelta(milliseconds=500),
            sequence=2,
            reason="STRUCTURAL_DEPEG",
            evidence=("redemption_suspended", "persistent_peg_loss"),
        ),
        _trade(
            1,
            sequence=3,
            trade_id=1,
            price=Decimal("0.9988"),
            quantity=Decimal("2"),
            buyer_is_maker=True,
        ),
        _trade(
            2,
            sequence=4,
            trade_id=2,
            price=Decimal("0.9989"),
            quantity=Decimal("2"),
            buyer_is_maker=False,
        ),
    ]

    result = PassiveExecutionSimulator(config).run(events, dataset_hash="fixture")

    assert result.risk_halt is True
    assert result.risk_halt_reason == "STRUCTURAL_DEPEG"
    assert [order.side.value for order in result.orders] == ["BUY", "SELL"]
    assert result.metrics["cycle_count"] == 1


def test_gap_blocks_decisions_until_snapshot_rebuild() -> None:
    events = [
        FeedGapEvent(timestamp=START, sequence=1, reason="disconnect"),
        BookDeltaEvent(
            timestamp=START + timedelta(seconds=1),
            sequence=2,
            first_update_id=10,
            final_update_id=10,
            bids=(PriceLevel(price=Decimal("0.9988"), quantity=Decimal("10")),),
            asks=(PriceLevel(price=Decimal("0.9989"), quantity=Decimal("10")),),
        ),
        _snapshot(at=START + timedelta(seconds=2), sequence=3, update_id=20),
    ]

    result = PassiveExecutionSimulator(S0Config()).run(events, dataset_hash="fixture")

    assert result.book_invalidations >= 1
    assert len(result.decisions) == 1
    assert result.decisions[0].latest_input_timestamp == START + timedelta(seconds=2)


def test_lookahead_audit_rejects_future_input() -> None:
    with pytest.raises(ValidationError, match="latest_input_timestamp"):
        DecisionAudit(
            action="PLACE_BUY",
            decision_timestamp=START,
            latest_input_timestamp=START + timedelta(microseconds=1),
        )


def test_fees_can_make_a_perfect_one_tick_cycle_impossible() -> None:
    zero = FeeModel(maker_rate=Decimal("0"))
    stressed = FeeModel(maker_rate=Decimal("0.0001"))

    assert zero.one_tick_net_quote(
        lower=Decimal("0.9988"),
        upper=Decimal("0.9989"),
        quantity=Decimal("100"),
        buy_role=LiquidityRole.MAKER,
        sell_role=LiquidityRole.MAKER,
    ) == Decimal("0.0100")
    assert (
        stressed.one_tick_net_quote(
            lower=Decimal("0.9988"),
            upper=Decimal("0.9989"),
            quantity=Decimal("100"),
            buy_role=LiquidityRole.MAKER,
            sell_role=LiquidityRole.MAKER,
        )
        < 0
    )


def test_same_events_and_configuration_are_reproducible() -> None:
    events = [_snapshot()]
    first = PassiveExecutionSimulator(S0Config()).run(events, dataset_hash="fixture")
    second = PassiveExecutionSimulator(S0Config()).run(events, dataset_hash="fixture")

    assert first.run_id == second.run_id
    assert first.model_dump(mode="json") == second.model_dump(mode="json")
