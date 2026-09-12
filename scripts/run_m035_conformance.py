"""Run the frozen M035 synthetic conformance gate and write canonical artifacts."""

from __future__ import annotations

import csv
import hashlib
import json
import subprocess
from decimal import Decimal as D
from pathlib import Path
from typing import Any

from crypto_strategy_lab.microstructure.parallel_pair_capital_manager import (
    AllocationCandidate,
    AllocationPriority,
    CycleAttributionLedger,
    CycleRecord,
    GlobalCapitalLedger,
    OrderStatus,
    PairEngine,
    ParallelPairCapitalAllocator,
    RiskExitAuthorization,
)

ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = ROOT / "reports" / "m035"
SOURCE_FILES = (
    ROOT / "src" / "crypto_strategy_lab" / "microstructure" / "parallel_pair_capital_manager.py",
    ROOT / "src" / "crypto_strategy_lab" / "microstructure" / "multi_stable_queue.py",
    ROOT / "tests" / "test_m035_parallel_pair_capital_manager.py",
    ROOT / "docs" / "microstructure" / "M035_PARALLEL_PAIR_CAPITAL_MANAGER.md",
    Path(__file__).resolve(),
)
LOGICAL_DURATION_SECONDS = 900
ZERO = D("0")


def bundle_hash(paths: tuple[Path, ...]) -> str:
    digest = hashlib.sha256()
    for path in sorted(paths):
        digest.update(path.relative_to(ROOT).as_posix().encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def config_hash(value: dict[str, Any]) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def git_value(*args: str) -> str | None:
    result = subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True, check=False
    )
    return result.stdout.strip() if result.returncode == 0 else None


def make_candidate(
    candidate_id: str,
    pair_id: str,
    amount: str,
    *,
    priority: AllocationPriority = AllocationPriority.NEW_ENTRY,
    productivity: str = "1",
    edge: str = "0.01",
    existing_capital_id: str | None = None,
) -> AllocationCandidate:
    return AllocationCandidate(
        candidate_id=candidate_id,
        pair_id=pair_id,
        requested_usdt=D(amount),
        priority=priority,
        marginal_productivity=D(productivity),
        fifo_value=D("0.1"),
        expected_lock_seconds=D("60"),
        expected_net_edge=D(edge),
        existing_capital_id=existing_capital_id,
    )


def make_engine(pair_id: str, symbol: str, asset: str) -> PairEngine:
    value = PairEngine(pair_id=pair_id, symbol=symbol, pair_asset=asset, tick_size=D("0.0001"))
    value.receive_book(bid=D("0.9999"), ask=D("1.0001"), now_us=0)
    value.initialize_grid(now_us=0)
    return value


