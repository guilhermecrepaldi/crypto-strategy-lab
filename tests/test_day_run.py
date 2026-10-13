from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any, cast

import pytest
import yaml

import crypto_strategy_lab.microstructure.day_run as day_run_module
from crypto_strategy_lab.microstructure.day_run import (
    DayRunPreflightError,
    run_day_campaign,
)

MODEL_ID = "M036"
PARENT_MODEL_ID = "M035"
CAMPAIGN_DAY = "2026-10-14"
WINDOW_START = "2026-10-14T00:00:00Z"
WINDOW_END = "2026-10-14T00:03:00Z"
WINDOW_TOKEN = f"{WINDOW_START}/{WINDOW_END}"
AUTHORIZED_STATUS = "AUTHORIZED_M036_LOCAL_CAUSAL_FIXTURE"


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_sha256(payload: dict[str, Any]) -> str:
    """Mirror ``canonical_hash`` for JSON/YAML primitive fixture values."""

    canonical = json.dumps(payload, default=str, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _git(root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _initialize_source_repository(root: Path) -> str:
    """Make the source binding that the frozen day-run contract requires.

    Campaign inputs deliberately remain outside this commit. The runner binds
    the reviewed source paths/lock files, rather than requiring an impossible
    self-referential commit that contains its own commit hash in the model spec.
    """

    (root / "src/crypto_strategy_lab").mkdir(parents=True)
    (root / "src/crypto_strategy_lab/__init__.py").write_text(
        '"""Fixture source tree for day-run source binding tests."""\n', encoding="utf-8"
    )
    (root / "pyproject.toml").write_text(
        "[project]\nname = 'day-run-fixture'\nversion = '0'\n", encoding="utf-8"
    )
    (root / "uv.lock").write_text("version = 1\n", encoding="utf-8")
    _git(root, "init", "--initial-branch=main")
    _git(root, "config", "user.email", "fixture@example.invalid")
    _git(root, "config", "user.name", "Day Run Fixture")
    _git(root, "add", "src", "pyproject.toml", "uv.lock")
    _git(root, "commit", "-m", "fixture source binding")
    assert _git(root, "branch", "--show-current") == "main"
    return _git(root, "rev-parse", "HEAD")


def _write_current_state(root: Path, spec_sha256: str, *, authorized: bool) -> None:
    """Write only the authoritative head read before CURRENT_STATE's history."""

    next_status = AUTHORIZED_STATUS if authorized else "NO_RERUN_M035_V2_NEW_EXPERIMENT_REQUIRED"
    next_model_hash = spec_sha256 if authorized else "PENDING_OWNER_AUTHORIZATION"
    next_window = WINDOW_TOKEN if authorized else "UNAUTHORIZED"
    (root / "docs/research").mkdir(parents=True, exist_ok=True)
    (root / "docs/research/CURRENT_STATE.md").write_text(
        "\n".join(
            (
                "# CURRENT STATE",
                "",
                "ACTIVE_EXECUTION_CAMPAIGN=NONE",
                "CURRENT_ACTIVE_RESEARCH_MODEL=M035_PARALLEL_PAIR_CAPITAL_MANAGER",
                "CAMPAIGN_STATUS=READY_FOR_NEW_IDENTITY",
                f"NEXT_CAMPAIGN_STATUS={next_status}",
                f"NEXT_CAMPAIGN_MODEL_HASH={next_model_hash}",
                f"NEXT_CAMPAIGN_WINDOW={next_window}",
                "",
                "<!-- Historical state retained as provenance. -->",
                "NEXT_CAMPAIGN_WINDOW=UNAUTHORIZED",
                "",
            )
        ),
        encoding="utf-8",
    )


def _tape_payload(
    *,
    trade_after_gap: bool = False,
    include_external_cancellation: bool = False,
    include_external_halt: bool = False,
    noncontiguous_trade_ids: bool = False,
    fresh_l2_near_cutoff: bool = False,
) -> dict[str, Any]:
    """A causal BUY then SELL with a valid book available at the frozen cutoff."""

    if trade_after_gap:
        return {
            "venue": "BINANCE_SPOT",
            "symbol": "USDCUSDT",
            "events": [
                {
                    "type": "snapshot",
                    "timestamp": WINDOW_START,
                    "sequence": 1,
                    "update_id": 100,
                    "bids": [{"price": "0.9997", "quantity": "20"}],
                    "asks": [{"price": "1.0031", "quantity": "20"}],
                },
                {
                    "type": "gap",
                    "timestamp": "2026-10-14T00:00:01Z",
                    "sequence": 2,
                    "reason": "fixture proves the post-gap trade is unsafe",
                },
                {
                    "type": "trade",
                    "trade_id": 1,
                    "timestamp": "2026-10-14T00:00:02Z",
                    "sequence": 3,
                    "price": "0.9998",
                    "quantity": "20",
                    "buyer_is_maker": True,
                },
            ],
            "cancellations": [],
        }
    tape: dict[str, Any] = {
        "venue": "BINANCE_SPOT",
        "symbol": "USDCUSDT",
        "events": [
            {
                "type": "snapshot",
                "timestamp": WINDOW_START,
                "sequence": 1,
                "update_id": 100,
                "bids": [
                    {"price": "0.9998", "quantity": "20"},
                    {"price": "0.9997", "quantity": "20"},
                ],
                "asks": [
                    {"price": "1.0030", "quantity": "20"},
                    {"price": "1.0031", "quantity": "20"},
                ],
            },
            {
                "type": "trade",
                "trade_id": 1,
                "timestamp": "2026-10-14T00:00:01Z",
                "sequence": 2,
                "price": "0.9998",
                "quantity": "30",
                "buyer_is_maker": True,
            },
            {
                "type": "trade",
                "trade_id": 3 if noncontiguous_trade_ids else 2,
                "timestamp": "2026-10-14T00:00:02Z",
                "sequence": 3,
                "price": "1.0030",
                "quantity": "30",
                "buyer_is_maker": False,
            },
        ],
        "cancellations": [],
    }
    if include_external_halt:
        tape["events"].insert(
            1,
            {
                "type": "halt",
                "timestamp": "2026-10-14T00:00:00.500000Z",
                "sequence": 0,
                "reason": "fixture external halt must not steer a replay",
                "evidence": ["fixture://untrusted-halt"],
            },
        )
        for sequence, event in enumerate(tape["events"], start=1):
            event["sequence"] = sequence
    if include_external_cancellation:
        tape["cancellations"] = [
            {"order_id": "order-000001", "requested_at": "2026-10-14T00:00:01Z"}
        ]
    if fresh_l2_near_cutoff:
        tape["events"].append(
            {
                "type": "delta",
                "timestamp": "2026-10-14T00:02:59Z",
                "sequence": 4,
                "first_update_id": 101,
                "final_update_id": 101,
                "bids": [],
                "asks": [],
            }
        )
    return tape


def _normalized_event_source(tape: dict[str, Any], role: str) -> dict[str, Any]:
    allowed_types = {"snapshot", "delta"} if role == "L2_SNAPSHOT_DELTA" else {"trade"}
    events = [
        event
        for event in cast(list[dict[str, Any]], tape["events"])
        if event["type"] in allowed_types
    ]
    return {
        "schema_version": "crypto-lab-day-raw-events-v1",
        "venue": "BINANCE_SPOT",
        "symbol": "USDCUSDT",
        "events": events,
    }


def _write_temporal_provenance(
    root: Path,
    campaign: Path,
    *,
    fee_bps: int,
    rule_lot_step: str,
    fee_capture_mismatch: bool,
) -> dict[str, dict[str, str]]:
    """Create local, hash-bound historical fee and exchange-rule evidence."""

    provenance_dir = campaign / "provenance"

    def relative(path: Path) -> str:
        return path.relative_to(root).as_posix()

    common = {
        "venue": "BINANCE_SPOT",
        "symbol": "USDCUSDT",
        "base_asset": "USDC",
        "quote_asset": "USDT",
        "evidence_status": "PROVEN_HISTORICAL",
        "effective": {"start": WINDOW_START, "end": WINDOW_END},
        "acquired_at": "2026-10-13T00:00:00Z",
    }
    fee_record_path = provenance_dir / "fee-record.json"
    fee_payload = {
        "schema_version": "crypto-lab-day-fee-record-v1",
        "record_id": "LOCAL_TEST_FIXTURE",
        **common,
        "account_tier_context": "fixture-standard-tier",
        "maker_rate": "0",
        "taker_rate": "0",
        "side_fee_semantics": {
            "BUY": "QUOTE/SPENT_ASSET",
            "SELL": "QUOTE/RECEIVED_ASSET",
        },
        "counterfactual_sensitivity_bps": [] if fee_bps == 0 else [fee_bps],
    }
    fee_capture_payload = dict(fee_payload)
    if fee_capture_mismatch:
        fee_capture_payload["maker_rate"] = "0.0001"
    fee_capture_path = provenance_dir / "fee-capture.json"
    _write_json(
        fee_capture_path,
        {
            "schema_version": "crypto-lab-day-venue-evidence-capture-v1",
            "record_kind": "fee",
            "record_payload": fee_capture_payload,
        },
    )
    _write_json(
        fee_record_path,
        {
            **fee_payload,
            "sources": [
                {
                    "path": relative(fee_capture_path),
                    "sha256": _file_sha256(fee_capture_path),
                    "reference": "fixture://historical-fee",
                    "locator": "fixture-fee-record",
                    "provenance": "local test evidence",
                    "artifact_type": "IMMUTABLE_CAPTURE",
                }
            ],
        },
    )
    rule_record_path = provenance_dir / "rule-record.json"
    rule_payload = {
        "schema_version": "crypto-lab-day-rule-record-v1",
        "record_id": "LOCAL_TEST_RULES_FIXTURE",
        **common,
        "trading_status": "TRADING",
        "order_capability": {
            "order_type": "LIMIT_MAKER",
            "time_in_force": "GTC",
            "post_only": True,
        },
        "filters": {
            "price": {
                "min_price": "0.0001",
                "max_price": "10",
                "tick_size": "0.0001",
            },
            "lot": {
                "min_quantity": "0.01",
                "max_quantity": "1000",
                "step_size": rule_lot_step,
            },
            "notional": {
                "min_notional": "5",
                "max_notional": None,
                "applies_to_limit": True,
            },
        },
        "raw_filter_types": ["PRICE_FILTER", "LOT_SIZE", "MIN_NOTIONAL"],
        "validated_filter_types": ["PRICE_FILTER", "LOT_SIZE", "MIN_NOTIONAL"],
        "unsupported_active_filter_types": [],
    }
    rule_capture_path = provenance_dir / "rule-capture.json"
    _write_json(
        rule_capture_path,
        {
            "schema_version": "crypto-lab-day-venue-evidence-capture-v1",
            "record_kind": "rule",
            "record_payload": rule_payload,
        },
    )
    _write_json(
        rule_record_path,
        {
            **rule_payload,
            "sources": [
                {
                    "path": relative(rule_capture_path),
                    "sha256": _file_sha256(rule_capture_path),
                    "reference": "fixture://historical-rules",
                    "locator": "fixture-rule-record",
                    "provenance": "local test evidence",
                    "artifact_type": "IMMUTABLE_CAPTURE",
                }
            ],
        },
    )
    return {
        "fee_record": {
            "path": relative(fee_record_path),
            "sha256": _file_sha256(fee_record_path),
            "venue": "BINANCE_SPOT",
            "symbol": "USDCUSDT",
        },
        "rule_record": {
            "path": relative(rule_record_path),
            "sha256": _file_sha256(rule_record_path),
            "venue": "BINANCE_SPOT",
            "symbol": "USDCUSDT",
        },
    }


def _invariants() -> dict[str, bool]:
    return {
        "frozen_event_order_replay": True,
        "l2_inferred_fills_require_continuous_l2_and_individual_trades": True,
        "public_l2_queue_never_claims_own_queue_rank": True,
        "capture_arrival_and_latency_not_historical_proof": True,
        "decimal_exact": True,
        "capital_conservation": True,
        "zero_loss": True,
        "no_negative_ordinary_cycle_exit": True,
        "cancel_release_requires_ack": True,
        "live_testnet_closed": True,
        "llm_in_execution_loop": False,
    }


def _write_campaign(
    root: Path,
    *,
    current_state_authorized: bool = True,
    upper: str = "1.0030",
    fee_bps: int = 0,
    oracle_backend: str = "cpu",
    trade_after_gap: bool = False,
    include_external_cancellation: bool = False,
    include_external_halt: bool = False,
    noncontiguous_trade_ids: bool = False,
    fresh_l2_near_cutoff: bool = False,
    max_l2_update_age_seconds: int = 180,
    rule_lot_step: str = "0.0001",
    fee_capture_mismatch: bool = False,
) -> Path:
    """Create a complete local campaign with all post-review bindings frozen."""

    source_commit = _initialize_source_repository(root)
    campaign = root / "campaigns" / CAMPAIGN_DAY
    campaign.mkdir(parents=True)
    strategy_path = campaign / "STRATEGY.md"
    strategy_path.write_text(
        "# M036 local causal fixture\n\n"
        "A hash-bound, offline fixture used only to exercise day-run orchestration.\n",
        encoding="utf-8",
    )

    tape = _tape_payload(
        trade_after_gap=trade_after_gap,
        include_external_cancellation=include_external_cancellation,
        include_external_halt=include_external_halt,
        noncontiguous_trade_ids=noncontiguous_trade_ids,
        fresh_l2_near_cutoff=fresh_l2_near_cutoff,
    )
    tape_path = campaign / "tape.json"
    _write_json(tape_path, tape)
    l2_source_path = campaign / "source-l2.json"
    trades_source_path = campaign / "source-trades.json"
    _write_json(l2_source_path, _normalized_event_source(tape, "L2_SNAPSHOT_DELTA"))
    _write_json(trades_source_path, _normalized_event_source(tape, "INDIVIDUAL_TRADES"))
    tape_relative_path = f"campaigns/{CAMPAIGN_DAY}/tape.json"
    manifest_path = campaign / "tape-manifest.json"
    _write_json(
        manifest_path,
        {
            "schema_version": "crypto-lab-day-tape-manifest-v1",
            "venue": "BINANCE_SPOT",
            "symbol": "USDCUSDT",
            "tape_path": tape_relative_path,
            "tape_sha256": _file_sha256(tape_path),
            "windows": [{"start": WINDOW_START, "end": WINDOW_END}],
            "l2_snapshot_delta_validation": "PASS",
            "individual_trade_binding": "PASS",
            "individual_trade_id_coverage": {
                "mode": "CONTIGUOUS_NATIVE_IDS",
                "first_trade_id": 1,
                "last_trade_id": 3 if noncontiguous_trade_ids else 2,
            },
            "no_future_data": True,
            "source_files": [
                {
                    "role": "L2_SNAPSHOT_DELTA",
                    "path": f"campaigns/{CAMPAIGN_DAY}/source-l2.json",
                    "sha256": _file_sha256(l2_source_path),
                },
                {
                    "role": "INDIVIDUAL_TRADES",
                    "path": f"campaigns/{CAMPAIGN_DAY}/source-trades.json",
                    "sha256": _file_sha256(trades_source_path),
                },
            ],
        },
    )
    temporal_provenance = _write_temporal_provenance(
        root,
        campaign,
        fee_bps=fee_bps,
        rule_lot_step=rule_lot_step,
        fee_capture_mismatch=fee_capture_mismatch,
    )

    job: dict[str, Any] = {
        "schema_version": "crypto-lab-day-job-v1",
        "day": CAMPAIGN_DAY,
        "model_id": MODEL_ID,
        "parent": PARENT_MODEL_ID,
        "window": {"start": WINDOW_START, "end": WINDOW_END},
        "scenarios": [{"name": "F0_single", "fee_bps": fee_bps, "mode": "single"}],
        "oracle": {"backend": oracle_backend, "candidates": []},
        "engine": "causal_cpu",
        "gates": {
            "min_l2_inferred_cycles": 1,
            "max_negative_cycles": 0,
            "capital_conservation": True,
        },
        "output_dir": "reports/m036",
        "terminal_mark_max_age_seconds": 180,
        "max_l2_update_age_seconds": max_l2_update_age_seconds,
        "current_state_binding": {
            "next_campaign_status": AUTHORIZED_STATUS,
            # The spec hash itself is bound to this job contract, so the job
            # uses a literal sentinel and CURRENT_STATE carries the final hash.
            "next_campaign_model_hash": "MODEL_SPEC_SHA256",
            "next_campaign_window": WINDOW_TOKEN,
        },
        "model_spec_sha256": "0" * 64,
        "execution_authorized": True,
    }
    job_contract = {key: value for key, value in job.items() if key != "model_spec_sha256"}
    model_spec: dict[str, Any] = {
        "schema_version": "crypto-lab-day-model-spec-v1",
        "model_id": MODEL_ID,
        "parent_model_id": PARENT_MODEL_ID,
        "identity": "M036_LOCAL_CAUSAL_CPU_FIXTURE",
        "classification": "OFFLINE_RESEARCH_ONLY",
        "status": "AUTHORIZED",
        "symbol": "USDCUSDT",
        "venue": "BINANCE_SPOT",
        "execution_authorized": True,
        "authorization": {"status": "AUTHORIZED"},
        "invariants": _invariants(),
        "execution": {
            "engine": "causal_cpu",
            "evidence_class": "COUNTERFACTUAL_L2_QUEUE_ENVELOPE",
            "tape_path": tape_relative_path,
            "tape_sha256": _file_sha256(tape_path),
            "tape_manifest_path": f"campaigns/{CAMPAIGN_DAY}/tape-manifest.json",
            "tape_manifest_sha256": _file_sha256(manifest_path),
            "temporal_provenance": temporal_provenance,
            "asset_mapping": {
                "base_asset": "USDC",
                "quote_asset": "USDT",
                "adapter": "legacy_s0_quote_base_v1",
            },
            "s0_config": {
                "strategy_id": "M036_LOCAL_CAUSAL_CPU_FIXTURE",
                "symbol": "USDCUSDT",
                "lower": "0.9998",
                "upper": upper,
                "quantity_override": "10",
                "initial_usdc": "100",
                "lot_mode": "FIXED_LOT",
                "fixed_lot_usdc": "10",
                "step_size": "0.0001",
                "min_quantity": "0.01",
                "min_notional": "5",
                "queue_model": "REALISTIC_QUEUE",
                "conservative_queue_multiplier": "2",
                "latency": {
                    "market_data_ms": 0,
                    "decision_ms": 0,
                    "order_submit_ms": 0,
                    "cancel_ms": 0,
                },
                "fees": {
                    "maker_rate": "0",
                    "taker_rate": "0",
                    "buy_fee_asset": "QUOTE",
                    "sell_fee_asset": "QUOTE",
                    "source": "LOCAL_TEST_FIXTURE",
                },
            },
        },
        "provenance": {
            "strategy_sha256": _file_sha256(strategy_path),
            "job_contract_sha256": _canonical_sha256(job_contract),
            "execution_source_commit": source_commit,
        },
    }
    model_spec["spec_sha256"] = _canonical_sha256(model_spec)
    job["model_spec_sha256"] = model_spec["spec_sha256"]
    _write_json(campaign / "model_spec.json", model_spec)
    (campaign / "job.yaml").write_text(yaml.safe_dump(job, sort_keys=False), encoding="utf-8")
    _write_current_state(root, model_spec["spec_sha256"], authorized=current_state_authorized)
    return campaign


def _payload(path: Path) -> dict[str, Any]:
    payload: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not all(isinstance(key, str) for key in payload):
        raise AssertionError(f"expected a JSON object with string keys: {path}")
    return cast(dict[str, Any], payload)


def _status(payload: dict[str, Any]) -> str:
    return str(payload.get("status", payload.get("STATUS", payload.get("state", "")))).upper()


def test_day_run_executes_authorized_local_causal_cpu_campaign(tmp_path: Path) -> None:
    campaign = _write_campaign(tmp_path)

    result = run_day_campaign(tmp_path, campaign)

    report_dir = tmp_path / "reports/m036"
    summary_path = report_dir / "SUMMARY.json"
    audit_path = report_dir / "AUDIT.json"
    scenario_path = report_dir / "SCENARIO_01_F0_single.json"
    status_path = campaign / "RUN_STATUS.json"
    assert result is not None
    assert summary_path.is_file()
    assert audit_path.is_file()
    assert scenario_path.is_file()
    assert status_path.is_file()

    summary = _payload(summary_path)
    audit = _payload(audit_path)
    scenario = _payload(scenario_path)
    status = _payload(status_path)
    assert summary["model_id"] == MODEL_ID
    assert audit["model_id"] == MODEL_ID
    assert status["model_id"] == MODEL_ID
    assert _status(summary) == "COMPLETE"
    assert summary["verdict"] == "INCONCLUSIVE"
    assert status["state"] == "COMPLETED_INCONCLUSIVE"
    assert status["verdict"] == "INCONCLUSIVE"
    assert status["evidence_class"] == "COUNTERFACTUAL_L2_QUEUE_ENVELOPE"
    assert scenario["result"]["run_id"]
    assert scenario["result"]["modeled_orders"]
    assert scenario["result"]["l2_inferred_fills"]
    assert scenario["result"]["l2_inferred_fills"][0]["source_trade_id"] == 1
    assert scenario["economic_eligibility"].startswith("INCONCLUSIVE_PUBLIC_L2_QUEUE")
    assert scenario["asset_mapping"] == {
        "base_asset": "USDC",
        "quote_asset": "USDT",
        "legacy_engine_cash_field": "usdc",
        "legacy_engine_inventory_field": "fdusd",
    }
    assert audit["scenario_evidence"][0]["path"] == "reports/m036/SCENARIO_01_F0_single.json"
    current_state = (tmp_path / "docs/research/CURRENT_STATE.md").read_text(encoding="utf-8")
    assert current_state.index("## Day-run record") < current_state.index("<!--")


def test_day_run_can_correct_preflight_rejection_without_consuming_identity(tmp_path: Path) -> None:
    campaign = _write_campaign(tmp_path, current_state_authorized=False)
    status_path = campaign / "RUN_STATUS.json"

    with pytest.raises(DayRunPreflightError, match="CURRENT_STATE_WINDOW_UNAUTHORIZED"):
        run_day_campaign(tmp_path, campaign)

    rejected = _payload(status_path)
    assert rejected["state"] == "PREFLIGHT_REJECTED"
    assert not (tmp_path / "reports/m036/SUMMARY.json").exists()

    spec = _payload(campaign / "model_spec.json")
    _write_current_state(tmp_path, spec["spec_sha256"], authorized=True)
    result = run_day_campaign(tmp_path, campaign)

    status = _payload(status_path)
    assert result.status == "COMPLETED_INCONCLUSIVE"
    assert status["state"] == "COMPLETED_INCONCLUSIVE"
    assert len(status["preflight_rejections"]) == 1
    assert status["preflight_rejections"][0]["state"] == "PREFLIGHT_REJECTED"
    assert (tmp_path / "reports/m036/SUMMARY.json").is_file()


def test_day_run_rejects_tampered_strategy_before_claim(tmp_path: Path) -> None:
    campaign = _write_campaign(tmp_path)
    (campaign / "STRATEGY.md").write_text("# tampered after review\n", encoding="utf-8")

    with pytest.raises(DayRunPreflightError, match="STRATEGY_HASH_MISMATCH"):
        run_day_campaign(tmp_path, campaign)

    assert not (tmp_path / "reports/m036/SUMMARY.json").exists()
    assert _payload(campaign / "RUN_STATUS.json")["state"] == "PREFLIGHT_REJECTED"


def test_day_run_rejects_nonpositive_exit_edge_before_claim(tmp_path: Path) -> None:
    campaign = _write_campaign(tmp_path, upper="0.9999", fee_bps=1)

    with pytest.raises(
        DayRunPreflightError,
        match="POSITIVE_NET_EXIT_EDGE_REQUIRED_FOR_EACH_SCENARIO",
    ):
        run_day_campaign(tmp_path, campaign)

    assert not (tmp_path / "reports/m036/SUMMARY.json").exists()
    assert _payload(campaign / "RUN_STATUS.json")["state"] == "PREFLIGHT_REJECTED"


def test_day_run_rejects_trade_after_feed_gap_without_resnapshot_before_claim(
    tmp_path: Path,
) -> None:
    campaign = _write_campaign(tmp_path, trade_after_gap=True)

    with pytest.raises(DayRunPreflightError, match="AUTHORIZED_DAY_RUN_REJECTS_FEED_GAPS"):
        run_day_campaign(tmp_path, campaign)

    assert not (tmp_path / "reports/m036/SUMMARY.json").exists()
    assert _payload(campaign / "RUN_STATUS.json")["state"] == "PREFLIGHT_REJECTED"


def test_day_run_rejects_external_cancellation_without_frozen_causal_policy(
    tmp_path: Path,
) -> None:
    campaign = _write_campaign(tmp_path, include_external_cancellation=True)

    with pytest.raises(
        DayRunPreflightError,
        match="AUTHORIZED_DAY_RUN_REJECTS_EXTERNAL_CANCELLATIONS",
    ):
        run_day_campaign(tmp_path, campaign)

    assert not (tmp_path / "reports/m036/SUMMARY.json").exists()
    assert _payload(campaign / "RUN_STATUS.json")["state"] == "PREFLIGHT_REJECTED"


def test_day_run_rejects_external_risk_halt_without_frozen_causal_policy(
    tmp_path: Path,
) -> None:
    campaign = _write_campaign(tmp_path, include_external_halt=True)

    with pytest.raises(
        DayRunPreflightError,
        match="AUTHORIZED_DAY_RUN_REJECTS_EXTERNAL_RISK_HALTS",
    ):
        run_day_campaign(tmp_path, campaign)

    assert not (tmp_path / "reports/m036/SUMMARY.json").exists()
    assert _payload(campaign / "RUN_STATUS.json")["state"] == "PREFLIGHT_REJECTED"


def test_day_run_rejects_noncontiguous_native_trade_ids_before_claim(tmp_path: Path) -> None:
    campaign = _write_campaign(tmp_path, noncontiguous_trade_ids=True)

    with pytest.raises(DayRunPreflightError, match="TAPE_INDIVIDUAL_TRADE_IDS_NOT_CONTIGUOUS"):
        run_day_campaign(tmp_path, campaign)

    assert not (tmp_path / "reports/m036/SUMMARY.json").exists()
    assert _payload(campaign / "RUN_STATUS.json")["state"] == "PREFLIGHT_REJECTED"


def test_day_run_rejects_stale_l2_cutoff_coverage_before_claim(tmp_path: Path) -> None:
    campaign = _write_campaign(tmp_path, max_l2_update_age_seconds=1)

    with pytest.raises(DayRunPreflightError, match="TAPE_L2_CUTOFF_GAP_EXCEEDS_FROZEN_MAX_AGE"):
        run_day_campaign(tmp_path, campaign)

    assert not (tmp_path / "reports/m036/SUMMARY.json").exists()
    assert _payload(campaign / "RUN_STATUS.json")["state"] == "PREFLIGHT_REJECTED"


def test_day_run_rejects_stale_intra_window_l2_coverage_before_claim(tmp_path: Path) -> None:
    campaign = _write_campaign(
        tmp_path,
        fresh_l2_near_cutoff=True,
        max_l2_update_age_seconds=60,
    )

    with pytest.raises(DayRunPreflightError, match="TAPE_L2_UPDATE_GAP_EXCEEDS_FROZEN_MAX_AGE"):
        run_day_campaign(tmp_path, campaign)

    assert not (tmp_path / "reports/m036/SUMMARY.json").exists()
    assert _payload(campaign / "RUN_STATUS.json")["state"] == "PREFLIGHT_REJECTED"


def test_day_run_preflights_explicit_gpu_with_nonempty_probe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    probe_calls: list[tuple[object, object, str]] = []

    def unavailable_gpu_probe(prices: object, candidates: object, *, backend: str) -> None:
        probe_calls.append((prices, candidates, backend))
        raise RuntimeError("fixture GPU unavailable")

    monkeypatch.setattr(day_run_module, "scan_oracle", unavailable_gpu_probe)
    campaign = _write_campaign(tmp_path, oracle_backend="gpu")

    with pytest.raises(DayRunPreflightError, match="EXPLICIT_GPU_ORACLE_UNAVAILABLE:RuntimeError"):
        run_day_campaign(tmp_path, campaign)

    assert probe_calls == [((0,), ((0, 1),), "gpu")]
    assert not (tmp_path / "reports/m036/SUMMARY.json").exists()
    assert _payload(campaign / "RUN_STATUS.json")["state"] == "PREFLIGHT_REJECTED"


def test_day_run_rejects_distinct_tick_and_lot_steps_before_claim(tmp_path: Path) -> None:
    campaign = _write_campaign(tmp_path, rule_lot_step="0.01")

    with pytest.raises(
        DayRunPreflightError,
        match="RULE_RECORD_LEGACY_S0_REQUIRES_EQUAL_TICK_AND_LOT_STEP",
    ):
        run_day_campaign(tmp_path, campaign)

    assert not (tmp_path / "reports/m036/SUMMARY.json").exists()
    assert _payload(campaign / "RUN_STATUS.json")["state"] == "PREFLIGHT_REJECTED"


def test_day_run_rejects_provenance_capture_semantic_mismatch_before_claim(
    tmp_path: Path,
) -> None:
    campaign = _write_campaign(tmp_path, fee_capture_mismatch=True)

    with pytest.raises(
        DayRunPreflightError,
        match="TEMPORAL_PROVENANCE_CAPTURE_SEMANTIC_MISMATCH",
    ):
        run_day_campaign(tmp_path, campaign)

    assert not (tmp_path / "reports/m036/SUMMARY.json").exists()
    assert _payload(campaign / "RUN_STATUS.json")["state"] == "PREFLIGHT_REJECTED"


def test_day_run_rejects_noncontiguous_windows_before_claim(tmp_path: Path) -> None:
    campaign = _write_campaign(tmp_path)
    job_path = campaign / "job.yaml"
    raw_job: object = yaml.safe_load(job_path.read_text(encoding="utf-8"))
    if not isinstance(raw_job, dict):  # pragma: no cover - fixture invariant
        raise AssertionError("fixture job must be a YAML object")
    job = cast(dict[str, Any], raw_job)
    job.pop("window")
    job["windows"] = [
        {"start": WINDOW_START, "end": "2026-10-14T00:01:00Z"},
        {"start": "2026-10-14T00:02:00Z", "end": WINDOW_END},
    ]
    job_path.write_text(yaml.safe_dump(job, sort_keys=False), encoding="utf-8")

    with pytest.raises(DayRunPreflightError, match="DAY_RUN_WINDOWS_MUST_BE_CONTIGUOUS"):
        run_day_campaign(tmp_path, campaign)

    assert not (tmp_path / "reports/m036/SUMMARY.json").exists()
    assert _payload(campaign / "RUN_STATUS.json")["state"] == "PREFLIGHT_REJECTED"
