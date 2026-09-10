"""Exactly one published-source M026 three-hour historical L2 run."""

from __future__ import annotations

import json
import os
import re
import subprocess
from decimal import Decimal as D
from pathlib import Path
from typing import Any

from crypto_strategy_lab.microstructure.recovery_reserve_study import file_sha, write_json
from crypto_strategy_lab.ml.model_registry import ModelRegistry, ModelStatus, compute_model_hash
from scripts import run_triangular_pre_aged_queue as parent_runner
from scripts.audit_dynamic_hotline_321 import independent_dynamic_hotline_audit
from scripts.register_dynamic_hotline_321 import OWNER, PREREG, SPEC, registered_model_payload
from scripts.run_high_uptime_recovery import (
    PROFILE_CONFIG,
    PROFILE_CONFIG_SHA,
    campaign_writer_lock,
    lf_sha,
    published_bytes,
    published_sha,
    validate_review,
)
from scripts.run_l2_monthly_samples import json_hash
from scripts.validate_tardis_l2_samples import MANIFEST, TRADE_MANIFEST, trade_timestamp_matches
from scripts.validate_tardis_l2_samples import OUTPUT as VALIDATION_REPORT

ROOT = Path(__file__).resolve().parents[1]
MODEL_ID = "M026"
START_US, END_US = parent_runner.START_US, parent_runner.END_US
OWNER_WINDOW = Path("docs/microstructure/OWNER_GATED_REPLAY_WINDOW.md")
REVIEW = Path("reports/usdcusdt/M026-preflight-independent-review.md")
JOURNAL = Path("docs/research/M026_JOURNAL.md")
OUTPUT = Path("artifacts/usdcusdt/l2-monthly-samples/M026/OWNER_GATED_3H/PRICE_PRIORITY")
RESULT = Path("reports/usdcusdt/M026-3h-result.json")
SOURCE_PATHS = tuple(
    dict.fromkeys(
        (
            Path("scripts/run_dynamic_hotline_321.py"),
            Path("scripts/audit_dynamic_hotline_321.py"),
            Path("scripts/register_dynamic_hotline_321.py"),
            Path("src/crypto_strategy_lab/microstructure/dynamic_hotline_321.py"),
            Path("tests/test_dynamic_hotline_321.py"),
            Path("tests/test_run_dynamic_hotline_321.py"),
            *parent_runner.SOURCE_PATHS,
        )
    )
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
        "AUTHORIZED_SCENARIO_COUNT": "1",
    }.items():
        if re.findall(rf"^{key}=(.*)$", authority, flags=re.MULTILINE) != [value]:
            raise ValueError(f"M026_OWNER_GATE_REQUIRED:{key}")


def _assert_unused_output(output: Path = OUTPUT, result: Path = RESULT) -> None:
    if output.exists() or result.exists():
        raise ValueError("EXISTING_M026_EXPERIMENT_PRESERVED")


def _assert_published_head(sha: str) -> None:
    if _git_output("status", "--porcelain"):
        raise ValueError("PRE_EXECUTION_WORKTREE_NOT_CLEAN")
    if _git_output("branch", "--show-current") != "main":
        raise ValueError("CANONICAL_MAIN_REQUIRED")
    if any(_git_output("rev-parse", ref) != sha for ref in ("HEAD", "origin/main")):
        raise ValueError("M026_REQUIRES_PUBLISHED_HEAD")


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
        raise ValueError("M026_REQUIRES_CREATED_STATUS")
    model = registry.get(MODEL_ID)
    if dict(model.model) != expected or model.model_hash != compute_model_hash(expected):
        raise ValueError("M026_REGISTERED_DESIGN_MISMATCH")
    return sha, json.loads(MANIFEST.read_bytes()), json.loads(VALIDATION_REPORT.read_bytes())


def bounded_inputs(manifest: dict[str, Any], validation: dict[str, Any]):
    return parent_runner.bounded_inputs(manifest, validation)


def bounded_native_events(slices):
    yield from parent_runner.bounded_native_events(slices)


def make_probe(profile):
    from crypto_strategy_lab.microstructure.dynamic_hotline_321 import DynamicHotline321Probe

    return DynamicHotline321Probe(
        start_us=START_US,
        end_us=END_US,
        latency_us=profile.latency_us,
        cancel_latency_us=profile.cancel_latency_us,
    )


