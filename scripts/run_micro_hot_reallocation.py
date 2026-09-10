"""Fail-closed one-control/one-treatment M027 three-hour runner."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import subprocess
from datetime import UTC, datetime
from decimal import Decimal as D
from pathlib import Path
from typing import Any

from crypto_strategy_lab.microstructure.b10_reality import ExecutionProfile, Trade
from crypto_strategy_lab.microstructure.data import (
    HistoryManifest,
    iter_history,
    select_history_archives,
)
from crypto_strategy_lab.microstructure.recovery_reserve_study import file_sha, write_json
from crypto_strategy_lab.microstructure.serial_replay import _datetime_to_micros
from crypto_strategy_lab.microstructure.tardis_l2 import iter_native_events
from crypto_strategy_lab.ml.model_registry import ModelRegistry, ModelStatus, compute_model_hash
from scripts import run_dynamic_hotline_321 as parent_runner
from scripts.audit_micro_hot_reallocation import independent_micro_hot_audit
from scripts.register_micro_hot_reallocation import OWNER, PREREG, SPEC, registered_model_payload
from scripts.run_b10_reality import typed
from scripts.run_high_uptime_recovery import (
    PROFILE_CONFIG,
    PROFILE_CONFIG_SHA,
    campaign_writer_lock,
    lf_sha,
    published_bytes,
    published_sha,
    validate_review,
)
from scripts.run_l2_monthly_samples import json_hash, verify_published_day_evidence
from scripts.validate_tardis_l2_samples import (
    MANIFEST,
    TRADE_MANIFEST,
    checked_path,
    raw_lines,
    trade_timestamp_matches,
    validate_slice_metadata,
)
from scripts.validate_tardis_l2_samples import OUTPUT as VALIDATION_REPORT

ROOT = Path(__file__).resolve().parents[1]
MODEL_ID = "M027"
SOURCE_DAY = "2026-05-01"
START = datetime(2026, 5, 1, tzinfo=UTC)
END = datetime(2026, 5, 1, 3, tzinfo=UTC)
START_US, END_US = _datetime_to_micros(START), _datetime_to_micros(END)
OWNER_WINDOW = Path("docs/microstructure/OWNER_GATED_REPLAY_WINDOW.md")
REVIEW = Path("reports/usdcusdt/M027-preflight-independent-review.md")
JOURNAL = Path("docs/research/M027_JOURNAL.md")
RULE_EVIDENCE = Path("docs/binance/BINANCE_USDCUSDT_EXECUTION_AUTHORITY.md")
OUTPUT = Path("artifacts/usdcusdt/l2-monthly-samples/M027/OWNER_GATED_3H/PRICE_PRIORITY")
RESULT = Path("reports/usdcusdt/M027-3h-control-treatment-result.json")
SOURCE_PATHS = (
    Path("scripts/run_micro_hot_reallocation.py"),
    Path("scripts/audit_micro_hot_reallocation.py"),
    Path("scripts/register_micro_hot_reallocation.py"),
    Path("src/crypto_strategy_lab/microstructure/micro_hot_reallocation.py"),
    Path("tests/test_micro_hot_reallocation.py"),
    Path("tests/test_run_micro_hot_reallocation.py"),
    *parent_runner.SOURCE_PATHS,
)


def _git_output(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def require_owner_gate(root: Path = ROOT) -> None:
    authority = (root / OWNER_WINDOW).read_text(encoding="utf-8")
    for key, value in {
        "APPROVED_COMPARISON_DAYS": "1",
        "EXTENSION_AUTHORIZED": "false",
        "NEW_REPLAY_AUTHORIZED_NOW": "true",
        "AUTHORIZED_MODEL": MODEL_ID,
        "AUTHORIZED_SCENARIO_COUNT": "2",
    }.items():
        if re.findall(rf"^{key}=(.*)$", authority, flags=re.MULTILINE) != [value]:
            raise ValueError(f"M027_OWNER_GATE_REQUIRED:{key}")


def _assert_unused_output() -> None:
    if OUTPUT.exists() or RESULT.exists():
        raise ValueError("EXISTING_M027_EXPERIMENT_PRESERVED")


def _assert_published_head(sha: str) -> None:
    if _git_output("status", "--porcelain"):
        raise ValueError("PRE_EXECUTION_WORKTREE_NOT_CLEAN")
    if _git_output("branch", "--show-current") != "main":
        raise ValueError("CANONICAL_MAIN_REQUIRED")
    if any(_git_output("rev-parse", ref) != sha for ref in ("HEAD", "origin/main")):
        raise ValueError("M027_REQUIRES_PUBLISHED_HEAD")


def campaign_preflight() -> tuple[str, dict[str, Any], dict[str, Any]]:
    require_owner_gate()
    _assert_unused_output()
    if Path.cwd().resolve() != ROOT.resolve():
        raise ValueError("CANONICAL_REPOSITORY_CWD_REQUIRED")
    sha = published_sha()
    _assert_published_head(sha)
    for path in (
        *SOURCE_PATHS,
        OWNER,
        OWNER_WINDOW,
        SPEC,
        PREREG,
        REVIEW,
        JOURNAL,
        RULE_EVIDENCE,
        MANIFEST,
        VALIDATION_REPORT,
        TRADE_MANIFEST,
        PROFILE_CONFIG,
    ):
        published_bytes(path, sha)
    validate_review(REVIEW, SOURCE_PATHS)
    if file_sha(PROFILE_CONFIG) != PROFILE_CONFIG_SHA:
        raise ValueError("FROZEN_PROFILE_CHANGED")
    expected = registered_model_payload()
    registry = ModelRegistry()
    if registry.current_status(MODEL_ID) != ModelStatus.CREATED:
        raise ValueError("M027_REQUIRES_CREATED_STATUS")
    model = registry.get(MODEL_ID)
    if dict(model.model) != expected or model.model_hash != compute_model_hash(expected):
        raise ValueError("M027_REGISTERED_DESIGN_MISMATCH")
    if registry.current_status("M026") != ModelStatus.INCONCLUSIVE:
        raise ValueError("M027_REQUIRES_PRESERVED_M026")
    return sha, json.loads(MANIFEST.read_bytes()), json.loads(VALIDATION_REPORT.read_bytes())


def bounded_inputs(manifest: dict[str, Any], validation: dict[str, Any]):
    trade_manifest = json.loads(TRADE_MANIFEST.read_bytes())
    entry = next(item for item in manifest["dates"] if item["date"] == SOURCE_DAY)
    checked = next(item for item in validation["days"] if item["date"] == SOURCE_DAY)
    verified = verify_published_day_evidence(entry, checked, trade_manifest)
    slices = tuple(
        sorted(
            (item for item in entry["raw_slices"] if int(item["offset"]) < 180),
            key=lambda item: int(item["offset"]),
        )
    )
    if len(slices) != 18 or tuple(item["offset"] for item in slices) != tuple(range(0, 180, 10)):
        raise ValueError("M027_EXACT_FIRST_18_SLICES_REQUIRED")
    for item in slices:
        validate_slice_metadata(SOURCE_DAY, item)
        path = checked_path(ROOT, item["local_path"], SOURCE_DAY, raw=True)
        if path.stat().st_size != item["bytes"] or file_sha(path) != item["sha256"]:
            raise ValueError("M027_BOUNDED_NATIVE_EVIDENCE_CHANGED")
    history = HistoryManifest.model_validate_json(TRADE_MANIFEST.read_bytes())
    selected = select_history_archives(history, start=START, end_exclusive=END)
    if (
        len(selected) != 1
        or selected[0].cadence != "daily"
        or file_sha(Path(selected[0].local_path)) != selected[0].sha256
    ):
        raise ValueError("M027_CANONICAL_TRADE_ARCHIVE_CHANGED")
    canonical: dict[int, Trade] = {}
    for event in iter_history(history, start=START, end_exclusive=END):
        if event.trade_id in canonical:
            raise ValueError("M027_DUPLICATE_CANONICAL_TRADE")
        canonical[event.trade_id] = Trade(
            _datetime_to_micros(event.timestamp),
            event.trade_id,
            event.price,
            event.quantity,
            event.buyer_is_maker,
        )
    config = json.loads(PROFILE_CONFIG.read_bytes())
    profile = typed(
        ExecutionProfile,
        next(
            row
            for row in config["profiles"]
            if row["profile"]["name"] == "B_REALISTIC_CONSERVATIVE"
        )["profile"],
    )
    evidence = {
        "validation": verified,
        "bounded_slice_count": 18,
        "bounded_slice_offsets": list(range(0, 180, 10)),
        "bounded_slice_sha256": hashlib.sha256(
            "\n".join(f"{item['offset']}:{item['sha256']}" for item in slices).encode()
        ).hexdigest(),
        "canonical_trade_count": len(canonical),
        "canonical_first_trade_id": min(canonical),
        "canonical_last_trade_id": max(canonical),
        "end_us": END_US,
    }
    return profile, canonical, slices, evidence


def bounded_native_events(slices):
    for event in iter_native_events(raw_lines(ROOT, SOURCE_DAY, slices)):
        if not (
            START_US <= event["local_us"] < END_US and START_US <= event["exchange_us"] < END_US
        ):
            raise ValueError("M027_NATIVE_EVENT_ESCAPED_3H_BOUND")
        yield event


def validate_fine_tick(slices, canonical) -> dict[str, Any]:
    from crypto_strategy_lab.microstructure.micro_hot_reallocation import (
        validate_micro_offset_for_tick,
    )

    l2_gcd_units = 0
    trade_gcd_units = 0
    l2_fine_observed = 0
    trade_fine_observed = 0
    l2_prices = 0
    # Read native update prices directly for this gate. Reconstructing and
    # copying the entire book for every update is needlessly quadratic and
    # does not add evidence about price granularity.
    for line in raw_lines(ROOT, SOURCE_DAY, slices):
        payload = json.loads(line.split(" ", 1)[1])["data"]
        if payload.get("e") == "depthUpdate":
            values = [row[0] for row in (*payload.get("b", []), *payload.get("a", []))]
            l2_prices += len(values)
            source = "L2"
        elif payload.get("e") == "trade":
            values = [payload["p"]]
            source = "TRADE"
        else:
            values = []
            source = "OTHER"
        for price in values:
            scaled = D(price) * D(100000)
            if scaled != scaled.to_integral_value():
                raise ValueError("BLOCKED_FINE_TICK_DATASET_NOT_VALIDATED")
            units = int(scaled)
            if source == "L2":
                l2_gcd_units = math.gcd(l2_gcd_units, units)
                l2_fine_observed += units % 10 != 0
            elif source == "TRADE":
                trade_gcd_units = math.gcd(trade_gcd_units, units)
                trade_fine_observed += units % 10 != 0
    if l2_gcd_units != 1 or l2_fine_observed == 0 or not canonical:
        raise ValueError("BLOCKED_FINE_TICK_DATASET_NOT_VALIDATED")
    validate_micro_offset_for_tick(D("0.00001"))
    return {
        "OBSERVED_PRICE_INCREMENT": "0.00001",
        "VALIDATED_TICK_SIZE": "0.00001",
        "L2_OBSERVED_PRICE_INCREMENT": "0.00001",
        "L2_FINE_GRID_PRICES_OBSERVED": l2_fine_observed,
        "TRADE_FINE_GRID_PRICES_OBSERVED": trade_fine_observed,
        "TRADE_PRICE_UNIT_GCD": trade_gcd_units,
        "L2_PRICES_VALIDATED": l2_prices,
        "EXCHANGE_RULE_EVIDENCE": str(RULE_EVIDENCE),
    }


def make_probe(profile, scenario):
    from crypto_strategy_lab.microstructure.micro_hot_reallocation import MicroHotReallocationProbe

    return MicroHotReallocationProbe(
        scenario=scenario,
        start_us=START_US,
        end_us=END_US,
        latency_us=profile.latency_us,
        cancel_latency_us=profile.cancel_latency_us,
    )


def preflight_capital_match(profile, slices) -> dict[str, str]:
    first_book = next(
        event
        for event in bounded_native_events(slices)
        if event["kind"] == "BOOK" and event["sequence_validated"]
    )
    book = {
        "exchange_time_us": first_book["exchange_us"],
        "exchange_upper_us": first_book["exchange_upper_us"],
        "capture_time_us": first_book["local_us"],
        "bids": first_book["bids"],
        "asks": first_book["asks"],
        "known_bid_floor": first_book["known_bid_floor"],
        "known_ask_ceiling": first_book["known_ask_ceiling"],
    }
    engines = {scenario: make_probe(profile, scenario) for scenario in ("CONTROL", "TREATMENT")}
    for engine in engines.values():
        engine.receive_book(book)
    control = engines["CONTROL"].initial_mark
    treatment = engines["TREATMENT"].initial_mark
    error = abs(treatment - control) / control * D(100)
    if error > D("0.01"):
        raise ValueError("M027_INITIAL_CAPITAL_MATCH_GATE_FAILED")
    return {
        "CONTROL_INITIAL_CAPITAL": str(control),
        "TREATMENT_INITIAL_CAPITAL": str(treatment),
        "CAPITAL_MATCH_ERROR_PCT": str(error),
    }


def _write_ledger(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        for row in rows:
            stream.write(json.dumps(row, sort_keys=True, default=str) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def execute_scenario(engine, canonical, slices, identity, evidence, output: Path):
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / "run-manifest.json", {**identity, "evidence": evidence})
    audit_file = output / "execution-audit.jsonl"
    seen: set[int] = set()
    try:
        for event in bounded_native_events(slices):
            if event["kind"] == "BOOK":
                if event["sequence_validated"]:
                    engine.receive_book(
                        {
                            "exchange_time_us": event["exchange_us"],
                            "exchange_upper_us": event["exchange_upper_us"],
                            "capture_time_us": event["local_us"],
                            "bids": event["bids"],
                            "asks": event["asks"],
                            "known_bid_floor": event["known_bid_floor"],
                            "known_ask_ceiling": event["known_ask_ceiling"],
                        }
                    )
                continue
            native = event["data"]
            trade = canonical.get(native["t"])
            if (
                trade is None
                or trade.trade_id in seen
                or D(native["p"]) != trade.price
                or D(native["q"]) != trade.quantity
                or native["m"] is not trade.buyer_maker
                or not trade_timestamp_matches(trade.time_us, native["T"])
            ):
                raise ValueError("M027_CANONICAL_TRADE_BINDING_CHANGED")
            consumed = engine.receive_trade(trade, capture_time_us=event["local_us"])
            if not D(0) <= consumed <= trade.quantity:
                raise ValueError("M027_GLOBAL_TRADE_BUDGET_EXCEEDED")
            seen.add(trade.trade_id)
        if seen != set(canonical):
            raise ValueError("M027_CANONICAL_3H_NOT_FULLY_DELIVERED")
        metrics = engine.finish(time_us=END_US)
        terminal = engine.checkpoint()
        _write_ledger(audit_file, engine.audit)
        write_json(output / "terminal-engine-state.json", terminal)
        audit = independent_micro_hot_audit(
            engine.audit, terminal, metrics, canonical, scenario=identity["scenario"]
        )
        audit.update(terminal_sha256=terminal["sha256"], ledger_sha256=file_sha(audit_file))
        metrics["AUDIT"] = audit["status"]
        metrics["STATUS"] = "COMPLETE"
        result = {
            **identity,
            "RUN_STATUS": "COMPLETE",
            "DISCLAIMER": engine.normalized_label,
            "METRICS": metrics,
            "AUDIT": audit,
        }
        write_json(output / "independent-audit.json", audit)
        write_json(output / "summary.json", result)
        return result
    except BaseException as exc:
        if not audit_file.exists():
            _write_ledger(audit_file, engine.audit)
        write_json(
            output / "failure.json",
            {
                "RUN_STATUS": "INCOMPLETE_PRESERVED",
                "exception_type": type(exc).__name__,
                "error": str(exc),
                "ledger_sha256": file_sha(audit_file),
            },
        )
        raise


def compare(
    control: dict[str, Any], treatment: dict[str, Any], tick: dict[str, Any]
) -> dict[str, Any]:
    c, t = control["METRICS"], treatment["METRICS"]
    c_cycles, t_cycles = int(c["PHYSICAL_CYCLES"]), int(t["PHYSICAL_CYCLES"])
    initial_c, initial_t = D(c["INITIAL_TOTAL"]), D(t["INITIAL_TOTAL"])
    error = abs(initial_t - initial_c) / initial_c * D(100)
    if error > D("0.01"):
        raise ValueError("M027_INITIAL_CAPITAL_MATCH_GATE_FAILED")
    physical_delta = t_cycles - c_cycles
    physical_pct = D(physical_delta) / D(c_cycles) * D(100) if c_cycles else None
    near_gain = (
        int(t["MICRO_HOT_PHYSICAL_CYCLES"])
        + int(t["HOT_RANK1_CYCLES"])
        - int(c["HOT_RANK1_CYCLES"])
    )
    return {
        "MODEL": MODEL_ID,
        "SOURCE_DAY": SOURCE_DAY,
        **tick,
        "COARSE_GRID_SPACING": "0.0001",
        "MICRO_OFFSET": "0.00005",
        "CONTROL_INITIAL_CAPITAL": c["INITIAL_TOTAL"],
        "TREATMENT_INITIAL_CAPITAL": t["INITIAL_TOTAL"],
        "CAPITAL_MATCH_ERROR_PCT": str(error),
        "CONTROL_PHYSICAL_CYCLES": c_cycles,
        "TREATMENT_PHYSICAL_CYCLES": t_cycles,
        "CONTROL_PHYSICAL_CYCLES_PER_HOUR": c["PHYSICAL_CYCLES_PER_HOUR"],
        "TREATMENT_PHYSICAL_CYCLES_PER_HOUR": t["PHYSICAL_CYCLES_PER_HOUR"],
        "PHYSICAL_DELTA": physical_delta,
        "PHYSICAL_DELTA_PCT": (
            str(physical_pct) if physical_pct is not None else "UNDEFINED_CONTROL_ZERO"
        ),
        "CONTROL_SLOT_CYCLES": c["SLOT_EQUIVALENT_CYCLES"],
        "TREATMENT_SLOT_CYCLES": t["SLOT_EQUIVALENT_CYCLES"],
        "CONTROL_SLOT_CYCLES_PER_HOUR": c["SLOT_EQUIVALENT_CYCLES_PER_HOUR"],
        "TREATMENT_SLOT_CYCLES_PER_HOUR": t["SLOT_EQUIVALENT_CYCLES_PER_HOUR"],
        "MICRO_HOT_PHYSICAL_CYCLES": t["MICRO_HOT_PHYSICAL_CYCLES"],
        "MICRO_C1_CYCLES": t["MICRO_C1_CYCLES"],
        "MICRO_C2_CYCLES": t["MICRO_C2_CYCLES"],
        "CONTROL_HOT_RANK1_CYCLES": c["HOT_RANK1_CYCLES"],
        "TREATMENT_HOT_RANK1_CYCLES": t["HOT_RANK1_CYCLES"],
        "NET_NEAR_HOT_CYCLE_GAIN": near_gain,
        "CONTROL_FAR14_CYCLES": c["FAR14_CYCLES"],
        "CONTROL_FAR15_CYCLES": c["FAR15_CYCLES"],
        "MICRO_HOT_MECHANICS_FAVORABLE": t_cycles > c_cycles,
        "MICRO_HOT_STRONG_FREQUENCY_GATE_PASS": c_cycles > 0
        and D(t["PHYSICAL_CYCLES_PER_HOUR"]) >= D("1.20") * D(c["PHYSICAL_CYCLES_PER_HOUR"]),
        "AUDIT": "PASS"
        if c["AUDIT"].startswith("PASS") and t["AUDIT"].startswith("PASS")
        else "FAIL",
        "STATUS": "COMPLETE",
    }


def run():
    sha, manifest, validation = campaign_preflight()
    with campaign_writer_lock():
        profile, canonical, slices, evidence = bounded_inputs(manifest, validation)
        tick = validate_fine_tick(slices, canonical)
        capital_match = preflight_capital_match(profile, slices)
        require_owner_gate()
        _assert_published_head(sha)
        OUTPUT.mkdir(parents=True, exist_ok=False)
        model = ModelRegistry().get(MODEL_ID)
        common = {
            "model_id": MODEL_ID,
            "model_hash": model.model_hash,
            "source_day": SOURCE_DAY,
            "start": START.isoformat(),
            "end_exclusive": END.isoformat(),
            "published_config_sha": sha,
            "source_sha256_lf": {path.as_posix(): lf_sha(path) for path in SOURCE_PATHS},
            "evidence_sha256": json_hash(evidence),
            "tick_validation": tick,
            "preflight_capital_match": capital_match,
            "order_notional_mode": "SLOT_BASE_1_USDT_EQ_NON_EXECUTABLE",
            "virtual_filter_override": "MIN_NOTIONAL_ONLY",
        }
        results = {}
        for scenario in ("CONTROL", "TREATMENT"):
            identity = {**common, "scenario": scenario, "run_ordinal": 1}
            identity["run_hash"] = json_hash(identity)
            results[scenario] = execute_scenario(
                make_probe(profile, scenario),
                canonical,
                slices,
                identity,
                evidence,
                OUTPUT / scenario,
            )
        comparison = compare(results["CONTROL"], results["TREATMENT"], tick)
        payload = {
            "MODEL": MODEL_ID,
            "PERIOD": "3H",
            "RUN_STATUS": "COMPLETE",
            "DISCLAIMER": "NORMALIZED_NON_LIVE_EXECUTABLE",
            "COMPARISON": comparison,
            "SCENARIOS": results,
        }
        write_json(OUTPUT / "comparison.json", payload)
        write_json(RESULT, payload)
        return payload


if __name__ == "__main__":
    print(json.dumps(run(), indent=2, sort_keys=True))
