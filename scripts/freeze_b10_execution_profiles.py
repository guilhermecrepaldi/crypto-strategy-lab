"""Deterministic conditional-pilot profile freeze; never consumes strategy results."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from datetime import UTC, datetime
from decimal import ROUND_CEILING, Decimal
from pathlib import Path

from crypto_strategy_lab.microstructure.public_calibration import weighted_quantiles
from crypto_strategy_lab.microstructure.serial_replay import (
    USDCUSDT_FINE_GRID_OBSERVED_FROM,
    _datetime_to_micros,
)

D = Decimal
START = "2026-01-01T00:00:00+00:00"
END = "2026-09-05T23:59:59.783644+00:00"
IDENTITY = "097abdab8225038b091cb721bdd36bedb8a636c94bed1c87120adc0c9e10953a"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def choose_joint(rows: list[dict], percentile: int) -> dict:
    # One declared queue-difficulty statistic; retain every other coordinate
    # of that same observed book state instead of splicing marginal extremes.
    ordered = sorted(
        rows,
        key=lambda row: (
            max(D(row["bid_best_qty"]), D(row["ask_best_qty"])),
            row["start_monotonic_ns"],
        ),
    )
    target = D(sum(row["duration_ns"] for row in ordered)) * percentile / 100
    elapsed = 0
    for row in ordered:
        elapsed += row["duration_ns"]
        if elapsed >= target:
            return row
    raise ValueError("NO_POSITIVE_JOINT_DURATION")


def freeze(calibration: Path, output: Path) -> dict:
    if output.exists():
        raise ValueError("PROFILE_FREEZE_IMMUTABLE; preserve existing identity")
    manifest_path = calibration / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest["status"] != "CAPTURED" or manifest["failure"] is not None:
        raise ValueError("COMPLETE_PUBLIC_CAPTURE_REQUIRED")
    for record in manifest["files"]:
        if sha(Path(record["path"])) != record["sha256"]:
            raise ValueError("CALIBRATION_HASH_MISMATCH")
    counts = manifest["counts"]
    if any(
        counts.get(key, 0)
        for key in (
            "trade_id_discontinuities",
            "bookticker_sequence_regressions",
            "queued_gap_records_dropped",
        )
    ):
        raise ValueError("PILOT_DATA_INTEGRITY_GATE")
    rows = json.loads((calibration / "joint-book-samples.json").read_text(encoding="utf-8"))
    if not rows or counts.get("trade", 0) == 0:
        raise ValueError("TRADES_AND_SYNCHRONIZED_BOOK_REQUIRED")
    audit = Path("reports/usdcusdt/B10-data-manifest-audit.json")
    raw_audit = json.loads(audit.read_text(encoding="utf-8"))
    fresh = raw_audit["fresh_aggregate"]
    if not raw_audit["coverage_exact"] or any(
        fresh[key] != raw_audit["archive_count"]
        for key in (
            "manifest_hash_match_count",
            "manifest_size_match_count",
            "sidecar_hash_match_count",
            "zip_test_ok_count",
        )
    ):
        raise ValueError("FRESH_PHYSICAL_ARCHIVE_AUDIT_REQUIRED")
    authority = Path("artifacts/binance/usdcusdt-execution-rules.json")
    rule_manifest = json.loads(authority.read_text(encoding="utf-8"))
    observed = next(
        row["payload"]
        for row in rule_manifest["current_observations"]
        if row["endpoint"] == "exchangeInfo"
    )
    symbol = observed["symbols"][0]
    filters = {row["filterType"]: row for row in symbol["filters"]}
    price, lot, notional = filters["PRICE_FILTER"], filters["LOT_SIZE"], filters["NOTIONAL"]
    orders = next(
        row
        for row in observed["rateLimits"]
        if row["rateLimitType"] == "ORDERS" and row["interval"] == "SECOND"
    )
    common_rule = {
        "tick_size": price["tickSize"],
        "step_size": lot["stepSize"],
        "min_quantity": lot["minQty"],
        "max_quantity": lot["maxQty"],
        "min_notional": notional["minNotional"],
        "max_notional": notional["maxNotional"],
        "min_price": price["minPrice"],
        "max_price": price["maxPrice"],
        "evidence_sha256": sha(authority),
        "orders_per_window": orders["limit"],
        "window_us": orders["intervalNum"] * 1_000_000,
    }
    start_us = _datetime_to_micros(datetime.fromisoformat(START))
    end_us = _datetime_to_micros(datetime.fromisoformat(END))
    transition_us = _datetime_to_micros(USDCUSDT_FINE_GRID_OBSERVED_FROM)
    rules = [
        {
            "start_us": start_us,
            "end_us": transition_us,
            "rule": {**common_rule, "tick_size": "0.0001"},
        },
        {"start_us": transition_us, "end_us": end_us, "rule": common_rule},
    ]
    refresh = weighted_quantiles(
        [D(row["duration_ns"]) / 1000 for row in rows], [row["duration_ns"] for row in rows]
    )["p50"]
    refresh_us = max(1, int(D(refresh).to_integral_value(rounding=ROUND_CEILING)))
    result_profiles = []
    for label, percentile in (
        ("A_OBSERVED_BEST_SUPPORTED", 10),
        ("B_REALISTIC_CONSERVATIVE", 50),
        ("C_ADVERSARIAL_PLAUSIBLE", 90),
    ):
        row = choose_joint(rows, percentile)
        rtt_key = {10: "p10", 50: "p50", 90: "p99"}[percentile]
        measured_rtt = D(manifest["rest_rtt_us"][rtt_key])
        latency = max(measured_rtt, D(row["ws_delay_offset_adjusted_us"]), D(1))
        latency_us = max(1, int(latency.to_integral_value(rounding=ROUND_CEILING)))
        result_profiles.append(
            {
                "profile": {
                    "name": label,
                    "evidence_sha256": sha(manifest_path),
                    "latency_us": latency_us,
                    "cancel_latency_us": latency_us,
                    "queue_ahead": str(max(D(row["bid_best_qty"]), D(row["ask_best_qty"]))),
                    "maker_fee": "0",
                    "taker_fee": "0",
                },
                "envelope": {
                    "evidence_sha256": sha(manifest_path),
                    "half_spread": str(D(row["spread"]) / 2),
                    "release_slippage": "0",
                    "release_depth": row["bid_best_qty"],
                    "release_limit_distance": row["spread"],
                    "depth_refresh_us": refresh_us,
                },
                "evidence_class": "CONDITIONAL_PILOT_PARAMETERIZED_EXECUTION_ENVELOPE",
                "joint_sample": row,
                "difficulty_percentile": percentile,
                "latency_sample_quantile": rtt_key,
                "latency_tail_evidence": "DESCRIPTIVE_SAMPLE_ONLY; p99 of12 is sample maximum",
            }
        )
    fee_counterfactual = copy.deepcopy(result_profiles[1])
    fee_counterfactual["profile"].update(
        name="B_FEE10_PROMOTION_ABSENT", maker_fee="0.001", taker_fee="0.001"
    )
    fee_counterfactual["fee_evidence"] = (
        "Official regular10bps perleg counterfactual; NOT proven historical pair fee"
    )
    result_profiles.append(fee_counterfactual)
    history = Path("data/manifests/usdcusdt-trades-2025-2026.json")
    result = {
        "schema": "b10-binance-reality-profile-freeze-v1",
        "frozen_at": datetime.now(UTC).isoformat(),
        "strategy": "B10_FROZEN",
        "execution_profile": "BINANCE_REALITY_V1",
        "execution_authorized": False,
        "gate": "AWAITING_INDEPENDENT_IMPLEMENTATION_REVIEW_AND_PUBLISHED_SHA",
        "b10_artifact_identity": IDENTITY,
        "start": START,
        "end_exclusive": END,
        "history_manifest": str(history),
        "history_manifest_sha256": sha(history),
        "physical_archive_audit": str(audit),
        "physical_archive_audit_sha256": sha(audit),
        "calibration_manifest": str(manifest_path),
        "calibration_manifest_sha256": sha(manifest_path),
        "official_rule_manifest": str(authority),
        "official_rule_manifest_sha256": sha(authority),
        "profiles": result_profiles,
        "rules": rules,
        "profile_D": {
            "name": "D_PEG_STRESS",
            "status": "NOT_CALIBRATED",
            "verdict": "INCONCLUSIVE_EXECUTION_DATA",
            "reason": "No observed peg-stress joint regime; cannot invent calibration.",
        },
        "fee_sensitivities": [
            {
                "maker_fee": "0.001",
                "taker_fee": "0.001",
                "status": "PRE_REGISTERED_B_FEE10_PROMOTION_ABSENT_NOT_EXECUTED",
            }
        ],
        "assumptions": {
            "queue": (
                "Max of bid/ask displayed best depth of same observed joint state; "
                "not known queue rank."
            ),
            "latency": (
                "Total signal-to-activation proxy=max(RTT p10/p50/p99 for A/B/C, "
                "joint clock-adjusted WS delay). Private components/ACK unknown; "
                "p99 of12 requests is descriptive samplemax, not calibrated stress tail."
            ),
            "depth_refresh": (
                "Time-weighted median state residence as parameterized replenishment cadence; "
                "not observed historical refill."
            ),
            "book": (
                "INFERRED_TRADE_SIDE_BBO: seller-aggressor print proxies bid; buyer-aggressor "
                "print proxies ask. Spread rounded to historical tick. Not exact historical BBO."
            ),
            "fees": (
                "Pair zero-fee eligibility hypothesis; full-span exact rate and account "
                "special/tax commissions UNKNOWN."
            ),
            "filters": (
                "Current quantity/notional/bounds and order throttle PARAMETERIZED over history, "
                "not OFFICIAL_HISTORICAL_FACT."
            ),
            "tick": (
                "Historical canonical observed transition boundary proxy; exact order-filter "
                "rollout UNKNOWN; resting orders grandfathered."
            ),
            "dynamic_filters": (
                "Historical referencePrice unavailable; dynamic filter and execution range "
                "unknown, not silently represented as modeled."
            ),
            "release": (
                "IOC one observed spread below proxy bid; available best-depth budget; "
                "adverse market move may exceed theoretical10bps."
            ),
            "interpretation": (
                "Conditional pilot envelope only, not empirical historical profitability "
                "or certification of Binance execution."
            ),
        },
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--calibration", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = freeze(args.calibration, args.output)
    print({"profiles": len(result["profiles"]), "execution_authorized": False})
