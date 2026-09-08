"""Synthetic complete-day runner tests; no historical data or network."""

import copy
import json
from dataclasses import asdict, replace
from decimal import Decimal as D

import pytest
from test_observed_l2_execution import replay_book, replay_fixture

from scripts.run_l2_monthly_samples import (
    MeasuredReplay,
    audit_all_fills,
    execute_verified_experiment,
    mapped_tick_catalog,
    percentile,
    stitched_mapping,
    weighted_percentile,
)


@pytest.mark.parametrize("model", ["M015", "M016", "M017"])
def test_current_owner_pause_blocks_run_before_preflight_or_inputs(monkeypatch, model):
    from scripts import run_l2_monthly_samples as runner

    def forbidden(*args, **kwargs):
        pytest.fail("Owner gate must precede preflight, data and writer access")

    monkeypatch.setattr(runner, "campaign_preflight", forbidden)
    monkeypatch.setattr(runner, "build_stitched_inputs", forbidden)
    monkeypatch.setattr(runner, "campaign_writer_lock", forbidden)
    with pytest.raises(ValueError, match=r"OWNER_APPROVAL_REQUIRED|OWNER_WINDOW_EXCEEDED"):
        runner.run(model)


def test_m019_candidate_is_fail_closed_when_owner_gate_is_not_authorized(tmp_path):
    from scripts import run_l2_monthly_samples as runner

    authority = tmp_path / runner.OWNER_WINDOW_AUTHORITY
    authority.parent.mkdir(parents=True)
    authority.write_text(
        "APPROVED_COMPARISON_DAYS=1\nEXTENSION_AUTHORIZED=false\n"
        "NEW_REPLAY_AUTHORIZED_NOW=false\nAUTHORIZED_MODEL=M019\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="OWNER_APPROVAL_REQUIRED"):
        runner.require_owner_replay_approval(tmp_path, model_id="M019")
    assert runner.campaign_design_paths("M019") == (
        runner.M019_MODEL_SPEC,
        runner.M019_PREREGISTRATION,
        runner.M019_REVIEW,
    )


def test_m019_executor_writes_complete_audited_day_without_serial_engine(tmp_path):
    from crypto_strategy_lab.microstructure.adaptive_stablecoin_ladder import (
        AdaptiveStablecoinLadder,
    )
    from crypto_strategy_lab.microstructure.b10_reality import ExecutionProfile, SymbolRules, Trade
    from scripts import run_l2_monthly_samples as runner

    profile = ExecutionProfile("M019-test", "a" * 64, 10, 10, D(".001"), D("0"), D("0"))
    rules = SymbolRules(
        D(".0001"), D(".01"), D(".01"), D("10000"), D("5"), D("100000"),
        D(".01"), D("100"), "b" * 64, orders_per_window=1000, window_us=1_000_000,
    )
    engine = AdaptiveStablecoinLadder(profile, rules, lane_id="fixture")
    trade = Trade(1_000_000, 1, D(".90"), D(".05"), True)
    mapping = [{"logical_start_us": 0, "source_date": "2025-01-01"}]
    events = [
        {"kind": "SEAM", "local_us": 0, "source_date": "2025-01-01"},
        {
            "kind": "BOOK", "exchange_us": 0, "local_us": 100, "capture_order": 1,
            "native_update_id": 1, "bids": ((D("1"), D("100")),),
            "asks": ((D("1.01"), D("100")),), "known_bid_floor": D(".9"),
            "known_ask_ceiling": D("1.1"), "sequence_validated": True,
            "is_snapshot": True, "changes": None, "exchange_upper_us": 0,
            "exchange_precision": "EXACT_MICROSECONDS",
        },
        {
            "kind": "BOOK", "exchange_us": 500, "local_us": 600, "capture_order": 2,
            "native_update_id": 2, "bids": ((D("1"), D("100")),),
            "asks": ((D("1.01"), D("100")),), "known_bid_floor": D(".9"),
            "known_ask_ceiling": D("1.1"), "sequence_validated": True,
            "is_snapshot": False, "changes": None, "exchange_upper_us": 500,
            "exchange_precision": "EXACT_MICROSECONDS",
        },
        {
            "kind": "TRADE", "exchange_us": 1_000_000, "local_us": 1_000_100,
            "capture_order": 3, "clock_offset_us": 0,
            "data": {"t": 1, "T": 1000, "p": ".90", "q": ".05", "m": True},
        },
        {"kind": "SEAM", "local_us": runner.DAY_US, "source_date": "END"},
    ]
    identity = {"source_day_mapping": mapping, "model_id": "M019", "date": "OWNER_GATED_DAY1"}

    result = runner.execute_m019_experiment(
        engine, {1: trade}, iter(events), {"L2_DAY_VALID": True}, identity, tmp_path / "run"
    )

    assert result["RUN_STATUS"] == "COMPLETE"
    assert result["CYCLES_POSITIVE"] == 0
    assert result["AUDIT"]["status"] == "PASS_M019_LEDGER_EXECUTION_AND_LIQUIDITY"
    assert D(result["TOTAL_FINAL_EQUITY"]) <= D("100")
    assert (tmp_path / "run" / "terminal-engine-state.json").exists()

    audit_path = tmp_path / "run" / "execution-audit.jsonl"
    rows = [json.loads(line) for line in audit_path.read_text(encoding="utf-8").splitlines()]
    fill = next(row for row in rows if row.get("event") == "FILL")
    fill["source"] = "TRADE"
    tampered = tmp_path / "tampered.jsonl"
    tampered.write_text(
        "\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="M019_FILL_PRICE_SOURCE_MISMATCH"):
        runner.audit_m019_journal(tampered, {1: trade}, engine)

    cases = {
        "unsupported-source": (
            lambda data: next(row for row in data if row.get("event") == "FILL").update(
                source="UNSUPPORTED"
            ),
            "M019_UNSUPPORTED_FILL_SOURCE",
        ),
        "fill-side": (
            lambda data: next(row for row in data if row.get("event") == "FILL").update(
                side="SELL"
            ),
            "M019_FILL_ORDER_FIELDS_MISMATCH",
        ),
        "fill-price": (
            lambda data: next(row for row in data if row.get("event") == "FILL").update(
                price="999"
            ),
            "M019_FILL_ORDER_FIELDS_MISMATCH",
        ),
        "fill-quantity": (
            lambda data: next(row for row in data if row.get("event") == "FILL").update(
                quantity="0"
            ),
            "M019_INVALID_FILL_QUANTITY",
        ),
        "fill-remainder": (
            lambda data: next(row for row in data if row.get("event") == "FILL").update(
                remaining_after="999"
            ),
            "M019_FILL_TERMINAL_STATE_MISMATCH",
        ),
        "buy-reservation": (
            lambda data: next(
                row
                for row in data
                if row.get("event") == "SUBMIT" and row.get("side") == "BUY"
            ).update(reserved_quote="999"),
            "M019_ORDER_QUOTE_RESERVATION_MISMATCH",
        ),
        "lot-quantity": (
            lambda data: next(
                row
                for row in data
                if row.get("event") == "LOT_CREATED"
                and row.get("source_order_id") is not None
            ).update(quantity="999"),
            "M019_BUY_FILL_LOT_LINK_MISMATCH|M019_TERMINAL_LOT_RECONCILIATION",
        ),
        "endowment-cash": (
            lambda data: next(
                row for row in data if row.get("event") == "ENDOWMENT"
            ).update(cash="999"),
            "M019_ENDOWMENT_CASH_RECONCILIATION",
        ),
        "activation-bbo": (
            lambda data: next(
                row
                for row in data
                if row.get("event") == "ACTIVATED" and row.get("side") == "BUY"
            ).update(best_ask="0"),
            "M019_INVALID_ACTIVATION_CONTEXT",
        ),
        "blocked-trade-consumption": (
            lambda data: next(
                row for row in data if row.get("event") == "TRADE"
            ).update(event="TRADE_BLOCKED_FUTURE_BOOK"),
            "M019_BLOCKED_TRADE_CONSUMED_LIQUIDITY",
        ),
    }
    pristine = [json.loads(line) for line in audit_path.read_text(encoding="utf-8").splitlines()]
    for label, (mutate, expected) in cases.items():
        altered = copy.deepcopy(pristine)
        mutate(altered)
        altered_path = tmp_path / f"tampered-{label}.jsonl"
        altered_path.write_text(
            "\n".join(json.dumps(row, sort_keys=True) for row in altered) + "\n",
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match=expected):
            runner.audit_m019_journal(altered_path, {1: trade}, engine)


def test_m019_independent_auditor_reconstructs_a_complete_positive_cycle(tmp_path):
    from crypto_strategy_lab.microstructure.adaptive_stablecoin_ladder import (
        AdaptiveStablecoinLadder,
    )
    from crypto_strategy_lab.microstructure.b10_reality import ExecutionProfile, SymbolRules, Trade
    from crypto_strategy_lab.microstructure.observed_l2_execution import ObservedBookBatch
    from scripts import run_l2_monthly_samples as runner

    profile = ExecutionProfile("audit-cycle", "a" * 64, 10, 10, D(".001"), D(".001"), D(".001"))
    rules = SymbolRules(
        D(".0001"), D(".01"), D(".01"), D("10000"), D("5"), D("100000"),
        D(".01"), D("100"), "b" * 64, orders_per_window=1000, window_us=1_000_000,
    )

    def book(exchange_us, capture_us, update_id):
        return ObservedBookBatch(
            exchange_us, capture_us, update_id, update_id,
            ((D("1"), D("100")),), ((D("1.01"), D("100")),),
            D(".9"), D("1.1"), True, exchange_upper_us=exchange_us,
        )

    engine = AdaptiveStablecoinLadder(profile, rules, endowment_notional=D("0"))
    engine.receive_book(book(0, 100, 1))
    engine.receive_book(book(200, 200, 2))
    buy = next(order for order in engine.active_orders if order.side == "BUY")
    buy_trade = Trade(300, 1, buy.price, buy.quantity, True)
    engine.receive_trade(buy_trade, capture_time_us=300)
    engine.receive_book(book(60_000_400, 60_000_400, 3))
    engine.receive_book(book(60_000_500, 60_000_500, 4))
    sell = next(order for order in engine.active_orders if order.side == "SELL")
    sell_trade = Trade(60_000_600, 2, sell.price, sell.quantity, False)
    engine.receive_trade(sell_trade, capture_time_us=60_000_600)
    engine.finish(100_000_000)
    assert engine.cycle_count == 1

    audit_path = tmp_path / "cycle-audit.jsonl"
    audit_path.write_text(
        "\n".join(json.dumps(row, sort_keys=True) for row in engine.audit) + "\n",
        encoding="utf-8",
    )
    result = runner.audit_m019_journal(
        audit_path, {1: buy_trade, 2: sell_trade}, engine
    )
    assert result["cycles_checked"] == 1
    assert result["status"] == "PASS_M019_LEDGER_EXECUTION_AND_LIQUIDITY"

    rows = copy.deepcopy(engine.audit)
    cycle = next(row for row in rows if row.get("event") == "CYCLE_SETTLED")
    cycle["net_profit"] = "999"
    audit_path.write_text(
        "\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="M019_CYCLE_PNL_RECONCILIATION"):
        runner.audit_m019_journal(audit_path, {1: buy_trade, 2: sell_trade}, engine)

    rows = copy.deepcopy(engine.audit)
    activation = next(
        row
        for row in rows
        if row.get("event") == "ACTIVATED"
        and row.get("order_id") == buy.order_id
    )
    activation["queue"] = "1"
    audit_path.write_text(
        "\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="M019_FILL_BEFORE_QUEUE_DEPLETION"):
        runner.audit_m019_journal(audit_path, {1: buy_trade, 2: sell_trade}, engine)

    rows = copy.deepcopy(engine.audit)
    sale = next(row for row in rows if row.get("event") == "LOT_SOLD")
    sale["cost"] = str(D(sale["cost"]) + D(sale["profit"]) / D(2))
    sale["profit"] = str(D(sale["gross"]) - D(sale["fee"]) - D(sale["cost"]))
    audit_path.write_text(
        "\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="M019_SALE_LOT_COST_RECONCILIATION"):
        runner.audit_m019_journal(audit_path, {1: buy_trade, 2: sell_trade}, engine)


def test_m019_partial_buy_exit_then_cancel_ack_orders_cycle_after_terminal(tmp_path):
    from crypto_strategy_lab.microstructure.adaptive_stablecoin_ladder import (
        AdaptiveStablecoinLadder,
    )
    from crypto_strategy_lab.microstructure.b10_reality import ExecutionProfile, SymbolRules, Trade
    from crypto_strategy_lab.microstructure.observed_l2_execution import ObservedBookBatch
    from scripts import run_l2_monthly_samples as runner

    profile = ExecutionProfile("partial-cycle", "a" * 64, 10, 1_000, D(".001"), D("0"), D("0"))
    rules = SymbolRules(
        D(".0001"), D(".01"), D(".01"), D("10000"), D("5"), D("100000"),
        D(".01"), D("100"), "b" * 64, orders_per_window=1000, window_us=1_000_000,
    )

    def book(exchange_us, capture_us, update_id):
        return ObservedBookBatch(
            exchange_us, capture_us, update_id, update_id,
            ((D("1"), D("100")),), ((D("1.01"), D("100")),),
            D(".9"), D("1.1"), True, exchange_upper_us=exchange_us,
        )

    engine = AdaptiveStablecoinLadder(profile, rules, endowment_notional=D("0"))
    engine.receive_book(book(0, 100, 1))
    engine.receive_book(book(200, 200, 2))
    buy = next(order for order in engine.active_orders if order.side == "BUY")
    partial = buy.quantity - rules.step_size
    buy_trade = Trade(300, 1, buy.price, partial, True)
    engine.receive_trade(buy_trade, capture_time_us=300)
    lot = next(lot for lot in engine.lots if lot.source_order_id == buy.order_id)
    sell_price = engine._break_even_exit(lot)
    engine._submit("SELL", buy.slot, sell_price, partial, 400)
    engine.receive_book(book(500, 500, 3))
    sell = next(order for order in engine.active_orders if order.side == "SELL")
    engine._cancel(buy, 600, "TEST_PARTIAL_TERMINAL")
    sell_trade = Trade(700, 2, sell.price, sell.quantity, False)
    engine.receive_trade(sell_trade, capture_time_us=700)
    assert engine.cycle_count == 0
    engine.receive_book(book(2_000, 2_000, 4))
    engine.finish(3_000)
    assert engine.cycle_count == 1
    events = [row["event"] for row in engine.audit]
    assert events.index("CANCEL_ACK") < events.index("CYCLE_SETTLED")

    audit_path = tmp_path / "partial-cycle-audit.jsonl"
    audit_path.write_text(
        "\n".join(json.dumps(row, sort_keys=True) for row in engine.audit) + "\n",
        encoding="utf-8",
    )
    result = runner.audit_m019_journal(
        audit_path, {1: buy_trade, 2: sell_trade}, engine
    )
    assert result["cycles_checked"] == 1


def test_m018_owner_window_is_one_day_and_extensions_fail_closed(tmp_path):
    from scripts import run_l2_monthly_samples as runner

    path = tmp_path / runner.OWNER_WINDOW_AUTHORITY
    path.parent.mkdir(parents=True)
    base = ("APPROVED_COMPARISON_DAYS={days}\nEXTENSION_AUTHORIZED=false\n"
            "NEW_REPLAY_AUTHORIZED_NOW=true\nAUTHORIZED_MODEL=M018\n")
    path.write_text(base.format(days=1), encoding="utf-8")
    assert runner.require_owner_replay_approval(tmp_path, "M018") == ("2025-01-01",)
    for days in (2, 3, 12, 21):
        path.write_text(base.format(days=days), encoding="utf-8")
        with pytest.raises(ValueError, match="OWNER_EXTENSION_REQUIRES"):
            runner.require_owner_replay_approval(tmp_path, "M018")


def test_m018_run_verifies_and_builds_only_first_day(monkeypatch, tmp_path):
    from contextlib import nullcontext
    from types import SimpleNamespace

    from scripts import run_l2_monthly_samples as runner

    authority = tmp_path / "owner.md"
    authority.write_text(
        "APPROVED_COMPARISON_DAYS=1\nEXTENSION_AUTHORIZED=false\n"
        "NEW_REPLAY_AUTHORIZED_NOW=true\nAUTHORIZED_MODEL=M018\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(runner, "OWNER_WINDOW_AUTHORITY", authority)
    first = "2025-01-01"
    manifest = {"canonical_trade_manifest_sha256": "sha",
                "dates": [{"date": first}, {"date": "2025-02-01", "poison": True}]}
    validation = {"days": manifest["dates"]}
    monkeypatch.setattr(runner, "campaign_preflight", lambda **kw: ("source", manifest, validation))
    monkeypatch.setattr(runner, "PROFILE_CONFIG", SimpleNamespace(read_bytes=lambda: b"{}"))
    monkeypatch.setattr(runner, "TRADE_MANIFEST", SimpleNamespace(read_bytes=lambda: b"{}"))
    monkeypatch.setattr(
        runner, "HistoryManifest", SimpleNamespace(model_validate_json=lambda x: {})
    )
    monkeypatch.setattr(runner, "file_sha", lambda path: "sha")
    seen = []

    def verify(entry, result, history):
        assert entry["date"] == result["date"] == first
        assert "poison" not in entry
        seen.append(first)
        return {"input_sha256": "day"}

    def build(history, config, mapping):
        assert seen == [first]
        assert [row["source_date"] for row in mapping] == [first]
        raise RuntimeError("ONE_DAY_INPUT_BOUNDARY_VERIFIED")

    monkeypatch.setattr(runner, "verify_published_day_evidence", verify)
    monkeypatch.setattr(runner, "campaign_writer_lock", nullcontext)
    monkeypatch.setattr(runner, "build_stitched_inputs", build)
    with pytest.raises(RuntimeError, match="ONE_DAY_INPUT_BOUNDARY_VERIFIED"):
        runner.run("M018")


@pytest.mark.parametrize(
    "text,reason",
    [
        (None, "OWNER_APPROVAL_REQUIRED"),
        ("", "OWNER_APPROVAL_REQUIRED"),
        (
            "APPROVED_COMPARISON_DAYS=2\nEXTENSION_AUTHORIZED=false\n"
            "NEW_REPLAY_AUTHORIZED_NOW=true\n",
            "OWNER_WINDOW_EXCEEDED",
        ),
        (
            "APPROVED_COMPARISON_DAYS=12\nEXTENSION_AUTHORIZED=false\n"
            "NEW_REPLAY_AUTHORIZED_NOW=false\n",
            "OWNER_APPROVAL_REQUIRED",
        ),
        (
            "APPROVED_COMPARISON_DAYS=2\nEXTENSION_AUTHORIZED=true\n"
            "NEW_REPLAY_AUTHORIZED_NOW=true\n",
            "OWNER_WINDOW_EXCEEDED",
        ),
        (
            "APPROVED_COMPARISON_DAYS=2\nEXTENSION_AUTHORIZED=false\n"
            "NEW_REPLAY_AUTHORIZED_NOW=True\n",
            "OWNER_APPROVAL_REQUIRED",
        ),
        (
            "APPROVED_COMPARISON_DAYS=2\nAPPROVED_COMPARISON_DAYS=12\n"
            "EXTENSION_AUTHORIZED=false\nNEW_REPLAY_AUTHORIZED_NOW=true\n",
            "OWNER_APPROVAL_REQUIRED",
        ),
        (
            "APPROVED_COMPARISON_DAYS=0\nEXTENSION_AUTHORIZED=false\n"
            "NEW_REPLAY_AUTHORIZED_NOW=true\n",
            "OWNER_APPROVAL_REQUIRED",
        ),
    ],
)
def test_owner_authority_missing_invalid_or_too_short_fails_closed(tmp_path, text, reason):
    from scripts import run_l2_monthly_samples as runner

    path = tmp_path / runner.OWNER_WINDOW_AUTHORITY
    if text is not None:
        path.parent.mkdir(parents=True)
        path.write_text(text, encoding="utf-8")
    with pytest.raises(ValueError, match=reason):
        runner.campaign_preflight(root=tmp_path, model_id="M017")


def fixture():
    base, trades = replay_fixture()
    runtime = copy.copy(base.decisions.runtime)
    runtime.tape = base._source_tape
    runtime.timelines = runtime.tape.timelines((1,))
    identity = {**base.identity, "date": "2026-01-01"}
    replay = MeasuredReplay(
        runtime,
        base.engine.profile,
        base.rules_at,
        base.envelope,
        start_us=base.start_us,
        end_us=base.end_us,
        identity=identity,
        envelope="CONSERVATIVE_QUEUE",
    )
    book = asdict(replay_book(replay, 0, 100, 1))
    events = [
        {
            "kind": "BOOK",
            "local_us": book.pop("capture_time_us"),
            "exchange_us": book.pop("exchange_time_us"),
            **book,
        }
    ]
    events[0]["exchange_upper_us"] = events[0]["exchange_us"]
    events[0]["exchange_precision"] = "CAPTURE_BOUND"
    for index, trade in enumerate(trades, 2):
        events.append(
            {
                "kind": "TRADE",
                "local_us": replay.start_us + index * 100,
                "exchange_us": trade.time_us,
                "capture_order": index,
                "data": {
                    "t": trade.trade_id,
                    "T": trade.time_us,
                    "p": str(trade.price),
                    "q": str(trade.quantity),
                    "m": trade.buyer_maker,
                },
            }
        )
    return replay, {trade.trade_id: trade for trade in trades}, events, identity


def test_complete_independent_day_runner_persists_metrics_and_all_fill_audit(tmp_path):
    replay, canonical, events, identity = fixture()
    validation = {"input_sha256": "a" * 64, "CSV_ROWS": 5}
    result = execute_verified_experiment(
        replay, canonical, events, validation, identity, tmp_path / "run"
    )
    assert result["NET_POSITIVE_CYCLES"] == 1
    assert D(result["RESERVE_FINAL"]) == D("10.001")
    assert D(result["OPERATING_FINAL"]) == D("100.009")
    assert result["AUDIT_STATUS"] == "PASS_AUTOMATED_ALL_FILLS"
    assert result["OPEN_HOLD_CENSORED"] is False
    assert result["DATE"] == "2026-01-01" and result["ENVELOPE"] == "CONSERVATIVE_QUEUE"
    assert 0 <= D(result["MOTOR_UPTIME"]) <= 1
    assert 0 <= D(result["CAPITAL_WEIGHTED_UPTIME"]) <= 1
    saved = json.loads((tmp_path / "run/summary.json").read_text())
    assert saved == result
    audit = json.loads((tmp_path / "run/all-fill-audit.json").read_text())
    assert audit["fills_checked"] == 2 and audit["settlements_checked"] == 1


def test_unbound_trade_stops_preserves_trace_and_cannot_overwrite(tmp_path):
    replay, canonical, events, identity = fixture()
    events[1]["data"]["q"] = "999"
    validation = {"input_sha256": "a" * 64, "CSV_ROWS": 5}
    target = tmp_path / "run"
    with pytest.raises(ValueError, match="FIELDS_CHANGED"):
        execute_verified_experiment(replay, canonical, events, validation, identity, target)
    assert (target / "failure.json").exists() and not (target / "summary.json").exists()
    fresh, canonical, events, identity = fixture()
    with pytest.raises(ValueError, match="PRESERVED"):
        execute_verified_experiment(fresh, canonical, events, validation, identity, target)


def test_all_fill_audit_rejects_tampered_quantity(tmp_path):
    replay, canonical, events, identity = fixture()
    target = tmp_path / "run"
    execute_verified_experiment(
        replay, canonical, events, {"input_sha256": "a" * 64, "CSV_ROWS": 5}, identity, target
    )
    rows = [
        json.loads(line) for line in (target / "execution-audit.jsonl").read_text().splitlines()
    ]
    next(row for row in rows if row["kind"] == "FILL")["quantity"] = "108"
    tampered = tmp_path / "tampered.jsonl"
    tampered.write_text("\n".join(json.dumps(row) for row in rows) + "\n")
    with pytest.raises(ValueError, match="OVERFILL"):
        audit_all_fills(tampered, replay.engine.profile)


def test_quantile_definitions_and_absent_data():
    assert percentile([], 50) is None
    assert percentile([D(1), D(3)], 50) == 2
    assert percentile([D(1), D(3)], 90) == 3
    assert weighted_percentile({D(1): 99, D(3): 1}, 90) == 1
    assert weighted_percentile({D(1): 50, D(3): 50}, 50) == 2


def test_fixed_twelve_day_mapping_preserves_source_grid_and_compresses_gaps():
    from datetime import UTC, datetime, timedelta

    from crypto_strategy_lab.microstructure.serial_replay import USDCUSDT_TICK_CATALOG

    mapping = stitched_mapping()
    catalog = mapped_tick_catalog(mapping)
    assert len(mapping) == 12 and mapping[-1]["source_date"] == "2026-07-01"
    for index, item in enumerate(mapping):
        logical = datetime(2025, 1, 1, tzinfo=UTC) + timedelta(days=index)
        source = datetime.fromisoformat(item["source_date"]).replace(tzinfo=UTC)
        assert catalog.tick_size_at(logical) == USDCUSDT_TICK_CATALOG.tick_size_at(source)
        assert item["logical_start_us"] - mapping[0]["logical_start_us"] == index * 86_400_000_000


@pytest.mark.parametrize("first_print_offset_us", [0, 6766])
def test_stitched_builder_reads_only_selected_days_and_keeps_frozen_model_identity(
    monkeypatch, first_print_offset_us
):
    from datetime import UTC, datetime, timedelta
    from types import SimpleNamespace

    import scripts.run_l2_monthly_samples as runner
    from crypto_strategy_lab.microstructure.serial_replay import EVENT_ORDER_SCALE

    base, _ = replay_fixture()
    mapping = stitched_mapping(("2025-01-01", "2026-02-01"))
    calls = []
    history = SimpleNamespace(
        first_timestamp=datetime(2025, 1, 1, tzinfo=UTC)
        + timedelta(microseconds=first_print_offset_us)
    )

    def archives(history, *, start, end_exclusive):
        assert start >= history.first_timestamp
        calls.append((start, end_exclusive))
        return [SimpleNamespace(cadence="daily", local_path="synthetic.zip", sha256="bound")]

    def history_events(history, *, start, end_exclusive):
        for index, price in enumerate((D(1), D("1.0001"), D(1))):
            yield SimpleNamespace(
                timestamp=start + timedelta(microseconds=120 + index * 100),
                trade_id=start.year * 10000 + start.month * 100 + index,
                price=price,
                quantity=D(100),
                buyer_is_maker=index % 2 == 0,
            )

    monkeypatch.setattr(runner, "select_history_archives", archives)
    monkeypatch.setattr(runner, "iter_history", history_events)
    monkeypatch.setattr(runner, "file_sha", lambda path: "bound")
    config = {
        "profiles": [
            {
                "profile": {**asdict(base.engine.profile), "name": runner.PROFILE},
                "envelope": asdict(base.envelope),
            }
        ],
        "rules": [
            {
                "start_us": base.start_us,
                "end_us": base.start_us + 366 * runner.DAY_US,
                "rule": asdict(base.engine.rules),
            }
        ],
    }
    runtime, profile, envelope, rules_at, canonical = runner.build_stitched_inputs(
        history, config, mapping
    )
    assert len(canonical) == 6 and len(runtime.tape.events) == 6
    assert [start.date().isoformat() for start, end in calls] == ["2025-01-01", "2026-02-01"]
    assert calls[0][0] == history.first_timestamp
    assert calls[0][1] == datetime(2025, 1, 2, tzinfo=UTC)
    assert calls[1][1] - calls[1][0] == timedelta(days=1)
    assert runtime.tape.events[0] // EVENT_ORDER_SCALE == (
        mapping[0]["logical_start_us"] + first_print_offset_us + 120
    )
    assert runtime.tape.events[3] // EVENT_ORDER_SCALE == mapping[1]["logical_start_us"] + 120
    for name in runner.ENVELOPES:
        replay = runner.MeasuredReplay(
            runtime,
            profile,
            rules_at,
            envelope,
            start_us=mapping[0]["logical_start_us"],
            end_us=mapping[1]["logical_start_us"] + runner.DAY_US,
            identity={
                **base.identity,
                "model_id": "M015",
                "priority_trade_through": True,
                "expected_trade_count": 6,
            },
            envelope=name,
        )
        assert replay.engine.priority_trade_through == (name == "PRICE_PRIORITY")
        assert len(replay.decisions.runtime.tape.events) == 0


def test_stitched_boundaries_preserve_compounded_capital_and_write_daily_metrics(tmp_path):
    replay, canonical, events, identity = fixture()
    start = replay.start_us
    replay.end_us = start + 12 * 86_400_000_000

    def seam(index):
        return {
            "kind": "SEAM",
            "day_index": index,
            "source_date": "END" if index == 12 else "2025-02-01",
            "previous_source_date": "2025-01-01" if index == 1 else "2025-02-01",
            "local_us": start + index * 86_400_000_000,
        }

    events.extend(seam(index) for index in range(1, 13))
    target = tmp_path / "stitched"
    result = execute_verified_experiment(
        replay, canonical, events, {"input_sha256": "a" * 64, "CSV_ROWS": 5}, identity, target
    )
    first = json.loads((target / "daily/01.json").read_text())
    second = json.loads((target / "daily/02.json").read_text())
    assert D(second["OPERATING_START"]) == D(first["OPERATING_FINAL"]) == D("100.009")
    assert D(second["RESERVE_START"]) == D(first["RESERVE_FINAL"]) == D("10.001")
    assert second["DAILY_NET_POSITIVE_CYCLES"] == 0 and first["DAILY_NET_POSITIVE_CYCLES"] == 1
    assert result["NET_POSITIVE_CYCLES"] == 1 and second["VERDICT"] == "PENDING"
    assert D(result["DURATION_HOURS"]) == 288
    with runner_decimal_context():
        assert D(result["CYCLES_PER_HOUR"]) == D(1) / 288


def runner_decimal_context():
    from decimal import Context, localcontext

    return localcontext(Context(prec=128))


def test_executable_motor_excludes_carried_active_order_without_book():
    replay, canonical, _events, _identity = fixture()
    replay.receive_book(replay_book(replay, 0, 100, 1))
    trade = next(iter(canonical.values()))
    replay.receive_trade(trade, capture_time_us=replay.start_us + 200, capture_order=2)
    replay.advance_to(replay.start_us + 250)
    assert replay.engine.order.status == "ACTIVE"
    replay.engine.begin_sample_seam(replay.start_us + 250, "2025-02-01")
    motor, working = replay.motor_us, replay.working_order_us
    replay._integrate(replay.start_us + 260)
    assert replay.motor_us == motor and replay.working_order_us == working + 10


def test_stitched_capture_stream_retains_native_trade_time_and_reversible_mapping(
    tmp_path, monkeypatch
):
    import scripts.run_l2_monthly_samples as runner

    replay, canonical, events, identity = fixture()
    offset = -31 * runner.DAY_US
    original = copy.deepcopy(events)
    for event in original:
        event["local_us"] -= offset
        event["exchange_us"] -= offset
        if "exchange_upper_us" in event:
            event["exchange_upper_us"] -= offset
        if "data" in event:
            event["data"]["T"] -= offset
    mapping = [
        {
            "day_index": 0,
            "source_date": "2026-02-01",
            "logical_start_us": replay.start_us,
            "source_start_us": replay.start_us - offset,
        }
    ]
    monkeypatch.setattr(runner, "raw_lines", lambda *args: ())
    monkeypatch.setattr(runner, "iter_native_events", lambda lines: iter(original))
    mapped = runner.stitched_events({"2026-02-01": {"raw_slices": []}}, mapping)
    target = tmp_path / "mapped"
    result = execute_verified_experiment(
        replay, canonical, mapped, {"input_sha256": "a" * 64, "CSV_ROWS": 5}, identity, target
    )
    assert result["NET_POSITIVE_CYCLES"] == 1
    audit = [
        json.loads(line) for line in (target / "execution-audit.jsonl").read_text().splitlines()
    ]
    seam = next(row for row in audit if row["kind"] == "SOURCE_DAY_MAPPING")
    assert seam["clock_offset_us"] == offset and seam["source_date"] == "2026-02-01"


@pytest.mark.parametrize(
    "field", ["cash", "reserve", "dust_cost", "net_profit", "realized_fees_quote"]
)
def test_independent_ledger_rejects_tampered_settlement(tmp_path, field):
    replay, canonical, events, identity = fixture()
    target = tmp_path / "run"
    execute_verified_experiment(
        replay, canonical, events, {"input_sha256": "a" * 64, "CSV_ROWS": 5}, identity, target
    )
    rows = [
        json.loads(line) for line in (target / "execution-audit.jsonl").read_text().splitlines()
    ]
    settlement = next(row for row in rows if row["kind"] == "SETTLEMENT")
    settlement[field] = str(D(settlement[field]) + 1)
    path = tmp_path / "tampered-ledger.jsonl"
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n")
    with pytest.raises(ValueError, match="AUDIT_"):
        audit_all_fills(path, replay.engine.profile)


def test_validated_delta_path_matches_strict_book_execution():
    from test_observed_l2_execution import batch, engine, trade

    strict, _ = engine()
    fast, _ = engine()
    for value in (strict, fast):
        value.submit("BUY", D(1), 0)
        trade(value, 11, "105")
        value.submit("SELL", value.protected_exit()["price"], 12, release=True)
        value.observed_book(batch(23, 23, bids=[(".99", "40")]))
    for index, quantity in enumerate((20, 30, 30, 50), 24):
        update = batch(index, index, bids=[(".99", str(quantity))])
        strict.observed_book(update)
        fast.observed_book(replace(update, changes=(("bid", D(".99"), D(quantity)),)))
        assert strict.bids == fast.bids
        assert strict.bid_consumption_debt == fast.bid_consumption_debt
        assert strict.cash == fast.cash and strict.reserve == fast.reserve


def test_native_snapshot_bridge_to_complete_economic_artifact(tmp_path):
    from datetime import UTC, datetime, timedelta

    from crypto_strategy_lab.microstructure.tardis_l2 import iter_native_events

    replay, canonical, events, identity = fixture()
    epoch = datetime(1970, 1, 1, tzinfo=UTC)

    def line(capture, data, stream="usdcusdt@depth"):
        return (
            (epoch + timedelta(microseconds=capture)).isoformat()
            + " "
            + json.dumps({"stream": stream, "data": data})
        )

    lines = [
        line(
            replay.start_us + 90,
            {
                "e": "depthUpdate",
                "s": "USDCUSDT",
                "E": replay.start_us + 80,
                "U": 2,
                "u": 2,
                "b": [],
                "a": [],
            },
        ),
        line(
            replay.start_us + 100,
            {"lastUpdateId": 1, "bids": [["1", "5"], [".99", "100"]], "asks": [["1.0001", "7"]]},
            "usdcusdt@depthSnapshot",
        ),
    ]
    lines.extend(
        line(event["local_us"], {"e": "trade", "s": "USDCUSDT", **event["data"]}, "usdcusdt@trade")
        for event in events[1:]
    )
    native = list(iter_native_events(lines))
    for event in native:
        if event["kind"] == "BOOK":
            event["exchange_upper_us"] = event["exchange_us"]
            event["exchange_precision"] = (
                "CAPTURE_BOUND" if event["is_snapshot"] else "EXACT_MICROSECONDS"
            )
    result = execute_verified_experiment(
        replay,
        canonical,
        native,
        {"input_sha256": "b" * 64, "CSV_ROWS": 3},
        identity,
        tmp_path / "native",
    )
    assert result["NET_POSITIVE_CYCLES"] == 1
    assert result["DESCRIPTIVE_MARKET_STATS"]["tradecount"] == 3


def test_partial_consumption_followed_by_depth_decline_gets_no_cancellation_credit():
    from test_observed_l2_execution import batch, engine, trade

    value, _ = engine()
    value.submit("BUY", D(1), 0)
    trade(value, 11, "35")
    value.cancel(12)
    trade(value, 23, "1")
    value.submit("SELL", value.protected_exit()["price"], 34, release=True)
    value.observed_book(batch(45, 45, bids=[(".99", "40")]))
    assert value.bids[0][1] == 10
    value.observed_book(
        replace(batch(46, 46, bids=[(".99", "20")]), changes=(("bid", D(".99"), D(20)),))
    )
    assert value.bids[0][1] == 0


@pytest.mark.parametrize("tampering", ("future_book", "ineligible", "cancel"))
def test_all_fill_audit_rejects_causal_tampering(tmp_path, tampering):
    replay, canonical, events, identity = fixture()
    target = tmp_path / "run"
    execute_verified_experiment(
        replay, canonical, events, {"input_sha256": "a" * 64, "CSV_ROWS": 5}, identity, target
    )
    rows = [
        json.loads(line) for line in (target / "execution-audit.jsonl").read_text().splitlines()
    ]
    index = next(i for i, row in enumerate(rows) if row["kind"] == "FILL")
    fill = rows[index]
    if tampering == "future_book":
        next(row for row in rows if row["kind"] == "OBSERVED_BOOK")["exchange_upper_us"] = (
            replay.end_us
        )
    elif tampering == "ineligible":
        rows.insert(index, {"kind": "EXECUTION_EVENT_INELIGIBLE", "trade_id": fill["source_id"]})
    else:
        rows.insert(
            index,
            {
                "kind": "CANCEL_REQUEST",
                "order_id": fill["order_id"],
                "effective_us": fill["time_us"] - 1,
            },
        )
    path = tmp_path / "tampered.jsonl"
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n")
    with pytest.raises(ValueError, match=r"AUDIT_.*(BOOK_TRADE|CANCEL)"):
        audit_all_fills(path, replay.engine.profile)
