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


def test_missing_results_are_null_and_only_first_day_has_initial_capital(tmp_path):
    score = report.build(manifest(), results_root=tmp_path)
    assert len(score["inventory"]) == 21 and len(score["rows"]) == 24
    assert all(row["DAILY_NET_POSITIVE_CYCLES"] is None for row in score["rows"])
    assert all(
        row["OPERATING_START"] == ("100" if row["LOGICAL_DAY"] == 1 else None)
        for row in score["rows"]
    )
    assert score["REPLAY_MODE"] == report.SYNTHETIC_STATE
    assert report.render(score).count("## CONSERVATIVE_QUEUE") == 1
    assert report.render(score).count("## PRICE_PRIORITY") == 1


def write_day(root, number, **kwargs):
    path = root / "daily" / f"{number:02d}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "LOGICAL_DAY": number,
                "SOURCE_DATE": report.SYNTHETIC_SOURCE_DATES[number - 1],
                "ENVELOPE": "CONSERVATIVE_QUEUE",
                **kwargs,
            }
        )
    )


def test_carry_is_evidence_not_daily_reset_and_partial_is_not_pass(tmp_path):
    root = tmp_path / report.SYNTHETIC_STATE / "CONSERVATIVE_QUEUE"
    write_day(
        root,
        1,
        OPERATING_START="100",
        RESERVE_START="10",
        OPERATING_FINAL="103",
        RESERVE_FINAL="11",
        DAILY_NET_POSITIVE_CYCLES=2,
    )
    write_day(
        root,
        2,
        OPERATING_START="103",
        RESERVE_START="11",
        OPERATING_FINAL="104",
        RESERVE_FINAL="11.2",
        DAILY_NET_POSITIVE_CYCLES=1,
        AUDIT_STATUS="PASS_CONDITIONAL",
    )
    score = report.build(manifest(), results_root=tmp_path)
    assert score["rows"][1]["OPERATING_START"] == "103"
    assert score["rows"][1]["AUDIT_STATUS"] == "AUDIT_PENDING"
    assert score["rows"][2]["OPERATING_START"] is None
    assert score["aggregates"]["CONSERVATIVE_QUEUE"]["AUDITED_DAYS"] == 0
    write_day(root, 2, OPERATING_START="100", RESERVE_START="10")
    with pytest.raises(ValueError, match="CAPITAL_CARRY_MISMATCH"):
        report.build(manifest(), results_root=tmp_path)


def test_wrong_day_identity_rejected(tmp_path):
    root = tmp_path / report.SYNTHETIC_STATE / "CONSERVATIVE_QUEUE"
    write_day(root, 1, SOURCE_DATE="2025-11-01")
    with pytest.raises(ValueError, match="SYNTHETIC_IDENTITY"):
        report.build(manifest(), results_root=tmp_path)


def test_terminal_aggregate_uses_last_equity_not_peak_and_twelve_not_twentyfour():
    rows = [
        {
            "LOGICAL_DAY": day,
            "DAILY_NET_POSITIVE_CYCLES": day * 100,
            "TOTAL_EQUITY_FINAL": "200" if day == 1 else "121",
        }
        for day in range(1, 13)
    ]
    terminal = {"AUDIT_STATUS": "PASS_CONDITIONAL", "TOTAL_EQUITY_FINAL": "121"}
    result = report.aggregate(rows, terminal)
    assert result["AUDITED_DAYS"] == 12
    assert result["FINAL_EQUITY"] == "121" and result["SYNTHETIC_STRESS_RETURN"] == "0.1"
    assert result["MEDIAN_CYCLES"] == 650 and result["DAYS_GE500"] == 8
    assert result["BEST_DAY"] == 12 and result["WORST_DAY"] == 1
    assert report.aggregate(rows, None)["AUDIT_STATUS"] == "AUDIT_PENDING"


def test_terminal_mapping_and_audit_binding_gate(tmp_path):
    root = tmp_path / report.SYNTHETIC_STATE / "CONSERVATIVE_QUEUE"
    root.mkdir(parents=True)
    (root / "summary.json").write_text(
        json.dumps(
            {
                "MODEL_HASH": report.MODEL_HASH,
                "ENVELOPE": "CONSERVATIVE_QUEUE",
                "RUN_STATUS": "COMPLETE",
                "source_day_mapping": [],
            }
        )
    )
    with pytest.raises(ValueError, match="TERMINAL_IDENTITY"):
        report.build(manifest(), results_root=tmp_path)
