from __future__ import annotations

from decimal import Decimal as D

import pytest

from crypto_strategy_lab.microstructure.m034_zero_loss_backtest import (
    BacktestExecutionError,
    M034ZeroLossScenario,
    ZeroLossConfig,
    negative_risk_exit_allowed,
    run_scenarios,
    zero_loss_economic_pass,
)
from crypto_strategy_lab.microstructure.multi_stable_ledger import SlotLedger
from crypto_strategy_lab.microstructure.multi_stable_queue import CausalQueueEstimator

START = 1_735_689_600_000_000


def config_row(**changes):
    names = {
        "MIN_COMPLETION_PROBABILITY": ("0.90", "ratio"),
        "MAX_EXPECTED_LOCK_TIME": ("300", "seconds"),
        "RISK_BUFFER": ("2", "bps"),
        "MAX_INVENTORY_EXPOSURE": ("20", "USD"),
        "PEG_DEVIATION_THRESHOLD": ("0.0025", "ratio"),
        "MIN_NET_EDGE": ("1", "bps"),
        "TAIL_RISK_BOUND": ("1", "USD"),
        "MAX_SPREAD": ("5", "bps"),
        "MIN_DEPTH": ("1000", "USD"),
        "MIN_COMPATIBLE_FLOW": ("10", "asset/second"),
    }
    row = {
        "identity": "M034_ZERO_LOSS_DEV_BACKTEST_200USD_3H_V1",
        "start_us": START,
        "end_us": START + 10_800_000_000,
        "initial_bank_usdt": "200",
        "slot_base_usdt": "10",
        "activation_latency_us": 1_179_525,
        "cancel_ack_latency_us": 1_179_525,
        "tick_size": "0.0001",
        "quantity_step": "1",
        "minimum_quantity": "1",
        "minimum_notional": "5",
        "flow_window_seconds": 60,
        "depth_band_bps": "10",
        "diagnostic_completion_probability": "0.90",
        "diagnostic_expected_lock_seconds": "300",
        "diagnostic_execution_cost_bps": "1",
        "diagnostic_adverse_selection_bps": "1",
        "taker_contingency_fee_bps": "10",
        "fee_scenarios_bps": [0, 1, 2, 5, 10],
        "emergency_exit_peg_deviation": "0.0025",
        "thresholds": [
            {
                "name": name,
                "value": value,
                "unit": unit,
                "source_type": "PROTOCOL_CONSTANT",
                "source_reference": "OWNER_M034_ZERO_LOSS_PROMPT",
                "derivation_method": "OWNER_DIAGNOSTIC_ASSUMPTION",
                "calibration_dataset_hash": None,
                "effective_from_us": START,
                "frozen_at_us": START + 60_000_000_000,
            }
            for name, (value, unit) in names.items()
        ],
    }
    row.update(changes)
    return row


def config(**changes) -> ZeroLossConfig:
    return ZeroLossConfig.from_mapping(config_row(**changes))


def book(
    local_us: int,
    *,
    bid="0.9999",
    ask="1.0001",
    bid_quantity="100000",
    ask_quantity="100000",
    upper_us=None,
):
    return {
        "kind": "BOOK",
        "local_us": local_us,
        "exchange_us": local_us,
        "exchange_upper_us": local_us if upper_us is None else upper_us,
        "sequence_validated": True,
        "bids": [(D(bid), D(bid_quantity))],
        "asks": [(D(ask), D(ask_quantity))],
    }


def trade(
    local_us: int,
    trade_id: int,
    *,
    price: str,
    quantity="1000",
    buyer_maker=True,
    exchange_us=None,
):
    return {
        "kind": "TRADE",
        "local_us": local_us,
        "exchange_us": local_us if exchange_us is None else exchange_us,
        "data": {
            "t": trade_id,
            "p": price,
            "q": quantity,
            "m": buyer_maker,
        },
    }


def test_negative_cycle_fails_zero_loss_invariant() -> None:
    assert not zero_loss_economic_pass(
        cycle_pnls=[D("-0.01")],
        negative_risk_exits=0,
        final_marked_equity=D("200"),
        initial_equity=D("200"),
    )


def test_positive_cycle_cannot_offset_negative_cycle() -> None:
    assert not zero_loss_economic_pass(
        cycle_pnls=[D("0.20"), D("-0.20")],
        negative_risk_exits=0,
        final_marked_equity=D("200"),
        initial_equity=D("200"),
    )