def run_gate() -> tuple[dict[str, Any], dict[str, Any]]:
    checks: dict[str, dict[str, Any]] = {}

    def record(name: str, passed: bool, evidence: dict[str, Any]) -> None:
        checks[name] = {"STATUS": "PASS" if passed else "FAIL", "EVIDENCE": evidence}

    pair_a = make_engine("PAIR_A", "USDCUSDT", "USDC")
    pair_b = make_engine("PAIR_B", "FDUSDUSDT", "FDUSD")
    b_before = pair_b.state.hotline
    pair_a.receive_book(
        bid=D("1.0002"), ask=D("1.0004"), now_us=60_000_000, reason="TEST_A_PAIR_A_MOVE"
    )
    isolation_a = pair_a.state.hotline == D("1.0003") and pair_b.state.hotline == b_before
    a_before = pair_a.state.hotline
    pair_b.receive_book(
        bid=D("0.9996"), ask=D("0.9998"), now_us=120_000_000, reason="TEST_A_PAIR_B_MOVE"
    )
    isolation_b = pair_b.state.hotline == D("0.9997") and pair_a.state.hotline == a_before
    record(
        "HOTLINE_ISOLATION",
        isolation_a and isolation_b,
        {
            "PAIR_A_HOTLINE": str(pair_a.state.hotline),
            "PAIR_B_HOTLINE": str(pair_b.state.hotline),
            "PAIR_A_EVENTS": len(pair_a.state.event_log),
            "PAIR_B_EVENTS": len(pair_b.state.event_log),
        },
    )

    c1 = next(
        row
        for row in pair_a.state.orders.values()
        if row.side == "BUY" and row.rank == 1 and row.column == 1
    )
    c2 = next(
        row
        for row in pair_a.state.orders.values()
        if row.side == "BUY" and row.rank == 1 and row.column == 2
    )
    record(
        "GRID_FOLLOWS_HOTLINE",
        c1.status == OrderStatus.ACTIVE
        and c2.status == OrderStatus.CANCEL_PENDING
        and c2.replacement_price == D("1.0002"),
        {
            "C1_PRICE": str(c1.price),
            "C1_STATUS": c1.status,
            "C2_OLD_PRICE": str(c2.price),
            "C2_TARGET_PRICE": str(c2.replacement_price),
            "C2_STATUS": c2.status,
        },
    )
    equal_move = pair_a.c1_should_move(
        new_value=D("1.03"),
        current_value=D("1"),
        lost_fifo_value=D("0.01"),
        cancel_cost=D("0.01"),
        reentry_cost=D("0.01"),
    )
    profitable_move = pair_a.c1_should_move(
        new_value=D("1.04"),
        current_value=D("1"),
        lost_fifo_value=D("0.01"),
        cancel_cost=D("0.01"),
        reentry_cost=D("0.01"),
    )
    record(
        "C1_FIFO_PRESERVATION",
        not equal_move and profitable_move and c1.status == OrderStatus.ACTIVE,
        {
            "MOVE_AT_EQUALITY": equal_move,
            "MOVE_WHEN_STRICTLY_GREATER": profitable_move,
            "AGED_C1_STATUS_AFTER_HOTLINE_MOVE": c1.status,
        },
    )
    free_before_ack = c2.order_id in pair_a.queue.order_group
    replacement = pair_a.acknowledge_grid_cancel(c2.order_id, now_us=180_000_000)
    replacement_price = None if replacement is None else replacement.price
    replacement_time = None if replacement is None else replacement.submitted_at_us
    record(
        "C2_MOBILITY",
        free_before_ack
        and c2.order_id not in pair_a.queue.order_group
        and replacement_price == D("1.0002"),
        {
            "OLD_ORDER_REMAINED_QUEUED_BEFORE_ACK": free_before_ack,
            "REPLACEMENT_PRICE": str(replacement_price),
            "REPLACEMENT_ACTIVATED_AT_US": replacement_time,
        },
    )

    shared = GlobalCapitalLedger()
    allocator = ParallelPairCapitalAllocator(shared)
    grants = allocator.allocate(
        [make_candidate("A70", "PAIR_A", "70"), make_candidate("B60", "PAIR_B", "60")],
        now_us=240_000_000,
    )
    committed = sum((row.amount_usdt for row in grants), D("0"))
    record(
        "GLOBAL_CAPITAL_CONSERVATION",
        committed == D("130")
        and shared.free_usdt == D("70")
        and shared.marked_equity({}) == D("200"),
        {
            "PAIR_A_COMMITTED": "70",
            "PAIR_B_COMMITTED": "60",
            "FREE": str(shared.free_usdt),
            "TOTAL_EQUITY": str(shared.marked_equity({})),
        },
    )

    constrained = GlobalCapitalLedger()
    constrained_grants = ParallelPairCapitalAllocator(constrained).allocate(
        [
            make_candidate("A150", "PAIR_A", "150", productivity="1"),
            make_candidate("B100", "PAIR_B", "100", productivity="2"),
        ],
        now_us=300_000_000,
    )
    constrained_total = sum((row.amount_usdt for row in constrained_grants), D("0"))
    record(
        "NO_DOUBLE_CAPITAL",
        constrained_total == D("200") and constrained.free_usdt == D("0"),
        {
            "REQUESTED_TOTAL": "250",
            "GRANTED_TOTAL": str(constrained_total),
            "GRANTS": [
                {"CANDIDATE": row.candidate_id, "AMOUNT_USDT": str(row.amount_usdt)}
                for row in constrained_grants
            ],
        },
    )

    priority_ledger = GlobalCapitalLedger()
    priority_allocator = ParallelPairCapitalAllocator(priority_ledger)
    owned_capital = priority_allocator.allocate(
        [make_candidate("A_INVENTORY", "PAIR_A", "70")], now_us=330_000_000
    )[0].capital_id
    priority_ledger.record_entry_fill(
        owned_capital,
        asset="USDC",
        quantity_net=D("70"),
        causal_mark_usdt=D("1"),
        attributable_cost_usdt=D("0"),
        now_us=340_000_000,
    )
    priority_grants = priority_allocator.allocate(
        [
            make_candidate("NEW_B", "PAIR_B", "150", productivity="100"),
            make_candidate(
                "RETURN_A",
                "PAIR_A",
                "70",
                priority=AllocationPriority.OWNED_RETURN,
                productivity="0",
                edge="0",
                existing_capital_id=owned_capital,
            ),
        ],
        now_us=360_000_000,
    )
    record(
        "OWNED_RETURN_PRIORITY",
        [row.candidate_id for row in priority_grants] == ["RETURN_A", "NEW_B"],
        {
            "ALLOCATION_ORDER": [row.candidate_id for row in priority_grants],
            "AMOUNTS": [str(row.amount_usdt) for row in priority_grants],
            "FREE_AFTER": str(priority_ledger.free_usdt),
            "OWNED_STATE": priority_ledger.positions[owned_capital].state,
        },
    )

    dust_ledger = GlobalCapitalLedger()
    dust_capital = ParallelPairCapitalAllocator(dust_ledger).allocate(
        [make_candidate("DUST", "PAIR_A", "9")], now_us=420_000_000
    )[0].capital_id
    dust_ledger.record_entry_fill(
        dust_capital,
        asset="USDC",
        quantity_net=D("8.9991"),
        causal_mark_usdt=D("1"),
        attributable_cost_usdt=D("0"),
        input_usdt=D("9"),
        now_us=480_000_000,
    )
    dust_ledger.reserve_owned_return(dust_capital, now_us=540_000_000)
    dust_ledger.settle_return(
        dust_capital,
        cycle_id="DUST-CYCLE-1",
        sold_quantity=D("8"),
        net_proceeds_usdt=D("8.0016"),
        residual_mark_usdt=D("1"),
        now_us=600_000_000,
    )
    before_dust_equity = dust_ledger.marked_equity({"USDC": D("1")})
    tradeable = dust_ledger.dust.tradeable_quantity(
        "USDC", step_size=D("0.1"), minimum_quantity=D("0.1"), pair_id="PAIR_A"
    )
    aggregate_id = dust_ledger.reserve_aggregated_dust(
        pair_id="PAIR_A",
        asset="USDC",
        quantity=tradeable,
        mark_usdt=D("1"),
        now_us=660_000_000,
    )
    after_dust_equity = dust_ledger.marked_equity({"USDC": D("1")})
    record(
        "DUST_ACCOUNTING",
        before_dust_equity == D("200.0007")
        and after_dust_equity == before_dust_equity
        and dust_ledger.dust.quantity("USDC", pair_id="PAIR_A") == D("0.0991"),
        {
            "ORIGINAL_NET_ASSET": "8.9991",
            "FIRST_RETURN_QUANTITY": "8",
            "DUST_BEFORE_AGGREGATION": "0.9991",
            "AGGREGATED_TRADEABLE": str(tradeable),
            "DUST_AFTER_AGGREGATION": str(
                dust_ledger.dust.quantity("USDC", pair_id="PAIR_A")
            ),
            "AGGREGATED_CAPITAL_ID": aggregate_id,
            "MARKED_EQUITY_BEFORE_AND_AFTER": str(after_dust_equity),
        },
    )

    cycles = CycleAttributionLedger()
    cycles.record(
        CycleRecord("A", "PAIR_A", D("10.10"), D("10"), D("0"), D("0"), D("0"))
    )
    cycles.record(
        CycleRecord("B", "PAIR_B", D("9.99"), D("10"), D("0"), D("0"), D("0"))
    )
    record(
        "ZERO_LOSS_ATTRIBUTION",
        cycles.aggregate_pnl_usdt == D("0.09")
        and cycles.negative_closed_cycles == 1
        and not cycles.zero_loss_cycle_pass,
        {
            "AGGREGATE_PNL_USDT": str(cycles.aggregate_pnl_usdt),
            "NEGATIVE_CLOSED_CYCLES": cycles.negative_closed_cycles,
            "ZERO_LOSS_CYCLE_PASS": cycles.zero_loss_cycle_pass,
        },
    )

    cancel_ledger = GlobalCapitalLedger()
    cancel_capital = ParallelPairCapitalAllocator(cancel_ledger).allocate(
        [make_candidate("CANCEL", "PAIR_A", "70")], now_us=720_000_000
    )[0].capital_id
    cancel_ledger.request_cancel(cancel_capital, now_us=780_000_000)
    before_cancel_ack = cancel_ledger.free_usdt
    cancel_ledger.acknowledge_cancel(cancel_capital, now_us=840_000_000)
    record(
        "CANCEL_ACK",
        before_cancel_ack == D("130") and cancel_ledger.free_usdt == D("200"),
        {
            "FREE_AFTER_REQUEST": str(before_cancel_ack),
            "FREE_AFTER_ACK": str(cancel_ledger.free_usdt),
        },
    )

    own_order = next(iter(pair_b.state.orders.values()))
    self_fill_blocked = False
    try:
        pair_b.consume_public_trade(
            trade_id=own_order.order_id,
            side=own_order.side,
            price=own_order.price,
            quantity=D("1"),
            now_us=850_000_000,
            source="OWN_ORDER",
        )
    except ValueError as exc:
        self_fill_blocked = str(exc) == "M035_SELF_FILL_PROHIBITED"
    record("NO_SELF_FILL", self_fill_blocked, {"SELF_FILL_REJECTED": self_fill_blocked})

    physical_ledger = GlobalCapitalLedger()
    physical_allocator = ParallelPairCapitalAllocator(physical_ledger)
    physical_a = PairEngine(
        pair_id="PAIR_A",
        symbol="USDCUSDT",
        pair_asset="USDC",
        tick_size=D("0.0001"),
        capital_ledger=physical_ledger,
    )
    physical_b = PairEngine(
        pair_id="PAIR_B",
        symbol="FDUSDUSDT",
        pair_asset="FDUSD",
        tick_size=D("0.0001"),
        capital_ledger=physical_ledger,
    )
    for pair in (physical_a, physical_b):
        pair.receive_book(bid=D("0.9999"), ask=D("1.0001"), now_us=0)
        pair.initialize_grid(now_us=0)
    physical_grants = physical_allocator.allocate(
        [
            make_candidate("PHYSICAL-A", "PAIR_A", "0.9999"),
            make_candidate("PHYSICAL-B", "PAIR_B", "0.9999"),
        ],
        now_us=700_000_000,
    )
    grant_by_pair = {row.pair_id: row for row in physical_grants}
    physical_orders = {}
    for pair in (physical_a, physical_b):
        order = next(
            row
            for row in pair.state.orders.values()
            if row.side == "BUY" and row.rank == 1 and row.column == 1
        )
        pair.bind_order_capital(
            order.order_id, grant_by_pair[pair.state.pair_id].capital_id, now_us=700_000_000
        )
        physical_orders[pair.state.pair_id] = order
        pair.consume_public_trade(
            trade_id="T1",
            side="BUY",
            price=D("0.9999"),
            quantity=D("1"),
            now_us=720_000_000,
            source="PUBLIC_TRADE",
        )
    pair_trade_isolation = (
        physical_orders["PAIR_A"].filled_quantity == D("1")
        and physical_orders["PAIR_B"].filled_quantity == D("1")
        and physical_a.state.inventory_quantity == D("1")
        and physical_b.state.inventory_quantity == D("1")
        and physical_ledger.marked_equity({}) == D("200")
    )
    record(
        "PUBLIC_TRADE_ISOLATION",
        pair_trade_isolation,
        {
            "PAIR_A_INVENTORY": str(physical_a.state.inventory_quantity),
            "PAIR_B_INVENTORY": str(physical_b.state.inventory_quantity),
            "SAME_NATIVE_TRADE_ID_ALLOWED_PER_SYMBOL": True,
            "GLOBAL_MARKED_EQUITY": str(physical_ledger.marked_equity({})),
        },
    )
    a_capital = grant_by_pair["PAIR_A"].capital_id
    return_order = physical_a.submit_owned_return(
        a_capital,
        cycle_id="PHYSICAL-A-CYCLE-1",
        price=D("1.0001"),
        quantity=D("1"),
        now_us=740_000_000,
    )
    physical_a.consume_public_trade(
        trade_id="RETURN-T1",
        side="SELL",
        price=D("1.0001"),
        quantity=D("1"),
        now_us=760_000_000,
        source="PUBLIC_TRADE",
    )
    record(
        "PHYSICAL_PATH_INTEGRATION",
        physical_a.state.cycle_history == ["PHYSICAL-A-CYCLE-1"]
        and physical_ledger.cycles.zero_loss_economic_pass
        and physical_ledger.owner_of(a_capital) is None,
        {
            "PAIR_A_ORDER_STATUS": physical_orders["PAIR_A"].status,
            "PAIR_A_RETURN_ORDER_STATUS": return_order.status,
            "PAIR_A_CYCLES": physical_a.state.cycle_history,
            "GLOBAL_CYCLE_PNL": str(physical_ledger.cycles.aggregate_pnl_usdt),
            "GLOBAL_FREE_USDT": str(physical_ledger.free_usdt),
            "PAIR_B_CAPITAL_OWNER": physical_ledger.owner_of(
                grant_by_pair["PAIR_B"].capital_id
            ),
        },
    )
    unfunded_order = next(
        row
        for row in physical_a.state.orders.values()
        if row.status == OrderStatus.UNFUNDED
    )
    unfunded_fill = physical_a.consume_public_trade(
        trade_id="UNFUNDED-PRINT",
        side=unfunded_order.side,
        price=unfunded_order.price,
        quantity=D("1"),
        now_us=770_000_000,
        source="PUBLIC_TRADE",
    )
    record(
        "UNFUNDED_ORDER_INERT",
        unfunded_fill == {}
        and unfunded_order.filled_quantity == ZERO
        and unfunded_order.order_id not in physical_a.queue.order_group,
        {
            "FILLS": unfunded_fill,
            "ORDER_STATUS": unfunded_order.status,
            "PAIR_INVENTORY": str(physical_a.state.inventory_quantity),
        },
    )

    cost_ledger = GlobalCapitalLedger()
    cost_capital = ParallelPairCapitalAllocator(cost_ledger).allocate(
        [make_candidate("COST", "PAIR_A", "10")], now_us=1
    )[0].capital_id
    cost_ledger.record_entry_fill(
        cost_capital,
        asset="USDC",
        quantity_net=D("10"),
        causal_mark_usdt=D("1"),
        attributable_cost_usdt=D("1"),
        input_usdt=D("10"),
        now_us=2,
    )
    cost_ledger.update_mark(cost_capital, mark_usdt=D("1"), now_us=3)
    cost_ledger.reserve_owned_return(cost_capital, now_us=4)
    cost_ledger.settle_return(
        cost_capital,
        cycle_id="COST-CYCLE",
        sold_quantity=D("10"),
        net_proceeds_usdt=D("11"),
        residual_mark_usdt=ZERO,
        now_us=5,
    )
    record(
        "PHYSICAL_COST_CONSERVATION",
        cost_ledger.marked_equity() == D("200")
        and cost_ledger.cycles.aggregate_pnl_usdt == ZERO,
        {
            "EXTERNAL_COSTS_USDT": str(cost_ledger.external_costs_usdt),
            "FINAL_MARKED_EQUITY": str(cost_ledger.marked_equity()),
            "CYCLE_PNL_USDT": str(cost_ledger.cycles.aggregate_pnl_usdt),
        },
    )

    risk_ledger = GlobalCapitalLedger()
    risk_capital = ParallelPairCapitalAllocator(risk_ledger).allocate(
        [make_candidate("RISK", "PAIR_A", "10")], now_us=1
    )[0].capital_id
    risk_ledger.record_entry_fill(
        risk_capital,
        asset="USDC",
        quantity_net=D("10"),
        causal_mark_usdt=D("1"),
        attributable_cost_usdt=ZERO,
        input_usdt=D("10"),
        now_us=2,
    )
    risk_ledger.reserve_owned_return(risk_capital, now_us=3)
    invented_auth_blocked = False
    try:
        risk_ledger.settle_return(
            risk_capital,
            cycle_id="INVENTED",
            sold_quantity=D("10"),
            net_proceeds_usdt=D("9"),
            residual_mark_usdt=ZERO,
            now_us=4,
            risk_exit_authorization_id="NOT_REGISTERED",
        )
    except ValueError as exc:
        invented_auth_blocked = str(exc) == "M035_RISK_EXIT_AUTHORIZATION_NOT_APPLICABLE"
    risk_ledger.register_risk_exit_authorization(
        RiskExitAuthorization(
            authorization_id="RISK-AUTH-1",
            capital_id=risk_capital,
            pair_id="PAIR_A",
            decided_at_us=4,
            expires_at_us=5,
            rule_hash="M035-FROZEN-RISK-RULE",
            quantity=D("10"),
            expected_hold_loss_usdt=D("2"),
            opportunity_cost_usdt=ZERO,
            tail_risk_usdt=ZERO,
            loss_if_exit_now_usdt=D("1"),
        ),
        now_us=4,
    )
    risk_ledger.settle_return(
        risk_capital,
        cycle_id="AUTHORIZED-RISK",
        sold_quantity=D("10"),
        net_proceeds_usdt=D("9"),
        residual_mark_usdt=ZERO,
        now_us=5,
        risk_exit_authorization_id="RISK-AUTH-1",
    )
    record(
        "RISK_EXIT_AUTHORIZATION",
        invented_auth_blocked
        and risk_ledger.cycles.negative_risk_exits == 1
        and not risk_ledger.zero_loss_economic_pass(),
        {
            "INVENTED_AUTHORIZATION_BLOCKED": invented_auth_blocked,
            "NEGATIVE_RISK_EXITS": risk_ledger.cycles.negative_risk_exits,
            "ZERO_LOSS_ECONOMIC_PASS": risk_ledger.zero_loss_economic_pass(),
        },
    )

    physical_b.receive_book(
        bid=D("0.90"), ask=D("0.9002"), now_us=800_000_000, reason="MARKED_LOSS_PROBE"
    )
    record(
        "OPEN_INVENTORY_MARKING",
        physical_ledger.marked_equity() == D("199.9003")
        and not physical_ledger.zero_loss_economic_pass(),
        {
            "PAIR_B_MARK": "0.90",
            "GLOBAL_MARKED_EQUITY": str(physical_ledger.marked_equity()),
            "ZERO_LOSS_ECONOMIC_PASS": physical_ledger.zero_loss_economic_pass(),
        },
    )

    causal = make_engine("PAIR_A", "USDCUSDT", "USDC")
    cutoff = 870_000_000
    past = causal.hotline_at(cutoff)
    causal.receive_book(bid=D("1.0099"), ask=D("1.0101"), now_us=880_000_000)
    record(
        "NO_FUTURE_DATA",
        causal.hotline_at(cutoff) == past,
        {
            "CUTOFF_US": cutoff,
            "HOTLINE_AT_CUTOFF_BEFORE_FUTURE": str(past),
            "HOTLINE_AT_CUTOFF_AFTER_FUTURE": str(causal.hotline_at(cutoff)),
            "FUTURE_HOTLINE": str(causal.state.hotline),
        },
    )

    required = {
        "HOTLINE_ISOLATION",
        "GRID_FOLLOWS_HOTLINE",
        "C1_FIFO_PRESERVATION",
        "C2_MOBILITY",
        "GLOBAL_CAPITAL_CONSERVATION",
        "NO_DOUBLE_CAPITAL",
        "OWNED_RETURN_PRIORITY",
        "DUST_ACCOUNTING",
        "ZERO_LOSS_ATTRIBUTION",
        "CANCEL_ACK",
        "NO_SELF_FILL",
        "NO_FUTURE_DATA",
    }
    all_pass = required.issubset(checks) and all(
        row["STATUS"] == "PASS" for row in checks.values()
    )
    frozen_config = {
        "IDENTITY": "M035_PARALLEL_PAIR_CAPITAL_MANAGER_CONFORMANCE_V1",
        "MODE": "SYNTHETIC_DETERMINISTIC_CONFORMANCE_ONLY",
        "LOGICAL_DURATION_SECONDS": LOGICAL_DURATION_SECONDS,
        "INITIAL_BANK_USDT": "200.00",
        "PAIRS": ["PAIR_A:USDCUSDT", "PAIR_B:FDUSDUSDT_SYNTHETIC_FIXTURE"],
        "RANKS_PER_SIDE": 7,
        "COLUMNS": ["C1_PERSISTENT", "C2_OPPORTUNISTIC"],
    }
    source_sha = bundle_hash(SOURCE_FILES)
    report = {
        "MODEL": "M035_PARALLEL_PAIR_CAPITAL_MANAGER",
        "REPORT": "M035_CONFORMANCE_REPORT",
        "STATUS": "PASS" if all_pass else "FAIL",
        "SCIENTIFIC_ROLE": "SOFTWARE_CONFORMANCE_NOT_ECONOMIC_RESULT",
        "CONFIG": frozen_config,
        "CONFIG_SHA256": config_hash(frozen_config),
        "SOURCE_BUNDLE_SHA256": source_sha,
        "BASE_GIT_HEAD": git_value("rev-parse", "HEAD"),
        "SOURCE_PUBLISHED": False,
        "SOURCE_REVIEW_STATUS": "PENDING_INDEPENDENT_SOURCE_BOUND_REVIEW",
        "CHECKS": checks,
        "ALL_REQUIRED_GATES_PASS": all_pass,
        "ECONOMIC_RUN_AUTHORIZED": False,
        "ECONOMIC_RUN_BLOCKER": "MULTI_PAIR_HISTORICAL_TEST_BLOCKED_BY_PAIR_B_DATA",
    }
    return report, frozen_config


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_header_only(path: Path, columns: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        csv.writer(handle).writerow(columns)


def main() -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report, frozen_config = run_gate()
    write_json(REPORT_DIR / "M035_CONFORMANCE_REPORT.json", report)
    result = {
        "MODEL": "M035_PARALLEL_PAIR_CAPITAL_MANAGER",
        "IDENTITY": "M035_200USD_3H_V1_NOT_STARTED",
        "STATUS": "BLOCKED_PRE_ECONOMIC_RUN",
        "BLOCKER": "MULTI_PAIR_HISTORICAL_TEST_BLOCKED_BY_PAIR_B_DATA",
        "REASON": "No second canonical Binance pair has aligned physical L2 and individual trades.",
        "INITIAL_BANK_USD": "200.00",
        "DURATION_HOURS": 3,
        "SAME_BANK": True,
        "PARALLEL": True,
        "PAIR_A": {"SYMBOL": "USDCUSDT", "DATA_STATUS": "AVAILABLE"},
        "PAIR_B": {"SYMBOL": "FDUSDUSDT", "DATA_STATUS": "UNAVAILABLE"},
        "ALIGNED_TWO_PAIR_WINDOWS": 0,
        "CONFORMANCE_STATUS": report["STATUS"],
        "CONFORMANCE_CONFIG_SHA256": report["CONFIG_SHA256"],
        "SOURCE_BUNDLE_SHA256": report["SOURCE_BUNDLE_SHA256"],
        "SOURCE_PUBLISHED": False,
        "SOURCE_REVIEW_STATUS": report["SOURCE_REVIEW_STATUS"],
        "TAPE_CONSUMED": False,
        "ECONOMIC_RUNS": 0,
        "SINGLE_PAIR_BASELINE": "NOT_EXECUTED",
        "M029_M030_COMPATIBLE_BASELINE": "NOT_EXECUTED",
        "M035_TREATMENT": "NOT_EXECUTED",
        "METRICS": {
            "INITIAL_EQUITY": "200.00",
            "FINAL_REALIZED_EQUITY": None,
            "FINAL_MARKED_EQUITY": None,
            "REALIZED_PNL": None,
            "MARKED_PNL": None,
            "REALIZED_RETURN_PCT": None,
            "MARKED_RETURN_PCT": None,
            "PHYSICAL_CYCLES": None,
            "SLOT_EQUIVALENT_CYCLES": None,
            "CYCLES_PER_HOUR": None,
            "NET_PNL_PER_CAPITAL_HOUR": None,
            "PARALLEL_CYCLE_GAIN_PCT": None,
            "PARALLEL_PRODUCTIVITY_GAIN_PCT": None,
            "NEGATIVE_CLOSED_CYCLES": None,
            "NEGATIVE_RISK_EXITS": None,
            "DUST_BY_ASSET": None,
        },
        "DATA_AUTHORITIES": [
            "reports/usdcusdt/M034-pair-universe.json",
            "reports/usdcusdt/M034_BINANCE_DATASET_MANIFEST.json",
            "docs/research/M034_BINANCE_EVIDENCE_PACK.md",
        ],
        "NEXT_EVIDENCE_ACTION": (
            "Prepare a separately authorized simultaneous Binance public L2 + individual-trade "
            "capture for USDCUSDT and FDUSDUSDT; validate continuity before preregistering replay."
        ),
        "FROZEN_CONFORMANCE_CONFIG": frozen_config,
    }
    write_json(REPORT_DIR / "M035_200USD_3H_RESULT.json", result)
    write_header_only(
        REPORT_DIR / "M035_CYCLES.csv",
        [
            "cycle_id",
            "pair_id",
            "route",
            "start_timestamp_us",
            "end_timestamp_us",
            "duration_seconds",
            "capital_used_usdt",
            "gross_pnl_usdt",
            "fees_usdt",
            "execution_cost_usdt",
            "adverse_selection_usdt",
            "net_pnl_usdt",
            "return_pct",
        ],
    )
    timeline_columns = [
        "timestamp_us",
        "free_usdt",
        "reserved_pair_a_usdt",
        "reserved_pair_b_usdt",
        "inventory_pair_a_marked_usdt",
        "inventory_pair_b_marked_usdt",
        "return_pair_a_marked_usdt",
        "return_pair_b_marked_usdt",
        "cancel_pending_marked_usdt",
        "dust_marked_usdt",
        "total_marked_equity_usdt",
    ]
    write_header_only(REPORT_DIR / "M035_CAPITAL_TIMELINE.csv", timeline_columns)
    pair_columns = [
        "timestamp_us",
        "pair_id",
        "symbol",
        "hotline",
        "free_capital_usdt",
        "committed_capital_usdt",
        "inventory_quantity",
        "dust_quantity",
        "physical_cycles",
        "realized_pnl_usdt",
    ]
    write_header_only(REPORT_DIR / "M035_PAIR_A_TIMELINE.csv", pair_columns)
    write_header_only(REPORT_DIR / "M035_PAIR_B_TIMELINE.csv", pair_columns)
    if report["STATUS"] != "PASS":
        raise SystemExit("M035_CONFORMANCE_FAILED")


if __name__ == "__main__":
    main()
