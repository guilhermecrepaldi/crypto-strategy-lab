from __future__ import annotations

import json
from decimal import Decimal as D

import pytest

from crypto_strategy_lab.microstructure.kraken_l3_recorder import KrakenL3RawRecorder
from crypto_strategy_lab.microstructure.multi_stable_queue import CausalQueueEstimator
from crypto_strategy_lab.microstructure.multi_venue_ledger import MultiVenuePortfolio
from crypto_strategy_lab.microstructure.multi_venue_models import (
    AssetSafetyEvidence,
    BookKey,
    L3EventType,
    L3OrderEvent,
    Venue,
    VenueFeeProfile,
    VenueOperationalEvidence,
    VenueRoute,
    VenueRouteLeg,
    VenueSymbolRule,
)
from crypto_strategy_lab.microstructure.multi_venue_queue import (
    L2QueueModel,
    L3QueueModel,
    L3ToL2AblationHarness,
)
from crypto_strategy_lab.microstructure.venue_adapters import BinanceL2Adapter, KrakenSpotAdapter

BINANCE = BookKey(Venue.BINANCE, "USDCUSDT")
KRAKEN = BookKey(Venue.KRAKEN, "USDC/USDT")


def event(
    event_id: str,
    event_type: L3EventType,
    order_id: str,
    quantity: str,
    *,
    book: BookKey = KRAKEN,
    side: str = "BUY",
    price: str = "1.0000",
    order_time: int = 1,
    exchange_time: int = 1,
    sequence: int = 1,
) -> L3OrderEvent:
    return L3OrderEvent(
        book,
        event_id,
        event_type,
        side,
        D(price),
        order_id,
        D(quantity),
        order_time,
        exchange_time,
        exchange_time,
        sequence,
    )


def portfolio() -> MultiVenuePortfolio:
    value = MultiVenuePortfolio()
    value.add_venue(
        Venue.BINANCE, {"USDT": "100", "USDC": "100"}, marks_usd={"USDT": "1", "USDC": "1"}
    )
    value.add_venue(
        Venue.KRAKEN, {"USDT": "100", "USDC": "100"}, marks_usd={"USDT": "1", "USDC": "1"}
    )
    for venue in Venue:
        value.ledger(venue).create_slot(
            "SAME", origin_asset="USDT", usd_equivalent=D("5"), now_us=0
        )
    return value


def test_book_key_includes_venue() -> None:
    assert BookKey(Venue.KRAKEN, "USDCUSDT") != BINANCE
    assert BINANCE.canonical_id == "BINANCE:USDCUSDT"


def test_same_order_id_on_two_venues_does_not_collide() -> None:
    value = portfolio()
    value.reserve(
        Venue.BINANCE, slot_id="SAME", reservation_id="R", asset="USDT", quantity=D("5"), now_us=1
    )
    value.reserve(
        Venue.KRAKEN, slot_id="SAME", reservation_id="R", asset="USDT", quantity=D("5"), now_us=1
    )
    assert value.ledger(Venue.BINANCE).free["USDT"] == D("95")
    assert value.ledger(Venue.KRAKEN).free["USDT"] == D("95")


def test_global_portfolio_is_sum_of_independent_ledgers() -> None:
    value = portfolio()
    assert value.venue_equities() == {Venue.BINANCE: D("200"), Venue.KRAKEN: D("200")}
    assert value.global_marked_equity() == D("400")
    value.reconcile()


def test_remote_capital_cannot_fund_local_route() -> None:
    value = MultiVenuePortfolio()
    value.add_venue(Venue.BINANCE, {"USDT": "200"}, marks_usd={"USDT": "1"})
    value.add_venue(Venue.KRAKEN, {"USDT": "0"}, marks_usd={"USDT": "1"})
    route = VenueRoute(
        "K",
        "USDT",
        (
            VenueRouteLeg(KRAKEN, "USDT", "USDC"),
            VenueRouteLeg(KRAKEN, "USDC", "USDT"),
        ),
    )
    with pytest.raises(ValueError, match="REMOTE_VENUE_CAPITAL"):
        value.assert_route_fundable(route, asset="USDT", quantity=D("5"))


