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


def test_curve_rejects_tampered_prefix(tmp_path):
    path = tmp_path / "curve.jsonl"
    path.write_bytes(b"{}\n")
    with pytest.raises(ValueError, match="CAPITAL_CURVE_PREFIX_HASH_MISMATCH"):
        report.read_curve_prefix(path, {"bytes": 3, "sha256": "bad"})