def test_open_inventory_is_marked_at_cutoff() -> None:
    scenario = M034ZeroLossScenario(config(), fee_bps=D(0))
    scenario.last_book = {"bids": ((D("0.98"), D(100)),), "asks": ((D("0.99"), D(100)),)}
    scenario.ledger.free["USDT"] -= D(10)
    scenario.ledger._asset_totals["USDT"] -= D(10)
    scenario.ledger.free["USDC"] += D(10)
    scenario.ledger._asset_totals["USDC"] += D(10)
    free, reserved, owned = scenario._bucket_values()
    assert free + reserved + owned == D("199.8")


def test_realized_zero_does_not_hide_negative_unrealized() -> None:
    assert not zero_loss_economic_pass(
        cycle_pnls=[],
        negative_risk_exits=0,
        final_marked_equity=D("199.8"),
        initial_equity=D("200"),
    )


def test_owned_return_priority_blocks_exposure_above_global_cap() -> None:
    scenario = M034ZeroLossScenario(config(), fee_bps=D(0))
    slot = scenario.ledger.create_slot(
        "slot", origin_asset="USDT", usd_equivalent=D(10), now_us=START
    )
    scenario.ledger.owned[slot.slot_id]["USDC"] = D(20)
    scenario.ledger._asset_totals["USDC"] += D(20)
    assert scenario._potential_exposure() == D(20)


def test_no_cosmetic_negative_exit() -> None:
    assert not negative_risk_exit_allowed(
        peg_deviation=D("0.001"),
        trigger_deviation=D("0.0025"),
        expected_hold_loss=D("1"),
        opportunity_cost_of_lock=D(0),
        tail_risk_increase=D(0),
        realized_loss_of_exit=D("0.5"),
    )
    assert not negative_risk_exit_allowed(
        peg_deviation=D("0.003"),
        trigger_deviation=D("0.0025"),
        expected_hold_loss=D("0.4"),
        opportunity_cost_of_lock=D(0),
        tail_risk_increase=D(0),
        realized_loss_of_exit=D("0.5"),
    )


def test_negative_risk_exit_marks_zero_loss_fail() -> None:
    assert not zero_loss_economic_pass(
        cycle_pnls=[D("0.1")],
        negative_risk_exits=1,
        final_marked_equity=D("201"),
        initial_equity=D("200"),
    )


def test_cancel_ack_required() -> None:
    ledger = SlotLedger({"USDT": D(200)}, marks_usd={"USDT": D(1)})
    ledger.create_slot("s", origin_asset="USDT", usd_equivalent=D(10), now_us=1)
    ledger.reserve_free("s", "r", asset="USDT", quantity=D(10), now_us=1)
    ledger.activate("r", now_us=2)
    ledger.request_cancel("r", now_us=3)
    assert ledger.free["USDT"] == D(190)
    ledger.acknowledge_cancel("r", now_us=4)
    assert ledger.free["USDT"] == D(200)


def test_cancel_ack_returns_owned_inventory_to_its_slot() -> None:
    ledger = SlotLedger({"USDT": D(200), "USDC": D(0)}, marks_usd={"USDT": D(1), "USDC": D(1)})
    ledger.create_slot("s", origin_asset="USDT", usd_equivalent=D(10), now_us=1)
    ledger.owned["s"]["USDC"] = D(10)
    ledger._asset_totals["USDC"] += D(10)
    ledger.reserve_owned("s", "r", asset="USDC", quantity=D(10), now_us=2)
    ledger.activate("r", now_us=3)
    ledger.request_cancel("r", now_us=4)
    assert ledger.owned["s"]["USDC"] == 0
    ledger.acknowledge_cancel("r", now_us=5)
    assert ledger.owned["s"]["USDC"] == D(10)
    assert ledger.free["USDC"] == 0
    ledger.reconcile()


def test_no_self_fill() -> None:
    scenario = M034ZeroLossScenario(config(), fee_bps=D(0))
    scenario.receive_trade(trade(START + 1_000_000, 1, price="0.9999", buyer_maker=True))
    scenario.receive_trade(trade(START + 2_000_000, 2, price="1.0001", buyer_maker=False))
    scenario.receive_book(book(START + 3_000_000))
    assert all(order.filled_quantity == 0 for order in scenario.orders.values())