def _write_ledger(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        for row in rows:
            stream.write(json.dumps(row, sort_keys=True, default=str) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def execute(engine, canonical, slices, identity, evidence, output=OUTPUT, result_path=RESULT):
    _assert_unused_output(output, result_path)
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / "run-manifest.json", {**identity, "evidence": evidence})
    audit_file = output / "execution-audit.jsonl"
    try:
        seen: set[str] = set()
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
            if event["kind"] != "TRADE":
                raise ValueError("M026_UNKNOWN_NATIVE_EVENT")
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
                raise ValueError("M026_CANONICAL_TRADE_BINDING_CHANGED")
            consumed = engine.receive_trade(trade, capture_time_us=event["local_us"])
            if not D(0) <= consumed <= trade.quantity:
                raise ValueError("M026_GLOBAL_TRADE_BUDGET_EXCEEDED")
            seen.add(trade.trade_id)
        if seen != set(canonical):
            raise ValueError("M026_CANONICAL_3H_NOT_FULLY_DELIVERED")
        metrics = engine.finish(time_us=END_US)
        terminal = engine.checkpoint()
        _write_ledger(audit_file, engine.audit)
        write_json(output / "terminal-engine-state.json", terminal)
        audit = independent_dynamic_hotline_audit(engine.audit, terminal, metrics, canonical)
        audit.update(terminal_sha256=terminal["sha256"], ledger_sha256=file_sha(audit_file))
        metrics["AUDIT"] = audit["status"]
        metrics["STATUS"] = "COMPLETE"
        result = {
            **identity,
            "MODEL": MODEL_ID,
            "PERIOD": "3H",
            "RUN_STATUS": "COMPLETE",
            "VERDICT": "M026_MECHANICS_MEASURED_NOT_LIVE_APPROVAL",
            "DISCLAIMER": engine.normalized_label,
            "METRICS": metrics,
            "AUDIT": audit,
            "AUDIT_FILE": str(audit_file),
        }
        write_json(output / "independent-audit.json", audit)
        write_json(output / "summary.json", result)
        write_json(result_path, result)
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
                "run_hash": identity.get("run_hash"),
                "ledger_sha256": file_sha(audit_file),
            },
        )
        raise


def run():
    sha, manifest, validation = campaign_preflight()
    with campaign_writer_lock():
        profile, canonical, slices, evidence = bounded_inputs(manifest, validation)
        require_owner_gate()
        _assert_published_head(sha)
        model = ModelRegistry().get(MODEL_ID)
        identity = {
            "model_id": MODEL_ID,
            "model_hash": model.model_hash,
            "capital_mode": "PHYSICAL_DYNAMIC_NORMALIZED_MECHANICS_BANK",
            "order_notional_mode": "SLOT_BASE_1_USDT_EQ_QUANTIZED_WHOLE_USDC_NON_EXECUTABLE",
            "virtual_filter_override": "MIN_NOTIONAL_ONLY",
            "start": "2025-01-01T00:00:00Z",
            "end_exclusive": "2025-01-01T03:00:00Z",
            "published_config_sha": sha,
            "expected_trade_count": len(canonical),
            "source_sha256_lf": {path.as_posix(): lf_sha(path) for path in SOURCE_PATHS},
            "owner_directive_sha256_lf": lf_sha(OWNER),
            "owner_window_sha256_lf": lf_sha(OWNER_WINDOW),
            "spec_sha256_lf": lf_sha(SPEC),
            "protocol_sha256_lf": lf_sha(PREREG),
            "review_sha256_lf": lf_sha(REVIEW),
            "pre_run_journal_sha256_lf": lf_sha(JOURNAL),
            "data_manifest_sha256": file_sha(MANIFEST),
            "profile_sha256": file_sha(PROFILE_CONFIG),
            "latency_us": profile.latency_us,
            "cancel_latency_us": profile.cancel_latency_us,
            "cutoff_liquidation": False,
            "day2_authorized": False,
            "evidence_sha256": json_hash(evidence),
        }
        identity["run_hash"] = json_hash(identity)
        return execute(make_probe(profile), canonical, slices, identity, evidence)


if __name__ == "__main__":
    print(json.dumps(run(), sort_keys=True, default=str))
