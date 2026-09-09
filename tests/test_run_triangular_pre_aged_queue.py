from __future__ import annotations

import json
from contextlib import nullcontext
from copy import deepcopy
from decimal import Decimal as D
from pathlib import Path
from types import SimpleNamespace

import pytest

from crypto_strategy_lab.domain import canonical_hash
from crypto_strategy_lab.microstructure.triangular_pre_aged_queue import TriangularPreAgedQueueProbe
from crypto_strategy_lab.ml.model_registry import ModelStatus, compute_model_hash
from scripts import register_triangular_pre_aged_queue as registration
from scripts import run_triangular_pre_aged_queue as runner


def authority(root: Path, **changes: str) -> None:
    values = {
        "APPROVED_COMPARISON_DAYS": "1",
        "EXTENSION_AUTHORIZED": "false",
        "NEW_REPLAY_AUTHORIZED_NOW": "true",
        "AUTHORIZED_MODEL": "M024",
    }
    values.update(changes)
    path = root / runner.OWNER_WINDOW
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(f"{key}={value}\n" for key, value in values.items()))


def test_frozen_design_and_duration() -> None:
    design = json.loads(registration.SPEC.read_bytes())
    runner.validate_frozen_design(design)
    assert runner.END_US - runner.START_US == 10_800_000_000
    assert len(runner.SOURCE_PATHS) == len(set(runner.SOURCE_PATHS))
    assert Path("src/crypto_strategy_lab/microstructure/triangular_pre_aged_queue.py") in (
        runner.SOURCE_PATHS
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("initial_usdt", "100"),
        ("initial_usdc", "0"),
        ("normalized_quantity_usdc", "2"),
        ("run_count_authorized", True),
        ("end_exclusive", "2025-01-02T00:00:00Z"),
        ("public_cancellation_credit", True),
        ("hard_simulated_open_order_cap", 201),
        ("counterfactual_creating_trade_eligible", True),
        ("fee_assumption", "PROVEN_ACCOUNT_ZERO"),
    ],
)
def test_policy_mutations_fail_closed(field, value) -> None:
    design = json.loads(registration.SPEC.read_bytes())
    design[field] = value
    with pytest.raises(ValueError, match=f"POLICY_MISMATCH:{field}"):
        runner.validate_frozen_design(design)


@pytest.mark.parametrize(
    "changes",
    [
        {"AUTHORIZED_MODEL": "M023"},
        {"EXTENSION_AUTHORIZED": "true"},
        {"NEW_REPLAY_AUTHORIZED_NOW": "false"},
        {"APPROVED_COMPARISON_DAYS": "2"},
        {"AUTHORIZED_MODEL": "M024\nAUTHORIZED_MODEL=M024"},
    ],
)
def test_owner_gate_rejects_conflicts(tmp_path, changes) -> None:
    authority(tmp_path, **changes)
    with pytest.raises(ValueError, match="OWNER_GATE_REQUIRED"):
        runner.require_owner_gate(tmp_path)


def test_owner_gate_missing_and_valid(tmp_path) -> None:
    with pytest.raises(ValueError, match="AUTHORITY_UNAVAILABLE"):
        runner.require_owner_gate(tmp_path)
    authority(tmp_path)
    runner.require_owner_gate(tmp_path)


@pytest.mark.parametrize("kind", ["empty_directory", "result"])
def test_one_run_preservation_includes_empty_directory(tmp_path, kind) -> None:
    output, result = tmp_path / "run", tmp_path / "result.json"
    if kind == "empty_directory":
        output.mkdir()
    else:
        result.write_text("immutable")
    with pytest.raises(ValueError, match="EXISTING_M024_EXPERIMENT_PRESERVED"):
        runner._assert_unused_output(output, result)


@pytest.mark.parametrize(
    "mutation,error",
    [
        (("status", "--porcelain", "dirty"), "NOT_CLEAN"),
        (("branch", "--show-current", "other"), "MAIN_REQUIRED"),
        (("rev-parse", "origin/main", "old"), "PUBLISHED_HEAD"),
    ],
)
def test_published_clean_head_gate(monkeypatch, mutation, error) -> None:
    responses = {
        ("status", "--porcelain"): "",
        ("branch", "--show-current"): "main",
        ("rev-parse", "HEAD"): "sha",
        ("rev-parse", "origin/main"): "sha",
    }
    responses[mutation[:2]] = mutation[2]
    monkeypatch.setattr(runner, "_git_output", lambda *args: responses[args])
    with pytest.raises(ValueError, match=error):
        runner._assert_published_head("sha")


