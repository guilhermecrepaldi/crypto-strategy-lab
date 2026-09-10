"""Recover M030's derived report from its immutable completed physical ledger.

No book/trade event is delivered here.  The script restores the terminal state,
recomputes report-only metrics, and repeats the independent physical audit.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from decimal import Decimal as D
from pathlib import Path
from typing import Any

from crypto_strategy_lab.domain import canonical_hash
from crypto_strategy_lab.microstructure.hotline_first_reallocation import (
    DEFAULT_EVALUATION_WINDOWS,
    HotlineFirstDynamic321Probe,
)
from crypto_strategy_lab.microstructure.recovery_reserve_study import file_sha, write_json
from scripts import run_m026_24h_extension as base
from scripts.audit_hotline_first_reallocation import (
    independent_m030_audit,
    normalize_m030_reporting_metrics,
)
from scripts.audit_m026_24h_extension import normalize_full_day_metrics
from scripts.run_hotline_first_reallocation import (
    MANAGEMENT_COVERAGE_MIN_PP,
    MANAGEMENT_STRANDED_REDUCTION_MIN_PCT,
    OUTPUT,
    RESULT,
    ROOT,
    matched_baseline,
)
from scripts.run_l2_monthly_samples import json_hash
from scripts.validate_tardis_l2_samples import MANIFEST
from scripts.validate_tardis_l2_samples import OUTPUT as VALIDATION_REPORT

SOURCE_COMMIT = "459d0237ae9005fd272a91e00de744c21da71435"
EXPECTED_RUN_HASH = "83483b9bfaaeae68f49c23504650a93f7e5701017a7c37a05d416d6095d376ee"
EXPECTED_PHYSICAL_SHA256 = {
    "run-manifest.json": "c68fe9bec2b48714f4a5a998fadd36dd2439dfef98774302cf75d6d41d20489d",
    "execution-audit.jsonl": "afc84dea354415eb1bde0b315258cc250d9edeaeef71913ce1b86b63737e3b66",
    "terminal-engine-state.json": (
        "78f9f4ffe50f618e7848c92eb2972967611acff3a08c1be205cf8740f8eaf59c"
    ),
    "failure.json": "d6a5e59fa62507186de37c3e7b3867d716cee7775bf91a5431c6bf9eb9c341eb",
}


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_bytes())


def _rows(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _git_blob(path: str) -> bytes:
    return subprocess.check_output(["git", "show", f"{SOURCE_COMMIT}:{path}"], cwd=ROOT)


def _lf_hash(raw: bytes) -> str:
    return hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest()


def _jsonable(value: Any) -> Any:
    return json.loads(json.dumps(value, sort_keys=True, default=str))


def _verify_provenance(manifest: dict[str, Any]) -> None:
    if manifest.get("published_config_sha") != SOURCE_COMMIT:
        raise ValueError("M030_RECOVERY_SOURCE_COMMIT")
    if manifest.get("run_hash") != EXPECTED_RUN_HASH:
        raise ValueError("M030_RECOVERY_RUN_HASH")
    if json_hash(manifest["evidence"]) != manifest["evidence_sha256"]:
        raise ValueError("M030_RECOVERY_EVIDENCE_HASH")
    identity = {
        key: value
        for key, value in manifest.items()
        if key not in {"evidence", "run_hash"}
    }
    if json_hash(identity) != EXPECTED_RUN_HASH:
        raise ValueError("M030_RECOVERY_IDENTITY_HASH")
    source_fields = {
        **manifest["source_sha256_lf"],
        "docs/microstructure/M030_HOTLINE_FIRST_REALLOCATION_OWNER_DIRECTIVE.md": manifest[
            "owner_directive_sha256_lf"
        ],
        "docs/microstructure/OWNER_GATED_REPLAY_WINDOW.md": manifest[
            "owner_window_sha256_lf"
        ],
        "docs/microstructure/M030_MODEL_SPEC.json": manifest["spec_sha256_lf"],
        "docs/microstructure/M030_HOTLINE_FIRST_REALLOCATION_PREREGISTRATION.md": manifest[
            "protocol_sha256_lf"
        ],
        "reports/usdcusdt/M030-preflight-independent-review.md": manifest[
            "review_sha256_lf"
        ],
        "docs/research/M030_JOURNAL.md": manifest["pre_run_journal_sha256_lf"],
    }
    for path, expected in source_fields.items():
        if _lf_hash(_git_blob(path)) != expected:
            raise ValueError(f"M030_RECOVERY_PUBLISHED_SOURCE:{path}")
    for name, expected in EXPECTED_PHYSICAL_SHA256.items():
        if file_sha(OUTPUT / name) != expected:
            raise ValueError(f"M030_RECOVERY_PHYSICAL_HASH:{name}")
    failure = _read(OUTPUT / "failure.json")
    if failure != {
        "RUN_STATUS": "INCOMPLETE_PRESERVED",
        "error": "M030_AUDIT_RANDOM_STRANDED",
        "exception_type": "ValueError",
        "ledger_sha256": EXPECTED_PHYSICAL_SHA256["execution-audit.jsonl"],
        "run_hash": EXPECTED_RUN_HASH,
    }:
        raise ValueError("M030_RECOVERY_ORIGINAL_FAILURE_CHANGED")


def _comparison(metrics: dict[str, Any], audit: dict[str, Any]) -> dict[str, Any]:
    baseline = matched_baseline()
    treatment_cycles = int(metrics["M030_EVAL_PHYSICAL_CYCLES"])
    baseline_cycles = int(baseline["PHYSICAL_CYCLES"])
    delta = treatment_cycles - baseline_cycles
    improvement = D(delta) / D(baseline_cycles) * D(100) if baseline_cycles else None
    baseline_coverage = D(baseline["HOT_COVERAGE"]["RANDOM_3H_TIME_WEIGHTED"])
    treatment_coverage = D(metrics["HOT_FUNDING_COVERAGE_RANDOM_3H_TIME_WEIGHTED"])
    coverage_delta_pp = (treatment_coverage - baseline_coverage) * D(100)
    baseline_stranded = D(
        baseline["HOT_COVERAGE"]["RANDOM_3H_RECLAIMABLE_CAPITAL_STRANDED_TIME_PCT"]
    )
    treatment_stranded = D(metrics["RANDOM_3H_RECLAIMABLE_CAPITAL_STRANDED_TIME_PCT"])
    stranded_reduction = (
        (baseline_stranded - treatment_stranded) / baseline_stranded * D(100)
        if baseline_stranded > 0
        else (D(100) if treatment_stranded == 0 else D(-100))
    )
    coverage_pass = coverage_delta_pp >= MANAGEMENT_COVERAGE_MIN_PP
    stranded_pass = (
        treatment_stranded == 0
        if baseline_stranded == 0
        else stranded_reduction >= MANAGEMENT_STRANDED_REDUCTION_MIN_PCT
    )
    return {
        "BASELINE": baseline,
        "TREATMENT": {
            "MODEL": "M030",
            "PHYSICAL_CYCLES": treatment_cycles,
            "PHYSICAL_CYCLES_PER_HOUR": metrics["M030_EVAL_PHYSICAL_CYCLES_PER_HOUR"],
            "SLOT_CYCLES": metrics["M030_EVAL_SLOT_CYCLES"],
            "SLOT_CYCLES_PER_HOUR": metrics["M030_EVAL_SLOT_CYCLES_PER_HOUR"],
            "HOT_COVERAGE_RANDOM_3H_TIME_WEIGHTED": str(treatment_coverage),
            "HOT_COVERAGE_FULL_DAY_TIME_WEIGHTED": metrics[
                "HOT_FUNDING_COVERAGE_TIME_WEIGHTED"
            ],
            "RECLAIMABLE_STRANDED_RANDOM_3H_TIME_PCT": str(treatment_stranded),
        },
        "PHYSICAL_CYCLE_DELTA": delta,
        "PHYSICAL_CYCLE_IMPROVEMENT_PCT": None if improvement is None else str(improvement),
        "FREQUENCY_IMPROVEMENT_PASS": treatment_cycles > baseline_cycles,
        "STRONG_IMPROVEMENT_20PCT_PASS": improvement is not None and improvement >= D(20),
        "MANAGEMENT": {
            "BASELINE_HOT_COVERAGE_RANDOM_3H": str(baseline_coverage),
            "TREATMENT_HOT_COVERAGE_RANDOM_3H": str(treatment_coverage),
            "COVERAGE_DELTA_PERCENTAGE_POINTS": str(coverage_delta_pp),
            "COVERAGE_MINIMUM_PERCENTAGE_POINTS": str(MANAGEMENT_COVERAGE_MIN_PP),
            "COVERAGE_PASS": coverage_pass,
            "BASELINE_RECLAIMABLE_STRANDED_TIME_PCT": str(baseline_stranded),
            "TREATMENT_RECLAIMABLE_STRANDED_TIME_PCT": str(treatment_stranded),
            "STRANDED_REDUCTION_PCT": str(stranded_reduction),
            "STRANDED_REDUCTION_MINIMUM_PCT": str(MANAGEMENT_STRANDED_REDUCTION_MIN_PCT),
            "STRANDED_REDUCTION_PASS": stranded_pass,
            "MANAGEMENT_SUCCESS_PASS": coverage_pass
            and stranded_pass
            and audit["status"].startswith("PASS_"),
        },
    }


def recover() -> dict[str, Any]:
    if RESULT.exists():
        raise ValueError("M030_DERIVED_RESULT_ALREADY_EXISTS")
    manifest = _read(OUTPUT / "run-manifest.json")
    _verify_provenance(manifest)
    terminal = _read(OUTPUT / "terminal-engine-state.json")
    if terminal.get("sha256") != canonical_hash(terminal.get("state")):
        raise ValueError("M030_RECOVERY_TERMINAL_HASH")
    engine = HotlineFirstDynamic321Probe.from_checkpoint(
        terminal, start_us=base.START_US, end_us=base.END_US
    )
    if _jsonable(engine.checkpoint()) != _jsonable(terminal):
        raise ValueError("M030_RECOVERY_CHECKPOINT_ROUNDTRIP")
    rows = _rows(OUTPUT / "execution-audit.jsonl")
    raw_metrics = engine.metrics()
    metrics = normalize_full_day_metrics(raw_metrics, model_id="M030")
    metrics = normalize_m030_reporting_metrics(metrics, rows, DEFAULT_EVALUATION_WINDOWS)
    validation = _read(VALIDATION_REPORT)
    data_manifest = _read(MANIFEST)
    _profile, canonical, _slices, evidence = base.bounded_inputs(data_manifest, validation)
    if len(canonical) != manifest["expected_trade_count"]:
        raise ValueError("M030_RECOVERY_CANONICAL_COUNT")
    audit = independent_m030_audit(
        rows, terminal, metrics, canonical, DEFAULT_EVALUATION_WINDOWS
    )
    audit.update(
        terminal_sha256=terminal["sha256"],
        ledger_sha256=EXPECTED_PHYSICAL_SHA256["execution-audit.jsonl"],
        reporting_recovery="PASS_NO_EVENT_REPLAY",
        canonical_trade_count=len(canonical),
    )
    comparison = _comparison(metrics, audit)
    metrics.update(AUDIT=audit["status"], STATUS="COMPLETE")
    result = {
        **{key: value for key, value in manifest.items() if key != "evidence"},
        "MODEL": "M030",
        "PARENT_STRATEGY": "M026",
        "BASELINE": "M029",
        "PERIOD": "24H_CONTINUOUS_RANDOM_3H_PRIMARY",
        "RUN_STATUS": "COMPLETE_AUDITED_REPORTING_RECOVERY",
        "VERDICT": "INCONCLUSIVE",
        "DISCLAIMER": engine.normalized_label,
        "RANDOM_EVALUATION": {
            "SEED": manifest["random_seed"],
            "HOURS_UTC": manifest["random_hours_utc"],
            "WINDOWS_US": [list(row) for row in DEFAULT_EVALUATION_WINDOWS],
            "MASK_AFFECTS_DECISIONS": False,
        },
        "MATCHED_COMPARISON": comparison,
        "METRICS": metrics,
        "AUDIT": audit,
        "AUDIT_FILE": str(OUTPUT / "execution-audit.jsonl"),
        "REPORTING_RECOVERY": {
            "MODE": "REPORTING_ONLY_NO_EVENT_REPLAY",
            "ORIGINAL_FAILURE_PRESERVED": str(OUTPUT / "failure.json"),
            "ORIGINAL_FAILURE_SHA256": EXPECTED_PHYSICAL_SHA256["failure.json"],
            "PHYSICAL_RUN_HASH_UNCHANGED": EXPECTED_RUN_HASH,
            "SOURCE_COMMIT": SOURCE_COMMIT,
            "EVENTS_DELIVERED_DURING_RECOVERY": 0,
            "ENGINE_METHODS_USED_AFTER_RESTORE": ["checkpoint", "metrics"],
            "CORRECTED_SCOPE": "DERIVED_REPORTING_LABEL_AND_LITERAL_STRANDED_RECONSTRUCTION",
            "ECONOMIC_LEDGER_CHANGED": False,
            "CANONICAL_INPUT_EVIDENCE": evidence,
        },
        "PHYSICAL_EVIDENCE_SHA256": EXPECTED_PHYSICAL_SHA256,
    }
    write_json(OUTPUT / "posthoc-independent-audit.json", audit)
    write_json(OUTPUT / "posthoc-summary.json", result)
    write_json(RESULT, result)
    return result


if __name__ == "__main__":
    value = recover()
    print(
        json.dumps(
            {
                "MODEL": value["MODEL"],
                "RUN_STATUS": value["RUN_STATUS"],
                "RANDOM_3H_CYCLES": value["METRICS"]["M030_EVAL_PHYSICAL_CYCLES"],
                "FULL_DAY_CYCLES": value["METRICS"]["PHYSICAL_CYCLES"],
                "FINAL_EQUITY": value["METRICS"]["FINAL_TOTAL_MARKED"],
                "AUDIT": value["AUDIT"]["status"],
                "EVENT_REPLAY": False,
            },
            sort_keys=True,
        )
    )
