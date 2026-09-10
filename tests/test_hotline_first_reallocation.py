from __future__ import annotations

from copy import deepcopy
from decimal import Decimal as D

import pytest

from crypto_strategy_lab.domain import canonical_hash
from crypto_strategy_lab.microstructure.hotline_first_reallocation import (
    HotlineFirstDynamic321Probe,
)
from scripts.audit_hotline_first_reallocation import (
    independent_m030_audit,
    normalize_m030_reporting_metrics,
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


def probe(*, cancel_latency_us: int = 1, windows=None) -> HotlineFirstDynamic321Probe:
    kwargs = {}
    if windows is not None:
        kwargs["evaluation_windows"] = windows
    value = HotlineFirstDynamic321Probe(
        start_us=0,
        end_us=10_000_000,
        latency_us=0,
        cancel_latency_us=cancel_latency_us,
        **kwargs,
    )
    value.receive_book(book(1))
    return value


def test_five_tick_book_jump_is_one_final_reconciliation() -> None:
    value = probe()
    before = value._physical_reconciles
    value.receive_book(book(2, "1.0025", "1.0026"))
    assert value.hotline == D("1.0025")
    assert value._total_ticks_crossed == 5
    assert value._multi_tick_book_moves == 1
    assert value._intermediate_reconciles_avoided == 4
    assert value._physical_reconciles == before + 1


def test_five_distinct_one_tick_books_are_five_reconciliations() -> None:
    value = probe()
    before = value._physical_reconciles
    for index in range(1, 6):
        hotline = D("1.0020") + D(index) * D("0.0001")
        value.receive_book(book(index + 1, str(hotline), str(hotline + D("0.0001"))))
    assert value._total_ticks_crossed == 5
    assert value._multi_tick_book_moves == 0
    assert value._physical_reconciles == before + 5


def test_zero_fill_reclaim_waits_for_cancel_ack_then_funds_hot() -> None:
    value = probe(cancel_latency_us=2)
    value.receive_book(book(2, "1.0021", "1.0022"))
    assert value._reclaim_requests
    requests = len(value._reclaim_requests)
    assert value._zero_fill_reclaimed == 0
    value.receive_book(book(3, "1.0021", "1.0022"))
    assert value._zero_fill_reclaimed == 0
    value.receive_book(book(4, "1.0021", "1.0022"))
    assert value._zero_fill_reclaimed > 0
    assert len(value._reclaim_requests) < requests or value._hot_submit_success > 0


def test_partial_fill_order_is_never_reclaimable() -> None:
    value = probe()
    order = next(row for row in value.orders if row.role == "ENTRY" and row.level == 15)
    order.filled = D(1)
    assert value._reclaim_class(order) is None


def test_partial_fill_during_cancel_is_preserved_not_reclaimed() -> None:
    value = probe(cancel_latency_us=3)
    value.receive_book(book(2))
    order = next(
        row
        for row in value.orders
        if row.side == "BUY" and row.level == 15 and row.status == "ACTIVE"
    )
    value._request_reclaim(order, 2, purpose="TEST_PARTIAL_DURING_CANCEL")
    value._fill_order(order, D("0.5"), 3, "partial-after-request")
    value.receive_book(book(5))
    assert order.status == "CANCELED_PARTIAL"
    assert value._reclaim_became_partial == 1
    assert value._zero_fill_reclaimed == 0
    lot = next(row for row in value.lots if row.entry_order_id == order.order_id)
    assert lot.quantity == D("0.5")
    assert lot.stage == "SUBSTEP_INVENTORY_LOCKED"


def test_full_fill_during_cancel_closes_request_without_reclaim() -> None:
    value = probe(cancel_latency_us=3)
    value.receive_book(book(2))
    order = next(
        row
        for row in value.orders
        if row.side == "BUY" and row.level == 15 and row.status == "ACTIVE"
    )
    value._request_reclaim(order, 2, purpose="TEST_FULL_FILL_DURING_CANCEL")
    value._fill_order(order, order.quantity, 3, "full-after-request")
    assert order.status == "FILLED"
    assert order.order_id not in value._reclaim_requests
    assert value._reclaim_full_fill_terminal == 1
    assert value._zero_fill_reclaimed == 0
    assert value._reclaimed_pool["USDT"] == 0


def test_reclaim_order_is_class_then_farthest_then_youngest() -> None:
    value = probe()
    value.receive_book(book(2, "1.0022", "1.0023"))
    candidates = value._reclaimable_orders("BUY")
    classes = [value._reclaim_class(row) for row in candidates]
    rank = {"OUTSIDE": 0, "FAR": 1, "MID": 2, "DEMOTED_HOT": 3}
    assert [rank[item] for item in classes] == sorted(rank[item] for item in classes)


def test_fully_funded_hot_does_not_cancel_initial_orders() -> None:
    value = probe()
    assert value._hot_funded_slots("BUY") == D(45)
    assert value._hot_funded_slots("SELL") == D(45)
    assert not value._reclaim_requests


def test_zero_required_reclaim_never_cancels() -> None:
    value = probe()
    assert value._reclaim_for("BUY", D(0), 2, purpose="TEST") is False
    assert value._reclaim_request_count == 0


def test_mid_and_far_admission_stop_while_hot_is_incomplete(monkeypatch) -> None:
    value = probe()
    attempted: list[tuple[str, str]] = []
    monkeypatch.setattr(value, "_hot_funded_slots", lambda _side: D(0))
    monkeypatch.setattr(
        value,
        "_submit_priority_cell",
        lambda side, _price, _column, zone, _now, *, promotion: attempted.append((side, zone)),
    )
    value._reconcile_grid(2)
    assert attempted
    assert {zone for _side, zone in attempted} == {"HOT"}


def test_pending_return_blocks_same_side_entry_admission(monkeypatch) -> None:
    value = probe()
    source = next(order for order in value.orders if order.direction == "BUY_FIRST")
    value._deferred_returns[source.order_id] = 999
    attempted: list[tuple[str, str]] = []
    monkeypatch.setattr(
        value,
        "_submit_priority_cell",
        lambda side, _price, _column, zone, _now, *, promotion: attempted.append((side, zone)),
    )
    value._reconcile_grid(2)
    assert attempted
    assert all(side != "SELL" for side, _zone in attempted)


def test_non_funding_submission_error_is_not_hidden(monkeypatch) -> None:
    value = probe()
    monkeypatch.setattr(
        value,
        "submit_order",
        lambda *args, **kwargs: (_ for _ in ()).throw(ValueError("NON_FUNDING_FAILURE")),
    )
    with pytest.raises(ValueError, match="NON_FUNDING_FAILURE"):
        value._submit_priority_cell(
            "BUY",
            value.hotline - D("0.0100"),
            1,
            "HOT",
            2,
            promotion=False,
        )


def test_true_shortfall_requires_exhausted_reclaim_and_mobility(monkeypatch) -> None:
    value = probe()
    monkeypatch.setattr(
        value,
        "submit_order",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            ValueError("M026_USDT_OWNERSHIP_INSUFFICIENT")
        ),
    )
    monkeypatch.setattr(value, "_reclaimable_orders", lambda _side: [])
    monkeypatch.setattr(value, "_pending_reclaim_value", lambda _side: D(0))
    monkeypatch.setattr(value, "_operational_available", lambda _side: D(0))
    order = value._submit_priority_cell(
        "BUY",
        value.hotline - D("0.0100"),
        1,
        "HOT",
        2,
        promotion=False,
    )
    assert order is None
    assert value._true_shortfall_events == 1
    assert any(row["event"] == "TRUE_CAPITAL_SHORTFALL" for row in value.audit)