def test_native_iterator_never_accepts_day_two_or_nineteenth_slice(monkeypatch) -> None:
    def poison(_):
        yield {"local_us": runner.END_US, "exchange_us": runner.END_US}
        pytest.fail("iterator advanced after first out-of-window event")

    monkeypatch.setattr(runner.parent_runner, "bounded_native_events", poison)
    slices = [{"offset": offset} for offset in range(0, 180, 10)]
    with pytest.raises(ValueError, match="ESCAPED_3H_BOUND"):
        list(runner.bounded_native_events(slices))
    with pytest.raises(ValueError, match="18_SLICES_REQUIRED"):
        list(runner.bounded_native_events([*slices, {"offset": 180}]))


def test_input_identity_mismatch_rejected_before_consumption(monkeypatch) -> None:
    monkeypatch.setattr(runner.parent_runner, "bounded_inputs", lambda *_: (None, {}, (), {}))
    with pytest.raises(ValueError, match="M023_INPUT_BINDING_MISMATCH"):
        runner.bounded_inputs({}, {})


def test_registration_requires_inconclusive_parent_without_write(monkeypatch) -> None:
    monkeypatch.setattr(registration, "registered_model_payload", lambda: {"model_id": "M024"})
    monkeypatch.setattr(
        registration,
        "ModelRegistry",
        lambda: SimpleNamespace(
            current_status=lambda _: ModelStatus.CREATED,
            register=lambda *_: pytest.fail("registry write not allowed"),
        ),
    )
    with pytest.raises(ValueError, match="INCONCLUSIVE_M023"):
        registration.register()


def test_existing_registration_is_idempotent_only_for_same_binding(monkeypatch) -> None:
    payload = {"model_id": "M024"}
    existing = SimpleNamespace(
        model_id="M024", model=payload, model_hash=compute_model_hash(payload)
    )
    registry = SimpleNamespace(
        current_status=lambda _: ModelStatus.INCONCLUSIVE,
        entries=lambda: [existing],
        get=lambda _: existing,
    )
    monkeypatch.setattr(registration, "ModelRegistry", lambda: registry)
    monkeypatch.setattr(registration, "registered_model_payload", lambda: payload)
    assert registration.register() is existing
    existing.model_hash = "wrong"
    with pytest.raises(ValueError, match="EXISTING_IDENTITY_MISMATCH"):
        registration.register()


def test_native_mismatch_preserves_failure_and_prevents_engine_call(tmp_path, monkeypatch) -> None:
    trade = SimpleNamespace(
        trade_id=1, time_us=runner.START_US + 10, price=D("1"), quantity=D("1"), buyer_maker=True
    )
    event = {
        "kind": "TRADE",
        "local_us": trade.time_us,
        "data": {
            "t": 1,
            "p": "2",
            "q": "1",
            "m": True,
            "T": trade.time_us,
        },
    }
    monkeypatch.setattr(runner, "bounded_native_events", lambda _: iter([event]))
    engine = SimpleNamespace(audit=[], receive_trade=lambda *_a, **_k: pytest.fail("bad trade"))
    output, result = tmp_path / "run", tmp_path / "result.json"
    with pytest.raises(ValueError, match="CANONICAL_TRADE_BINDING_CHANGED"):
        runner.execute(engine, {1: trade}, (), {"run_hash": "test"}, {}, output, result)
    assert (output / "failure.json").exists()
    assert not result.exists()
    with pytest.raises(ValueError, match="EXISTING_M024"):
        runner.execute(engine, {}, (), {}, {}, output, result)


def test_run_denied_before_any_input_or_kernel(monkeypatch) -> None:
    def denied():
        raise ValueError("OWNER_DENIED")

    monkeypatch.setattr(runner, "campaign_preflight", denied)
    monkeypatch.setattr(runner, "bounded_inputs", lambda *_: pytest.fail("data read"))
    monkeypatch.setattr(runner, "make_probe", lambda *_: pytest.fail("kernel instantiated"))
    with pytest.raises(ValueError, match="OWNER_DENIED"):
        runner.run()