def test_cross_venue_route_is_rejected() -> None:
    with pytest.raises(ValueError, match="CROSS_VENUE_ROUTE"):
        VenueRoute(
            "BAD",
            "USDT",
            (
                VenueRouteLeg(BINANCE, "USDT", "USDC"),
                VenueRouteLeg(KRAKEN, "USDC", "USDT"),
            ),
        )


def test_same_symbol_can_have_distinct_fee_and_rule() -> None:
    other = BookKey(Venue.KRAKEN, "USDCUSDT")
    fees = {
        BINANCE: VenueFeeProfile(BINANCE, D("0"), D("0.001"), "QUOTE", 0, None, "B", "B"),
        other: VenueFeeProfile(other, D("0.002"), D("0.002"), "QUOTE", 0, None, "K", "K"),
    }
    rules = {
        BINANCE: VenueSymbolRule(
            BINANCE, "USDC", "USDT", D("0.00001"), D("1"), D("1"), D("5"), 5, 0, None, "B"
        ),
        other: VenueSymbolRule(
            other, "USDC", "USDT", D("0.0001"), D("0.00000001"), D("5"), D("0.5"), 4, 0, None, "K"
        ),
    }
    assert fees[BINANCE].maker_rate != fees[other].maker_rate
    assert rules[BINANCE].tick_size != rules[other].tick_size


def test_order_semantics_and_unknown_latency_remain_venue_specific() -> None:
    binance = BinanceL2Adapter()
    kraken = KrakenSpotAdapter()
    assert binance.order_semantics().post_only_mechanism == "LIMIT_MAKER"
    assert kraken.order_semantics().quantity_decrease_priority == "PRESERVED"
    assert kraken.order_semantics().quantity_increase_priority == "LOST_BACK_OF_QUEUE"
    assert binance.conservative_latency_profile().order_ack_latency_us is None
    assert kraken.conservative_latency_profile().order_ack_latency_us is None


def test_asset_safety_is_separate_from_venue_operation() -> None:
    asset = AssetSafetyEvidence("USDC", D("1"), D("0.9"), D("0.8"), D("0.7"), 0, ("global",))
    venue = VenueOperationalEvidence(
        Venue.KRAKEN, "USDC", "enabled", True, D("0.5"), 0, ("kraken",)
    )
    assert asset.safety_score == D("0.85")
    assert venue.operational_quality_score == D("0.5")


def test_binance_adapter_preserves_native_symbol_and_values() -> None:
    row = {
        "symbol": "USDCUSDT",
        "side": "bid",
        "price": "0.9999",
        "amount": "10",
        "timestamp": 2,
        "local_timestamp": 3,
    }
    normalized = BinanceL2Adapter().normalize_l2_row(row)
    assert normalized.book == BINANCE
    assert (normalized.side, normalized.price, normalized.quantity) == ("BID", D("0.9999"), D("10"))


def test_kraken_l2_normalization_uses_native_slash_symbol() -> None:
    row = {
        "symbol": "USDC-USDT",
        "side": "ask",
        "price": "1.0001",
        "amount": "5",
        "timestamp": 2,
        "local_timestamp": 3,
    }
    normalized = KrakenSpotAdapter().normalize_l2_row(row)
    assert normalized.book == KRAKEN
    assert normalized.side == "ASK"


def test_kraken_current_rule_parsing() -> None:
    payload = {
        "error": [],
        "result": {
            "USDCUSDT": {
                "wsname": "USDC/USDT",
                "tick_size": "0.0001",
                "lot_decimals": 8,
                "ordermin": "5",
                "costmin": "0.5",
                "pair_decimals": 4,
            }
        },
    }
    rule = KrakenSpotAdapter.rule_from_asset_pairs(payload, as_of_us=10)
    assert rule.book == KRAKEN
    assert rule.quantity_step == D("0.00000001")
    rule.validate(price=D("1.0000"), quantity=D("5"), time_us=10)


