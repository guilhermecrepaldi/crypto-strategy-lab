from __future__ import annotations

from decimal import Decimal as D

import pytest

from crypto_strategy_lab.microstructure.order_size_capacity import (
    AUTHORIZED_QUANTITIES,
    OrderSizeCapacityProbe,
    _public_queue_zero_observations,
)


def probe(q: str = "500", *, latency: int = 1) -> OrderSizeCapacityProbe:
    return OrderSizeCapacityProbe(
        order_quantity=q,
        start_us=0,
        end_us=1_000_000,
        latency_us=latency,
        cancel_latency_us=latency,
    )


def trade(at: int, trade_id: str, qty: str, *, side: str = "BUY", price: str = "1.0000"):
    return {
        "time_us": at,
        "capture_time_us": at,
        "trade_id": trade_id,
        "price": price,
        "quantity": qty,
        "buyer_maker": side == "BUY",
    }


def book(engine: OrderSizeCapacityProbe, at: int, bid: str = "1.0000", ask: str = "1.0002"):
    engine.receive_book(
        {
            "exchange_time_us": at,
            "exchange_upper_us": at,
            "capture_time_us": at,
            "bids": ((D(bid), D("10000")),),
            "asks": ((D(ask), D("10000")),),
            "known_bid_floor": D("0.9900"),
            "known_ask_ceiling": D("1.0100"),
        }
    )


def test_authorized_scenario_set_is_exact() -> None:
    assert (
        tuple(D(value) for value in (10, 50, 100, 250, 500, 750, 1000, 1500, 2000, 3000, 5000))
        == AUTHORIZED_QUANTITIES
    )
    with pytest.raises(ValueError, match="UNAUTHORIZED"):
        probe("1")


@pytest.mark.parametrize("q", ["10", "500", "5000"])
def test_triangle_capital_and_all_physical_orders_scale_exactly(q: str) -> None:
    engine = probe(q)
    book(engine, 1, bid="1.0019", ask="1.0020")
    assert len(engine.orders) == 150
    assert all(order.quantity == D(q) for order in engine.orders)
    assert engine.initial_usdt == D("74.9900") * D(q)
    assert engine.initial_usdc == D(75) * D(q)
    assert engine.initial_mark == D("150.1325") * D(q)
    assert engine.open_order_count == 150


def test_q500_same_price_fifo_fragments_200_250_100_do_not_duplicate_volume() -> None:
    engine = probe("500")
    engine.seed_capital(usdt="2000")
    engine.seed_public_queue("BUY", "1.0000", "10000")
    c1 = engine.submit_order("BUY", "1.0000", time_us=1, activate_immediately=True, column=1)
    c2 = engine.submit_order("BUY", "1.0000", time_us=1, activate_immediately=True, column=2)
    assert engine.receive_trade(trade(2, "public", "10000")) == D("10000")
    assert engine.receive_trade(trade(3, "a", "200")) == D("200")
    assert engine.receive_trade(trade(4, "b", "250")) == D("250")
    assert engine.receive_trade(trade(5, "c", "100")) == D("100")
    assert c1.status == "FILLED" and c1.filled == D("500")
    assert c2.filled == D("50") and c2.status == "ACTIVE"
    assert not [row for row in engine.audit if row["event"] == "CYCLE"]


@pytest.mark.parametrize("q", ["10", "500", "5000"])
def test_partial_then_full_is_one_order_not_q_cycles(q: str) -> None:
    engine = probe(q)
    engine.seed_capital(usdt=D(q) * 2)
    order = engine.submit_order("BUY", "1.0000", time_us=1, activate_immediately=True)
    first = D(q) / D(2)
    engine.receive_trade(trade(2, "p1", str(first)))
    assert order.status == "ACTIVE"
    engine.receive_trade(trade(3, "p2", str(D(q) - first)))
    assert order.status == "FILLED"
    assert len([row for row in engine.audit if row["event"] == "FILL"]) == 2
    assert len([row for row in engine.audit if row["event"] == "CYCLE"]) == 0


def test_complete_q10_buy_return_counts_exactly_one_cycle_and_recycles_q10() -> None:
    engine = probe("10")
    engine.seed_capital(usdt="100")
    entry = engine.submit_order("BUY", "1.0000", time_us=1, activate_immediately=True)
    engine.receive_trade(trade(2, "entry", "10", price="0.9999"))
    returned = next(order for order in engine.orders if order.role == "RETURN")
    assert returned.quantity == D("10") and returned.source_order_id == entry.order_id
    # First post-submit event activates; a later physical print may fill.
    engine.receive_trade(trade(4, "activate-return", "0.1", side="SELL", price=str(returned.price)))
    engine.receive_trade(trade(5, "return", "10", side="SELL", price=str(returned.price)))
    assert engine._cycles == 1
    recycled = max(engine.orders, key=lambda order: order.order_id)
    assert recycled.role == "ENTRY" and recycled.quantity == D("10")
    assert engine._growth_cells == 0