@pytest.mark.parametrize(
    "model_status,binding,error",
    [
        (ModelStatus.RUNNING, "valid", "CREATED_STATUS"),
        (ModelStatus.CREATED, "tampered", "REGISTERED_DESIGN_MISMATCH"),
    ],
)
def test_preflight_registry_gate_before_data_reads(monkeypatch, model_status, binding, error):
    payload = {"model_id": "M024"}
    model = SimpleNamespace(
        model=payload,
        model_hash=(compute_model_hash(payload) if binding == "valid" else "tampered"),
    )
    monkeypatch.setattr(runner, "require_owner_gate", lambda: None)
    monkeypatch.setattr(runner, "_assert_unused_output", lambda: None)
    monkeypatch.setattr(runner, "published_sha", lambda: "sha")
    monkeypatch.setattr(runner, "_assert_published_head", lambda _: None)
    monkeypatch.setattr(runner, "published_bytes", lambda *_: None)
    monkeypatch.setattr(runner, "validate_review", lambda *_: None)
    monkeypatch.setattr(runner, "file_sha", lambda _: runner.PROFILE_CONFIG_SHA)
    monkeypatch.setattr(runner, "registered_model_payload", lambda: payload)
    monkeypatch.setattr(
        runner,
        "ModelRegistry",
        lambda: SimpleNamespace(
            get=lambda _: model,
            current_status=lambda _: model_status,
        ),
    )
    with pytest.raises(ValueError, match=error):
        runner.campaign_preflight()


def physical_fixture(*, buy_first=True, complete=False):
    latency = 1179525
    engine = TriangularPreAgedQueueProbe(
        start_us=runner.START_US,
        end_us=runner.END_US,
        latency_us=latency,
        cancel_latency_us=latency,
    )

    def book(at):
        engine.receive_book(
            {
                "exchange_time_us": at,
                "exchange_upper_us": at,
                "capture_time_us": at,
                "bids": [["1.0019", "2"]],
                "asks": [["1.0020", "2"]],
                "known_bid_floor": ".99",
                "known_ask_ceiling": "1.02",
            }
        )

    now = runner.START_US + 1
    book(now)
    now += 2 * latency
    book(now)
    canonical = {}

    def trade(buyer, price, quantity):
        nonlocal now
        now += 2 * latency
        tid = len(canonical) + 1
        item = SimpleNamespace(
            trade_id=tid, time_us=now, buyer_maker=buyer, price=D(price), quantity=D(quantity)
        )
        canonical[tid] = item
        engine.receive_trade(item, capture_time_us=now)

    trade(buy_first, "1.0019" if buy_first else "1.0020", "3")
    for _ in range(5):
        now += 2 * latency
        book(now)
    trade(not buy_first, "1.0020" if buy_first else "1.0019", "3" if complete else "2.4")
    metrics = engine.finish(time_us=runner.END_US)
    return deepcopy(engine.audit), deepcopy(engine.checkpoint()), canonical, deepcopy(metrics)


@pytest.mark.parametrize(
    "buy_first,complete", [(True, False), (False, False), (True, True), (False, True)]
)
def test_physical_audit_reconstructs_both_directions_and_partial_assets(buy_first, complete):
    evidence = physical_fixture(buy_first=buy_first, complete=complete)
    result = runner.independent_execution_audit(*evidence)
    assert result["status"] == "PASS_M024_PHYSICAL_LEDGER"
    assert result["complete_positive_cycles"] == int(complete)


def test_physical_audit_preserves_cancel_pending_during_later_activation():
    latency = 1179525
    engine = TriangularPreAgedQueueProbe(
        start_us=runner.START_US,
        end_us=runner.END_US,
        latency_us=latency,
        cancel_latency_us=latency,
    )

    def book(at, bid, ask):
        engine.receive_book(
            {
                "exchange_time_us": at,
                "exchange_upper_us": at,
                "capture_time_us": at,
                "bids": [[bid, "2"]],
                "asks": [[ask, "2"]],
                "known_bid_floor": ".99",
                "known_ask_ceiling": "1.02",
            }
        )

    start = runner.START_US + 1
    book(start, "1.0019", "1.0020")
    book(start + 1, "1.0021", "1.0022")
    book(start + latency, "1.0021", "1.0022")
    pending_activation = next(
        row
        for row in engine.audit
        if row["event"] == "ACTIVATED"
        and any(
            earlier["event"] == "CANCEL_REQUEST"
            and earlier["order_id"] == row["order_id"]
            and earlier["time_us"] < row["time_us"]
            for earlier in engine.audit
        )
    )
    assert next(
        order for order in engine.orders if order.order_id == pending_activation["order_id"]
    ).status == "CANCEL_PENDING"
    metrics = engine.finish(time_us=runner.END_US)
    result = runner.independent_execution_audit(
        deepcopy(engine.audit), deepcopy(engine.checkpoint()), {}, deepcopy(metrics)
    )
    assert result["status"] == "PASS_M024_PHYSICAL_LEDGER"


