from __future__ import annotations

from decimal import Decimal as D
from random import Random

import pytest

from crypto_strategy_lab.microstructure.b10_reality import Trade
from crypto_strategy_lab.microstructure.dynamic_hotline_321 import (
    DynamicHotline321Probe,
    quantized_quantity,
    zone_for_rank,
)


def book(time_us: int, bid: str = "1.0019", ask: str = "1.0020") -> dict:
    return {
        "time_us": time_us,
        "exchange_upper_us": time_us,
        "bids": [[bid, "1000"]],
        "asks": [[ask, "1000"]],
        "known_bid_floor": "0.98",
        "known_ask_ceiling": "1.02",
    }


def probe() -> DynamicHotline321Probe:
    value = DynamicHotline321Probe(start_us=0, end_us=10_000_000, latency_us=0, cancel_latency_us=0)
    value.receive_book(book(1))
    return value


def test_zone_geometry_is_frozen_321() -> None:
    assert [zone_for_rank(rank) for rank in (1, 5, 6, 10, 11, 15, 16)] == [
        "HOT",
        "HOT",
        "MID",
        "MID",
        "FAR",
        "FAR",
        None,
    ]


def test_quantity_uses_nearest_historical_step_with_one_floor() -> None:
    assert quantized_quantity("1", "1.0020") == D(1)
    assert quantized_quantity("2", "1.0020") == D(2)
    assert quantized_quantity("3", "1.0020") == D(3)
    assert quantized_quantity("0.1", "1.0020") == D(1)


def test_initial_grid_has_60_physical_orders_and_real_156_slot_bank() -> None:
    value = probe()
    assert value.open_order_count == 60
    assert value.initial_usdt == D("78.1040")
    assert value.initial_usdc == D(78)
    assert value.initial_mark == D("156.2522")
    assert sum(row.quantity for row in value.orders if row.side == "SELL") == D(70)
    assert value.buy_mobility_reserve == D(8)
    assert value.sell_mobility_reserve == D(8)


def test_hotline_half_tick_equality_holds() -> None:
    value = probe()
    value.receive_book(book(2, "1.0020", "1.0021"))
    assert value.hotline == D("1.0020")
    assert value._hotline_changes == 0


def test_hotline_moves_sequentially_by_whole_ticks() -> None:
    value = probe()
    value.receive_book(book(2, "1.0022", "1.0023"))
    assert value.hotline == D("1.0022")
    assert value._hotline_changes == 2
    assert value._move_directions == ["UP", "UP"]


def test_distinct_books_with_same_native_timestamp_are_not_deduplicated() -> None:
    value = probe()
    value.receive_book({**book(2, "1.0022", "1.0023"), "exchange_upper_us": 1})
    assert value.hotline == D("1.0022")


def test_old_order_absolute_price_size_and_epoch_do_not_change() -> None:
    value = probe()
    old = next(row for row in value.orders if row.side == "BUY" and row.level == 6)
    snapshot = (old.price, old.quantity, old.submitted_us, value._order_meta[old.order_id].copy())
    value.receive_book(book(2, "1.0021", "1.0022"))
    assert (old.price, old.quantity, old.submitted_us) == snapshot[:3]
    for key in ("slot_count", "slot_base", "slot_epoch", "line_price"):
        assert value._order_meta[old.order_id][key] == snapshot[3][key]


def test_promotion_adds_younger_columns_behind_existing_order() -> None:
    value = probe()
    price = D("1.0026")  # initial MID rank 6; becomes HOT after one upward move
    old = [row for row in value.orders if row.side == "SELL" and row.price == price]
    assert len(old) == 2
    value.receive_book(book(2, "1.0021", "1.0022"))
    current = [row for row in value.orders if row.side == "SELL" and row.price == price]
    assert len(current) == 3
    assert current[-1].column == 3
    assert current[-1].submitted_us >= old[-1].submitted_us


def test_demotion_is_drain_only_without_resizing() -> None:
    value = probe()
    value.receive_book(book(2))
    old = next(
        row
        for row in value.orders
        if row.side == "SELL" and row.price == D("1.0021") and row.column == 3
    )
    quantity = old.quantity
    value.receive_book(book(3, "1.0021", "1.0022"))
    assert value._order_meta[old.order_id]["drain_only"] is True
    assert old.quantity == quantity


def test_mobility_buffer_is_real_and_promotion_debits_it() -> None:
    value = probe()
    value.receive_book(book(2))
    before = value.sell_mobility_reserve
    value.receive_book(book(3, "1.0021", "1.0022"))
    assert value.sell_mobility_reserve < before
    assert value.cash >= value.buy_mobility_reserve


def test_negative_return_is_rejected() -> None:
    value = probe()
    with pytest.raises(ValueError, match="NEGATIVE_EXIT"):
        value.submit_order(
            "SELL",
            "1.0010",
            quantity="1",
            time_us=2,
            role="RETURN",
            direction="BUY_FIRST",
            asset_basis="1.0010",
        )


