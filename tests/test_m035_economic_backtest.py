from __future__ import annotations

from decimal import Decimal as D
from pathlib import Path

import pytest

from crypto_strategy_lab.microstructure import m035_data
from crypto_strategy_lab.microstructure.m035_economic_backtest import (
    M035BacktestConfig,
    M035BacktestExecutionError,
    M035EconomicScenario,
    run_mode,
)
from crypto_strategy_lab.microstructure.parallel_pair_capital_manager import (
    AllocationCandidate,
    AllocationPriority,
    GlobalCapitalLedger,
    ParallelPairCapitalAllocator,
)
from scripts.run_m035_economic_backtest import _create_json_exclusive

START = m035_data.START_US


def config(**changes: object) -> M035BacktestConfig:
    values: dict[str, object] = {
        "identity": "M035_200USD_3H_PARALLEL_DEVELOPMENT_BACKTEST_V1",
        "start_us": START,
        "end_us": START + 10_800_000_000,
    }
    values.update(changes)
    return M035BacktestConfig(**values)  # type: ignore[arg-type]


def book(
    symbol: str,
    local_us: int,
    *,
    bid: str = "0.9999",
    ask: str = "1.0001",
    known_bid_floor: str | None = None,
    known_ask_ceiling: str | None = None,
):
    return {
        "kind": "BOOK",
        "symbol": symbol,
        "local_us": local_us,
        "exchange_us": local_us,
        "exchange_upper_us": local_us,
        "capture_order": local_us,
        "sequence_validated": True,
        "bids": [(bid, "100000")],
        "asks": [(ask, "100000")],
        "known_bid_floor": known_bid_floor or str(D(bid) - D("0.01")),
        "known_ask_ceiling": known_ask_ceiling or str(D(ask) + D("0.01")),
    }


def trade(
    symbol: str,
    local_us: int,
    trade_id: int,
    *,
    price: str,
    quantity: str = "1000",
    buyer_maker: bool,
):
    return {
        "kind": "TRADE",
        "symbol": symbol,
        "local_us": local_us,
        "exchange_us": local_us,
        "capture_order": local_us,
        "data": {"t": trade_id, "p": price, "q": quantity, "m": buyer_maker},
    }


def warm_pair(scenario: M035EconomicScenario, symbol: str, offset: int = 0) -> None:
    scenario.receive(
        trade(
            symbol,
            START + offset + 1_000_000,
            offset + 1,
            price="0.9999",
            quantity="600",
            buyer_maker=True,
        )
    )
    scenario.receive(
        trade(
            symbol,
            START + offset + 2_000_000,
            offset + 2,
            price="1.0001",
            quantity="600",
            buyer_maker=False,
        )
    )
    scenario.receive(book(symbol, START + offset + 3_000_000))


def test_config_identity_bank_window_and_fee_grid_are_frozen() -> None:
    config().validate()
    with pytest.raises(ValueError, match="M035_ECONOMIC_CONFIG_NOT_FROZEN"):
        config(initial_bank_usdt=D("400")).validate()
    with pytest.raises(ValueError, match="M035_ECONOMIC_CONFIG_NOT_FROZEN"):
        config(end_us=START + 1).validate()


def test_parallel_scenario_uses_one_shared_200_usdt_bank() -> None:
    scenario = M035EconomicScenario(config(), fee_bps=D(0), parallel=True)
    warm_pair(scenario, "USDCUSDT")
    warm_pair(scenario, "FDUSDUSDT", offset=3_000_000)
    assert scenario.ledger.free_usdt >= 0
    assert scenario.ledger.committed_usdt <= D(200)
    assert scenario.ledger.marked_equity() == D(200)
    assert {row.pair_id for row in scenario.ledger.positions.values()} == {
        "PAIR_A",
        "PAIR_B",
    }


def test_economic_pair_hotlines_and_grids_are_isolated() -> None:
    scenario = M035EconomicScenario(config(), fee_bps=D(0), parallel=True)
    warm_pair(scenario, "USDCUSDT")
    pair_a = scenario.engines["USDCUSDT"]
    pair_b = scenario.engines["FDUSDUSDT"]
    assert pair_a.hotline == D("1.0000")
    assert pair_b.hotline is None
    pair_a_orders = set(pair_a.orders)

    warm_pair(scenario, "FDUSDUSDT", offset=3_000_000)
    assert pair_a.hotline == D("1.0000")
    assert set(pair_a.orders) == pair_a_orders
    assert pair_b.hotline == D("1.0000")


