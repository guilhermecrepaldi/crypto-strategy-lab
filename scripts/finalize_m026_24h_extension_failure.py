"""Register M028's preserved prefix-gate failure without replaying market events."""

from __future__ import annotations

import json
from decimal import Decimal as D
from pathlib import Path

from crypto_strategy_lab.domain import canonical_hash
from crypto_strategy_lab.microstructure.recovery_reserve_study import file_sha, write_json
from crypto_strategy_lab.ml.model_registry import BackendSpec, ModelRegistry, ModelStatus, RunSpec
from scripts.run_m026_24h_extension import OUTPUT, PARENT_LEDGER, PARENT_RESULT

SOURCE_COMMIT = "915cc44c3957dba467bc758dbe9adf81e484b468"
EXPECTED_CAMPAIGN_RUN_HASH = "cd0870708011efd12dd807b06cc68ad7fc025744b402459dcd3b50a4d1f025a3"
EXPECTED_LEDGER_SHA256 = "7d3fc1e67a41395c353009e829d1288562f8f25eb4554c3f2cf4db9743fd4bb8"
FAILURE_REPORT = Path("reports/usdcusdt/M028-technical-failure.json")


def build_failure_record() -> dict:
    """Reconcile the preserved artifacts and describe only the reached prefix."""
    manifest_path = OUTPUT / "run-manifest.json"
    ledger_path = OUTPUT / "execution-audit.jsonl"
    failure_path = OUTPUT / "failure.json"
    manifest = json.loads(manifest_path.read_bytes())
    failure = json.loads(failure_path.read_bytes())
    parent = json.loads(PARENT_RESULT.read_bytes())
    parent_metrics = parent["METRICS"]

    if (
        manifest.get("model_id") != "M028"
        or manifest.get("published_config_sha") != SOURCE_COMMIT
        or manifest.get("run_hash") != EXPECTED_CAMPAIGN_RUN_HASH
        or failure.get("run_hash") != EXPECTED_CAMPAIGN_RUN_HASH
        or failure.get("RUN_STATUS") != "INCOMPLETE_PRESERVED"
        or failure.get("error") != "M028_M026_PREFIX_ECONOMIC_STATE_MISMATCH"
        or file_sha(ledger_path) != EXPECTED_LEDGER_SHA256
        or file_sha(PARENT_LEDGER) != EXPECTED_LEDGER_SHA256
        or ledger_path.read_bytes() != PARENT_LEDGER.read_bytes()
    ):
        raise ValueError("M028_TECHNICAL_FAILURE_EVIDENCE_MISMATCH")

    physical_files = {
        str(path): file_sha(path) for path in (manifest_path, ledger_path, failure_path)
    }
    snapshot_id = canonical_hash(
        {
            "classification": "INVALIDATED_TECHNICAL",
            "physical_files": physical_files,
            "post_03h_events_processed": 0,
        }
    )
    initial = D(parent_metrics["INITIAL_TOTAL_MARKED"])
    prefix_final = D(parent_metrics["FINAL_TOTAL_MARKED"])
    return {
        "MODEL": "M028",
        "MODEL_STATUS": "INVALIDATED_TECHNICAL",
        "RUN_STATUS": "INCOMPLETE_PRESERVED_PREFIX_GATE_FAILURE",
        "CLASSIFICATION": "BUG_TECNICO_NO_COMPARADOR_DE_CHECKPOINT",
        "AUTHORIZED_PERIOD": "2025-01-01T00:00:00Z/2025-01-02T00:00:00Z",
        "REACHED_PERIOD": "2025-01-01T00:00:00Z/2025-01-01T03:00:00Z",
        "EVENTS_AFTER_03H_PROCESSED": 0,
        "FULL_DAY_RESULT_AVAILABLE": False,
        "FULL_DAY_INITIAL_MARKED_EQUITY": str(initial),
        "FULL_DAY_FINAL_MARKED_EQUITY": None,
        "FULL_DAY_GAIN_ABSOLUTE": None,
        "FULL_DAY_GAIN_PERCENT": None,
        "M026_PREFIX_INITIAL_MARKED_EQUITY": str(initial),
        "M026_PREFIX_FINAL_MARKED_EQUITY": str(prefix_final),
        "M026_PREFIX_GAIN_ABSOLUTE": str(prefix_final - initial),
        "M026_PREFIX_GAIN_PERCENT": str((prefix_final / initial - D(1)) * D(100)),
        "M026_PREFIX_PHYSICAL_CYCLES": parent_metrics["PHYSICAL_CYCLES"],
        "M026_PREFIX_SLOT_EQUIVALENT_CYCLES": parent_metrics["SLOT_EQUIVALENT_CYCLES"],
        "PREFIX_LEDGER_EXACT_BYTE_MATCH": True,
        "PREFIX_LEDGER_SHA256": EXPECTED_LEDGER_SHA256,
        "FAILURE": failure,
        "ROOT_CAUSE_DIAGNOSIS": (
            "The prefix gate compared an in-memory checkpoint containing Decimal values "
            "and integer dictionary keys with its JSON-deserialized published checkpoint, "
            "where those values and keys are strings. This representation defect was "
            "reproduced diagnostically and the economic ledger is byte-identical."
        ),
        "DIAGNOSTIC_LIMITATION": (
            "The failed process did not persist the rejected in-memory checkpoint, so the "
            "preserved physical artifacts cannot prove that representation differences were "
            "the only non-ledger state differences."
        ),
        "CORRECTIVE_ACTION_NOT_EXECUTED": (
            "Canonicalize both checkpoint states through the same JSON representation "
            "before the semantic equality check. A new authorized identity is required."
        ),
        "RERUN_PERFORMED": False,
        "EVENT_REPLAY_DURING_FINALIZATION": False,
        "CAMPAIGN_SNAPSHOT_ID": snapshot_id,
        "PHYSICAL_FILE_SHA256": physical_files,
    }