def test_checkpoint_roundtrip_preserves_dynamic_state() -> None:
    value = probe()
    value.receive_book(book(2, "1.0022", "1.0023"))
    checkpoint = value.checkpoint()
    restored = DynamicHotline321Probe.from_checkpoint(checkpoint, start_us=0, end_us=10_000_000)
    assert restored.checkpoint() == checkpoint
    assert restored.metrics() == value.metrics()


def test_slot_gate_is_exactly_60_and_physical_gate_is_38() -> None:
    value = probe()
    value._cycles = 37
    value._cycle_rows = [
        {"origin_zone": "FAR", "column": 1, "slot_equivalent_weight": 1} for _ in range(37)
    ]
    value._slot_cycles = 59
    metrics = value.metrics()
    assert metrics["PHYSICAL_GATE_GT_12_3333_PASS"] is False
    assert metrics["SLOT_GATE_20_PER_HOUR_PASS"] is False
    value._cycles = 38
    value._cycle_rows.append({"origin_zone": "FAR", "column": 1, "slot_equivalent_weight": 1})
    value._slot_cycles = 60
    metrics = value.metrics()
    assert metrics["PHYSICAL_GATE_GT_12_3333_PASS"] is True
    assert metrics["SLOT_GATE_20_PER_HOUR_PASS"] is True


def test_slot_reconciliation_invariant_rejects_drift() -> None:
    value = probe()
    value._slot_cycles = 1
    with pytest.raises(ValueError, match="SLOT_CYCLE_RECONCILIATION"):
        value.validate_invariants()


def test_min_notional_remains_explicitly_non_executable() -> None:
    assert "MIN_NOTIONAL" in DynamicHotline321Probe.normalized_label
    assert "UNKNOWN" in DynamicHotline321Probe.normalized_label


def test_complete_buy_first_cycle_counts_once_with_entry_slot_weight() -> None:
    value = probe()
    value.receive_book(book(2))
    entry = next(
        row for row in value.orders if row.side == "BUY" and row.level == 1 and row.column == 1
    )
    value._fill_order(entry, entry.quantity, 3, "synthetic-entry")
    returned = next(row for row in value.orders if row.source_order_id == entry.order_id)
    value._advance(4)
    value._fill_order(returned, returned.quantity, 5, "synthetic-return")
    assert value._cycles == 1
    assert value._slot_cycles == 3
    assert value._cycle_rows[0]["entry_quantity"] == "3"
    assert value._cycle_rows[0]["slot_equivalent_weight"] == 3
    value.validate_invariants()


def test_partial_entry_never_counts_full_physical_or_slot_cycle() -> None:
    value = probe()
    value.receive_book(book(2))
    entry = next(
        row for row in value.orders if row.side == "BUY" and row.level == 1 and row.column == 1
    )
    value._fill_order(entry, D(1), 3, "synthetic-partial")
    assert entry.remaining == D(2)
    assert value._cycles == 0
    assert value._slot_cycles == 0
    assert not any(row.source_order_id == entry.order_id for row in value.orders)
    assert value._cell_is_occupied(entry.cell_id or "") is True


def test_complete_sell_first_cycle_counts_once_and_restores_owned_usdc() -> None:
    value = probe()
    value.receive_book(book(2))
    entry = next(
        row for row in value.orders if row.side == "SELL" and row.level == 2 and row.column == 1
    )
    value._fill_order(entry, entry.quantity, 3, "synthetic-sell-entry")
    conflict = next(row for row in value.orders if row.side == "BUY" and row.price == D("1.0019"))
    assert conflict.status == "CANCEL_PENDING"
    value._advance(4)
    value._advance(5)
    returned = next(row for row in value.orders if row.source_order_id == entry.order_id)
    value._fill_order(returned, returned.quantity, 6, "synthetic-buy-return")
    assert value._cycles == 1
    assert value._slot_cycles == 3
    assert value._cycle_rows[0]["origin_zone"] == "HOT"
    value.validate_invariants()


def test_randomized_fragmentation_preserves_exact_pnl_identity() -> None:
    random = Random(0)
    value = DynamicHotline321Probe(
        start_us=0,
        end_us=100_000,
        latency_us=1,
        cancel_latency_us=1,
    )
    value.receive_book(book(1))
    for sequence in range(1, 61):
        time_us = sequence * 10
        bid = D("1.0019") + D(random.randrange(-8, 9)) * D("0.0001")
        quantity = D(random.randrange(1, 20))
        value.receive_book(book(time_us, str(bid), str(bid + D("0.0001"))))
        value.receive_trade(
            Trade(
                time_us + 2,
                sequence,
                bid if sequence % 2 else bid + D("0.0001"),
                quantity,
                bool(sequence % 2),
            ),
            capture_time_us=time_us + 2,
        )
    assert D(value.metrics()["PNL_IDENTITY_RESIDUAL"]) == 0
    assert value.metrics()["PHYSICAL_CYCLES"] == 14
    value.validate_invariants()