def test_economic_grid_preserves_c1_and_c2_capital_until_cancel_ack() -> None:
    scenario = M035EconomicScenario(config(), fee_bps=D(0), parallel=False)
    warm_pair(scenario, "USDCUSDT")
    engine = scenario.engines["USDCUSDT"]
    scenario.receive(book("USDCUSDT", START + 5_000_000))
    c1_before = {
        row.order_id: (row.price, row.status)
        for row in engine.orders.values()
        if row.kind == "ENTRY" and row.column == 1
    }
    free_before_move = scenario.ledger.free_usdt

    scenario.receive(
        book("USDCUSDT", START + 6_000_000, bid="1.0000", ask="1.0002")
    )
    assert all(
        engine.orders[order_id].price == price
        and engine.orders[order_id].status in {"ACTIVE", "PENDING", "PARTIAL"}
        for order_id, (price, _status) in c1_before.items()
    )
    assert any(
        row.kind == "ENTRY" and row.column == 2 and row.status == "CANCEL_PENDING"
        for row in engine.orders.values()
    )
    assert scenario.ledger.free_usdt == free_before_move

    scenario.receive(
        book(
            "USDCUSDT",
            START + 6_000_000 + scenario.config.cancel_ack_latency_us - 1,
            bid="1.0000",
            ask="1.0002",
        )
    )
    assert any(row.status == "CANCEL_PENDING" for row in engine.orders.values())
    scenario.receive(
        book(
            "USDCUSDT",
            START + 6_000_000 + scenario.config.cancel_ack_latency_us,
            bid="1.0000",
            ask="1.0002",
        )
    )
    assert any(row.status == "CANCELLED" for row in engine.orders.values())


def test_complete_physical_cycle_is_positive_and_has_no_cross_subsidy() -> None:
    scenario = M035EconomicScenario(config(), fee_bps=D(0), parallel=False)
    warm_pair(scenario, "USDCUSDT")
    scenario.receive(book("USDCUSDT", START + 5_000_000))
    scenario.receive(
        trade(
            "USDCUSDT",
            START + 6_000_000,
            3,
            price="0.9992",
            buyer_maker=True,
        )
    )
    scenario.receive(book("USDCUSDT", START + 8_000_000))
    scenario.receive(
        trade(
            "USDCUSDT",
            START + 10_000_000,
            4,
            price="1.0008",
            buyer_maker=False,
        )
    )
    assert scenario.ledger.cycles.cycles
    assert scenario.ledger.cycles.negative_closed_cycles == 0
    assert all(row.net_pnl_usdt > 0 for row in scenario.ledger.cycles.cycles.values())
    scenario.ledger.reconcile()


def test_entry_fill_preserves_latest_causal_book_mark() -> None:
    scenario = M035EconomicScenario(config(), fee_bps=D(0), parallel=False)
    warm_pair(scenario, "USDCUSDT")
    scenario.receive(book("USDCUSDT", START + 5_000_000))
    scenario.receive(
        trade(
            "USDCUSDT",
            START + 6_000_000,
            3,
            price="0.9992",
            buyer_maker=True,
        )
    )
    assert scenario.ledger.asset_marks_usdt["USDC"] == D("0.9999")
    assert all(
        row.marked_value_usdt == row.quantity * D("0.9999")
        for row in scenario.ledger.positions.values()
        if row.asset == "USDC"
    )


def test_hotline_move_cannot_create_same_price_column_collision() -> None:
    scenario = M035EconomicScenario(config(), fee_bps=D(0), parallel=False)
    warm_pair(scenario, "USDCUSDT")
    scenario.receive(book("USDCUSDT", START + 5_000_000))
    scenario.receive(
        trade(
            "USDCUSDT",
            START + 6_000_000,
            3,
            price="0.9997",
            quantity="10",
            buyer_maker=True,
        )
    )
    scenario.receive(book("USDCUSDT", START + 8_000_000, bid="0.9998", ask="1.0000"))
    active = [
        row
        for row in scenario.engines["USDCUSDT"].orders.values()
        if row.kind == "ENTRY" and row.status in {"PENDING", "ACTIVE", "PARTIAL", "CANCEL_PENDING"}
    ]
    physical_keys = [(row.price, row.column) for row in active]
    assert len(physical_keys) == len(set(physical_keys))
    scenario.receive(book("USDCUSDT", START + 10_000_000, bid="0.9998", ask="1.0000"))


