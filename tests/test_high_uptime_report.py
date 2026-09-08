import hashlib
import json
import xml.etree.ElementTree as ET

import pytest

from scripts import report_high_uptime_recovery as report


def test_capital_curves_and_journal_preserve_evidence(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(report, "reference_count", lambda event: 1000)
    folder = tmp_path / "run"
    folder.mkdir()
    journal = tmp_path / "docs/research/M012_JOURNAL.md"
    journal.parent.mkdir(parents=True)
    journal.write_text("# Original journal\n")
    original = journal.read_bytes()
    row = {
        "CAPITAL_MODE": "COMPOUNDING",
        "RUN_STATUS": "RUNNING",
        "SIMULATION_TIMESTAMP": "2026-01-02T00:00:00+00:00",
        "OPERATING_BANK": "100.95",
        "RESERVE": "5.05",
        "TOTAL_EQUITY": "106",
        "CYCLE_NOTIONAL": "100.95",
        "FULL_FILL_CYCLES": 1,
        "CANONICAL_CUTOFF_EVENT": 1,
    }
    curve_raw = (json.dumps(row) + "\n").encode()
    row["CAPITAL_CURVE_PREFIX"] = {
        "bytes": len(curve_raw),
        "sha256": hashlib.sha256(curve_raw).hexdigest(),
    }
    (folder / "scoreboard.json").write_text(json.dumps(row))
    (folder / "capital-curve.jsonl").write_bytes(curve_raw + b'{"incomplete":')
    result = report.publish(folder, 10, 0)
    assert result["REALITY_RETENTION"] == "0.001"
    assert result["VERDICT"] == "PENDING"
    assert result["OPERATING_BANK"] == "100.95"
    saved = journal.read_bytes()
    assert saved.startswith(original)
    report.publish(folder, 10, 0)
    assert journal.read_bytes() == saved
    for name in ("equity", "operating", "reserve", "notional"):
        svg = (report.ROOT / f"M012-{name}-curve.svg").read_text()
        assert ET.fromstring(svg).tag.endswith("svg")
        assert "<circle" in svg


def test_fixed_primary_report_fails_closed(tmp_path):
    (tmp_path / "scoreboard.json").write_text('{"CAPITAL_MODE":"FIXED_NOTIONAL_100"}')
    with pytest.raises(ValueError, match="FIXED_NOTIONAL_PRIMARY_FORBIDDEN"):
        report.publish(tmp_path)


def test_m014_daily_cycles_separate_releases_and_require_checkpoint(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(report, "reference_count", lambda _: pytest.fail("F0 is not F2.5 control"))
    (tmp_path / "docs/research").mkdir(parents=True)
    folder = tmp_path / "run"
    folder.mkdir()
    (folder / "checkpoint.json").write_bytes(b"{}")
    row = {
        "MODEL_ID": "M014",
        "CAPITAL_MODE": "COMPOUNDING",
        "RUN_STATUS": "RUNNING",
        "CHECKPOINT_REASON": "DAY_1",
        "SIMULATION_TIMESTAMP": "2026-01-02T00:00:00+00:00",
        "OPERATING_BANK": "100.018",
        "RESERVE": "10.002",
        "TOTAL_EQUITY": "110.02",
        "DAILY_FULL_CYCLES": {"2026-01-01": 2},
        "DAILY_NET_POSITIVE_CYCLES": {"2026-01-01": 2},
        "RELEASE_FILLED": 1,
        "FULL_FILL_CYCLES": 2,
        "CANONICAL_CUTOFF_EVENT": 1,
        "CHECKPOINT_SHA256": hashlib.sha256(b"{}").hexdigest(),
    }
    raw = (json.dumps(row) + "\n").encode()
    row["CAPITAL_CURVE_PREFIX"] = {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
    (folder / "capital-curve.jsonl").write_bytes(raw)
    (folder / "scoreboard.json").write_text(json.dumps(row))
    result = report.publish(folder, 7, 0)
    assert result["DAYS_MEETING_2000_TARGET"] == 0
    assert result["REALITY_RETENTION"] is None
    assert result["DAILY_CLOSES"]["2026-01-01"]["FULL_FILL_CYCLES"] == 2
    text = (report.ROOT / "M014-reality-report.md").read_text(encoding="utf-8")
    assert "100.018000 | 10.002000 | 110.020000 | 2 | 2 | 1" in text
    row["RUN_STATUS"] = "COMPLETE"
    (folder / "scoreboard.json").write_text(json.dumps(row))
    audit = {
        "status": "PASS_CONDITIONAL",
        "scoreboard_sha256": hashlib.sha256((folder / "scoreboard.json").read_bytes()).hexdigest(),
        "checkpoint_sha256": row["CHECKPOINT_SHA256"],
        "ordinary_audited_raw": 2,
    }
    (folder / "independent-audit.json").write_text(json.dumps(audit))
    audited = report.publish(folder, 7, 0)
    assert audited["INDEPENDENT_RUN_AUDIT"] == "PASS_CONDITIONAL"
    assert "AWAITING_OWNER_APPROVAL" in audited["VERDICT"]
    audit["scoreboard_sha256"] = "tampered"
    (folder / "independent-audit.json").write_text(json.dumps(audit))
    with pytest.raises(ValueError, match="INDEPENDENT_AUDIT_BINDING_MISMATCH"):
        report.publish(folder)
    (folder / "checkpoint.json").write_bytes(b'{"changed":true}')
    with pytest.raises(ValueError, match="CHECKPOINT_SCOREBOARD_BINDING_MISMATCH"):
        report.publish(folder)


def test_curve_rejects_tampered_prefix(tmp_path):
    path = tmp_path / "curve.jsonl"
    path.write_bytes(b"{}\n")
    with pytest.raises(ValueError, match="CAPITAL_CURVE_PREFIX_HASH_MISMATCH"):
        report.read_curve_prefix(path, {"bytes": 3, "sha256": "bad"})
