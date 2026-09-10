from __future__ import annotations

from copy import deepcopy
from decimal import Decimal as D
from random import Random
from types import SimpleNamespace

import pytest

from crypto_strategy_lab.domain import canonical_hash
from crypto_strategy_lab.microstructure.b10_reality import Trade
from crypto_strategy_lab.microstructure.dynamic_hotline_321 import DynamicHotline321Probe
from scripts.audit_dynamic_hotline_321 import independent_dynamic_hotline_audit
from scripts.run_dynamic_hotline_321 import require_owner_gate


def book(time_us: int) -> dict:
    return {
        "time_us": time_us,
        "exchange_upper_us": time_us,
        "bids": [["1.0019", "0"]],
        "asks": [["1.0020", "0"]],
        "known_bid_floor": "0.98",
        "known_ask_ceiling": "1.02",
    }


def completed_probe() -> DynamicHotline321Probe:
    value = DynamicHotline321Probe(start_us=0, end_us=10_000_000, latency_us=0, cancel_latency_us=0)
    value.receive_book(book(1))
    value.receive_book(book(2))
    entry = next(
        row for row in value.orders if row.side == "BUY" and row.level == 1 and row.column == 1
    )
    value._fill_order(entry, entry.quantity, 3, "entry-trade")
    returned = next(row for row in value.orders if row.source_order_id == entry.order_id)
    value._advance(4)
    value._fill_order(returned, returned.quantity, 5, "return-trade")
    # Physical TRADE rows are required by the independent audit. Synthetic fills
    # above deliberately append their causal budget rows after the fact.
    value._record(
        "TRADE",
        3,
        trade_id="entry-trade",
        native_time_us=3,
        original_quantity="3",
        consumed_quantity="3",
        buyer_maker=True,
        price=str(entry.price),
    )
    value._record(
        "TRADE",
        5,
        trade_id="return-trade",
        native_time_us=5,
        original_quantity="3",
        consumed_quantity="3",
        buyer_maker=False,
        price=str(returned.price),
    )
    return value


def canonical_for(value: DynamicHotline321Probe) -> dict[str, SimpleNamespace]:
    rows = {row["trade_id"]: row for row in value.audit if row["event"] == "TRADE"}
    return {
        trade_id: SimpleNamespace(
            trade_id=trade_id,
            time_us=int(row["native_time_us"]),
            price=D(row["price"]),
            quantity=D(row["original_quantity"]),
            buyer_maker=bool(row["buyer_maker"]),
        )
        for trade_id, row in rows.items()
    }


def test_owner_gate_names_exactly_one_m026_run() -> None:
    require_owner_gate()


def test_independent_audit_accepts_reconciled_cycle() -> None:
    value = completed_probe()
    metrics = value.metrics()
    result = independent_dynamic_hotline_audit(
        value.audit, value.checkpoint(), metrics, canonical_for(value)
    )
    assert result["physical_cycles_reconciled"] == 1
    assert result["slot_cycles_reconciled"] == 3


def test_independent_audit_rejects_fabricated_fill_even_after_rehash() -> None:
    value = completed_probe()
    metrics = value.metrics()
    terminal = deepcopy(value.checkpoint())
    terminal["state"]["parent"]["audit"].append(
        {
            "event": "FILL",
            "time_us": 6,
            "order_id": 999999,
            "side": "BUY",
            "price": "1",
            "quantity": "999999999",
            "source_id": "INVENTED",
            "column": 1,
            "slot_count": 1,
            "slot_epoch": 1,
            "line_price": "1",
        }
    )
    terminal["sha256"] = canonical_hash(terminal["state"])
    with pytest.raises(ValueError, match=r"FILL_UNKNOWN_ORDER|FILL_UNKNOWN_TRADE"):
        independent_dynamic_hotline_audit(
            terminal["state"]["parent"]["audit"],
            terminal,
            metrics,
            canonical_for(value),
        )


