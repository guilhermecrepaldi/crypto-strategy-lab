"""Run the sole OWNER-authorized corrected M026 full-day retry."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from crypto_strategy_lab.ml.model_registry import ModelRegistry, ModelStatus, compute_model_hash
from scripts import run_m026_24h_extension as base
from scripts.register_m029_m026_24h_retry import (
    OWNER,
    PREREG,
    SPEC,
    registered_model_payload,
)
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
from scripts.validate_tardis_l2_samples import MANIFEST, TRADE_MANIFEST
from scripts.validate_tardis_l2_samples import OUTPUT as VALIDATION_REPORT

ROOT = Path(__file__).resolve().parents[1]
MODEL_ID = "M029"
OWNER_WINDOW = Path("docs/microstructure/OWNER_GATED_REPLAY_WINDOW.md")
REVIEW = Path("reports/usdcusdt/M029-preflight-independent-review.md")
JOURNAL = Path("docs/research/M029_JOURNAL.md")
OUTPUT = Path("artifacts/usdcusdt/l2-monthly-samples/M029/OWNER_GATED_24H/PRICE_PRIORITY")
RESULT = Path("reports/usdcusdt/M029-m026-24h-result.json")
SOURCE_PATHS = tuple(
    dict.fromkeys(
        (
            Path("scripts/run_m029_m026_24h_retry.py"),
            Path("scripts/register_m029_m026_24h_retry.py"),
            Path("scripts/run_m026_24h_extension.py"),
            Path("scripts/audit_m026_24h_extension.py"),
            Path("tests/test_m029_m026_24h_retry.py"),
            Path("tests/test_m026_24h_extension.py"),
            Path("tests/test_run_m026_24h_extension.py"),
            *base.parent_runner.SOURCE_PATHS,
        )
    )
)


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
            raise ValueError(f"M029_OWNER_GATE_REQUIRED:{key}")


def _assert_unused_output() -> None:
    if OUTPUT.exists() or RESULT.exists():
        raise ValueError("EXISTING_M029_EXPERIMENT_PRESERVED")


def campaign_preflight() -> tuple[str, dict[str, Any], dict[str, Any]]:
    require_owner_gate()
    _assert_unused_output()
    if Path.cwd().resolve() != ROOT.resolve():
        raise ValueError("CANONICAL_REPOSITORY_CWD_REQUIRED")
    sha = published_sha()
    base._assert_published_head(sha)
    for path in (
        *SOURCE_PATHS,
        OWNER,
        OWNER_WINDOW,
        SPEC,
        PREREG,
        REVIEW,
        JOURNAL,
        base.PARENT_RESULT,
        MANIFEST,
        VALIDATION_REPORT,
        TRADE_MANIFEST,
        PROFILE_CONFIG,
    ):
        published_bytes(path, sha)
    validate_review(REVIEW, SOURCE_PATHS)
    base._assert_parent_source_unchanged()
    if base.file_sha(PROFILE_CONFIG) != PROFILE_CONFIG_SHA:
        raise ValueError("M029_FROZEN_PROFILE_CHANGED")
    expected = registered_model_payload()
    registry = ModelRegistry()
    if registry.current_status("M026") != ModelStatus.INCONCLUSIVE:
        raise ValueError("M029_REQUIRES_PRESERVED_INCONCLUSIVE_M026")
    if registry.current_status("M028") != ModelStatus.INVALIDATED_TECHNICAL:
        raise ValueError("M029_REQUIRES_PRESERVED_INVALIDATED_M028")
    if registry.current_status(MODEL_ID) != ModelStatus.CREATED:
        raise ValueError("M029_REQUIRES_CREATED_STATUS")
    model = registry.get(MODEL_ID)
    if dict(model.model) != expected or model.model_hash != compute_model_hash(expected):
        raise ValueError("M029_REGISTERED_DESIGN_MISMATCH")
    return sha, json.loads(MANIFEST.read_bytes()), json.loads(VALIDATION_REPORT.read_bytes())


def run():
    sha, manifest, validation = campaign_preflight()
    with campaign_writer_lock():
        profile, canonical, slices, evidence = base.bounded_inputs(manifest, validation)
        evidence["m029_end_us"] = evidence.pop("m028_end_us")
        require_owner_gate()
        base._assert_published_head(sha)
        registry = ModelRegistry()
        model = registry.get(MODEL_ID)
        identity = {
            "model_id": MODEL_ID,
            "model_hash": model.model_hash,
            "parent_model_id": "M026",
            "parent_model_hash": registry.get("M026").model_hash,
            "technical_failure_predecessor": "M028",
            "capital_mode": "PHYSICAL_DYNAMIC_NORMALIZED_MECHANICS_BANK",
            "order_notional_mode": (
                "SLOT_BASE_1_USDT_EQ_QUANTIZED_WHOLE_USDC_NON_EXECUTABLE"
            ),
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
            "data_manifest_sha256": base.file_sha(MANIFEST),
            "profile_sha256": base.file_sha(PROFILE_CONFIG),
            "latency_us": profile.latency_us,
            "cancel_latency_us": profile.cancel_latency_us,
            "cutoff_liquidation": False,
            "another_day_authorized": False,
            "technical_correction": "CANONICAL_JSON_CHECKPOINT_STATE_COMPARISON",
            "evidence_sha256": json_hash(evidence),
        }
        identity["run_hash"] = json_hash(identity)
        return base.execute(
            base.make_probe(profile),
            canonical,
            slices,
            identity,
            evidence,
            output=OUTPUT,
            result_path=RESULT,
            model_id=MODEL_ID,
        )


if __name__ == "__main__":
    print(json.dumps(run(), sort_keys=True, default=str))
