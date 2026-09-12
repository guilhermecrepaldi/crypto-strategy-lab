from __future__ import annotations

from decimal import Decimal as D
from pathlib import Path

import pytest

from crypto_strategy_lab.microstructure import m035_data
from crypto_strategy_lab.microstructure.m035_economic_backtest import (
    M035BacktestConfig,
    M035EconomicScenario,
)
from crypto_strategy_lab.microstructure.parallel_pair_capital_manager import (
    AllocationCandidate,
    AllocationPriority,
    GlobalCapitalLedger,
    ParallelPairCapitalAllocator,
)

START = m035_data.START_US


def config(**changes: object) -> M035BacktestConfig:
    values: dict[str, object] = {
        "identity": "M035_200USD_3H_PARALLEL_DEVELOPMENT_BACKTEST_V1",
        "start_us": START,
        "end_us": START + 10_800_000_000,
    }
    values.update(changes)
    return M035BacktestConfig(**values)  # type: ignore[arg-type]


def book(symbol: str, local_us: int, *, bid: str = "0.9999", ask: str = "1.0001"):
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
