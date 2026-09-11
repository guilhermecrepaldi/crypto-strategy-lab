"""Exactly one published-source full-day replication of the M026 strategy."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from datetime import UTC, datetime
from decimal import Decimal as D
from pathlib import Path
from typing import Any

from crypto_strategy_lab.domain import canonical_hash
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
from scripts.audit_m026_24h_extension import (
    independent_m026_24h_audit,
    normalize_full_day_metrics,
)
from scripts.register_m026_24h_extension import OWNER, PREREG, SPEC, registered_model_payload
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
MODEL_ID = "M028"
SOURCE_DAY = "2025-01-01"
START = datetime(2025, 1, 1, tzinfo=UTC)
END = datetime(2025, 1, 2, tzinfo=UTC)
M026_END = datetime(2025, 1, 1, 3, tzinfo=UTC)
START_US = _datetime_to_micros(START)
END_US = _datetime_to_micros(END)
M026_END_US = _datetime_to_micros(M026_END)
OWNER_WINDOW = Path("docs/microstructure/OWNER_GATED_REPLAY_WINDOW.md")
REVIEW = Path("reports/usdcusdt/M028-preflight-independent-review.md")
JOURNAL = Path("docs/research/M028_JOURNAL.md")
PARENT_RESULT = Path("reports/usdcusdt/M026-3h-result.json")
PARENT_LEDGER = Path(
    "artifacts/usdcusdt/l2-monthly-samples/M026/OWNER_GATED_3H/PRICE_PRIORITY/execution-audit.jsonl"
)
PARENT_TERMINAL = Path(
    "artifacts/usdcusdt/l2-monthly-samples/M026/OWNER_GATED_3H/PRICE_PRIORITY/"
    "terminal-engine-state.json"
)
OUTPUT = Path("artifacts/usdcusdt/l2-monthly-samples/M028/OWNER_GATED_24H/PRICE_PRIORITY")
RESULT = Path("reports/usdcusdt/M028-m026-24h-result.json")
SOURCE_PATHS = tuple(
    dict.fromkeys(
        (
            Path("scripts/run_m026_24h_extension.py"),
            Path("scripts/audit_m026_24h_extension.py"),
            Path("scripts/register_m026_24h_extension.py"),
            Path("tests/test_m026_24h_extension.py"),
            Path("tests/test_run_m026_24h_extension.py"),
            *parent_runner.SOURCE_PATHS,
        )
    )
)
PARENT_NON_ECONOMIC_HASH_TRANSITIONS = {
    "tests/test_run_dynamic_hotline_321.py": (
        "3e4597d16777307aa5944871ee7ba51568172ed573e3fb4a8d12c565d4e07fa5",
        "05935eb076cb5c1699548118e5f6ea18a401e7ff691bfae14f8e451f70ce5dd2",
    )
}


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
            raise ValueError(f"M028_OWNER_GATE_REQUIRED:{key}")


def _assert_unused_output(output: Path = OUTPUT, result: Path = RESULT) -> None:
    if output.exists() or result.exists():
        raise ValueError("EXISTING_M028_EXPERIMENT_PRESERVED")


def _assert_published_head(sha: str) -> None:
    if _git_output("status", "--porcelain"):
        raise ValueError("PRE_EXECUTION_WORKTREE_NOT_CLEAN")
    if _git_output("branch", "--show-current") != "main":
        raise ValueError("CANONICAL_MAIN_REQUIRED")
    if any(_git_output("rev-parse", ref) != sha for ref in ("HEAD", "origin/main")):
        raise ValueError("M028_REQUIRES_PUBLISHED_HEAD")


def _assert_parent_source_unchanged() -> None:
    parent = json.loads(PARENT_RESULT.read_bytes())
    if parent.get("model_id") != "M026" or parent.get("MODEL_STATUS") != "INCONCLUSIVE":
        raise ValueError("M028_PARENT_RESULT_IDENTITY")
    for name, expected in parent["source_sha256_lf"].items():
        observed = lf_sha(Path(name))
        allowed_transition = PARENT_NON_ECONOMIC_HASH_TRANSITIONS.get(name)
        if observed != expected and allowed_transition != (expected, observed):
            raise ValueError(f"M028_PARENT_SOURCE_CHANGED:{name}")
    physical = parent["REGISTRY"]["physical_file_sha256"]
    for name, expected in physical.items():
        if file_sha(Path(name)) != expected:
            raise ValueError(f"M028_PARENT_PHYSICAL_EVIDENCE_CHANGED:{name}")


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
        PARENT_RESULT,
        MANIFEST,
        VALIDATION_REPORT,
        TRADE_MANIFEST,
        PROFILE_CONFIG,
    ):
        published_bytes(path, sha)
    validate_review(REVIEW, SOURCE_PATHS)
    _assert_parent_source_unchanged()
    if file_sha(PROFILE_CONFIG) != PROFILE_CONFIG_SHA:
        raise ValueError("FROZEN_PROFILE_CHANGED")
    expected = registered_model_payload()
    registry = ModelRegistry()
    if registry.current_status("M026") != ModelStatus.INCONCLUSIVE:
        raise ValueError("M028_REQUIRES_PRESERVED_INCONCLUSIVE_M026")
    if registry.current_status(MODEL_ID) != ModelStatus.CREATED:
        raise ValueError("M028_REQUIRES_CREATED_STATUS")
    model = registry.get(MODEL_ID)
    if dict(model.model) != expected or model.model_hash != compute_model_hash(expected):
        raise ValueError("M028_REGISTERED_DESIGN_MISMATCH")
    return sha, json.loads(MANIFEST.read_bytes()), json.loads(VALIDATION_REPORT.read_bytes())


def bounded_inputs(
    manifest: dict[str, Any], validation: dict[str, Any]
) -> tuple[ExecutionProfile, dict[int, Trade], tuple[dict[str, Any], ...], dict[str, Any]]:
    trade_manifest = json.loads(TRADE_MANIFEST.read_bytes())
    entry = next(item for item in manifest["dates"] if item["date"] == SOURCE_DAY)
    checked = next(item for item in validation["days"] if item["date"] == SOURCE_DAY)
    verified = verify_published_day_evidence(entry, checked, trade_manifest)
    slices = tuple(sorted(entry["raw_slices"], key=lambda item: int(item["offset"])))
    if len(slices) != 144 or tuple(item["offset"] for item in slices) != tuple(range(0, 1440, 10)):
        raise ValueError("M028_EXACT_ALL_144_SLICES_REQUIRED")
    for item in slices:
        validate_slice_metadata(SOURCE_DAY, item)
        path = checked_path(ROOT, item["local_path"], SOURCE_DAY, raw=True)
        if path.stat().st_size != item["bytes"] or file_sha(path) != item["sha256"]:
            raise ValueError("M028_NATIVE_EVIDENCE_CHANGED")

    history = HistoryManifest.model_validate_json(TRADE_MANIFEST.read_bytes())
    read_start = max(START, history.first_timestamp)
    selected = select_history_archives(history, start=read_start, end_exclusive=END)
    if len(selected) != 1 or selected[0].cadence != "daily":
        raise ValueError("M028_EXACT_DAILY_TRADE_ARCHIVE_REQUIRED")
    if file_sha(Path(selected[0].local_path)) != selected[0].sha256:
        raise ValueError("M028_CANONICAL_ARCHIVE_CHANGED")
    canonical: dict[int, Trade] = {}
    for event in iter_history(history, start=read_start, end_exclusive=END):
        if event.trade_id in canonical:
            raise ValueError("M028_DUPLICATE_CANONICAL_TRADE")
        canonical[event.trade_id] = Trade(
            _datetime_to_micros(event.timestamp),
            event.trade_id,
            event.price,
            event.quantity,
            event.buyer_is_maker,
        )
    config = json.loads(PROFILE_CONFIG.read_bytes())
    profile_row = next(
        row for row in config["profiles"] if row["profile"]["name"] == "B_REALISTIC_CONSERVATIVE"
    )
    profile = typed(ExecutionProfile, profile_row["profile"])
    if (
        profile.latency_us != 1179525
        or profile.cancel_latency_us != 1179525
        or profile.maker_fee != D(0)
        or profile.taker_fee != D(0)
    ):
        raise ValueError("M028_FROZEN_PROFILE_CHANGED")
    return (
        profile,
        canonical,
        slices,
        {
            "validation": verified,
            "bounded_slice_count": len(slices),
            "bounded_slice_offsets": [item["offset"] for item in slices],
            "bounded_slice_sha256": hashlib.sha256(
                "\n".join(f"{item['offset']}:{item['sha256']}" for item in slices).encode()
            ).hexdigest(),
            "canonical_trade_count": len(canonical),
            "canonical_first_trade_id": min(canonical),
            "canonical_last_trade_id": max(canonical),
            "m028_end_us": END_US,
        },
    )


def bounded_native_events(slices: tuple[dict[str, Any], ...]):
    if len(slices) != 144:
        raise ValueError("M028_ALL_SLICES_REQUIRED")
    for event in iter_native_events(raw_lines(ROOT, SOURCE_DAY, list(slices))):
        if not (
            START_US <= event["local_us"] < END_US and START_US <= event["exchange_us"] < END_US
        ):
            raise ValueError("M028_NATIVE_EVENT_ESCAPED_24H_BOUND")
        yield event


def make_probe(profile: ExecutionProfile):
    from crypto_strategy_lab.microstructure.dynamic_hotline_321 import DynamicHotline321Probe

    return DynamicHotline321Probe(
        start_us=START_US,
        end_us=END_US,
        latency_us=profile.latency_us,
        cancel_latency_us=profile.cancel_latency_us,
    )


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _canonical_checkpoint_state(state: dict[str, Any]) -> dict[str, Any]:
    """Normalize in-memory and JSON-restored checkpoint values identically."""
    return json.loads(json.dumps(state, sort_keys=True, default=str))


def verify_m026_prefix(
    engine,
    seen: set[str],
    canonical: dict[int, Trade],
    *,
    model_id: str = MODEL_ID,
) -> dict[str, Any]:
    """Fail closed before the first post-03:00 event if M026's prefix diverges."""
    # M026's own finish observes its configured boundary without advancing the
    # event clock. Mirror that exact behavior so end_us is the sole normalized
    # checkpoint difference and the 24h engine can then continue causally.
    engine._observe(M026_END_US)
    metrics = engine.metrics()
    expected_result = json.loads(PARENT_RESULT.read_bytes())
    expected_ledger = _read_jsonl(PARENT_LEDGER)
    if engine.audit != expected_ledger:
        raise ValueError(f"{model_id}_M026_PREFIX_LEDGER_MISMATCH")
    expected_ids = {trade.trade_id for trade in canonical.values() if trade.time_us < M026_END_US}
    if seen != expected_ids or len(seen) != expected_result["expected_trade_count"]:
        raise ValueError(f"{model_id}_M026_PREFIX_TRADE_SET_MISMATCH")
    actual_terminal = engine.checkpoint()
    expected_terminal = json.loads(PARENT_TERMINAL.read_bytes())
    normalized_state = _canonical_checkpoint_state(actual_terminal["state"])
    normalized_state["parent"]["config"]["end_us"] = M026_END_US
    expected_state = _canonical_checkpoint_state(expected_terminal["state"])
    if normalized_state != expected_state:
        raise ValueError(f"{model_id}_M026_PREFIX_ECONOMIC_STATE_MISMATCH")
    parent_metrics = expected_result["METRICS"]
    fields = (
        "PHYSICAL_CYCLES",
        "SLOT_EQUIVALENT_CYCLES",
        "TOTAL_FILLS",
        "FINAL_USDT",
        "FINAL_USDC",
        "FINAL_TOTAL_MARKED",
        "REALIZED_CYCLE_PNL",
        "REALIZED_DISPOSAL_PNL",
        "UNREALIZED_PNL",
        "ORDERS_CREATED",
        "HOTLINE_EPOCHS",
    )
    if any(metrics[field] != parent_metrics[field] for field in fields):
        raise ValueError(f"{model_id}_M026_PREFIX_METRIC_MISMATCH")
    return {
        "STATUS": "PASS_EXACT_M026_3H_PREFIX_EQUIVALENCE",
        "LEDGER_EXACT_MATCH": True,
        "ECONOMIC_STATE_MATCH": True,
        "METRIC_MATCH": True,
        "PREFIX_TRADES": len(seen),
        "PREFIX_LEDGER_SHA256": file_sha(PARENT_LEDGER),
        "PREFIX_TERMINAL_NORMALIZED_SHA256": canonical_hash(normalized_state),
    }