def finalize() -> dict:
    """Write the failure report and append terminal registry evidence."""
    record = build_failure_record()
    registry = ModelRegistry()
    if registry.current_status("M028") != ModelStatus.CREATED:
        raise ValueError("M028_FAILURE_FINALIZATION_REQUIRES_CREATED_STATUS")

    scenario_event = registry.append_scenario(
        "M028",
        {
            "scenario": {
                "name": "M028_M026_FULL_DAY_ATTEMPT_INVALIDATED_AT_3H_GATE",
                "execution_profile": "B_REALISTIC_CONSERVATIVE",
                "execution_envelope": "PRICE_PRIORITY",
                "initial_marked_equity": record["FULL_DAY_INITIAL_MARKED_EQUITY"],
                "capital_mode": "NORMALIZED_MECHANICS_PROBE",
                "campaign_run_hash": EXPECTED_CAMPAIGN_RUN_HASH,
                "completed": False,
            }
        },
    )
    manifest = json.loads((OUTPUT / "run-manifest.json").read_bytes())
    run_event = registry.append_run(
        "M028",
        RunSpec(
            scenario_hash=scenario_event["payload"]["SCENARIO_HASH"],
            dataset_hash=manifest["evidence"]["validation"]["input_sha256"],
            campaign_snapshot_id=record["CAMPAIGN_SNAPSHOT_ID"],
            interval={
                "authorized_start": "2025-01-01T00:00:00Z",
                "authorized_end_exclusive": "2025-01-02T00:00:00Z",
                "reached_end_exclusive": "2025-01-01T03:00:00Z",
                "complete": False,
            },
            code_commit=SOURCE_COMMIT,
            technical_revision="M028_PREFIX_CHECKPOINT_TYPE_COMPARATOR_FAILURE",
            backend=BackendSpec(backend="CPU"),
            initial_capital=D(record["FULL_DAY_INITIAL_MARKED_EQUITY"]),
            capital_mode="NORMALIZED_MECHANICS_PROBE",
            run={
                "artifact_directory": str(OUTPUT),
                "campaign_run_hash": EXPECTED_CAMPAIGN_RUN_HASH,
                "classification": "INVALIDATED_TECHNICAL",
                "post_03h_events_processed": 0,
                "event_replay_during_finalization": False,
            },
        ),
    )
    registry.transition(
        "M028",
        ModelStatus.RUNNING,
        reason="Register the preserved prefix reached by the only authorized M028 attempt",
    )
    registry.transition(
        "M028",
        ModelStatus.INVALIDATED_TECHNICAL,
        reason=(
            "Prefix economic ledger matched M026 exactly, but a Decimal/int-key versus "
            "JSON string-type checkpoint comparison falsely rejected the state before 03h+"
        ),
    )
    record["REGISTRY_RUN_HASH"] = run_event["payload"]["RUN_HASH"]
    write_json(FAILURE_REPORT, record)
    return record


if __name__ == "__main__":
    value = finalize()
    print(
        json.dumps(
            {
                "MODEL": value["MODEL"],
                "MODEL_STATUS": value["MODEL_STATUS"],
                "EVENTS_AFTER_03H_PROCESSED": value["EVENTS_AFTER_03H_PROCESSED"],
                "FULL_DAY_RESULT_AVAILABLE": value["FULL_DAY_RESULT_AVAILABLE"],
                "RERUN": value["RERUN_PERFORMED"],
            },
            sort_keys=True,
        )
    )