def test_reclaim_rejection_before_ack_releases_once_and_closes_request() -> None:
    value = probe(cancel_latency_us=5)
    order = next(row for row in value.orders if row.side == "BUY" and row.level == 1)
    value._reclaim_requests[order.order_id] = {
        "request_us": 1,
        "category": "FAR",
        "side": "BUY",
        "reserved_at_request": str(value._reservation_value(order)),
        "mobility_reserved_at_request": "0",
        "filled_at_request": "0",
        "purpose": "TEST_REJECTION",
    }
    value._reclaim_request_count = 1
    value.cancel(order.order_id, time_us=1)
    value.receive_book(book(2, str(order.price - D("0.0001")), str(order.price)))
    assert order.status == "REJECTED_POST_ONLY"
    assert order.order_id not in value._reclaim_requests
    assert value._reclaim_terminal_without_ack == 1
    assert value._zero_fill_reclaimed == 1


def test_return_priority_remains_above_hot() -> None:
    value = probe()
    entry = next(row for row in value.orders if row.side == "BUY" and row.level == 1)
    value._fill_order(entry, entry.quantity, 2, "entry")
    returned = next(row for row in value.orders if row.source_order_id == entry.order_id)
    assert returned.role == "RETURN"
    assert returned.reserved_base == returned.quantity