def test_l2_same_symbol_never_shares_queue_across_venues() -> None:
    model = L2QueueModel()
    for book, public in ((BINANCE, D("10")), (BookKey(Venue.KRAKEN, "USDCUSDT"), D("2"))):
        model.activate(
            book,
            side="BUY",
            price=D("1"),
            order_id="SAME",
            column=1,
            quantity=D("1"),
            observed_public_queue=public,
            now_us=1,
        )
    assert model.queue_ahead(BINANCE, "SAME") == D("10")
    assert model.queue_ahead(BookKey(Venue.KRAKEN, "USDCUSDT"), "SAME") == D("2")


def test_binance_l2_queue_regression_matches_m032_fixture() -> None:
    old = CausalQueueEstimator()
    new = L2QueueModel()
    old.activate(
        book="USDCUSDT",
        side="BUY",
        price=D("1"),
        order_id="C1",
        column=1,
        quantity=D("1"),
        observed_public_queue=D("2"),
        now_us=1,
    )
    new.activate(
        BINANCE,
        side="BUY",
        price=D("1"),
        order_id="C1",
        column=1,
        quantity=D("1"),
        observed_public_queue=D("2"),
        now_us=1,
    )
    old_fill = old.consume_compatible_flow(
        event_id="T", book="USDCUSDT", side="BUY", price=D("1"), quantity=D("3"), now_us=2
    )
    new_fill = new.consume(
        BINANCE, event_id="T", side="BUY", price=D("1"), quantity=D("3"), now_us=2
    )
    assert old_fill == new_fill == {"C1": D("1")}


def test_kraken_l3_adapter_snapshot_and_update() -> None:
    snapshot = {
        "channel": "level3",
        "type": "snapshot",
        "data": [
            {
                "symbol": "USDC/USDT",
                "timestamp": "2025-01-01T00:00:00Z",
                "bids": [
                    {
                        "order_id": "A",
                        "limit_price": 1,
                        "order_qty": 2,
                        "timestamp": "2025-01-01T00:00:00Z",
                    }
                ],
                "asks": [],
            }
        ],
    }
    rows = KrakenSpotAdapter.normalize_l3_message(
        snapshot, local_capture_time_us=2, sequence_start=7
    )
    assert len(rows) == 1 and rows[0].event_type == L3EventType.ADD
    update = {
        "channel": "level3",
        "type": "update",
        "data": [
            {
                "symbol": "USDC/USDT",
                "timestamp": "2025-01-01T00:00:01Z",
                "bids": [
                    {
                        "event": "modify",
                        "order_id": "A",
                        "limit_price": 1,
                        "order_qty": 1,
                        "timestamp": "2025-01-01T00:00:00Z",
                    }
                ],
                "asks": [],
            }
        ],
    }
    assert (
        KrakenSpotAdapter.normalize_l3_message(update, local_capture_time_us=3, sequence_start=8)[
            0
        ].event_type
        == L3EventType.MODIFY
    )


def test_l3_add_modify_delete_lifecycle() -> None:
    model = L3QueueModel()
    model.apply_public_event(event("A", L3EventType.ADD, "P", "2"))
    model.apply_public_event(event("M", L3EventType.MODIFY, "P", "1", exchange_time=2, sequence=2))
    assert model.aggregate_l2(KRAKEN) == {("BUY", D("1.0000")): D("1")}
    model.apply_public_event(event("D", L3EventType.DELETE, "P", "0", exchange_time=3, sequence=3))
    assert model.aggregate_l2(KRAKEN) == {}


