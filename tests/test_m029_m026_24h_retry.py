import json
from pathlib import Path

import pytest

import scripts.run_m029_m026_24h_retry as runner
from scripts.audit_m026_24h_extension import normalize_full_day_metrics
from scripts.register_m029_m026_24h_retry import validate_registration_design


def test_owner_gate_accepts_only_m029(tmp_path: Path) -> None:
    authority = tmp_path / runner.OWNER_WINDOW
    authority.parent.mkdir(parents=True)
    authority.write_text(
        "\n".join(
            (
                "APPROVED_COMPARISON_DAYS=1",
                "EXTENSION_AUTHORIZED=false",
                "NEW_REPLAY_AUTHORIZED_NOW=true",
                "AUTHORIZED_MODEL=M029",
                "AUTHORIZED_SCENARIO_COUNT=1",
            )
        ),
        encoding="utf-8",
    )
    runner.require_owner_gate(tmp_path)
    authority.write_text(
        authority.read_text(encoding="utf-8").replace("AUTHORIZED_MODEL=M029", "M028"),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="M029_OWNER_GATE_REQUIRED"):
        runner.require_owner_gate(tmp_path)


def test_m029_design_freezes_only_technical_retry() -> None:
    design = json.loads(runner.SPEC.read_bytes())
    validate_registration_design(design)
    assert design["parent_model_id"] == "M026"
    assert design["technical_failure_predecessor"] == "M028"
    assert design["only_technical_change_from_m028"] == (
        "CANONICAL_JSON_CHECKPOINT_STATE_COMPARISON"
    )
    assert design["runs"] == 1


def test_reporting_accepts_m029_identity() -> None:
    value = normalize_full_day_metrics(
        {
            "INITIAL_TOTAL_MARKED": "156.25220000",
            "FINAL_TOTAL_MARKED": "156.25220000",
            "PHYSICAL_CYCLES": 0,
            "SLOT_EQUIVALENT_CYCLES": 0,
        },
        model_id="M029",
    )
    assert value["MODEL"] == "M029"
    assert value["PERIOD"] == "24H"
    assert value["TOTAL_MARKED_GAIN_PCT"] == "0"
