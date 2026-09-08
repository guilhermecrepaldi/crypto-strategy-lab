from copy import deepcopy
from datetime import UTC, datetime, timedelta
from decimal import Decimal as D
from itertools import pairwise
from types import SimpleNamespace

import pytest

from crypto_strategy_lab.domain import canonical_hash
from crypto_strategy_lab.microstructure.b10_reality import Trade
from crypto_strategy_lab.microstructure.data import ArchiveTrade
from crypto_strategy_lab.microstructure.zonal_ping_pong import ZonalPingPong
from scripts.run_zonal_ping_pong import (
    END_US,
    START_US,
    _band_for_price,
    band_occupancy,
    fixed_bands,
    independent_execution_audit,
)


def test_frozen_geometry_is_nine_contiguous_historical_tick_bands() -> None:
    bands = fixed_bands()
    assert len(bands) == 9
    assert bands[0].price_low == D("0.9994")
    assert bands[-1].price_high == D("1.0003")
    assert all(left.price_high == right.price_low for left, right in pairwise(bands))


def test_shared_edge_belongs_to_upper_band_except_final_high() -> None:
    bands = fixed_bands()
    assert _band_for_price(D("0.9995"), bands) == "Z002"
    assert _band_for_price(D("1.0003"), bands) == "Z009"
    assert _band_for_price(D("1.0017"), bands) is None


def test_band_occupancy_uses_five_hour_denominator_and_step_duration() -> None:
    bands = fixed_bands()
    canonical = {
        1: Trade(START_US + 10, 1, D("0.99945"), D(2), True),
        2: Trade(START_US + 30, 2, D("1.0017"), D(3), False),
    }
    value = band_occupancy(canonical, bands)
    assert value["Z001"]["TIME_PRICE_INSIDE_BAND_US"] == 20
    assert value["Z001"]["TRADES_INSIDE_BAND"] == 1
    assert value["Z001"]["TOTAL_VOLUME_INSIDE_BAND"] == "2"
    assert sum(row["TIME_PRICE_INSIDE_BAND_US"] for row in value.values()) == 20


def test_exact_cutoff_constant_is_five_hours() -> None:
    assert END_US - START_US == 5 * 3_600_000_000