def test_one_trade_quantity_is_not_duplicated_across_touched_prices() -> None:
    queue = CausalQueueEstimator()
    for index, price in enumerate((D("0.9999"), D("0.9998")), 1):
        queue.activate(
            book="BINANCE:USDCUSDT",
            side="BUY",
            price=price,
            order_id=f"o{index}",
            column=1,
            quantity=D(10),
            observed_public_queue=D(0),
            now_us=index,
        )
    fills = queue.consume_trade_through(
        event_id="trade-1",
        book="BINANCE:USDCUSDT",
        side="BUY",
        trade_price=D("0.9997"),
        quantity=D(15),
        now_us=3,
    )
    assert fills == {"o1": D(10), "o2": D(5)}
    assert sum(fills.values(), D(0)) == D(15)


def test_no_future_event_changes_decision() -> None:
    scenario = M034ZeroLossScenario(config(), fee_bps=D(0))
    scenario.receive_trade(trade(START + 1_000_000, 1, price="0.9999", buyer_maker=True))
    scenario.receive_trade(trade(START + 2_000_000, 2, price="1.0001", buyer_maker=False))
    scenario.receive_book(book(START + 3_000_000))
    scenario.receive_book(book(START + 5_000_000, upper_us=START + 9_000_000))
    scenario.receive_trade(trade(START + 6_000_000, 3, price="0.9997", buyer_maker=True))
    assert all(order.filled_quantity == 0 for order in scenario.orders.values())


def test_delayed_trade_native_time_before_activation_cannot_fill() -> None:
    scenario = M034ZeroLossScenario(config(), fee_bps=D(0))
    scenario.receive_trade(trade(START + 1_000_000, 1, price="0.9999", buyer_maker=True))
    scenario.receive_trade(trade(START + 2_000_000, 2, price="1.0001", buyer_maker=False))
    scenario.receive_book(book(START + 3_000_000))
    scenario.receive_trade(
        trade(
            START + 6_000_000,
            3,
            price="0.9997",
            quantity="20",
            buyer_maker=True,
            exchange_us=START + 3_500_000,
        )
    )
    assert all(order.filled_quantity == 0 for order in scenario.orders.values())


def test_capital_conservation() -> None:
    ledger = SlotLedger({"USDT": D(200), "USDC": D(0)}, marks_usd={"USDT": D(1), "USDC": D(1)})
    ledger.create_slot("s", origin_asset="USDT", usd_equivalent=D(10), now_us=1)
    ledger.reserve_free("s", "r", asset="USDT", quantity=D(10), now_us=1)
    ledger.activate("r", now_us=2)
    ledger.debit_reserved_cost("r", quantity=D("0.01"), cost_kind="TEST", now_us=3)
    assert ledger.marked_equity() == D("199.99")
    ledger.reconcile()


def test_each_scenario_starts_exactly_200() -> None:
    scenarios = [M034ZeroLossScenario(config(), fee_bps=fee) for fee in config().fee_scenarios_bps]
    assert {scenario.ledger.initial_equity for scenario in scenarios} == {D(200)}


def test_fee_grid_is_frozen_before_results() -> None:
    with pytest.raises(ValueError, match="M034_ZERO_LOSS_CONFIG_NOT_FROZEN"):
        config(fee_scenarios_bps=[0, 2, 5, 10])


def test_same_tape_all_scenarios() -> None:
    results, cycles, checkpoints, evidence = run_scenarios(config(), [])
    assert not cycles
    assert len(checkpoints) == 35
    assert {(row["EVENT_COUNT"], row["BOOK_COUNT"], row["TRADE_COUNT"]) for row in results} == {
        (0, 0, 0)
    }
    assert {row["INITIAL_BANK_USD"] for row in results} == {"200"}
    assert len(evidence) == 5
    assert all("ledger" in row and "queue" in row and "eligibility" in row for row in evidence)


def test_failure_preserves_executed_prefix_evidence() -> None:
    invalid = book(START + 1_000_000)
    invalid["kind"] = "UNKNOWN"
    with pytest.raises(BacktestExecutionError) as captured:
        run_scenarios(config(), [invalid])
    assert len(captured.value.evidence) == 5
    assert all(row["event_counts"]["events"] == 0 for row in captured.value.evidence)