def test_l3_queue_ahead_and_c1_c2_insertion() -> None:
    model = L3QueueModel()
    model.apply_public_event(event("A", L3EventType.ADD, "P", "10"))
    model.activate_own(
        KRAKEN, side="BUY", price=D("1"), order_id="C1", quantity=D("1"), column=1, now_us=2
    )
    model.activate_own(
        KRAKEN, side="BUY", price=D("1"), order_id="C2", quantity=D("1"), column=2, now_us=3
    )
    assert model.queue_ahead(KRAKEN, "C1") == D("10")
    assert model.queue_ahead(KRAKEN, "C2") == D("11")
    assert model.public_orders_ahead(KRAKEN, "C2") == 1


def test_l3_rejects_duplicate_column_at_same_price() -> None:
    model = L3QueueModel()
    model.activate_own(
        KRAKEN, side="BUY", price=D("1"), order_id="C1", quantity=D("1"), column=1, now_us=1
    )
    with pytest.raises(ValueError, match="DUPLICATE_ACTIVE_COLUMN"):
        model.activate_own(
            KRAKEN,
            side="BUY",
            price=D("1"),
            order_id="ANOTHER_C1",
            quantity=D("1"),
            column=1,
            now_us=2,
        )


def test_l3_rejects_c2_without_c1() -> None:
    model = L3QueueModel()
    with pytest.raises(ValueError, match="C2_REQUIRES_ACTIVE_C1"):
        model.activate_own(
            KRAKEN, side="BUY", price=D("1"), order_id="C2", quantity=D("1"), column=2, now_us=1
        )


def test_l3_execution_consumes_public_then_own_once_and_partial_blocks_c2() -> None:
    model = L3QueueModel()
    model.apply_public_event(event("A", L3EventType.ADD, "P", "2"))
    model.activate_own(
        KRAKEN, side="BUY", price=D("1"), order_id="C1", quantity=D("2"), column=1, now_us=2
    )
    model.activate_own(
        KRAKEN, side="BUY", price=D("1"), order_id="C2", quantity=D("1"), column=2, now_us=3
    )
    assert model.consume_execution(
        KRAKEN, event_id="T", side="BUY", price=D("1"), quantity=D("3"), exchange_time_us=4
    ) == {"C1": D("1")}
    assert model.queue_ahead(KRAKEN, "C2") == D("1")
    with pytest.raises(ValueError, match="DUPLICATE"):
        model.consume_execution(
            KRAKEN, event_id="T", side="BUY", price=D("1"), quantity=D("1"), exchange_time_us=4
        )


def test_same_timestamp_tie_is_conservative_for_our_order() -> None:
    model = L3QueueModel()
    model.activate_own(
        KRAKEN, side="BUY", price=D("1"), order_id="C1", quantity=D("1"), column=1, now_us=1
    )
    model.apply_public_event(event("A", L3EventType.ADD, "P", "2", order_time=1, exchange_time=1))
    assert model.queue_ahead(KRAKEN, "C1") == D("2")


def test_own_amend_down_keeps_priority() -> None:
    model = L3QueueModel()
    model.activate_own(
        KRAKEN, side="BUY", price=D("1"), order_id="C1", quantity=D("2"), column=1, now_us=1
    )
    model.apply_public_event(event("A", L3EventType.ADD, "P", "1", order_time=2, exchange_time=2))
    model.amend_own(KRAKEN, "C1", new_quantity=D("1"), now_us=3)
    assert model.queue_ahead(KRAKEN, "C1") == 0


def test_own_amend_up_moves_to_back() -> None:
    model = L3QueueModel()
    model.activate_own(
        KRAKEN, side="BUY", price=D("1"), order_id="C1", quantity=D("1"), column=1, now_us=1
    )
    model.apply_public_event(event("A", L3EventType.ADD, "P", "2", order_time=2, exchange_time=2))
    model.amend_own(KRAKEN, "C1", new_quantity=D("2"), now_us=3)
    assert model.queue_ahead(KRAKEN, "C1") == D("2")