def test_owner_gate_fails_closed_before_public_authorization(monkeypatch, tmp_path) -> None:
    from scripts import run_zonal_ping_pong as runner

    gate = tmp_path / "gate.md"
    gate.write_text(
        "APPROVED_COMPARISON_DAYS=1\n"
        "EXTENSION_AUTHORIZED=false\n"
        "NEW_REPLAY_AUTHORIZED_NOW=false\n"
        "AUTHORIZED_MODEL=NONE\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(runner, "OWNER_WINDOW", gate)
    with pytest.raises(ValueError, match="M020_OWNER_GATE_REQUIRED"):
        runner.require_owner_gate(tmp_path)


def test_independent_audit_reconciles_and_rejects_liquidity_tamper() -> None:
    value = ZonalPingPong(
        fixed_bands(),
        start_us=START_US,
        end_us=END_US,
        latency_us=1,
        cancel_latency_us=2,
    )

    def observed_book(offset: int) -> dict:
        return {
            "exchange_time_us": START_US + offset,
            "exchange_upper_us": START_US + offset,
            "capture_time_us": START_US + offset,
            "bids": ((D("0.9996"), D("100")),),
            "asks": ((D("0.9999"), D("100")),),
            "known_bid_floor": D("0.9994"),
            "known_ask_ceiling": D("1.0003"),
        }

    value.receive_book(observed_book(1))
    value.receive_book(observed_book(3))
    value.receive_book(observed_book(5))
    target = next(order for order in value.active_buys if order.band_id == "Z001")
    value.receive_trade(
        Trade(START_US + 6, 1, target.price - D("0.0001"), D("1"), True),
        capture_time_us=START_US + 6,
    )
    value.finish(time_us=END_US)
    terminal = value.checkpoint()
    canonical = {"1": Trade(START_US + 6, 1, target.price - D("0.0001"), D("1"), True)}
    audit = independent_execution_audit(value.audit, terminal, canonical, value.metrics())
    assert audit["status"] == "PASS_M020_LEDGER_EXECUTION_LIQUIDITY"

    tampered = deepcopy(value.audit)
    row = next(item for item in tampered if item["event"] == "TRADE")
    row["consumed_quantity"] = "2"
    with pytest.raises(ValueError, match="GLOBAL_LIQUIDITY_OVERCONSUMED"):
        independent_execution_audit(tampered, terminal, canonical, value.metrics())

    noncausal = deepcopy(value.audit)
    delivered = next(item for item in noncausal if item["event"] == "TRADE")
    delivered["native_time_us"] = 0
    with pytest.raises(ValueError, match="CANONICAL_PRINT_MISMATCH"):
        independent_execution_audit(noncausal, terminal, canonical, value.metrics())

    financial_tamper = deepcopy(terminal)
    financial_tamper["state"]["cash"] = str(D(financial_tamper["state"]["cash"]) + 1)
    financial_tamper["state"]["realized_profit"] = str(
        D(financial_tamper["state"]["realized_profit"]) + 1
    )
    financial_tamper["sha256"] = canonical_hash(financial_tamper["state"])
    with pytest.raises(ValueError, match="FILL_BASED_FINANCIAL_RECONCILIATION_FAILED"):
        independent_execution_audit(
            value.audit,
            financial_tamper,
            canonical,
            {**value.metrics(), "realized_profit": financial_tamper["state"]["realized_profit"]},
        )


def test_independent_audit_proves_both_cycle_legs() -> None:
    value = ZonalPingPong(
        fixed_bands(),
        start_us=START_US,
        end_us=END_US,
        latency_us=1,
        cancel_latency_us=2,
    )

    def observed_book(offset: int) -> dict:
        return {
            "exchange_time_us": START_US + offset,
            "exchange_upper_us": START_US + offset,
            "capture_time_us": START_US + offset,
            "bids": ((D("0.9996"), D("100")),),
            "asks": ((D("0.9999"), D("100")),),
            "known_bid_floor": D("0.9994"),
            "known_ask_ceiling": D("1.0003"),
        }

    value.receive_book(observed_book(1))
    value.receive_book(observed_book(3))
    value.receive_book(observed_book(5))
    buy = value.active_buys[0]
    first = Trade(START_US + 6, 1, buy.price - D("0.0001"), D("1"), True)
    value.receive_trade(first, capture_time_us=START_US + 6)
    value.receive_book(observed_book(8))
    value.receive_book(observed_book(10))
    sell = next(order for order in value.active_sells if order.band_id == buy.band_id)
    second = Trade(START_US + 11, 2, sell.price + D("0.0001"), D("1"), False)
    value.receive_trade(second, capture_time_us=START_US + 11)
    value.finish(time_us=END_US)
    canonical = {"1": first, "2": second}
    terminal = value.checkpoint()
    audit = independent_execution_audit(value.audit, terminal, canonical, value.metrics())
    assert audit["cycles"] == 1

    unlinked = deepcopy(value.audit)
    exit_fill = next(
        row for row in unlinked if row["event"] == "FILL" and row["side"] == "SELL"
    )
    exit_fill["economic_source_order_ids"] = []
    with pytest.raises(ValueError, match="BUY_SELL_LINK_MISMATCH"):
        independent_execution_audit(unlinked, terminal, canonical, value.metrics())


def test_independent_audit_reconciles_exact_level_queue_consumption() -> None:
    value = ZonalPingPong(
        fixed_bands(),
        start_us=START_US,
        end_us=END_US,
        latency_us=1,
        cancel_latency_us=2,
    )
    observed = {
        "exchange_time_us": START_US + 1,
        "exchange_upper_us": START_US + 1,
        "capture_time_us": START_US + 1,
        "bids": ((D("0.9996"), D("100")),),
        "asks": ((D("0.9999"), D("100")),),
        "known_bid_floor": D("0.9994"),
        "known_ask_ceiling": D("1.0003"),
    }
    value.receive_book(observed)
    value.receive_book(
        {
            **observed,
            "exchange_time_us": START_US + 3,
            "capture_time_us": START_US + 3,
        }
    )
    target = next(order for order in value.active_buys if order.price == D("0.9996"))
    exact = Trade(START_US + 4, 90, target.price, D("20"), True)
    assert value.receive_trade(exact, capture_time_us=START_US + 4) == D("20")
    assert target.filled == 0
    value.finish(time_us=END_US)
    audit = independent_execution_audit(
        value.audit,
        value.checkpoint(),
        {"90": exact},
        value.metrics(),
    )
    assert audit["queue_reconciled"] is True
    queue_tamper = deepcopy(value.audit)
    flow = next(row for row in queue_tamper if row["event"] == "QUEUE_FLOW")
    flow["queue_after"] = "999999"
    with pytest.raises(ValueError, match="QUEUE_TRANSITION_MISMATCH"):
        independent_execution_audit(
            queue_tamper,
            value.checkpoint(),
            {"90": exact},
            value.metrics(),
        )


def test_history_reader_stops_parsing_at_exclusive_cutoff(monkeypatch) -> None:
    from crypto_strategy_lab.microstructure import data

    start = datetime(2025, 1, 1, tzinfo=UTC)
    end = start + timedelta(hours=5)
    visited: list[int] = []

    def records(*_args, **_kwargs):
        for index, instant in enumerate(
            (start, end - timedelta(microseconds=1), end, end + timedelta(hours=1)), 1
        ):
            visited.append(index)
            yield ArchiveTrade(
                index,
                index,
                1,
                instant,
                "microseconds",
                D("1"),
                D("1"),
                True,
            )

    monkeypatch.setattr(
        data,
        "select_history_archives",
        lambda *_args, **_kwargs: (SimpleNamespace(local_path="unused"),),
    )
    monkeypatch.setattr(data, "iter_archive", records)
    rows = list(data.iter_history(SimpleNamespace(kind="trades"), start=start, end_exclusive=end))
    assert [row.trade_id for row in rows] == [1, 2]
    assert visited == [1, 2, 3]
