"""Read one atomic B10 checkpoint; derive owner metrics without touching its writer."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import UTC, datetime, timedelta
from decimal import Decimal, localcontext
from pathlib import Path

import numpy as np

from crypto_strategy_lab.domain import canonical_hash

SCALE = 4096
DAY_US = 86_400_000_000
HOUR_US = 3_600_000_000
TAPE = Path(
    "artifacts/usdcusdt/market-tape/22307d010fe179b2b834931f839376014423bde9a7751b4f453463de16bdcf18"
)
INDEX = Path("artifacts/binance/b10-reference-prefix/exit-events.npy")
REFERENCE_SHA = "2b08d28152b27000120f6c503838ff1c8ed7da12c33d34892826c41c3da98e51"
SHORT = {
    "A_OBSERVED_BEST_SUPPORTED": "A",
    "B_REALISTIC_CONSERVATIVE": "B",
    "C_ADVERSARIAL_PLAUSIBLE": "C",
    "B_FEE10_PROMOTION_ABSENT": "B_FEE10",
}


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def dec(value):
    return Decimal(value["decimal"] if isinstance(value, dict) else str(value))


def stamp(micros):
    return (datetime(1970, 1, 1, tzinfo=UTC) + timedelta(microseconds=micros)).isoformat()


def exact_event(state, tape_dir=TAPE):
    manifest = json.loads((tape_dir / "manifest.json").read_text(encoding="utf-8"))
    if manifest["tape_hash"] != "505fd6c31b010eac4e8da2d7e290137bb455d475b95409ac306d1ded7be55b6c":
        raise ValueError("B10_TAPE_IDENTITY_MISMATCH")
    events_path = tape_dir / "events.npy"
    if digest(events_path) != manifest["files"]["events"]["sha256"]:
        raise ValueError("CANONICAL_EVENTS_HASH_MISMATCH")
    events = np.load(events_path, mmap_mode="r", allow_pickle=False)
    begin = int(np.searchsorted(events, state["start_us"] * SCALE))
    index = begin + state["processed_trades"] - 1
    event = int(events[index])
    if event // SCALE != state["last_us"]:
        raise ValueError("CHECKPOINT_CANONICAL_EVENT_MISMATCH")
    return event


def reference_count(event, index_path=INDEX):
    metadata = json.loads(index_path.with_suffix(".json").read_text(encoding="utf-8"))
    if metadata["source_sha256"] != REFERENCE_SHA or metadata["count"] != 3580880:
        raise ValueError("REFERENCE_INDEX_IDENTITY_MISMATCH")
    if digest(index_path) != metadata["index_sha256"]:
        raise ValueError("REFERENCE_INDEX_HASH_MISMATCH")
    exits = np.load(index_path, mmap_mode="r", allow_pickle=False)
    return int(np.searchsorted(exits, event, side="right"))


def summarize(payload, prefix_count, *, run_status="RUNNING"):
    state = payload["state"]
    engine = payload["execution"]["state"]
    start, end, now = state["start_us"], state["end_us"], state["last_us"]
    complete = state["completed"]
    horizon = end if complete else now
    total_days = (end - 1) // DAY_US - start // DAY_US + 1
    closed_days = total_days if complete else now // DAY_US - start // DAY_US
    current_date = stamp(now)[:10]
    full_days = state["full_days"]
    active_closed = sum(v > 0 for k, v in full_days.items() if complete or k < current_date)
    counts = engine["counts"]
    holds = list(state["holds_us"])
    if engine["entry_us"] is not None:
        holds.append(horizon - engine["entry_us"])
    orders = {"BUY": Counter(), "SELL": Counter()}
    release_orders = 0
    for wrapped in engine["orders"]:
        order = wrapped["fields"]
        if order["release"]:
            release_orders += 1
            continue
        amount, qty = dec(order["filled"]), dec(order["quantity"])
        bucket = "FULL" if amount == qty else ("PARTIAL_ONLY" if amount > 0 else "NOT_FILLED")
        orders[order["side"]][bucket] += 1
    settlements = engine["settlements"]
    with localcontext() as context:
        context.prec = 128
        settled_net = sum((dec(row["net_profit"]) for row in settlements), Decimal(0))
        settled_gross = sum((dec(row["gross_pnl"]) for row in settlements), Decimal(0))
        pending_realized = dec(engine["sell_net"]) - dec(engine["sold_cost"])
        net = settled_net + pending_realized
        gross = settled_gross + pending_realized + dec(engine["realized_cycle_fees"])
        marked = (
            dec(engine["cash"])
            + dec(engine["reserve"])
            + (dec(engine["inventory"]) + dec(engine["dust"])) * dec(engine["bids"][0][0])
        )
        maximum = str(Decimal(max(holds, default=0)) / HOUR_US)
        lock = str(Decimal(sum(max(0, h - DAY_US) for h in holds)) / HOUR_US)
        retention = (
            str(Decimal(counts.get("FULLY_FILLED_CYCLES", 0)) / prefix_count)
            if prefix_count
            else None
        )
        progress = str(Decimal(horizon - start) / (end - start) * 100)
    profile = engine["profile"]["fields"]["name"]
    return {
        "strategy": "B10_FROZEN",
        "run_id": state["identity"]["profile_config_sha256"],
        "profile": SHORT.get(profile, profile),
        "profile_name": profile,
        "status": "COMPLETE" if complete else run_status,
        "simulation_start": stamp(start),
        "simulation_timestamp": stamp(now),
        "simulation_end": stamp(end),
        "calendar_days_processed": closed_days,
        "calendar_days_total": total_days,
        "progress_percent": progress,
        "price_path_reference_full": 3580880,
        "price_path_opportunities_same_prefix": prefix_count,
        "full_fill_cycles": counts.get("FULLY_FILLED_CYCLES", 0),
        "net_positive_cycles": counts.get("NET_POSITIVE_CYCLES", 0),
        "reality_retention_same_prefix": retention,
        "zero_cycle_days_so_far": closed_days - active_closed,
        "active_days_so_far": active_closed,
        "current_partial_day_cycles": None if complete else full_days.get(current_date, 0),
        **{
            f"{side.lower()}_{kind.lower()}": orders[side][kind]
            for side in ("BUY", "SELL")
            for kind in ("FULL", "PARTIAL_ONLY", "NOT_FILLED")
        },
        "release_attempted": counts.get("RELEASE_SIGNALS", 0),
        "release_ioc_orders": release_orders,
        "release_filled": counts.get("RELEASE_FILLED", 0),
        "release_blocked": payload["release_evaluations"].get("INSUFFICIENT_RESERVE", 0),
        "releases_gt10bps_executed": counts.get("RELEASES_GT10BPS_EXECUTED_LOT", 0),
        "net_pnl_fixed_100": str(net),
        "gross_pnl_fixed_100": str(gross),
        "settled_net_pnl_fixed_100": str(settled_net),
        "pending_partial_sale_realized_pnl": str(pending_realized),
        "fees_paid": str(dec(engine["fees"])),
        "slippage_cost": None,
        "reserve_initial": 5,
        "reserve_contributions": str(dec(engine["reserve_funding"])),
        "reserve_consumption": str(dec(engine["reserve_consumption"])),
        "reserve_final": str(dec(engine["reserve"])),
        "reserve_min": str(dec(engine["reserve_min"])),
        "reserve_depletion_events": counts.get("RESERVE_DEPLETION_EVENTS", 0),
        "max_hold": maximum,
        "lock_hours": lock,
        "max_drawdown": str(dec(state["max_drawdown"])),
        "operating_cash": str(dec(engine["cash"])),
        "inventory_usdc": str(dec(engine["inventory"])),
        "inventory_cost_basis": str(dec(engine["cost"])),
        "dust_usdc": str(dec(engine["dust"])),
        "marked_total_equity": str(marked),
        "processed_trades": state["processed_trades"],
        "expected_trades": state["identity"]["expected_trade_count"],
        "execution_source_commit": state["identity"]["published_config_sha"],
        "verdict": "INCONCLUSIVE_EXECUTION_DATA" if complete else "PENDING",
        "semantics": {
            "days": "Completed UTC calendar days only; current incomplete day shown separately.",
            "progress": "Elapsed simulated time, not fraction of trade rows.",
            "retention": "Full-fill count / original ordinary exits at SAME inclusive canonical "
            "event; productivity ratio, not mapped survivor identities.",
            "orders": "Normal BUY/SELL submitted orders only; full/partial-only/zero-fill cohorts; "
            "zero-fill includes pending/rejected/canceled.",
            "releases": "Attempted counts B10 release signals; IOC order attempts are separate. "
            "Blocked counts INSUFFICIENT_RESERVE predicate evaluations.",
            "loss_bps": "Executed lot cost denominator, never clamped at 10bps.",
            "pnl": "Realized settled PnL plus realized partial sales in open lot; excludes unsold "
            "inventory mark and internal reserve transfers.",
            "max_hold_and_lock": "Hours; includes ongoing position through checkpoint T. "
            "Lock is sum of holding hours beyond24h.",
            "drawdown": "Fraction of marked cash+inventory+dust+reserve equity.",
        },
        "unavailable_until": {
            "slippage_cost": "Independent spread/latency/slippage decomposition from historical "
            "execution evidence; current envelope embeds costs in fill prices, "
            "no isolated estimate."
        },
    }


def read_checkpoint(folder, config_path, *, run_status="RUNNING"):
    raw = (folder / "checkpoint.json").read_bytes()  # one atomic file version
    checkpoint = json.loads(raw)
    payload = checkpoint["replay"]["payload"]
    if canonical_hash(payload) != checkpoint["replay"]["sha256"]:
        raise ValueError("CHECKPOINT_PAYLOAD_HASH_MISMATCH")
    config_sha = digest(config_path)
    if payload["state"]["identity"]["profile_config_sha256"] != config_sha:
        raise ValueError("CHECKPOINT_PROFILE_HASH_MISMATCH")
    event = exact_event(payload["state"])
    count = reference_count(event)
    result = summarize(payload, count, run_status=run_status)
    result["updated_at"] = datetime.now(UTC).isoformat()
    result["evidence"] = {
        "checkpoint_path": str(folder / "checkpoint.json"),
        "checkpoint_sha256": hashlib.sha256(raw).hexdigest(),
        "checkpoint_payload_sha256": checkpoint["replay"]["sha256"],
        "journal_durable_prefix": checkpoint["audit"],
        "profile_config_sha256": config_sha,
        "canonical_cutoff_event": event,
        "reference_index_manifest": str(INDEX.with_suffix(".json")),
        "reference_source_sha256": REFERENCE_SHA,
        "snapshot_note": "Derived from immutable in-memory copy of one atomic checkpoint; "
        "no writer lock or engine access. Journal prefix hash declared here, "
        "not re-audited by reporter.",
    }
    return result