def test_own_price_amend_moves_to_back_of_new_price() -> None:
    model = L3QueueModel()
    model.apply_public_event(event("A", L3EventType.ADD, "P", "3", price="0.9999"))
    model.activate_own(
        KRAKEN, side="BUY", price=D("1"), order_id="C1", quantity=D("1"), column=1, now_us=2
    )
    model.amend_own(KRAKEN, "C1", new_quantity=D("1"), new_price=D("0.9999"), now_us=3)
    assert model.queue_ahead(KRAKEN, "C1") == D("3")


def test_own_price_amend_cannot_duplicate_column_at_destination() -> None:
    model = L3QueueModel()
    model.activate_own(
        KRAKEN, side="BUY", price=D("1"), order_id="C1_A", quantity=D("1"), column=1, now_us=1
    )
    model.activate_own(
        KRAKEN,
        side="BUY",
        price=D("0.9999"),
        order_id="C1_B",
        quantity=D("1"),
        column=1,
        now_us=2,
    )
    with pytest.raises(ValueError, match="AMEND_WOULD_DUPLICATE"):
        model.amend_own(KRAKEN, "C1_A", new_quantity=D("1"), new_price=D("0.9999"), now_us=3)
    assert model.queue_ahead(KRAKEN, "C1_A") == D("0")


def test_cancel_ack_rejects_partial_own_order() -> None:
    model = L3QueueModel()
    model.activate_own(
        KRAKEN, side="BUY", price=D("1"), order_id="C1", quantity=D("2"), column=1, now_us=1
    )
    model.consume_execution(
        KRAKEN, event_id="T", side="BUY", price=D("1"), quantity=D("1"), exchange_time_us=2
    )
    model.cancel_request(KRAKEN, "C1", now_us=3)
    with pytest.raises(ValueError, match="NOT_RECLAIMABLE"):
        model.cancel_ack(KRAKEN, "C1", now_us=4)


def test_cancel_ack_requires_prior_request_and_causal_time() -> None:
    model = L3QueueModel()
    model.activate_own(
        KRAKEN, side="BUY", price=D("1"), order_id="C1", quantity=D("1"), column=1, now_us=10
    )
    with pytest.raises(ValueError, match="NOT_RECLAIMABLE"):
        model.cancel_ack(KRAKEN, "C1", now_us=11)
    model.cancel_request(KRAKEN, "C1", now_us=12)
    assert model.cancel_ack(KRAKEN, "C1", now_us=13) == D("1")


def test_execution_before_own_activation_fails_closed() -> None:
    model = L3QueueModel()
    model.activate_own(
        KRAKEN, side="BUY", price=D("1"), order_id="FUTURE", quantity=D("1"), column=1, now_us=100
    )
    with pytest.raises(ValueError, match="OUT_OF_ORDER"):
        model.consume_execution(
            KRAKEN, event_id="EARLY", side="BUY", price=D("1"), quantity=D("1"), exchange_time_us=1
        )


def test_same_timestamp_execution_cannot_fill_new_own_order() -> None:
    model = L3QueueModel()
    model.activate_own(
        KRAKEN, side="BUY", price=D("1"), order_id="C1", quantity=D("1"), column=1, now_us=100
    )
    assert (
        model.consume_execution(
            KRAKEN, event_id="SAME", side="BUY", price=D("1"), quantity=D("1"), exchange_time_us=100
        )
        == {}
    )


def test_trade_consumption_reconciles_matching_native_modify_once() -> None:
    model = L3QueueModel()
    model.apply_public_event(event("A", L3EventType.ADD, "P", "2"))
    assert (
        model.consume_execution(
            KRAKEN, event_id="T", side="BUY", price=D("1"), quantity=D("1"), exchange_time_us=2
        )
        == {}
    )
    model.apply_public_event(event("M", L3EventType.MODIFY, "P", "1", exchange_time=2, sequence=2))
    assert model.aggregate_l2(KRAKEN) == {("BUY", D("1.0000")): D("1")}