def test_fee_dust_is_retained_and_does_not_reject_entry() -> None:
    scenario = M035EconomicScenario(config(), fee_bps=D(1), parallel=False)
    warm_pair(scenario, "USDCUSDT")
    assert scenario.engines["USDCUSDT"].orders
    scenario.receive(book("USDCUSDT", START + 5_000_000))
    scenario.receive(
        trade(
            "USDCUSDT",
            START + 6_000_000,
            3,
            price="0.9992",
            buyer_maker=True,
        )
    )
    scenario.receive(book("USDCUSDT", START + 8_000_000))
    scenario.receive(
        trade(
            "USDCUSDT",
            START + 10_000_000,
            4,
            price="1.0008",
            buyer_maker=False,
        )
    )
    assert scenario.ledger.dust.quantity("USDC") > 0
    assert scenario.ledger.dust.marked_value({"USDC": D(1)}) > 0
    scenario.ledger.reconcile()


def test_tradeable_dust_reenters_owned_return_pipeline() -> None:
    scenario = M035EconomicScenario(config(), fee_bps=D(1), parallel=False)
    warm_pair(scenario, "USDCUSDT")
    scenario.receive(book("USDCUSDT", START + 5_000_000))
    scenario.receive(
        trade(
            "USDCUSDT",
            START + 6_000_000,
            3,
            price="0.9992",
            buyer_maker=True,
        )
    )
    scenario.receive(book("USDCUSDT", START + 8_000_000))
    scenario.receive(
        trade(
            "USDCUSDT",
            START + 10_000_000,
            4,
            price="1.0008",
            buyer_maker=False,
        )
    )
    before = scenario.ledger.dust.quantity("USDC")
    assert before >= D(1)
    scenario.receive(book("USDCUSDT", START + 12_000_000))
    dust_return = next(
        row for row in scenario.engines["USDCUSDT"].orders.values() if row.kind == "DUST_RETURN"
    )
    assert dust_return.status == "PENDING"
    assert scenario.ledger.dust.quantity("USDC") < before
    scenario.receive(book("USDCUSDT", START + 14_000_000))
    scenario.receive(
        trade(
            "USDCUSDT",
            START + 16_000_000,
            5,
            price="1.0008",
            buyer_maker=False,
        )
    )
    assert dust_return.cycle_id in scenario.ledger.cycles.cycles
    assert scenario.ledger.cycles.cycles[dust_return.cycle_id].net_pnl_usdt >= 0
    result = scenario.finish()
    assert D(result["GLOBAL_CAPITAL_CONSERVATION_RESIDUAL"]) == 0
    assert result["NEGATIVE_CLOSED_CYCLES"] == 0


def test_owned_return_and_dust_return_share_price_column_occupancy() -> None:
    scenario = M035EconomicScenario(config(), fee_bps=D(1), parallel=False)
    warm_pair(scenario, "USDCUSDT")
    scenario.receive(book("USDCUSDT", START + 5_000_000))
    scenario.receive(
        trade(
            "USDCUSDT",
            START + 6_000_000,
            3,
            price="0.9992",
            buyer_maker=True,
        )
    )
    scenario.receive(book("USDCUSDT", START + 8_000_000))
    scenario.receive(
        trade(
            "USDCUSDT",
            START + 10_000_000,
            4,
            price="1.0008",
            buyer_maker=False,
        )
    )
    scenario.receive(book("USDCUSDT", START + 12_000_000))
    for offset in (14_000_000, 16_000_000, 18_000_000):
        scenario.receive(
            book("USDCUSDT", START + offset, bid="0.9996", ask="0.9998")
        )
    scenario.receive(
        trade(
            "USDCUSDT",
            START + 19_000_000,
            5,
            price="0.9989",
            buyer_maker=True,
        )
    )
    scenario.receive(book("USDCUSDT", START + 21_000_000, bid="0.9996", ask="0.9998"))
    engine = scenario.engines["USDCUSDT"]
    live_returns = [
        row
        for row in engine.orders.values()
        if row.kind in {"RETURN", "DUST_RETURN"}
        and row.status in {"PENDING", "ACTIVE", "PARTIAL", "CANCEL_PENDING"}
    ]
    physical_keys = [(row.price, row.column) for row in live_returns]
    assert len(physical_keys) == len(set(physical_keys))


