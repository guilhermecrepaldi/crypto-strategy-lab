import json
from pathlib import Path

from scripts import report_b10_reality as report


def payload():
    return {
        "strategy": "B10_FROZEN",
        "run_id": "run",
        "profile": "A",
        "profile_name": "A_TEST",
        "status": "RUNNING",
        "updated_at": "2026-09-07T23:00:00+00:00",
        "simulation_timestamp": "2026-03-01T12:00:00+00:00",
        "progress_percent": "25",
        "full_fill_cycles": 1128,
        "net_positive_cycles": 1100,
        "price_path_opportunities_same_prefix": 1474430,
        "net_pnl_fixed_100": "12.30",
        "reserve_final": "4.2",
        "release_filled": 27,
        "zero_cycle_days_so_far": 4,
        "max_hold": "28",
        "lock_hours": "5",
        "max_drawdown": "0.01",
        "execution_source_commit": "a918",
        "evidence": {"checkpoint_sha256": "snapshot1", "checkpoint_path": "run/checkpoint.json"},
        "verdict": "PENDING",
    }


def test_checkpoint_parser_enriches_without_mixing_audit_scope(tmp_path, monkeypatch):
    folder = tmp_path / "runs" / "A_TEST"
    folder.mkdir(parents=True)
    (folder / "checkpoint.json").write_text("{}")
    monkeypatch.setattr(report, "read_checkpoint", lambda *a, **kw: payload())
    audit = tmp_path / "audit.json"
    audit.write_text(
        json.dumps(
            {
                "status": "PASS_PRELIMINARY_DURABLE_PREFIX_ONLY",
                "checkpoint_sha256": "older",
                "ordinary_raw_sample": 100,
                "release_settlements": 13,
            }
        )
    )
    result = report.build_scoreboard(
        Path("unused"), tmp_path / "runs", audit_path=audit, head="observed"
    )
    assert result["full_fill_cycles"] == 1128
    assert result["software_tests"]["passed"] == 93
    assert result["verdict"] == "PENDING"
    assert not result["independent_audit"]["covers_current_checkpoint"]
    rendered = report.render_markdown(result)
    assert rendered.startswith("# B10 REALITY — CURRENT SCOREBOARD\n")
    assert "| Net PnL US$100 | 12.300000 |" in rendered
    assert rendered.index("12.30") < rendered.index("93 passaram")
    assert "under pressure" in rendered
    assert rendered.count("\n## ") == 5
    current = report.render_current(result)
    assert "SOFTWARE_VALIDATION=PASS" in current
    assert "STRATEGY_RESULT=PENDING" in current
    completed = payload()
    completed["verdict"] = "INCONCLUSIVE_EXECUTION_DATA"
    monkeypatch.setattr(report, "read_checkpoint", lambda *a, **kw: completed)
    result = report.build_scoreboard(
        Path("unused"), tmp_path / "runs", audit_path=audit, head="observed"
    )
    assert result["verdict"] == "INCONCLUSIVE_EXECUTION_DATA"
    assert "STRATEGY_RESULT=INCONCLUSIVE_EXECUTION_DATA" in report.render_current(result)


def test_journal_append_is_idempotent_and_preserves_history(tmp_path):
    result = payload()
    path = tmp_path / "journal.md"
    assert report.append_journal(path, result)
    original = path.read_bytes()
    assert not report.append_journal(path, result)
    assert path.read_bytes() == original
    result["evidence"]["checkpoint_sha256"] = "snapshot2"
    assert report.append_journal(path, result)
    assert path.read_bytes().startswith(original)
    assert path.read_text().count("\n## ") == 2