def test_negative_native_remaining_cannot_create_liquidity() -> None:
    model = L3QueueModel()
    model.apply_public_event(event("A", L3EventType.ADD, "P", "2"))
    model.consume_execution(
        KRAKEN, event_id="T", side="BUY", price=D("1"), quantity=D("1"), exchange_time_us=2
    )
    with pytest.raises(ValueError, match="NEGATIVE_L3_REMAINING"):
        model.apply_public_event(
            event("M", L3EventType.MODIFY, "P", "-1", exchange_time=2, sequence=2)
        )
    assert model.aggregate_l2(KRAKEN) == {("BUY", D("1.0000")): D("1")}


def test_native_delete_before_trade_suppresses_ambiguous_fill_inference() -> None:
    model = L3QueueModel()
    model.apply_public_event(event("A", L3EventType.ADD, "P", "1"))
    model.activate_own(
        KRAKEN, side="BUY", price=D("1"), order_id="C1", quantity=D("1"), column=1, now_us=2
    )
    model.apply_public_event(event("D", L3EventType.DELETE, "P", "0", exchange_time=3, sequence=2))
    with pytest.raises(ValueError, match="ORDERING_AMBIGUOUS"):
        model.consume_execution(
            KRAKEN, event_id="T", side="BUY", price=D("1"), quantity=D("1"), exchange_time_us=3
        )


def test_native_delete_beyond_pending_confirmation_suppresses_next_fill() -> None:
    model = L3QueueModel()
    model.apply_public_event(event("A", L3EventType.ADD, "P", "2"))
    model.activate_own(
        KRAKEN, side="BUY", price=D("1"), order_id="C1", quantity=D("1"), column=1, now_us=2
    )
    model.consume_execution(
        KRAKEN, event_id="T1", side="BUY", price=D("1"), quantity=D("1"), exchange_time_us=3
    )
    model.apply_public_event(event("D", L3EventType.DELETE, "P", "0", exchange_time=3, sequence=2))
    with pytest.raises(ValueError, match="ORDERING_AMBIGUOUS"):
        model.consume_execution(
            KRAKEN, event_id="T2", side="BUY", price=D("1"), quantity=D("1"), exchange_time_us=3
        )


def test_native_modify_beyond_pending_confirmation_suppresses_next_fill() -> None:
    model = L3QueueModel()
    model.apply_public_event(event("A", L3EventType.ADD, "P", "3"))
    model.activate_own(
        KRAKEN, side="BUY", price=D("1"), order_id="C1", quantity=D("1"), column=1, now_us=2
    )
    model.consume_execution(
        KRAKEN, event_id="T1", side="BUY", price=D("1"), quantity=D("1"), exchange_time_us=3
    )
    model.apply_public_event(event("M", L3EventType.MODIFY, "P", "1", exchange_time=3, sequence=2))
    with pytest.raises(ValueError, match="ORDERING_AMBIGUOUS"):
        model.consume_execution(
            KRAKEN, event_id="T2", side="BUY", price=D("1"), quantity=D("1"), exchange_time_us=3
        )


def test_l3_gap_blocks_new_orders_and_execution() -> None:
    model = L3QueueModel()
    model.mark_gap(KRAKEN)
    with pytest.raises(ValueError, match="GAPPED"):
        model.activate_own(
            KRAKEN, side="BUY", price=D("1"), order_id="C1", quantity=D("1"), column=1, now_us=1
        )


def test_duplicate_and_out_of_order_public_events_fail() -> None:
    model = L3QueueModel()
    first = event("A", L3EventType.ADD, "P", "1", exchange_time=5)
    model.apply_public_event(first)
    with pytest.raises(ValueError, match="DUPLICATE"):
        model.apply_public_event(first)
    with pytest.raises(ValueError, match="OUT_OF_ORDER"):
        model.apply_public_event(event("B", L3EventType.ADD, "Q", "1", exchange_time=4))