def test_complete_q10_sell_return_counts_one_cycle_and_preserves_owned_quantity() -> None:
    engine = probe("10")
    engine.seed_capital(usdc="10")
    entry = engine.submit_order(
        "SELL",
        "1.0002",
        time_us=1,
        activate_immediately=True,
        direction="SELL_FIRST",
        asset_basis="1.0000",
    )
    engine.receive_trade(trade(2, "entry-sell", "10", side="SELL", price="1.0003"))
    returned = next(order for order in engine.orders if order.role == "RETURN")
    assert returned.quantity == D("10") and returned.source_order_id == entry.order_id
    engine.receive_trade(trade(4, "activate-buy", "0.1", price=str(returned.price)))
    engine.receive_trade(trade(5, "return-buy", "10", price=str(returned.price)))
    assert engine._cycles == 1
    assert engine.free_usdc + engine.reserved_usdc + engine.inventory_qty == D("10")


def test_scenarios_never_share_state_or_trade_consumption() -> None:
    q10, q500 = probe("10"), probe("500")
    q10.seed_capital(usdt="10")
    q500.seed_capital(usdt="500")
    first = q10.submit_order("BUY", "1", time_us=1, activate_immediately=True)
    second = q500.submit_order("BUY", "1", time_us=1, activate_immediately=True)
    physical = trade(2, "same-physical-id", "10")
    assert q10.receive_trade(physical) == D("10")
    assert q500.receive_trade(physical) == D("10")
    assert first.status == "FILLED"
    assert second.filled == D("10") and second.status == "ACTIVE"
    assert q10._processed_trades is not q500._processed_trades


def test_growth_expansion_is_impossible_even_with_sufficient_pool() -> None:
    engine = probe("500")
    engine.growth_pool = D("1000000")
    with pytest.raises(ValueError, match="GROWTH_EXPANSION_DISABLED"):
        engine.fund_growth_cell("BUY", "1.0000", time_us=1, level=1)
    engine._try_profit_funded_growth(1)
    assert engine._growth_cells == 0


def test_cancel_partial_releases_only_residual_and_locks_without_cycle() -> None:
    engine = probe("500")
    engine.seed_capital(usdt="500")
    order = engine.submit_order("BUY", "1.0000", time_us=1, activate_immediately=True)
    engine.cancel(order.order_id, time_us=2)
    engine.receive_trade(trade(2, "race", "200"))
    # Advance past cancel ACK without initializing the historical triangle.
    engine._advance(3)
    assert order.status == "CANCELED_PARTIAL"
    assert engine.cash == D("300")
    assert engine.inventory_qty == D("200")
    lot = next(lot for lot in engine.lots if lot.entry_order_id == order.order_id)
    assert lot.stage == "SUBSTEP_INVENTORY_LOCKED"
    assert engine._cycles == 0
    locked = [row for row in engine.audit if row["event"] == "PARTIAL_ENTRY_CANCELED_LOCKED"]
    assert locked == [
        {
            **locked[0],
            "required_full_order_quantity": "500",
            "partial_return_created": False,
            "cycle_counted": False,
        }
    ]


def test_checkpoint_binds_quantity_and_growth_policy() -> None:
    engine = probe("500")
    engine.seed_capital(usdt="500")
    engine.submit_order("BUY", "1.0000", time_us=1, activate_immediately=True)
    checkpoint = engine.checkpoint()
    restored = OrderSizeCapacityProbe.from_checkpoint(
        checkpoint, start_us=0, end_us=1_000_000, order_quantity="500"
    )
    assert restored.checkpoint() == checkpoint
    with pytest.raises(ValueError, match="SCENARIO_MISMATCH"):
        probe("1000").restore(checkpoint)