def test_independent_audit_rejects_cash_tamper_after_rehash() -> None:
    value = completed_probe()
    terminal = deepcopy(value.checkpoint())
    terminal["state"]["parent"]["cash"] = "1000000000"
    terminal["sha256"] = canonical_hash(terminal["state"])
    with pytest.raises(ValueError, match="CAPITAL_RECONSTRUCTION:cash"):
        independent_dynamic_hotline_audit(
            terminal["state"]["parent"]["audit"],
            terminal,
            value.metrics(),
            canonical_for(value),
        )


def test_independent_audit_rejects_impossible_fill_price_side_and_time() -> None:
    value = completed_probe()
    terminal = deepcopy(value.checkpoint())
    fill = next(row for row in terminal["state"]["parent"]["audit"] if row["event"] == "FILL")
    fill.update(price="100", side="SELL", time_us=0)
    terminal["sha256"] = canonical_hash(terminal["state"])
    with pytest.raises(ValueError, match=r"FILL_SIDE_BINDING|FILL_PRICE_BINDING"):
        independent_dynamic_hotline_audit(
            terminal["state"]["parent"]["audit"],
            terminal,
            value.metrics(),
            canonical_for(value),
        )


def test_integrated_receive_trade_path_closes_positive_cycles_and_audits() -> None:
    value = DynamicHotline321Probe(start_us=0, end_us=10_000_000, latency_us=0, cancel_latency_us=0)
    value.receive_book(book(1))
    value.receive_book(book(2))
    entry_trade = Trade(3, 101, D("1.0019"), D(9), True)
    value.receive_trade(entry_trade, capture_time_us=3)
    value._advance(4)
    return_trade = Trade(5, 102, D("1.0020"), D(9), False)
    value.receive_trade(return_trade, capture_time_us=5)
    assert value._cycles == 3
    canonical = {101: entry_trade, 102: return_trade}
    audit = independent_dynamic_hotline_audit(
        value.audit, value.checkpoint(), value.metrics(), canonical
    )
    assert audit["physical_cycles_reconciled"] == 3


def test_independent_audit_rejects_unconsumed_invented_public_barrier() -> None:
    value = completed_probe()
    terminal = deepcopy(value.checkpoint())
    activation = next(
        row for row in terminal["state"]["parent"]["audit"] if row["event"] == "ACTIVATED"
    )
    activation["public_barrier_added"] = "999999"
    activation["public_remaining"] = "999999"
    terminal["sha256"] = canonical_hash(terminal["state"])
    with pytest.raises(
        ValueError,
        match=r"ACTIVATION_PUBLIC_QUEUE_TOTAL|OWN_FIFO_OR_PUBLIC_BARRIER|TERMINAL_PUBLIC",
    ):
        independent_dynamic_hotline_audit(
            terminal["state"]["parent"]["audit"],
            terminal,
            value.metrics(),
            canonical_for(value),
        )


def test_independent_audit_derives_profit_and_slot_weight_from_orders() -> None:
    value = completed_probe()
    terminal = deepcopy(value.checkpoint())
    cycle = next(row for row in terminal["state"]["parent"]["audit"] if row["event"] == "CYCLE")
    cycle.update(profit="1000000", entry_slot_count=60, slot_equivalent_weight=60)
    terminal["state"]["m026"]["slot_cycles"] = 60
    terminal["sha256"] = canonical_hash(terminal["state"])
    metrics = value.metrics()
    metrics["SLOT_EQUIVALENT_CYCLES"] = 60
    with pytest.raises(
        ValueError,
        match=r"CYCLE_PROFIT_DERIVATION|ENTRY_SLOT_DERIVATION|SLOT_WEIGHT_DERIVATION",
    ):
        independent_dynamic_hotline_audit(
            terminal["state"]["parent"]["audit"],
            terminal,
            metrics,
            canonical_for(value),
        )