def test_l3_to_l2_aggregation_and_ablation_fixture() -> None:
    harness = L3ToL2AblationHarness()
    harness.apply_public_event(event("A", L3EventType.ADD, "P1", "2", sequence=1))
    harness.activate_own(
        KRAKEN, side="BUY", price=D("1"), order_id="C1", quantity=D("1"), column=1, now_us=2
    )
    harness.apply_public_event(
        event("B", L3EventType.ADD, "P2", "3", order_time=3, exchange_time=3, sequence=2)
    )
    assert harness.l3.aggregate_l2(KRAKEN) == {("BUY", D("1.0000")): D("5")}
    comparison = harness.compare(KRAKEN, "C1")
    assert comparison.l3_queue_ahead == D("2")
    assert comparison.l2_queue_ahead == D("2")
    assert comparison.difference == D("0")
    l3_fills, l2_fills = harness.consume_execution(
        KRAKEN,
        event_id="T",
        side="BUY",
        price=D("1"),
        quantity=D("3"),
        exchange_time_us=4,
    )
    assert l3_fills == {"C1": D("1")}
    assert l2_fills == {"C1": D("1")}


def test_recorder_requires_auth_token_without_accessing_account() -> None:
    with pytest.raises(PermissionError, match="AUTH_TOKEN_REQUIRED"):
        KrakenL3RawRecorder.require_subscription_token(None)


def test_recorder_persists_raw_before_normalized_and_reports_gap(tmp_path) -> None:
    recorder = KrakenL3RawRecorder(tmp_path / "capture", book=KRAKEN, started_at_us=1)
    recorder.append_raw(b'{"channel":"level3"}', local_capture_time_us=2, sequence=1)
    recorder.append_normalized({"event": "ADD"}, raw_sequence=1, source_event_index=0)
    recorder.append_raw(b'{"channel":"level3"}', local_capture_time_us=4, sequence=3)
    recorder.record_reconnect(at_us=5, reason="test")
    manifest = recorder.close(ended_at_us=6)
    assert manifest.event_count == 2
    assert manifest.sequence_valid is False
    assert manifest.capture_valid is False
    assert manifest.gaps == [{"start_sequence": 2, "end_sequence": 2, "detected_at_us": 4}]
    assert manifest.reconnects == [{"at_us": 5, "reason": "test"}]
    payload = json.loads((tmp_path / "capture" / "manifest.json").read_text())
    assert payload["raw_sha256"] and payload["normalized_sha256"]
    with pytest.raises(ValueError, match="ALREADY_CLOSED"):
        recorder.append_raw(b"{}", local_capture_time_us=7, sequence=4)


def test_normalization_before_raw_is_rejected(tmp_path) -> None:
    recorder = KrakenL3RawRecorder(tmp_path / "capture", book=KRAKEN, started_at_us=1)
    with pytest.raises(ValueError, match="BEFORE_RAW"):
        recorder.append_normalized({"event": "ADD"}, raw_sequence=1, source_event_index=0)


def test_normalized_event_is_bound_to_exact_raw_message(tmp_path) -> None:
    recorder = KrakenL3RawRecorder(tmp_path / "capture", book=KRAKEN, started_at_us=1)
    expected_hash = recorder.append_raw(
        b'{"channel":"level3"}', local_capture_time_us=2, sequence=7
    )
    recorder.append_normalized({"event": "ADD"}, raw_sequence=7, source_event_index=0)
    row = json.loads(recorder.normalized_path.read_text().strip())
    assert row["raw_sequence"] == 7
    assert row["native_message_sha256"] == expected_hash
    with pytest.raises(ValueError, match="DUPLICATE_NORMALIZED"):
        recorder.append_normalized({"event": "ADD"}, raw_sequence=7, source_event_index=0)
