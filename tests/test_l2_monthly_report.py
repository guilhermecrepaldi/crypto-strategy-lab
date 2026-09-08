import json

import pytest

from scripts import report_l2_monthly_samples as report


def manifest():
    return {
        "dates": [
            {"date": day, "status": "AVAILABLE", "rows": 100, "bytes": 50}
            for day in report.candidates()
        ]
    }


def test_no_replay_is_not_zero_cycles_and_years_are_separate(tmp_path):
    score = report.build(manifest(), results_root=tmp_path)
    assert len(score["rows"]) == 42
    assert all(row["NET_POSITIVE_CYCLES"] is None for row in score["rows"])
    groups = score["aggregates"]["CONSERVATIVE_QUEUE"]
    assert groups["CALIBRATION"]["TOTAL_INDEPENDENT_DAYS"] == 12
    assert groups["EVALUATION"]["TOTAL_INDEPENDENT_DAYS"] == 9
    assert groups["COMBINED"]["MEDIAN_CYCLES_PER_DAY"] is None
    assert groups["COMBINED"]["DAYS_WITH_ZERO_CYCLES"] == 0
    assert "PENDING_DATA_VALIDATION" in report.render(score)


def test_results_require_matching_day_validation_evidence(tmp_path):
    day, envelope = "2026-01-01", "CONSERVATIVE_QUEUE"
    output = tmp_path / day / envelope
    output.mkdir(parents=True)
    (output / "summary.json").write_text(
        json.dumps(
            {
                "DATE": day,
                "ENVELOPE": envelope,
                "STRATEGY_MODEL_USED": "M015",
                "MODEL_HASH": report.MODEL_HASH,
                "VALIDATION_INPUT_SHA256": "wrong",
            }
        )
    )
    validation = {"days": [{"date": day, "L2_DAY_VALID": True, "input_sha256": "expected"}]}
    with pytest.raises(ValueError, match="VALIDATION_BINDING_MISMATCH"):
        report.build(manifest(), validation, results_root=tmp_path)