def test_mask_changes_reporting_only() -> None:
    a = probe(windows=((100, 200), (300, 400), (500, 600)))
    b = probe(windows=((700, 800), (900, 1000), (1100, 1200)))
    for now, bid, ask in ((2, "1.0022", "1.0023"), (4, "1.0020", "1.0021")):
        a.receive_book(book(now, bid, ask))
        b.receive_book(book(now, bid, ask))
    state_a = deepcopy(a.checkpoint()["state"])
    state_b = deepcopy(b.checkpoint()["state"])
    state_a["m026"].pop("m030")
    state_b["m026"].pop("m030")
    assert state_a == state_b


def test_checkpoint_roundtrip_preserves_m030_state() -> None:
    value = probe()
    value.receive_book(book(2, "1.0024", "1.0025"))
    checkpoint = value.checkpoint()
    restored = HotlineFirstDynamic321Probe.from_checkpoint(
        checkpoint, start_us=0, end_us=10_000_000
    )
    assert restored.checkpoint() == checkpoint


def test_half_tick_equality_preserves_hotline() -> None:
    value = probe()
    value.receive_book(book(2, "1.0020", "1.0021"))
    assert value.hotline == D("1.0020")
    assert value._total_ticks_crossed == 0


def full_day_audit_fixture() -> tuple[HotlineFirstDynamic321Probe, dict, dict]:
    start = 1_735_689_600_000_000
    end = 1_735_776_000_000_000
    value = HotlineFirstDynamic321Probe(
        start_us=start,
        end_us=end,
        latency_us=0,
        cancel_latency_us=1,
    )
    value.receive_book(
        {
            "time_us": start,
            "exchange_upper_us": start,
            "bids": [["1.0019", "1000"]],
            "asks": [["1.0020", "1000"]],
            "known_bid_floor": "0.98",
            "known_ask_ceiling": "1.02",
        }
    )
    metrics = normalize_m030_reporting_metrics(
        value.finish(time_us=end), value.audit, value.evaluation_windows
    )
    terminal = value.checkpoint()
    return value, metrics, terminal


def test_independent_audit_rejects_falsified_coverage_metric() -> None:
    value, metrics, terminal = full_day_audit_fixture()
    bad = deepcopy(metrics)
    bad["HOT_FUNDING_COVERAGE_TIME_WEIGHTED"] = "0"
    with pytest.raises(ValueError, match="M030_AUDIT_FULL_DAY_COVERAGE"):
        independent_m030_audit(
            value.audit,
            terminal,
            bad,
            {},
            value.evaluation_windows,
        )


def test_independent_audit_rejects_falsified_literal_stranded_metric() -> None:
    value, metrics, terminal = full_day_audit_fixture()
    bad = deepcopy(metrics)
    bad["RECLAIMABLE_CAPITAL_STRANDED_TIME_PCT"] = "99"
    with pytest.raises(ValueError, match="M030_AUDIT_FULL_DAY_LITERAL_STRANDED"):
        independent_m030_audit(value.audit, terminal, bad, {}, value.evaluation_windows)


def test_independent_audit_rejects_falsified_raw_administrative_metric() -> None:
    value, metrics, terminal = full_day_audit_fixture()
    bad = deepcopy(metrics)
    bad["RAW_ENGINE_RECLAIMABLE_CAPITAL_STRANDED_TIME_PCT"] = "99"
    with pytest.raises(ValueError, match="M030_AUDIT_RAW_STRANDED_TIME"):
        independent_m030_audit(value.audit, terminal, bad, {}, value.evaluation_windows)


def test_independent_audit_rejects_jointly_falsified_shortfall() -> None:
    value, metrics, terminal = full_day_audit_fixture()
    bad_metrics = deepcopy(metrics)
    bad_terminal = deepcopy(terminal)
    bad_terminal["state"]["m026"]["m030"]["true_shortfall_time_us"] = 86_400_000_000
    bad_metrics["TRUE_CAPITAL_SHORTFALL_TIME_PCT"] = "100"
    bad_terminal["sha256"] = canonical_hash(bad_terminal["state"])
    with pytest.raises(ValueError, match="M030_AUDIT_SHORTFALL"):
        independent_m030_audit(
            value.audit,
            bad_terminal,
            bad_metrics,
            {},
            value.evaluation_windows,
        )


def test_independent_audit_rejects_falsified_current_shortfall() -> None:
    value, metrics, terminal = full_day_audit_fixture()
    bad = deepcopy(metrics)
    bad["TRUE_CAPITAL_SHORTFALL"]["USDT"] = "999"
    with pytest.raises(ValueError, match="M030_AUDIT_CURRENT_USDT_SHORTFALL"):
        independent_m030_audit(
            value.audit,
            terminal,
            bad,
            {},
            value.evaluation_windows,
        )