@pytest.mark.parametrize("field", ["cash", "free_usdc", "inventory_qty", "growth_pool"])
def test_physical_audit_rejects_rehashed_financial_tampering(field):
    rows, terminal, canonical, metrics = physical_fixture()
    terminal["state"][field] = str(D(terminal["state"][field]) + 1)
    terminal["sha256"] = canonical_hash(terminal["state"])
    with pytest.raises(ValueError, match="CAPITAL_RECONSTRUCTION"):
        runner.independent_execution_audit(rows, terminal, canonical, metrics)


@pytest.mark.parametrize(
    "mutation,error",
    [
        ("negative_queue", "PUBLIC_DEBIT"),
        ("overfill", "GLOBAL_TRADE_BUDGET|ORDER_OVERFILLED"),
        ("negative_profit", "NONPOSITIVE_CYCLE"),
        ("duplicate_membership", "SEGMENT_MEMBERSHIP"),
        ("reset_age", "QUEUE_AGE_RESET"),
        ("self_source", "NONCANONICAL_SOURCE"),
    ],
)
def test_physical_audit_rejects_mutated_events_even_with_valid_hash(mutation, error):
    rows, terminal, canonical, metrics = physical_fixture(complete=True)
    if mutation == "negative_queue":
        next(r for r in rows if r["event"] == "PUBLIC_QUEUE_CONSUMED")["quantity"] = "2.5"
    elif mutation == "overfill":
        next(r for r in rows if r["event"] == "FILL")["quantity"] = "9"
    elif mutation == "negative_profit":
        next(r for r in rows if r["event"] == "CYCLE")["profit"] = "-.01"
    elif mutation == "duplicate_membership":
        segment = next(
            s for g in terminal["state"]["groups"] for s in g["segments"] if s["order_ids"]
        )
        segment["order_ids"].append(segment["order_ids"][0])
    elif mutation == "reset_age":
        terminal["state"]["orders"][0]["activation_evaluated_us"] += 1
    else:
        next(r for r in rows if r["event"] == "FILL")["source_id"] = "OWN_ORDER"
    terminal["state"]["audit"] = deepcopy(rows)
    terminal["sha256"] = canonical_hash(terminal["state"])
    with pytest.raises(ValueError, match=error):
        runner.independent_execution_audit(rows, terminal, canonical, metrics)


def test_revoked_authority_after_preparation_never_instantiates_kernel(monkeypatch):
    monkeypatch.setattr(runner, "campaign_preflight", lambda: ("sha", {}, {}))
    monkeypatch.setattr(runner, "campaign_writer_lock", nullcontext)
    monkeypatch.setattr(runner, "_assert_unused_output", lambda: None)
    monkeypatch.setattr(runner, "bounded_inputs", lambda *_: (None, {}, (), {}))

    def revoked():
        raise ValueError("OWNER_REVOKED_DURING_PREPARATION")

    monkeypatch.setattr(runner, "require_owner_gate", revoked)
    monkeypatch.setattr(runner, "make_probe", lambda *_: pytest.fail("kernel instantiated"))
    with pytest.raises(ValueError, match="OWNER_REVOKED_DURING_PREPARATION"):
        runner.run()


def test_physical_audit_rejects_native_print_before_activation():
    rows, terminal, canonical, metrics = physical_fixture()
    first_fill = next(row for row in rows if row["event"] == "FILL")
    order_id = first_fill["order_id"]
    activation = next(
        row for row in rows if row["event"] == "ACTIVATED" and row["order_id"] == order_id
    )
    canonical[int(first_fill["source_id"])].time_us = activation["time_us"]
    with pytest.raises(ValueError, match=r"PUBLIC_DEBIT_OR_CLOCK|FILL_BEFORE_ACTIVATION"):
        runner.independent_execution_audit(rows, terminal, canonical, metrics)