def test_fee_zero_physical_cycle_closes_without_cross_subsidy() -> None:
    scenario = M034ZeroLossScenario(config(), fee_bps=D(0))
    scenario.receive_trade(
        trade(START + 1_000_000, 1, price="0.9999", quantity="600", buyer_maker=True)
    )
    scenario.receive_trade(
        trade(START + 2_000_000, 2, price="1.0001", quantity="600", buyer_maker=False)
    )
    scenario.receive_book(book(START + 3_000_000))
    scenario.receive_book(book(START + 5_000_000))
    scenario.receive_trade(
        trade(START + 6_000_000, 3, price="0.9997", quantity="30", buyer_maker=True)
    )
    scenario.receive_book(book(START + 8_000_000))
    scenario.receive_book(book(START + 10_000_000))
    scenario.receive_trade(
        trade(START + 11_000_000, 4, price="1.0003", quantity="30", buyer_maker=False)
    )
    assert len(scenario.cycles) == 2
    assert all(D(row["net_pnl"]) >= 0 for row in scenario.cycles)


def test_nonzero_received_asset_fee_cannot_hide_dust() -> None:
    scenario = M034ZeroLossScenario(config(), fee_bps=D(1))
    scenario.receive_trade(
        trade(START + 1_000_000, 1, price="0.9999", quantity="600", buyer_maker=True)
    )
    scenario.receive_trade(
        trade(START + 2_000_000, 2, price="1.0001", quantity="600", buyer_maker=False)
    )
    scenario.receive_book(book(START + 3_000_000))
    assert not scenario.orders
    assert scenario.rejections["FEE_DUST_PREVENTS_FULL_RETURN"] > 0


def test_negative_risk_exit_waits_for_return_cancel_ack_and_is_realized() -> None:
    scenario = M034ZeroLossScenario(config(), fee_bps=D(0))
    scenario.receive_trade(
        trade(START + 1_000_000, 1, price="0.9999", quantity="600", buyer_maker=True)
    )
    scenario.receive_trade(
        trade(START + 2_000_000, 2, price="1.0001", quantity="600", buyer_maker=False)
    )
    scenario.receive_book(book(START + 3_000_000))
    scenario.receive_book(book(START + 5_000_000))
    scenario.receive_trade(
        trade(START + 6_000_000, 3, price="0.9997", quantity="10", buyer_maker=True)
    )
    return_order = next(order for order in scenario.orders.values() if order.kind == "RETURN")
    scenario.receive_book(book(START + 8_000_000, bid="0.9940", ask="0.9942"))
    assert return_order.status == "CANCEL_PENDING"
    assert scenario.negative_risk_exits == 0
    scenario.receive_book(book(START + 10_000_000, bid="0.9940", ask="0.9942"))
    assert return_order.status == "CANCELLED"
    assert scenario.negative_risk_exits == 1
    result = scenario.finish()
    assert result["ZERO_LOSS_ECONOMIC_PASS"] is False
    assert D(result["NET_REALIZED_PNL_USD"]) < 0
    assert D(result["UNREALIZED_PNL_USD"]) == 0


def test_owned_return_reservations_remain_inside_global_exposure_cap() -> None:
    scenario = M034ZeroLossScenario(config(), fee_bps=D(0))
    scenario.receive_trade(
        trade(START + 1_000_000, 1, price="0.9999", quantity="600", buyer_maker=True)
    )
    scenario.receive_trade(
        trade(START + 2_000_000, 2, price="1.0001", quantity="600", buyer_maker=False)
    )
    scenario.receive_book(book(START + 3_000_000))
    scenario.receive_book(book(START + 5_000_000))
    scenario.receive_trade(
        trade(START + 6_000_000, 3, price="0.9997", quantity="20", buyer_maker=True)
    )
    assert D("19") < scenario._potential_exposure() <= D("20")
    before = len(scenario._active_orders(kind="ENTRY"))
    scenario.receive_book(book(START + 8_000_000))
    assert len(scenario._active_orders(kind="ENTRY")) == before


def test_partial_entry_is_protected_from_risk_exit() -> None:
    scenario = M034ZeroLossScenario(config(), fee_bps=D(0))
    scenario.receive_trade(
        trade(START + 1_000_000, 1, price="0.9999", quantity="600", buyer_maker=True)
    )
    scenario.receive_trade(
        trade(START + 2_000_000, 2, price="1.0001", quantity="600", buyer_maker=False)
    )
    scenario.receive_book(book(START + 3_000_000))
    scenario.receive_book(book(START + 5_000_000))
    scenario.receive_trade(
        trade(START + 6_000_000, 3, price="0.9997", quantity="5", buyer_maker=True)
    )
    scenario.receive_book(book(START + 8_000_000, bid="0.9940", ask="0.9942"))
    assert scenario.negative_risk_exits == 0
    assert scenario.rejections["PARTIAL_ENTRY_PROTECTED"] > 0