def test_partial_cancel_below_minimum_moves_inventory_to_owned_dust() -> None:
    scenario = M035EconomicScenario(config(), fee_bps=D(1), parallel=False)
    warm_pair(scenario, "USDCUSDT")
    scenario.receive(book("USDCUSDT", START + 5_000_000))
    scenario.receive(
        trade(
            "USDCUSDT",
            START + 6_000_000,
            3,
            price="0.9996",
            quantity="12",
            buyer_maker=True,
        )
    )
    scenario.receive(book("USDCUSDT", START + 8_000_000, bid="1.0000", ask="1.0002"))
    scenario.receive(book("USDCUSDT", START + 10_000_000, bid="1.0000", ask="1.0002"))
    assert scenario.ledger.dust.quantity("USDC", pair_id="PAIR_A") == D("1.9998")
    assert all(
        not (row.asset == "USDC" and row.quantity == D("1.9998"))
        for row in scenario.ledger.positions.values()
    )
    assert any(
        row["event"] == "UNTRADEABLE_INVENTORY_MOVED_TO_DUST"
        for row in scenario.ledger.audit
    )
    expected_open_owners = len(scenario.ledger.positions) + len(scenario.ledger.dust.lots)
    result = scenario.finish()
    assert result["LOCK_OBSERVATIONS_OPEN_CAPITAL"] == expected_open_owners
    assert all(
        row.status != "DUSTED" or row.capital_id not in scenario.ledger.positions
        for row in scenario.engines["USDCUSDT"].orders.values()
    )