def test_owner_capacity_metric_contract_is_complete() -> None:
    engine = probe("500")
    book(engine, 1, bid="1.0019", ask="1.0020")
    metrics = engine.metrics()
    required = {
        "COMPLETED_ROUNDTRIP_USDC",
        "COMPLETED_ROUNDTRIP_USDC_PER_HOUR",
        "TWO_WAY_TRADED_USDC_PER_HOUR",
        "TWO_WAY_NOTIONAL_USDT_PER_HOUR",
        "FULL_ENTRY_ORDERS",
        "FULL_RETURN_ORDERS",
        "PARTIALLY_FILLED_ORDERS",
        "PARTIAL_FILL_RATE",
        "FULL_FILL_RATE",
        "ORDERS_OPEN_AT_CUTOFF",
        "TIME_TO_FIRST_FILL_US",
        "TIME_FIRST_TO_FULL_FILL_US",
        "TIME_TO_FULL_FILL_US",
        "TIME_PUBLIC_QUEUE_ZERO_TO_FIRST_OWN_FILL_US",
        "TIME_PUBLIC_QUEUE_ZERO_TO_FULL_OWN_FILL_US",
        "QUEUE_ZERO_REACHED_COUNT",
        "QUEUE_ZERO_THEN_FILLED_COUNT",
        "QUEUE_ZERO_CENSORED_WITHOUT_FILL_COUNT",
        "QUEUE_ZERO_NOT_OBSERVED_BEFORE_FIRST_FILL_COUNT",
        "QUEUE_ZERO_TO_FIRST_FILL_DENOMINATOR",
        "QUEUE_ZERO_ACTIVATED_ORDER_DENOMINATOR",
        "PUBLIC_QUEUE_AHEAD_AT_ACTIVATION_USDC",
        "OWN_QUANTITY_AHEAD_AT_ACTIVATION_USDC",
        "PUBLIC_QUEUE_QUANTITY_CONSUMED_USDC",
        "OWN_QUEUE_QUANTITY_CONSUMED_USDC",
        "OPEN_INVENTORY_USDC",
        "OPEN_INVENTORY_COST_USDT",
        "PARTIAL_ENTRY_RESIDUAL_USDC",
        "PARTIAL_RETURN_RESIDUAL_USDC",
        "CAPITAL_LOCKED_IN_PARTIALS_USDT",
        "CAPITAL_LOCKED_IN_OPEN_LOTS_USDT",
        "RETURN_ON_INITIAL_EQUITY",
        "REALIZED_PNL_PER_HOUR",
        "PNL_PER_HOUR_PER_1000_INITIAL_USDT",
        "ROUNDTRIP_USDC_PER_HOUR_PER_1000_INITIAL_USDT",
        "ORDER_NOTIONAL_USDT_MIN",
        "ORDER_NOTIONAL_USDT_MEDIAN",
        "ORDER_NOTIONAL_USDT_MAX",
    }
    assert required <= set(metrics)
    for field in (
        "TIME_TO_FIRST_FILL_US",
        "TIME_FIRST_TO_FULL_FILL_US",
        "TIME_TO_FULL_FILL_US",
        "TIME_PUBLIC_QUEUE_ZERO_TO_FIRST_OWN_FILL_US",
        "TIME_PUBLIC_QUEUE_ZERO_TO_FULL_OWN_FILL_US",
        "PUBLIC_QUEUE_AHEAD_AT_ACTIVATION_USDC",
        "OWN_QUANTITY_AHEAD_AT_ACTIVATION_USDC",
    ):
        assert set(metrics[field]) == {"mean", "median", "p95", "max"}
        assert all(
            value is None or value >= 0 for value in metrics[field].values()
        )


def test_queue_zero_uses_ledger_ordinal_before_fill_or_cancel_ack() -> None:
    from types import SimpleNamespace

    orders = {
        order_id: SimpleNamespace(side="BUY", price=D("1.0000"))
        for order_id in (1, 2, 3)
    }
    rows = [
        {
            "event": "ACTIVATED",
            "time_us": 10,
            "order_id": 1,
            "side": "BUY",
            "price": "1.0000",
            "cohort_activation_us": 10,
            "public_barrier_added": "5",
        },
        {"event": "FILL", "time_us": 20, "order_id": 1},
        {
            "event": "PUBLIC_QUEUE_CONSUMED",
            "time_us": 20,
            "side": "BUY",
            "price": "1.0000",
            "cohort_activation_us": 10,
            "quantity": "5",
        },
        {
            "event": "ACTIVATED",
            "time_us": 30,
            "order_id": 2,
            "side": "BUY",
            "price": "1.0000",
            "cohort_activation_us": 30,
            "public_barrier_added": "5",
        },
        {"event": "CANCEL_ACK", "time_us": 40, "order_id": 2},
        {
            "event": "PUBLIC_QUEUE_CONSUMED",
            "time_us": 40,
            "side": "BUY",
            "price": "1.0000",
            "cohort_activation_us": 30,
            "quantity": "5",
        },
        {
            "event": "ACTIVATED",
            "time_us": 50,
            "order_id": 3,
            "side": "BUY",
            "price": "1.0000",
            "cohort_activation_us": 50,
            "public_barrier_added": "5",
        },
        {
            "event": "PUBLIC_QUEUE_CONSUMED",
            "time_us": 60,
            "side": "BUY",
            "price": "1.0000",
            "cohort_activation_us": 50,
            "quantity": "5",
        },
        {"event": "FILL", "time_us": 60, "order_id": 3},
    ]
    assert _public_queue_zero_observations(rows, orders) == {3: 60}


def test_quantity_mismatch_and_negative_exit_fail_closed() -> None:
    engine = probe("500")
    engine.seed_capital(usdt="1000", usdc="1000")
    with pytest.raises(ValueError, match="QUANTITY_MISMATCH"):
        engine.submit_order("BUY", "1", quantity="499", time_us=1)
    with pytest.raises(ValueError, match="NEGATIVE_EXIT"):
        engine.submit_order("SELL", "1", asset_basis="1", time_us=1)
