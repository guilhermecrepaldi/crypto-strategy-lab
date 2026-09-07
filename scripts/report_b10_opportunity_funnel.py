"""Post-run execution funnel with honest historical-reference denominators.

Consumer: B10-reality report / Q1. Does not rerun a strategy or allocate actual
fills to historical opportunities using an invented correspondence.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from decimal import Decimal, localcontext
from pathlib import Path


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def summarize(rows, reference_cycles, scoreboard):
    if reference_cycles != 3580880:
        raise ValueError("FROZEN_REFERENCE_COUNT_MISMATCH")
    orders = {}
    full_cycles = positive_cycles = releases = 0
    for row in rows:
        kind = row["kind"]
        if kind == "SUBMIT":
            orders[row["order_id"]] = {
                "side": row["side"],
                "release": row["release"],
                "quantity": Decimal(str(row["quantity"])),
                "filled": Decimal(0),
                "active": False,
                "compatible_flow": False,
                "queue_cleared": False,
            }
        elif kind == "ORDER_ACTIVE":
            orders[row["order_id"]]["active"] = True
        elif kind == "QUEUE_FLOW":
            order = orders[row["order_id"]]
            order["compatible_flow"] = True
            order["queue_cleared"] |= Decimal(row["queue_after"]) == 0
        elif kind == "FILL":
            with localcontext() as context:
                context.prec = 128
                orders[row["order_id"]]["filled"] += Decimal(row["quantity"])
        elif kind == "SETTLEMENT":
            if row["release"]:
                releases += 1
            else:
                full_cycles += 1
                positive_cycles += Decimal(row["net_profit"]) > 0
    if (
        full_cycles != scoreboard["FULLY_FILLED_CYCLES"]
        or positive_cycles != scoreboard["NET_POSITIVE_CYCLES"]
    ):
        raise ValueError("JOURNAL_SCOREBOARD_CYCLE_MISMATCH")
    funnels = {}
    for side in ("BUY", "SELL"):
        cohort = [
            order for order in orders.values() if order["side"] == side and not order["release"]
        ]
        counts = Counter(submitted=len(cohort))
        for order in cohort:
            counts["active"] += order["active"]
            counts["compatible_flow"] += order["compatible_flow"]
            counts["queue_cleared"] += order["queue_cleared"]
            counts["any_fill"] += order["filled"] > 0
            counts["full_fill"] += order["filled"] == order["quantity"]
            counts["partial_only"] += 0 < order["filled"] < order["quantity"]
        funnels[side] = {"denominator": "NORMAL_SUBMITTED_ORDERS_OF_THIS_SIDE", **dict(counts)}
    with localcontext() as context:
        context.prec = 128
        full_ratio = str(Decimal(full_cycles) / reference_cycles)
        economic_ratio = str(Decimal(positive_cycles) / reference_cycles)
    return {
        "schema": "b10-opportunity-funnel-v1",
        "strategy": "B10_FROZEN",
        "execution_profile": scoreboard["EXECUTION_PROFILE"],
        "original_reference_cycles": reference_cycles,
        "Q1_aggregate_full_fill_cycles": full_cycles,
        "net_positive_cycles": positive_cycles,
        "aggregate_reality_retention_ratio": full_ratio,
        "aggregate_economic_retention_ratio": economic_ratio,
        "ratio_semantics": (
            "PRODUCTIVITY_RATIO_TO_REFERENCE_COUNT; NOT AN IDENTIFIED SURVIVOR_SUBSET"
        ),
        "original_opportunity_mapping": {
            "status": "NOT_IDENTIFIED",
            "original_trade_at_price": None,
            "original_compatible_aggressor_flow": None,
            "original_order_active_in_time": None,
            "original_queue_cleared": None,
            "original_buy_full": None,
            "original_sell_full": None,
            "original_net_positive": None,
            "reason": (
                "Delayed fills alter serial inventory, selector/release path and later orders. "
                "Count ratios alone do not identify which original cycles survived."
            ),
            "reference_event_list": (
                "Preserved original replay.json.gz; endpoints do not choose a unique "
                "execution-to-reference correspondence."
            ),
            "possible_future_diagnostic": (
                "Endpoint or interval matching with explicit deterministic ties could be "
                "reported retrospectively; it is a chosen relation, not causal survival."
            ),
        },
        "actual_order_funnels": funnels,
        "release_settlements": releases,
        "cohort_caveats": [
            (
                "BUY and SELL have separate cohorts; cancellation/continuation can create "
                "several orders for one serial lot."
            ),
            (
                "QUEUE_FLOW establishes modeled compatibility; raw evidence is checked "
                "by the separate independent audit."
            ),
            (
                "Partial-only means an order never reached its full quantity, "
                "not every order that temporarily partially filled."
            ),
            (
                "Trade-level misses are not disjoint original-cycle losses "
                "and must not be subtracted from 3580880."
            ),
            (
                "If productivity ratio exceeds 1, report it; "
                "do not cap it or label it survival probability."
            ),
        ],
    }


def report(reference_path, folder):
    reference = json.loads(reference_path.read_text())
    board_path = folder / "scoreboard.json"
    board = json.loads(board_path.read_text())
    if board.get("STATUS") != "COMPLETED_PARAMETERIZED_EXECUTION_REPLAY":
        raise ValueError("COMPLETE_PROFILE_REQUIRED")
    trace = folder / "execution-audit.jsonl"
    binding = json.loads((folder / "audit-manifest.json").read_text())
    trace_sha = sha(trace)
    if trace_sha != binding["sha256"] or trace.stat().st_size != binding["bytes"]:
        raise ValueError("TRACE_BINDING_MISMATCH")
    with trace.open(encoding="utf-8") as stream:
        result = summarize(
            (json.loads(line) for line in stream if line.strip()),
            reference["completed_reference"]["cycles"],
            board,
        )
    result["inputs"] = {
        "reference_sha256": sha(reference_path),
        "scoreboard_sha256": sha(board_path),
        "journal_sha256": trace_sha,
    }
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--reference", type=Path, default=Path("reports/usdcusdt/B10-reference-reconciliation.json")
    )
    parser.add_argument("--profile-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = report(args.reference, args.profile_dir)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