def test_independent_audit_binds_slot_metadata_to_original_submit() -> None:
    value = completed_probe()
    terminal = deepcopy(value.checkpoint())
    cycle = next(row for row in terminal["state"]["parent"]["audit"] if row["event"] == "CYCLE")
    entry_id = int(cycle["entry_order_id"])
    terminal["state"]["m026"]["order_meta"][str(entry_id)]["slot_count"] = 60
    cycle.update(entry_slot_count=60, slot_equivalent_weight=60)
    terminal["state"]["m026"]["slot_cycles"] = 60
    terminal["sha256"] = canonical_hash(terminal["state"])
    metrics = value.metrics()
    metrics["SLOT_EQUIVALENT_CYCLES"] = 60
    with pytest.raises(ValueError, match="META_SLOT_BINDING"):
        independent_dynamic_hotline_audit(
            terminal["state"]["parent"]["audit"],
            terminal,
            metrics,
            canonical_for(value),
        )


def test_independent_audit_binds_all_primary_financial_metrics() -> None:
    value = completed_probe()
    metrics = value.metrics()
    metrics.update(
        FINAL_USDT="1000000000",
        FINAL_TOTAL="1000000000",
        REALIZED_DISPOSAL_PNL="1000000000",
    )
    with pytest.raises(ValueError, match=r"FINANCIAL_METRIC:FINAL_USDT"):
        independent_dynamic_hotline_audit(
            value.audit,
            value.checkpoint(),
            metrics,
            canonical_for(value),
        )


def test_independent_audit_requires_return_to_preserve_entry_quantity() -> None:
    value = completed_probe()
    terminal = deepcopy(value.checkpoint())
    parent = terminal["state"]["parent"]
    return_order = next(row for row in parent["orders"] if row["role"] == "RETURN")
    return_id = int(return_order["order_id"])
    return_submit = next(
        row
        for row in parent["audit"]
        if row["event"] == "SUBMIT" and int(row["order_id"]) == return_id
    )
    return_order["quantity"] = "2"
    return_submit["quantity"] = "2"
    actual = D(return_submit["price"]) * D(2)
    return_submit["actual_order_notional"] = str(actual)
    return_submit["quantization_error"] = str(actual - D(return_submit["target_slot_notional"]))
    meta = terminal["state"]["m026"]["order_meta"][str(return_id)]
    meta["actual_notional"] = str(actual)
    meta["quantization_error"] = return_submit["quantization_error"]
    terminal["sha256"] = canonical_hash(terminal["state"])
    with pytest.raises(ValueError, match="RETURN_QUANTITY_NOT_PRESERVED"):
        independent_dynamic_hotline_audit(
            parent["audit"],
            terminal,
            value.metrics(),
            canonical_for(value),
        )


def test_failed_funding_is_atomic_under_adversarial_fragmentation() -> None:
    random = Random(3)
    value = DynamicHotline321Probe(
        start_us=0,
        end_us=100_000,
        latency_us=2,
        cancel_latency_us=3,
    )
    value.receive_book(book(1))
    canonical: dict[int, Trade] = {}
    for sequence in range(1, 61):
        time_us = sequence * 10
        bid = D("1.0019") + D(random.randrange(-8, 9)) * D("0.0001")
        value.receive_book(
            {
                **book(time_us),
                "bids": [[str(bid), "0"]],
                "asks": [[str(bid + D("0.0001")), "0"]],
            }
        )
        trade = Trade(
            time_us + 3,
            sequence,
            bid if sequence % 2 else bid + D("0.0001"),
            D(random.randrange(1, 190)) / D(10),
            bool(sequence % 2),
        )
        canonical[sequence] = trade
        value.receive_trade(trade, capture_time_us=time_us + 3)
    result = independent_dynamic_hotline_audit(
        value.audit,
        value.checkpoint(),
        value.metrics(),
        canonical,
    )
    assert result["status"] == "PASS_M026_INDEPENDENT_LEDGER_AND_TERMINAL_AUDIT"
    assert set(value._order_asset_cost_remaining) == {order.order_id for order in value.orders}
