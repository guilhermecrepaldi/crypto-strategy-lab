"""Independent execution ledger and sampled official raw-flow audit.

Uses only the standard library, never simulator accounting/selection helpers.
Reads each required ZIP at most once; ordinary sample is first 100 settlements,
chosen before inspecting profitability, plus every release order and settlement.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from collections import defaultdict
from datetime import UTC, datetime
from decimal import ROUND_FLOOR, Decimal, localcontext
from pathlib import Path

D = Decimal
EPSILON = D("1e-110")


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def iter_rows(path):
    if path.suffix == ".jsonl":
        with path.open(encoding="utf-8") as stream:
            for line in stream:
                if line.strip():
                    yield json.loads(line)
    else:
        yield from json.loads(path.read_text(encoding="utf-8"))


def number(value):
    # SUBMIT rows may use the project's tagged Decimal checkpoint encoding.
    if isinstance(value, dict) and set(value) == {"decimal"}:
        value = value["decimal"]
    return D(str(value))


def same(actual, expected, description):
    if abs(number(actual) - number(expected)) > EPSILON:
        raise ValueError(f"{description}: actual={actual}, expected={expected}")


def reconstruct(rows, profile, *, owner_reserve=False):
    """Independent balances and lot basis for every fill, including unsold inventory."""
    cash, reserve = D(100), D(10) if owner_reserve else D(5)
    inventory = basis = sold_basis = sale_net = dust = dust_basis = fees = D(0)
    funding = consumption = D(0)
    orders, fills, settlements = {}, [], []
    terminal = set()
    release_evaluations = []
    signal_records = {}
    cycle_orders = set()
    released = False
    with localcontext() as context:
        context.prec = 128
        for index, row in enumerate(rows):
            kind = row["kind"]
            if kind == "RELEASE_SIGNAL":
                signal_records[row["signal_id"]] = row
            if kind in {"IOC_EXPIRED", "CANCELED", "REJECTION"} and "order_id" in row:
                terminal.add(row["order_id"])
            if kind == "CANCELED":
                orders[row["order_id"]]["cancel_effective_us"] = row["time_us"]
            if kind == "RELEASE_BOOK_EVALUATION":
                release_evaluations.append(row)
                order = orders[row["order_id"]]
                if not order["release"] or row["time_us"] <= order["active_us"]:
                    raise ValueError("INVALID_RELEASE_ACTIVATION")
            if kind == "IOC_EXPIRED":
                order = orders[row["order_id"]]
                same(row["filled"], order["audit_filled"], "IOC_FILLED")
                same(
                    row["remaining"],
                    number(order["quantity"]) - order["audit_filled"],
                    "IOC_REMAINING",
                )
            if kind == "SUBMIT":
                order_id = row["order_id"]
                if order_id in orders:
                    raise ValueError("DUPLICATE_ORDER_ID")
                orders[order_id] = {**row, "audit_filled": D(0), "row_index": index}
            elif kind == "FILL":
                order = orders[row["order_id"]]
                amount, price = number(row["quantity"]), number(row["price"])
                if amount <= 0 or price <= 0 or row["time_us"] <= order["active_us"]:
                    raise ValueError("INVALID_FILL_QUANTITY_PRICE_OR_ACTIVATION")
                if row["side"] != order["side"] or row["release"] != order["release"]:
                    raise ValueError("FILL_ORDER_IDENTITY_MISMATCH")
                if row["time_us"] > order.get("cancel_effective_us", row["time_us"]):
                    raise ValueError("FILL_AFTER_CANCELLATION")
                order["audit_filled"] += amount
                if order["audit_filled"] > number(order["quantity"]) + EPSILON:
                    raise ValueError("ORDER_OVERFILL")
                gross = amount * price
                rate = number(profile["taker_fee"] if row["release"] else profile["maker_fee"])
                fee = gross * rate
                same(row["fee_quote"], fee, "COMMISSION_QUOTE")
                if row["side"] == "BUY":
                    if row["commission_asset"] != "USDC":
                        raise ValueError("BUY_FEE_ASSET")
                    same(row["commission"], amount * rate, "BUY_COMMISSION")
                    cash -= gross
                    inventory += amount * (1 - rate)
                    basis += gross
                else:
                    if amount > inventory or row["commission_asset"] != "USDT":
                        raise ValueError("SELL_INVENTORY_OR_FEE_ASSET")
                    same(row["commission"], fee, "SELL_COMMISSION")
                    allocated = basis * amount / inventory
                    basis -= allocated
                    sold_basis += allocated
                    inventory -= amount
                    cash += gross - fee
                    sale_net += gross - fee
                fees += fee
                released |= row["release"]
                cycle_orders.add(row["order_id"])
                fills.append(row)
                if min(cash, inventory, basis, reserve) < -EPSILON:
                    raise ValueError("NEGATIVE_FINANCIAL_BALANCE")
            elif kind == "SETTLEMENT":
                profit = sale_net - sold_basis
                same(row["net_profit"], profit, "NET_REALIZED_PNL")
                same(row["sold_cost"], sold_basis, "SOLD_COST")
                if row["release"] != released:
                    raise ValueError("RELEASE_CLASSIFICATION")
                deficit = max(D(0), -profit) if released else D(0)
                lot_bps = deficit / sold_basis * 10000 if sold_basis else D(0)
                signal_id = row.get("release_signal_id")
                bank_bps = None
                if signal_id is not None:
                    signal_bank = number(signal_records[signal_id]["operating_bank_before"])
                    same(row["release_signal_bank"], signal_bank, "SIGNAL_BANK_BINDING")
                    bank_bps = deficit / signal_bank * 10000
                if "actual_release_loss" in row:
                    same(row["actual_release_loss"], deficit, "ACTUAL_RELEASE_DEFICIT")
                    if "actual_loss_bps_executed_lot" in row:
                        same(row["actual_loss_bps_executed_lot"], lot_bps, "ACTUAL_LOT_BPS")
                    if bank_bps is not None and "actual_loss_bps_signal_bank" in row:
                        same(row["actual_loss_bps_signal_bank"], bank_bps, "ACTUAL_BANK_BPS")
                if released and not (owner_reserve and profit > 0):
                    transfer = max(D(0), -profit)
                    if owner_reserve and reserve - transfer < D("2.5") - EPSILON:
                        raise ValueError("OWNER_RESERVE_CORE_FLOOR_VIOLATION")
                    transfer = min(transfer, reserve) if not owner_reserve else transfer
                    reserve -= transfer
                    cash += transfer
                    consumption += transfer
                else:
                    transfer = max(D(0), profit) * (D("0.10") if owner_reserve else D("0.02"))
                    reserve += transfer
                    cash -= transfer
                    funding += transfer
                dust += inventory
                dust_basis += basis
                for key, value in (
                    ("cash", cash),
                    ("reserve", reserve),
                    ("dust", dust),
                    ("dust_cost", dust_basis),
                    ("reserve_transfer", transfer),
                ):
                    same(row[key], value, key)
                settlements.append(
                    {
                        "row_index": index,
                        "time_us": row["time_us"],
                        "order_ids": sorted(cycle_orders),
                        "release": released,
                        "net_profit": str(profit),
                        "release_signal_id": signal_id,
                        "executed_deficit": str(deficit),
                        "actual_loss_bps_executed_lot": str(lot_bps),
                        "actual_loss_bps_signal_bank": str(bank_bps)
                        if bank_bps is not None
                        else None,
                        "reserve_transfer": str(transfer),
                    }
                )
                inventory = basis = sold_basis = sale_net = D(0)
                cycle_orders = set()
                released = False
    return {
        "cash": cash,
        "reserve": reserve,
        "inventory": inventory,
        "basis": basis,
        "dust": dust,
        "dust_basis": dust_basis,
        "fees": fees,
        "funding": funding,
        "consumption": consumption,
        "orders": orders,
        "fills": fills,
        "settlements": settlements,
        "terminal": terminal,
        "release_evaluations": release_evaluations,
        "open_cycle_orders": cycle_orders,
        "signal_records": signal_records,
    }


def audit_raw_support(history, orders, fills, chosen, evaluations, envelope, rules):
    selected = [row for row in fills if row["order_id"] in chosen]
    for evaluation in evaluations:
        selected.append(
            {
                "order_id": evaluation["order_id"],
                "source_id": evaluation["book_source_id"],
                "source": "BOOK",
                "time_us": evaluation["time_us"],
                "quantity": "0",
                "price": evaluation["best_bid"],
                "side": "SELL",
            }
        )
    needed = {row["source_id"] for row in selected}
    wanted_rows = {}
    maker_windows = []
    for order_id in chosen:
        supporting = [
            row for row in selected if row["order_id"] == order_id and row["source"] == "TRADE"
        ]
        if supporting:
            order = orders[order_id]
            maker_windows.append(
                {
                    "order_id": order_id,
                    "start": order["active_us"],
                    "end": max(row["time_us"] for row in supporting),
                    "price": number(order["price"]),
                    "buyer_maker": order["side"] == "BUY",
                    "queue": number(order["queue"]),
                    "volume": D(0),
                    "filled": D(0),
                }
            )
    windows = sorted(maker_windows, key=lambda row: row["start"])
    required_spans = [(window["start"], window["end"]) for window in windows]
    required_spans += [(row["time_us"], row["time_us"]) for row in selected]
    fill_at = defaultdict(list)
    for row in selected:
        if row["source"] == "TRADE":
            fill_at[(row["order_id"], row["source_id"])].append(row)
    paths = []
    for archive in history["archives"]:
        day = datetime.fromisoformat(archive["utc_date"]).replace(tzinfo=UTC)
        first = int(day.timestamp()) * 1_000_000
        last = first + 86_400_000_000 - 1
        if any(start <= last and end >= first for start, end in required_spans):
            paths.append((archive, first, last))
    queue_checks, scanned = 0, []
    with localcontext() as context:
        context.prec = 128
        for archive, first, last in paths:
            path = Path(archive["local_path"])
            # ZIP identity is verified only for the archives actually opened.
            if digest(path) != archive["sha256"]:
                raise ValueError(f"RAW_ARCHIVE_HASH_MISMATCH:{path}")
            relevant = [
                window for window in windows if window["start"] <= last and window["end"] >= first
            ]
            cutoff = max(end for start, end in required_spans if start <= last and end >= first)
            lines = 0
            with zipfile.ZipFile(path) as zipped:
                members = [name for name in zipped.namelist() if name.endswith(".csv")]
                if len(members) != 1:
                    raise ValueError("EXPECTED_ONE_RAW_CSV")
                with zipped.open(members[0]) as source:
                    for line in source:
                        columns = line.strip().split(b",")
                        if not columns or not columns[0].isdigit():
                            continue
                        trade_id, stamp = int(columns[0]), int(columns[4])
                        lines += 1
                        if stamp > cutoff:
                            break
                        active = [
                            window
                            for window in relevant
                            if window["start"] < stamp <= window["end"]
                        ]
                        if not active and trade_id not in needed:
                            continue
                        price, quantity = D(columns[1].decode()), D(columns[2].decode())
                        side = columns[5].lower()
                        if side not in (b"true", b"false"):
                            raise ValueError("RAW_AGGRESSOR_INVALID")
                        buyer_maker = side == b"true"
                        if trade_id in needed:
                            wanted_rows[trade_id] = {
                                "time_us": stamp,
                                "price": price,
                                "quantity": quantity,
                                "buyer_maker": buyer_maker,
                            }
                        for window in active:
                            if price == window["price"] and buyer_maker == window["buyer_maker"]:
                                window["volume"] += quantity
                            for fill in fill_at[(window["order_id"], trade_id)]:
                                window["filled"] += number(fill["quantity"])
                                if window["volume"] + EPSILON < window["queue"] + window["filled"]:
                                    raise ValueError("UNSUPPORTED_QUEUE_CLEARANCE")
                                queue_checks += 1
            scanned.append({"path": str(path), "sha256": archive["sha256"], "rows_examined": lines})
        allocated = defaultdict(lambda: D(0))
        for fill in selected:
            raw = wanted_rows.get(fill["source_id"])
            if raw is None or raw["time_us"] != fill["time_us"]:
                raise ValueError("FILL_SOURCE_NOT_FOUND_OR_TIME_MISMATCH")
            if fill["source"] == "TRADE":
                same(fill["price"], raw["price"], "RAW_FILL_PRICE")
                if raw["buyer_maker"] != (fill["side"] == "BUY"):
                    raise ValueError("RAW_FILL_AGGRESSOR_MISMATCH")
                allocated[fill["source_id"]] += number(fill["quantity"])
                if allocated[fill["source_id"]] > raw["quantity"] + EPSILON:
                    raise ValueError("RAW_PRINT_QUANTITY_REUSED")
            elif fill["source"] != "BOOK":
                raise ValueError("UNKNOWN_FILL_SOURCE")
            else:
                rule = next(
                    row["rule"]
                    for row in rules
                    if row["start_us"] <= fill["time_us"] < row["end_us"]
                )
                tick = number(rule["tick_size"])
                implied_bid = raw["price"] - (
                    D(0) if raw["buyer_maker"] else 2 * number(envelope["half_spread"])
                )
                implied_bid -= number(envelope["release_slippage"])
                implied_bid = (implied_bid / tick).to_integral_value(rounding=ROUND_FLOOR) * tick
                same(fill["price"], implied_bid, "CONDITIONAL_RELEASE_PRICE_PROXY")
                if number(fill["quantity"]) > 0 and implied_bid < number(
                    orders[fill["order_id"]]["price"]
                ):
                    raise ValueError("RELEASE_FILL_BELOW_LIMIT")
        for evaluation in evaluations:
            before = number(evaluation["available_budget_before"])
            if before < 0 or before > number(envelope["release_depth"]):
                raise ValueError("INVALID_RELEASE_DEPTH_BUDGET")
            executed = sum(
                (
                    number(row["quantity"])
                    for row in fills
                    if row["order_id"] == evaluation["order_id"] and row["source"] == "BOOK"
                ),
                D(0),
            )
            if executed > before + EPSILON:
                raise ValueError("RELEASE_EXCEEDS_EVALUATED_DEPTH")
    return {
        "selected_fills": len(selected),
        "raw_source_ids_found": len(wanted_rows),
        "queue_cumulative_checks": queue_checks,
        "archives_read_once": scanned,
        "release_book_support": "RAW_EVENT_ANCHOR_ONLY; historical depth remains parameterized",
    }


def audit(config_path, folder, *, sample=100):
    if sample < 100:
        raise ValueError("MINIMUM_ORDINARY_SAMPLE_100")
    config = json.loads(config_path.read_text())
    scoreboard = json.loads((folder / "scoreboard.json").read_text())
    selected_profile = next(
        item
        for item in config["profiles"]
        if item["profile"]["name"] == scoreboard["EXECUTION_PROFILE"]
    )
    profile = selected_profile["profile"]
    audit_path = folder / "execution-audit.jsonl"
    if not audit_path.exists():
        audit_path = folder / "execution-audit.json"
    trace_binding_path = folder / "audit-manifest.json"
    if trace_binding_path.exists():
        binding = json.loads(trace_binding_path.read_text())
        if audit_path.stat().st_size != binding["bytes"] or digest(audit_path) != binding["sha256"]:
            raise ValueError("DURABLE_TRACE_BINDING_MISMATCH")
    ledger = reconstruct(iter_rows(audit_path), profile)
    with localcontext() as context:
        context.prec = 128
        total_net = sum((D(row["net_profit"]) for row in ledger["settlements"]), D(0))
    same(scoreboard["NET_PNL_FIXED_100"], total_net, "TOTAL_NET_PNL")
    for key, value in (
        ("OPERATING_FINAL", ledger["cash"]),
        ("RESERVE_FINAL", ledger["reserve"]),
        ("OPEN_INVENTORY", ledger["inventory"]),
        ("DUST_BASE", ledger["dust"]),
        ("DUST_COST_BASIS", ledger["dust_basis"]),
        ("TOTAL_FEES", ledger["fees"]),
        ("RESERVE_FUNDING", ledger["funding"]),
        ("RESERVE_CONSUMPTION", ledger["consumption"]),
    ):
        same(scoreboard[key], value, key)
    ordinary = [row for row in ledger["settlements"] if not row["release"]]
    releases = [row for row in ledger["settlements"] if row["release"]]
    same(scoreboard["FULLY_FILLED_CYCLES"], len(ordinary), "FULL_CYCLE_COUNT")
    same(
        scoreboard["NET_POSITIVE_CYCLES"],
        sum(D(row["net_profit"]) > 0 for row in ordinary),
        "POSITIVE_CYCLES",
    )
    chosen = {order for row in ordinary[:sample] + releases for order in row["order_ids"]}
    release_orders = {key for key, order in ledger["orders"].items() if order["release"]}
    chosen |= release_orders
    signals_path = folder / "release-signals.json"
    signals = json.loads(signals_path.read_text()) if signals_path.exists() else []
    for signal in signals:
        signal_us = signal["event"] // 4096
        closing = next((row for row in ledger["settlements"] if row["time_us"] >= signal_us), None)
        chosen.update(closing["order_ids"] if closing else ledger["open_cycle_orders"])
    history_path = Path(config["history_manifest"])
    if digest(history_path) != config["history_manifest_sha256"]:
        raise ValueError("HISTORY_MANIFEST_HASH_MISMATCH")
    support = audit_raw_support(
        json.loads(history_path.read_text()),
        ledger["orders"],
        ledger["fills"],
        chosen,
        ledger["release_evaluations"],
        selected_profile["envelope"],
        config["rules"],
    )
    pending = [
        key
        for key in release_orders
        if key not in ledger["terminal"]
        and ledger["orders"][key]["audit_filled"] < number(ledger["orders"][key]["quantity"])
    ]
    autopsy = []
    for signal_id, signal in enumerate(signals):
        settlement = next(
            (row for row in ledger["settlements"] if row["release_signal_id"] == signal_id), None
        )
        autopsy.append(
            {
                "signal_id": signal_id,
                "signal_time_us": signal["event"] // 4096,
                "theoretical_loss_usdt": signal["loss_usdt"],
                "theoretical_loss_bps_operating_bank": signal["loss_bps"],
                "signal_operating_bank": signal["operating_bank_before"],
                "outcome": (
                    "EXECUTED_RELEASE" if settlement["release"] else "ORDINARY_EXIT_WON_RACE"
                )
                if settlement
                else "UNSETTLED_AT_CUTOFF",
                "independent_settlement": settlement,
            }
        )
    return {
        "schema": "b10-independent-execution-audit-v1",
        "status": "PASS_CONDITIONAL",
        "scope": "ALL_FINANCIAL_FILLS_AND_SETTLEMENTS_PLUS_FIRST_100_ORDINARY_AND_ALL_RELEASES",
        "config_sha256": digest(config_path),
        "audit_sha256": digest(audit_path),
        "scoreboard_sha256": digest(folder / "scoreboard.json"),
        "ordinary_total": len(ordinary),
        "ordinary_audited_raw": min(sample, len(ordinary)),
        "release_settlements": len(releases),
        "release_signals": len(signals),
        "release_orders": len(release_orders),
        "release_book_evaluations": len(ledger["release_evaluations"]),
        "release_autopsy": autopsy,
        "pending_or_uninstrumented_release_orders": pending,
        "raw_support": support,
        "limitations": [
            "BOOK fills are conditional modeled liquidity, never verified historical L2.",
            "Theoretical strategy predicates require the separate canonical bridge review.",
            "Unfilled pending release orders remain open, not successful exits.",
        ],
    }


def audit_m014(config_path, folder, *, sample=100):
    """Hash-bound independent M014 audit; no simulator or strategy imports."""
    if sample < 100:
        raise ValueError("MINIMUM_ORDINARY_SAMPLE_100")
    config = json.loads(config_path.read_text(encoding="utf-8"))
    score = json.loads((folder / "scoreboard.json").read_text(encoding="utf-8"))
    if score.get("MODEL_ID") != "M014" or score.get("CAPITAL_MODE") != "COMPOUNDING":
        raise ValueError("M014_IDENTITY_OR_CAPITAL_MODE_MISMATCH")
    if score.get("RUN_STATUS") != "COMPLETE":
        raise ValueError("M014_RUN_NOT_COMPLETE")
    run_manifest = json.loads((folder / "run-manifest.json").read_text(encoding="utf-8"))
    identity_pairs = {
        "model_id": "MODEL_ID",
        "model_hash": "MODEL_HASH",
        "run_hash": "RUN_ID",
        "capital_mode": "CAPITAL_MODE",
    }
    for manifest_key, score_key in identity_pairs.items():
        if run_manifest.get(manifest_key) != score.get(score_key):
            raise ValueError(f"M014_{manifest_key.upper()}_IDENTITY_MISMATCH")
    if run_manifest.get("profile_config_sha256") != digest(config_path):
        raise ValueError("M014_PROFILE_CONFIG_HASH_MISMATCH")
    checkpoint = folder / "checkpoint.json"
    checkpoint_payload = json.loads(checkpoint.read_text(encoding="utf-8"))
    if digest(checkpoint) != score.get("CHECKPOINT_SHA256"):
        raise ValueError("M014_CHECKPOINT_BINDING_MISMATCH")
    audit_path = folder / "execution-audit.jsonl"
    if not audit_path.exists():
        audit_path = folder / "execution-audit.json"
    binding = score.get("AUDIT_PREFIX")
    manifest = folder / "audit-manifest.json"
    if manifest.exists():
        binding = json.loads(manifest.read_text(encoding="utf-8"))
    if not isinstance(binding, dict) or audit_path.stat().st_size != int(binding["bytes"]):
        raise ValueError("M014_AUDIT_SIZE_BINDING_MISMATCH")
    checkpoint_audit = checkpoint_payload.get("audit")
    if checkpoint_audit != binding:
        raise ValueError("M014_CHECKPOINT_AUDIT_BINDING_MISMATCH")
    replay_payload = checkpoint_payload.get("replay", {}).get("payload", {})
    checkpoint_identity = replay_payload.get("state", {}).get("identity")
    if checkpoint_identity != run_manifest:
        raise ValueError("M014_CHECKPOINT_IDENTITY_MISMATCH")
    if digest(audit_path) != binding["sha256"]:
        raise ValueError("M014_AUDIT_HASH_BINDING_MISMATCH")
    expected_config = config.get("expected_config_sha256") or config.get("config_sha256")
    if expected_config and digest(config_path) != expected_config:
        raise ValueError("M014_CONFIG_HASH_MISMATCH")
    selected_profile = next(
        item for item in config["profiles"]
        if item["profile"]["name"] == "B_REALISTIC_CONSERVATIVE"
    )
    profile, envelope = selected_profile["profile"], selected_profile["envelope"]
    engine_state = replay_payload["execution"]["state"]
    checkpoint_profile = engine_state["profile"]["fields"]
    for key, value in profile.items():
        if key in ("name", "evidence_sha256"):
            if checkpoint_profile[key] != value:
                raise ValueError("M014_CHECKPOINT_PROFILE_MISMATCH")
        else:
            same(checkpoint_profile[key], value, "M014_PROFILE_" + key)
    for key, value in envelope.items():
        if key == "evidence_sha256":
            if replay_payload["envelope"][key] != value:
                raise ValueError("M014_ENVELOPE_EVIDENCE_MISMATCH")
        else:
            same(replay_payload["envelope"][key], value, "M014_ENVELOPE_" + key)
    ledger = reconstruct(iter_rows(audit_path), profile, owner_reserve=True)
    ordinary = [row for row in ledger["settlements"] if not row["release"]]
    releases = [row for row in ledger["settlements"] if row["release"]]
    with localcontext() as context:
        context.prec = 128
        operating = ledger["cash"] + ledger["basis"] + ledger["dust_basis"]
        total_net = operating + ledger["reserve"] - D("110")
    reconcile = {
        "OPERATING_CAPITAL": str(operating),
        "CORE_RESERVE": str(ledger["reserve"]),
        "RESERVE": str(ledger["reserve"]),
        "NET_REALIZED_PNL": str(total_net),
        "TOTAL_FEES": str(ledger["fees"]),
        "ORDINARY_CYCLES": len(ordinary),
        "NET_POSITIVE_CYCLES": sum(D(row["net_profit"]) > 0 for row in ordinary),
        "RELEASE_SETTLEMENTS": len(releases),
    }
    score_fields = {
        "OPERATING_BANK": reconcile["OPERATING_CAPITAL"],
        "RESERVE": reconcile["RESERVE"],
        "NET_REALIZED_PNL": reconcile["NET_REALIZED_PNL"],
        "TOTAL_FEES_QUOTE": reconcile["TOTAL_FEES"],
        "FULL_FILL_CYCLES": reconcile["ORDINARY_CYCLES"],
        "RELEASE_FILLED": reconcile["RELEASE_SETTLEMENTS"],
        "NET_POSITIVE_CYCLES": reconcile["NET_POSITIVE_CYCLES"],
        "RESERVE_FUNDING": str(ledger["funding"]),
        "RESERVE_CONSUMPTION": str(ledger["consumption"]),
    }
    for name, expected in score_fields.items():
        if name not in score:
            raise ValueError(f"M014_SCORE_FIELD_MISSING:{name}")
        same(score[name], expected, name)
    same(engine_state["cash"], ledger["cash"], "CHECKPOINT_CASH")
    same(engine_state["inventory"], ledger["inventory"], "CHECKPOINT_INVENTORY")
    same(engine_state["cost"], ledger["basis"], "CHECKPOINT_COST")
    bids = engine_state["bids"]
    bid = number(bids[0][0]) if bids else D(0)
    with localcontext() as context:
        context.prec = 128
        marked = ledger["cash"] + ledger["reserve"] + (ledger["inventory"] + ledger["dust"]) * bid
        same(score["TOTAL_EQUITY"], marked, "TOTAL_EQUITY")
    selected = {order for row in ordinary[:sample] + releases for order in row["order_ids"]}
    selected.update(key for key, order in ledger["orders"].items() if order["release"])
    selected.update(ledger["open_cycle_orders"])
    support = {"status": "NOT_RUN", "reason": "M014_HISTORY_SUPPORT_NOT_BOUND"}
    history_path = config.get("history_manifest")
    if history_path:
        if (
            config.get("history_manifest_sha256")
            and digest(Path(history_path)) != config["history_manifest_sha256"]
        ):
            raise ValueError("M014_HISTORY_MANIFEST_HASH_MISMATCH")
        history = json.loads(Path(history_path).read_text(encoding="utf-8"))
        archives = history.get("archives", [])
        filtered = []
        for archive in archives:
            day = datetime.fromisoformat(archive["utc_date"]).date()
            if day >= datetime(2026, 1, 1).date() and day < datetime(2026, 1, 8).date():
                filtered.append(archive)
        if any(not ("2026-01-01" <= item["utc_date"] < "2026-01-08") for item in filtered):
            raise ValueError("M014_HISTORY_SUPPORT_OUTSIDE_FIRST_WEEK")
        history["archives"] = filtered
        support = audit_raw_support(
            history,
            ledger["orders"],
            ledger["fills"],
            selected,
            ledger["release_evaluations"],
            envelope,
            config.get("rules", []),
        )
        support["status"] = "VALIDATED"
    if support.get("status") != "VALIDATED":
        raise ValueError("M014_RAW_SUPPORT_NOT_VALIDATED")
    return {
        "schema": "m014-independent-execution-audit-v1",
        "status": "PASS_CONDITIONAL",
        "scope": "ALL_LEDGER_PLUS_FIRST_100_ORDINARY_AND_ALL_RELEASES",
        "config_sha256": digest(config_path),
        "scoreboard_sha256": digest(folder / "scoreboard.json"),
        "checkpoint_sha256": digest(checkpoint),
        "audit_sha256": digest(audit_path),
        "reconcile": reconcile,
        "ordinary_audited_raw": min(sample, len(ordinary)),
        "ordinary_total": len(ordinary),
        "release_settlements": len(releases),
        "raw_support": support,
        "limitations": ["PASS_CONDITIONAL is an audit status, not strategy PASS."]
        + ([f"Only {len(ordinary)} ordinary cycles available; fewer than 100."]
           if len(ordinary) < 100 else []),
    }


def passive_cycle_upper_bound(buy_flow, sell_flow, queue):
    """Necessary-volume relaxation, not a replay: at most one carry-in serial cycle."""
    with localcontext() as context:
        context.prec = 128
        buy_flow, sell_flow, queue = D(buy_flow), D(sell_flow), D(queue)
        if min(buy_flow, sell_flow) < 0 or queue <= 0:
            raise ValueError("INVALID_PASSIVE_CAPACITY_INPUT")
        # Ignore own size, prices, latency, ordering and profit: all loosen the bound.
        return 1 + int(min(buy_flow, sell_flow) // queue)


def audit_week1_passive_capacity(config_path):
    """Read only the seven authorized raw ZIPs, preserving the frozen profile."""
    config = json.loads(config_path.read_bytes())
    history_path = Path(config["history_manifest"])
    if digest(history_path) != config["history_manifest_sha256"]:
        raise ValueError("CAPACITY_HISTORY_HASH_MISMATCH")
    history = json.loads(history_path.read_bytes())
    if history["symbol"] != "USDCUSDT" or history["kind"] != "trades":
        raise ValueError("CAPACITY_USDCUSDT_TRADES_REQUIRED")
    profile = next(item["profile"] for item in config["profiles"]
                   if item["profile"]["name"] == "B_REALISTIC_CONSERVATIVE")
    queue = D(profile["queue_ahead"])
    archives = sorted((item for item in history["archives"]
                       if "2026-01-01" <= item["utc_date"] < "2026-01-08"),
                      key=lambda item: item["utc_date"])
    if [item["utc_date"] for item in archives] != [f"2026-01-{day:02}" for day in range(1, 8)]:
        raise ValueError("CAPACITY_EXACT_SEVEN_DAYS_REQUIRED")
    rows = []
    previous_id = None
    with localcontext() as context:
        context.prec = 128
        for item in archives:
            path = Path(item["local_path"])
            if digest(path) != item["sha256"]:
                raise ValueError("CAPACITY_ZIP_HASH_MISMATCH")
            first = int(datetime.fromisoformat(item["utc_date"]).replace(tzinfo=UTC).timestamp())
            first *= 1_000_000
            buy = sell = D(0)
            count = 0
            with zipfile.ZipFile(path) as archive:
                members = [name for name in archive.namelist() if name.endswith(".csv")]
                if len(members) != 1:
                    raise ValueError("CAPACITY_ONE_CSV_REQUIRED")
                with archive.open(members[0]) as source:
                    for line in source:
                        fields = line.strip().split(b",")
                        if not fields or not fields[0].isdigit():
                            continue
                        trade_id, stamp = int(fields[0]), int(fields[4])
                        if not first <= stamp < first + 86_400_000_000:
                            raise ValueError("CAPACITY_TRADE_OUTSIDE_AUTHORIZED_DAY")
                        if previous_id is not None and trade_id != previous_id + 1:
                            raise ValueError("CAPACITY_RAW_ID_DISCONTINUITY")
                        previous_id = trade_id
                        quantity = D(fields[2].decode())
                        if quantity <= 0 or fields[5].lower() not in (b"true", b"false"):
                            raise ValueError("CAPACITY_INVALID_FLOW")
                        if fields[5].lower() == b"true":
                            buy += quantity
                        else:
                            sell += quantity
                        count += 1
            rows.append({"day": item["utc_date"], "trades": count,
                         "buy_compatible_volume": str(buy), "sell_compatible_volume": str(sell),
                         "total_volume": str(buy + sell),
                         "optimistic_cycle_upper_bound": passive_cycle_upper_bound(
                             buy, sell, queue),
                         "archive": str(path), "archive_bytes": path.stat().st_size,
                         "archive_sha256": item["sha256"]})
    if sum(row["trades"] for row in rows) != 2489204:
        raise ValueError("CAPACITY_WEEK_1_COUNT_MISMATCH")
    return {"schema": "passive-serial-capacity-bound-v1", "status": "VERIFIED_NECESSARY_BOUND",
            "profile_config_sha256": digest(config_path),
            "history_manifest_sha256": digest(history_path), "profile": profile["name"],
            "queue_per_new_order": str(queue), "days": rows,
            "formula": "1 + floor(min(buy_compatible_volume,sell_compatible_volume)/queue)",
            "assumptions": ["One serial lot; new queue per ordinary BUY and SELL order",
                            "Up to one carry-in cycle at each daily boundary",
                            "Ignore own quantity, price, latency, sequence, fees and net profit",
                            "Releases excluded; no trade-flow reuse or fictitious queue priority"],
            "minimum_500_possible_in_all_days": all(
                row["optimistic_cycle_upper_bound"] >= 500 for row in rows),
            "scope": "FROZEN_PROFILE_MAKER_MAKER_ONLY; not a universal market impossibility",
            "execution_semantics": "No economic replay, strategy tuning or week2 access"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--profile-dir", type=Path)
    parser.add_argument("--capacity-week1", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.capacity_week1:
            result = audit_week1_passive_capacity(args.config)
        elif args.profile_dir is not None:
            result = audit(args.config, args.profile_dir)
        else:
            raise ValueError("PROFILE_DIR_REQUIRED_UNLESS_CAPACITY_WEEK1")
    except Exception as exc:
        result = {
            "schema": "b10-independent-execution-audit-v1",
            "status": "FAIL",
            "failure": f"{type(exc).__name__}: {exc}",
        }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    raise SystemExit(
        0 if result["status"] in ("PASS_CONDITIONAL", "VERIFIED_NECESSARY_BOUND") else 1
    )