def _write_ledger(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        for row in rows:
            stream.write(json.dumps(row, sort_keys=True, default=str) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def execute(
    engine,
    canonical,
    slices,
    identity,
    evidence,
    output=OUTPUT,
    result_path=RESULT,
    *,
    model_id: str = MODEL_ID,
):
    _assert_unused_output(output, result_path)
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / "run-manifest.json", {**identity, "evidence": evidence})
    audit_file = output / "execution-audit.jsonl"
    try:
        seen: set[str] = set()
        prefix: dict[str, Any] | None = None
        for event in bounded_native_events(slices):
            if prefix is None and event["local_us"] >= M026_END_US:
                prefix = verify_m026_prefix(engine, seen, canonical, model_id=model_id)
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
                raise ValueError(f"{model_id}_UNKNOWN_NATIVE_EVENT")
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
                raise ValueError(f"{model_id}_CANONICAL_TRADE_BINDING_CHANGED")
            consumed = engine.receive_trade(trade, capture_time_us=event["local_us"])
            if not D(0) <= consumed <= trade.quantity:
                raise ValueError(f"{model_id}_GLOBAL_TRADE_BUDGET_EXCEEDED")
            seen.add(trade.trade_id)
        if prefix is None:
            prefix = verify_m026_prefix(engine, seen, canonical, model_id=model_id)
        if seen != {trade.trade_id for trade in canonical.values()}:
            raise ValueError(f"{model_id}_CANONICAL_24H_NOT_FULLY_DELIVERED")
        metrics = normalize_full_day_metrics(engine.finish(time_us=END_US), model_id=model_id)
        terminal = engine.checkpoint()
        _write_ledger(audit_file, engine.audit)
        write_json(output / "terminal-engine-state.json", terminal)
        audit = independent_m026_24h_audit(
            engine.audit,
            terminal,
            metrics,
            canonical,
            prefix,
            model_id=model_id,
        )
        audit.update(terminal_sha256=terminal["sha256"], ledger_sha256=file_sha(audit_file))
        metrics["AUDIT"] = audit["status"]
        metrics["STATUS"] = "COMPLETE"
        result = {
            **identity,
            "MODEL": model_id,
            "PARENT_STRATEGY": "M026",
            "PERIOD": "24H",
            "RUN_STATUS": "COMPLETE",
            "VERDICT": "M026_FULL_DAY_MEASURED_NOT_LIVE_APPROVAL",
            "DISCLAIMER": engine.normalized_label,
            "PREFIX_EQUIVALENCE": prefix,
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
            "parent_model_id": "M026",
            "parent_model_hash": ModelRegistry().get("M026").model_hash,
            "capital_mode": "PHYSICAL_DYNAMIC_NORMALIZED_MECHANICS_BANK",
            "order_notional_mode": ("SLOT_BASE_1_USDT_EQ_QUANTIZED_WHOLE_USDC_NON_EXECUTABLE"),
            "virtual_filter_override": "MIN_NOTIONAL_ONLY",
            "start": "2025-01-01T00:00:00Z",
            "end_exclusive": "2025-01-02T00:00:00Z",
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
            "another_day_authorized": False,
            "evidence_sha256": json_hash(evidence),
        }
        identity["run_hash"] = json_hash(identity)
        return execute(make_probe(profile), canonical, slices, identity, evidence)


if __name__ == "__main__":
    print(json.dumps(run(), sort_keys=True, default=str))