def test_failed_fill_does_not_mutate_physical_queue(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scenario = M035EconomicScenario(config(), fee_bps=D(0), parallel=False)
    warm_pair(scenario, "USDCUSDT")
    scenario.receive(book("USDCUSDT", START + 5_000_000))
    scenario.receive(
        trade(
            "USDCUSDT",
            START + 6_000_000,
            3,
            price="0.9992",
            buyer_maker=True,
        )
    )
    scenario.receive(book("USDCUSDT", START + 8_000_000))
    engine = scenario.engines["USDCUSDT"]
    return_order = next(row for row in engine.orders.values() if row.kind == "RETURN")
    queue_order = next(
        row
        for group in engine.queue.groups.values()
        for row in group.own_orders
        if row.order_id == return_order.order_id
    )
    before = queue_order.remaining

    def reject(*_args, **_kwargs):
        raise ValueError("SYNTHETIC_SETTLEMENT_REJECTION")

    monkeypatch.setattr(GlobalCapitalLedger, "settle_return", reject)
    with pytest.raises(ValueError, match="SYNTHETIC_SETTLEMENT_REJECTION"):
        scenario.receive(
            trade(
                "USDCUSDT",
                START + 10_000_000,
                4,
                price="1.0008",
                buyer_maker=False,
            )
        )
    actual = next(
        row
        for group in engine.queue.groups.values()
        for row in group.own_orders
        if row.order_id == return_order.order_id
    )
    assert actual.remaining == before


def test_price_outside_known_l2_coverage_cannot_activate_or_fill() -> None:
    scenario = M035EconomicScenario(config(), fee_bps=D(0), parallel=False)
    scenario.receive(
        trade(
            "USDCUSDT",
            START + 1_000_000,
            1,
            price="0.9999",
            quantity="600",
            buyer_maker=True,
        )
    )
    scenario.receive(
        trade(
            "USDCUSDT",
            START + 2_000_000,
            2,
            price="1.0001",
            quantity="600",
            buyer_maker=False,
        )
    )
    for offset in (3_000_000, 5_000_000):
        scenario.receive(
            book(
                "USDCUSDT",
                START + offset,
                known_bid_floor="0.9998",
                known_ask_ceiling="1.0002",
            )
        )
    scenario.receive(
        trade(
            "USDCUSDT",
            START + 6_000_000,
            3,
            price="0.9997",
            quantity="1",
            buyer_maker=True,
        )
    )
    engine = scenario.engines["USDCUSDT"]
    assert all(row.filled_quantity == 0 for row in engine.orders.values())
    assert all(
        row.price >= D("0.9998")
        for row in engine.orders.values()
        if row.kind == "ENTRY"
    )


def test_partial_return_fill_is_reflected_in_realized_pnl_and_dust_lock_is_censored() -> None:
    scenario = M035EconomicScenario(config(), fee_bps=D(0), parallel=False)
    warm_pair(scenario, "USDCUSDT")
    scenario.receive(book("USDCUSDT", START + 5_000_000))
    scenario.receive(
        trade(
            "USDCUSDT",
            START + 6_000_000,
            3,
            price="0.9992",
            buyer_maker=True,
        )
    )
    scenario.receive(book("USDCUSDT", START + 8_000_000))
    scenario.receive(
        trade(
            "USDCUSDT",
            START + 10_000_000,
            4,
            price="1.0008",
            quantity="3",
            buyer_maker=False,
        )
    )
    expected = sum(
        (
            row.returned_proceeds_usdt
            - row.returned_cost_basis_usdt
            - row.returned_attributable_costs_usdt
            for row in scenario.ledger.positions.values()
        ),
        D(0),
    )
    result = scenario.finish()
    assert expected > 0
    assert D(result["REALIZED_PNL_USD"]) == expected
    assert result["P95_LOCK"] is not None


def test_candidate_scan_is_single_pass(monkeypatch: pytest.MonkeyPatch) -> None:
    scenario = M035EconomicScenario(config(), fee_bps=D(0), parallel=False)
    engine = scenario.engines["USDCUSDT"]
    calls = 0
    original = engine.candidates

    def counted(*, now_us: int):
        nonlocal calls
        calls += 1
        return original(now_us=now_us)

    monkeypatch.setattr(engine, "candidates", counted)
    scenario._allocate(START)
    assert calls == 1


def test_partial_inventory_consolidation_preserves_equity_and_owner() -> None:
    ledger = GlobalCapitalLedger()
    allocator = ParallelPairCapitalAllocator(ledger)
    request = AllocationCandidate(
        candidate_id="A",
        pair_id="PAIR_A",
        requested_usdt=D(10),
        priority=AllocationPriority.NEW_ENTRY,
        marginal_productivity=D(1),
        fifo_value=D(0),
        expected_lock_seconds=D(60),
        expected_net_edge=D("0.01"),
    )
    capital_id = allocator.allocate([request], now_us=1)[0].capital_id
    first = ledger.record_entry_fill(
        capital_id,
        asset="USDC",
        quantity_net=D("4.9995"),
        causal_mark_usdt=D(1),
        attributable_cost_usdt=D(0),
        input_usdt=D(5),
        now_us=2,
    )
    second = ledger.record_entry_fill(
        capital_id,
        asset="USDC",
        quantity_net=D("4.9995"),
        causal_mark_usdt=D(1),
        attributable_cost_usdt=D(0),
        input_usdt=D(5),
        now_us=3,
    )
    before = ledger.marked_equity()
    combined = ledger.consolidate_inventory(
        [first, second], pair_id="PAIR_A", asset="USDC", now_us=4
    )
    assert ledger.positions[combined].quantity == D("9.9990")
    assert ledger.owner_of(combined) == "PAIR_A"
    assert ledger.marked_equity() == before
    assert first not in ledger.positions and second not in ledger.positions


def test_merged_timeline_has_deterministic_pair_tie_break(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows = {
        "USDCUSDT": [book("USDCUSDT", START + 1)],
        "FDUSDUSDT": [book("FDUSDUSDT", START + 1)],
    }
    monkeypatch.setattr(m035_data, "_checked_events", lambda _root, symbol: iter(rows[symbol]))
    merged = list(m035_data.merged_events(Path(".")))
    assert [row["symbol"] for row in merged] == ["USDCUSDT", "FDUSDUSDT"]


def test_run_mode_preserves_all_fee_prefixes_on_failure() -> None:
    invalid = book("USDCUSDT", START + 1)
    invalid["kind"] = "UNKNOWN"
    with pytest.raises(M035BacktestExecutionError) as captured:
        run_mode(config(), events=[invalid], fees=(D(0), D(1), D(2), D(5), D(10)), parallel=False)
    error = captured.value
    assert error.mode == "SINGLE_PAIR"
    assert error.event_index == 1
    assert len(error.evidence) == 5
    assert [row["event_count"] for row in error.evidence] == [1, 0, 0, 0, 0]


def test_economic_engine_rejects_future_event() -> None:
    scenario = M035EconomicScenario(config(), fee_bps=D(0), parallel=False)
    with pytest.raises(ValueError, match="M035_EVENT_OUTSIDE_FROZEN_WINDOW"):
        scenario.receive(book("USDCUSDT", scenario.config.end_us))
    assert scenario.event_count == 0
    assert scenario.engines["USDCUSDT"].hotline is None


def test_one_shot_claim_creation_is_exclusive(tmp_path: Path) -> None:
    claim = tmp_path / "claim.json"
    _create_json_exclusive(claim, {"identity": "M035", "status": "STARTED"})
    with pytest.raises(FileExistsError):
        _create_json_exclusive(claim, {"identity": "M035", "status": "STARTED_AGAIN"})
    assert "STARTED_AGAIN" not in claim.read_text(encoding="utf-8")
