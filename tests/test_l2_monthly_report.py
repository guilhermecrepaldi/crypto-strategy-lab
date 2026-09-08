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


def test_aggregate_counts_audited_days_only_and_never_compounds_returns():
    def result(day, cycles, pnl, audit="PASS_CONDITIONAL"):
        return dict(
            DATE=day,
            RUN_STATUS="COMPLETE",
            AUDIT_STATUS=audit,
            L2_VALID=True,
            NET_POSITIVE_CYCLES=cycles,
            DAILY_RETURN=str(pnl),
            HARD_LOCK_VIOLATIONS=0,
        )

    rows = [
        result("2025-01-01", 0, "0.1"),
        result("2025-02-01", 500, "0.2"),
        result("2025-03-01", 2000, "0.3"),
        result("2025-04-01", 9999, "9", "FAIL"),
    ]
    stats = report.aggregate(rows)
    assert stats["AUDITED_COMPLETED_DAYS"] == 3
    assert stats["MEDIAN_CYCLES_PER_DAY"] == 500
    assert stats["DAYS_GE500"] == 2 and stats["DAYS_GE2000"] == 1
    assert stats["DAYS_WITH_ZERO_CYCLES"] == 1
    assert stats["MEDIAN_NET_RETURN"] == "0.2"
    assert stats["BEST_DAY"] == "2025-03-01"
    assert stats["P10_CYCLES_PER_DAY"] == 0 and stats["P90_CYCLES_PER_DAY"] == 2000