def test_partial_owned_return_is_protected_from_risk_cancel() -> None:
    scenario = M034ZeroLossScenario(config(), fee_bps=D(0))
    scenario.receive_trade(
        trade(START + 1_000_000, 1, price="0.9999", quantity="600", buyer_maker=True)
    )
    scenario.receive_trade(
        trade(START + 2_000_000, 2, price="1.0001", quantity="600", buyer_maker=False)
    )
    scenario.receive_book(book(START + 3_000_000))
    scenario.receive_book(book(START + 5_000_000))
    scenario.receive_trade(
        trade(START + 6_000_000, 3, price="0.9997", quantity="10", buyer_maker=True)
    )
    scenario.receive_book(book(START + 8_000_000))
    scenario.receive_trade(
        trade(START + 10_000_000, 4, price="1.0003", quantity="5", buyer_maker=False)
    )
    return_order = next(order for order in scenario.orders.values() if order.kind == "RETURN")
    assert return_order.status == "PARTIAL"
    scenario.receive_book(book(START + 12_000_000, bid="0.9940", ask="0.9942"))
    assert return_order.status == "PARTIAL"
    assert scenario.negative_risk_exits == 0
    assert scenario.rejections["PARTIAL_POSITION_PROTECTED"] > 0


def test_risk_exit_consumes_displayed_depth_once_across_slots() -> None:
    scenario = M034ZeroLossScenario(config(), fee_bps=D(0))
    scenario.receive_trade(
        trade(START + 1_000_000, 1, price="0.9999", quantity="600", buyer_maker=True)
    )
    scenario.receive_trade(
        trade(START + 2_000_000, 2, price="1.0001", quantity="600", buyer_maker=False)
    )
    scenario.receive_book(book(START + 3_000_000))
    scenario.receive_book(book(START + 5_000_000))
    scenario.receive_trade(
        trade(START + 6_000_000, 3, price="0.9997", quantity="20", buyer_maker=True)
    )
    scenario.receive_book(book(START + 8_000_000, bid="0.9940", ask="0.9942", bid_quantity="10"))
    scenario.receive_book(book(START + 10_000_000, bid="0.9940", ask="0.9942", bid_quantity="10"))
    assert scenario.negative_risk_exits == 1
    assert scenario.rejections["RISK_EXIT_DEPTH_INSUFFICIENT"] > 0
    assert scenario._residual_inventory() == {"USDC": "10"}
    scenario.receive_book(book(START + 12_000_000, bid="0.9940", ask="0.9942", bid_quantity="10"))
    assert scenario.negative_risk_exits == 1


@pytest.mark.parametrize("racing_quantity", ["15", "20"])
def test_cancel_ack_survives_partial_or_full_racing_fill(racing_quantity: str) -> None:
    scenario = M034ZeroLossScenario(config(), fee_bps=D(0))
    scenario.receive_trade(
        trade(START + 1_000_000, 1, price="0.9999", quantity="600", buyer_maker=True)
    )
    scenario.receive_trade(
        trade(START + 2_000_000, 2, price="1.0001", quantity="600", buyer_maker=False)
    )
    scenario.receive_book(book(START + 3_000_000))
    scenario.receive_book(book(START + 5_000_000))
    c2 = next(
        order for order in scenario.orders.values() if order.kind == "ENTRY" and order.column == 2
    )
    scenario.receive_book(book(START + 7_000_000, bid="1.0000", ask="1.0002"))
    assert c2.status == "CANCEL_PENDING"
    scenario.receive_trade(
        trade(
            START + 7_500_000,
            3,
            price="0.9997",
            quantity=racing_quantity,
            buyer_maker=True,
        )
    )
    assert c2.status == "CANCEL_PENDING"
    scenario.receive_book(book(START + 9_000_000, bid="1.0000", ask="1.0002"))
    assert c2.reservation_id not in scenario.ledger.reservations
    if D(racing_quantity) < D(20):
        assert c2.status == "PARTIAL_CANCELLED"
        assert c2.filled_quantity == D(5)
    else:
        assert c2.status == "FILLED"
        assert c2.filled_quantity == D(10)
        assert any(
            order.kind == "RETURN" and order.slot_id == c2.slot_id
            for order in scenario.orders.values()
        )
    scenario.ledger.reconcile()
