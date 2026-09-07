"""Read-only fixed-event ledger precision audit; never reruns strategy decisions."""

from __future__ import annotations

import argparse
import hashlib
import json
from decimal import ROUND_DOWN, Context, Decimal, Inexact
from pathlib import Path

D = Decimal


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("checkpoint", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    raw = args.checkpoint.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    saved = json.loads(raw)
    del raw
    payload = saved["payload"]
    state, runtime = payload["state"], payload["reserve"]
    events = sorted([*state["cycles"], *state["release_closures"]], key=lambda c: c["exit_event"])
    release_events = {row["event"] for row in runtime["releases"]}
    contexts = [Context(prec=28), Context(prec=128)]
    cash = [D(100), D(100)]
    reserve = [D(5), D(5)]
    skim_rate = D(runtime["config"]["skim_rate"])
    counts = {
        "inexact_settlement_28": 0,
        "inexact_settlement_128": 0,
        "different_skim": 0,
        "different_cash": 0,
        "different_reserve": 0,
        "affordable_quantity_rounding_difference_same_cash": 0,
    }
    samples: list[dict] = []
    first_inexact = None
    for index, cycle in enumerate(events):
        q, low, high = (D(cycle[k]) for k in ("quantity", "low", "high"))
        buy_fee, sell_fee = (D(cycle[k]) for k in ("buy_fee_quote", "sell_fee_quote"))
        affordable = []
        # Isolate arithmetic rounding from policy/cash-path differences. Zero-fee
        # canonical scenario has quantity_step 0.01; retain that explicit assumption.
        for context in contexts:
            units = context.divide(context.divide(cash[0], low), D("0.01"))
            affordable.append(
                context.multiply(units.to_integral_value(rounding=ROUND_DOWN), D("0.01"))
            )
        if affordable[0] != affordable[1]:
            counts["affordable_quantity_rounding_difference_same_cash"] += 1
        skims = []
        inexact = []
        for j, context in enumerate(contexts):
            context.clear_flags()
            cost = context.add(context.multiply(q, low), buy_fee)
            net = context.subtract(context.multiply(q, high), sell_fee)
            cash[j] = context.subtract(cash[j], cost)
            cash[j] = context.add(cash[j], net)
            if cycle["exit_event"] in release_events:
                deficit = context.subtract(cost, net)
                reserve[j] = context.subtract(reserve[j], deficit)
                cash[j] = context.add(cash[j], deficit)
                skim = D(0)
            else:
                profit = context.subtract(net, cost)
                skim = context.multiply(max(D(0), profit), skim_rate)
                cash[j] = context.subtract(cash[j], skim)
                reserve[j] = context.add(reserve[j], skim)
            skims.append(skim)
            inexact.append(context.flags[Inexact])
            counts[f"inexact_settlement_{context.prec}"] += int(context.flags[Inexact])
        if inexact[0] and first_inexact is None:
            first_inexact = {
                "index": index,
                "cycle": cycle,
                "cash_28": str(cash[0]),
                "cash_128": str(cash[1]),
                "reserve_28": str(reserve[0]),
                "reserve_128": str(reserve[1]),
                "skim_28": str(skims[0]),
                "skim_128": str(skims[1]),
            }
        differences = {
            "skim": skims[0] != skims[1],
            "cash": cash[0] != cash[1],
            "reserve": reserve[0] != reserve[1],
        }
        for key, differs in differences.items():
            counts[f"different_{key}"] += int(differs)
        if any(differences.values()) and len(samples) < 5:
            samples.append(
                {
                    "index": index,
                    "cycle": cycle,
                    "cash_28": str(cash[0]),
                    "cash_128": str(cash[1]),
                    "reserve_28": str(reserve[0]),
                    "reserve_128": str(reserve[1]),
                    "skim_28": str(skims[0]),
                    "skim_128": str(skims[1]),
                }
            )
    if state["entry_event"] is not None:
        for j, context in enumerate(contexts):
            cash[j] = context.subtract(cash[j], D(state["inventory_cost"]))
    exact = contexts[1]
    out = {
        "classification": "TECHNICAL_FIXED_EVENT_PRECISION_AUDIT_NOT_STRATEGY_REPLAY",
        "source": str(args.checkpoint),
        "source_sha256": digest,
        "source_checkpoint_payload_sha256": saved["sha256"],
        "source_identity": payload["identity"],
        "cursor": payload["cursor"],
        "events_audited": len(events),
        "contexts": [28, 128],
        "counts": counts,
        "first_inexact": first_inexact,
        "first_divergences": samples,
        "checkpoint_cash": state["cash"],
        "checkpoint_reserve": runtime["reserve"],
        "reconstructed_cash_28": str(cash[0]),
        "reconstructed_cash_128": str(cash[1]),
        "reconstructed_reserve_28": str(reserve[0]),
        "reconstructed_reserve_128": str(reserve[1]),
        "cash_28_matches_checkpoint": cash[0] == D(state["cash"]),
        "reserve_28_matches_checkpoint": reserve[0] == D(runtime["reserve"]),
        "cash_difference_28_minus_128": str(exact.subtract(cash[0], cash[1])),
        "reserve_difference_28_minus_128": str(exact.subtract(reserve[0], reserve[1])),
        "limitations": (
            "Recorded quantities and decision path held fixed; not a high-precision policy "
            "replay. Open acquisition uses recorded cost. Quantity arithmetic comparison "
            "assumes canonical zero fees and step 0.01."
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                k: v
                for k, v in out.items()
                if k not in {"source_identity", "first_divergences", "first_inexact"}
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