def test_independent_audit_rejects_invalid_original_terminal_hash() -> None:
    value, metrics, terminal = full_day_audit_fixture()
    terminal["sha256"] = "INVALID"
    with pytest.raises(ValueError, match="M030_AUDIT_ORIGINAL_TERMINAL_HASH"):
        independent_m030_audit(
            value.audit,
            terminal,
            metrics,
            {},
            value.evaluation_windows,
        )


def test_independent_audit_rejects_fictitious_capital_allocation() -> None:
    value, metrics, terminal = full_day_audit_fixture()
    bad_rows = deepcopy(value.audit)
    bad_rows.append(
        {
            "event": "RECLAIMED_CAPITAL_ALLOCATED",
            "time_us": 1_735_775_999_999_999,
            "order_id": 999_999,
            "asset": "USDT",
            "amount": "999",
            "role": "ENTRY",
            "zone": "HOT",
        }
    )
    bad_terminal = deepcopy(terminal)
    bad_terminal["state"]["parent"]["audit"] = deepcopy(bad_rows)
    bad_terminal["sha256"] = canonical_hash(bad_terminal["state"])
    bad_metrics = deepcopy(metrics)
    bad_metrics["CAPITAL_REALLOCATED_TO_CURRENT_HOT_USDT"] = "999"
    with pytest.raises(ValueError, match="M030_AUDIT_ALLOCATION_WITHOUT_PHYSICAL_ORDER"):
        independent_m030_audit(
            bad_rows,
            bad_terminal,
            bad_metrics,
            {},
            value.evaluation_windows,
        )


def test_independent_audit_accepts_direct_five_tick_jump() -> None:
    start = 1_735_689_600_000_000
    end = 1_735_776_000_000_000
    value = HotlineFirstDynamic321Probe(
        start_us=start,
        end_us=end,
        latency_us=0,
        cancel_latency_us=1,
    )
    value.receive_book(
        {
            "time_us": start,
            "exchange_upper_us": start,
            "bids": [["1.0019", "1000"]],
            "asks": [["1.0020", "1000"]],
            "known_bid_floor": "0.98",
            "known_ask_ceiling": "1.02",
        }
    )
    value.receive_book(
        {
            "time_us": start + 1,
            "exchange_upper_us": start + 1,
            "bids": [["1.0025", "1000"]],
            "asks": [["1.0026", "1000"]],
            "known_bid_floor": "0.98",
            "known_ask_ceiling": "1.02",
        }
    )
    metrics = normalize_m030_reporting_metrics(
        value.finish(time_us=end), value.audit, value.evaluation_windows
    )
    audit = independent_m030_audit(
        value.audit,
        value.checkpoint(),
        metrics,
        {},
        value.evaluation_windows,
    )
    assert audit["status"].startswith("PASS_")


def test_independent_audit_rejects_fictitious_ack_release() -> None:
    start = 1_735_689_600_000_000
    end = 1_735_776_000_000_000
    value = HotlineFirstDynamic321Probe(
        start_us=start,
        end_us=end,
        latency_us=0,
        cancel_latency_us=1,
    )
    for now, bid, ask in (
        (start, "1.0019", "1.0020"),
        (start + 1, "1.0021", "1.0022"),
        (start + 2, "1.0021", "1.0022"),
    ):
        value.receive_book(
            {
                "time_us": now,
                "exchange_upper_us": now,
                "bids": [[bid, "1000"]],
                "asks": [[ask, "1000"]],
                "known_bid_floor": "0.98",
                "known_ask_ceiling": "1.02",
            }
        )
    metrics = normalize_m030_reporting_metrics(
        value.finish(time_us=end), value.audit, value.evaluation_windows
    )
    terminal = value.checkpoint()
    bad_rows = deepcopy(value.audit)
    ack = next(row for row in bad_rows if row["event"] == "HOT_REALLOCATION_CANCEL_ACKED")
    ack["released"] = str(D(ack["released"]) + D(999))
    ack["operational_released"] = str(D(ack["operational_released"]) + D(999))
    terminal["state"]["parent"]["audit"] = deepcopy(bad_rows)
    terminal["sha256"] = canonical_hash(terminal["state"])
    with pytest.raises(ValueError, match="M030_AUDIT_TERMINAL_RELEASE_QUANTITY"):
        independent_m030_audit(
            bad_rows,
            terminal,
            metrics,
            {},
            value.evaluation_windows,
        )
