import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location(
    "reserve_dashboard", Path(__file__).parents[1] / "scripts/render_recovery_reserve_dashboard.py"
)
assert _spec is not None and _spec.loader is not None
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)
render = _module.render


def _fixture(tmp_path: Path) -> tuple[Path, Path]:
    artifact = tmp_path / "artifact" / "SCENARIO"
    artifact.mkdir(parents=True)
    audit = {
        "series": [
            {
                "timestamp": "2026-01-01T00:00:00+00:00",
                "operating_bank": "100",
                "reserve": "5",
                "total_equity": "105",
            },
            {
                "timestamp": "2026-01-02T00:00:00+00:00",
                "operating_bank": "99",
                "reserve": "4.99",
                "total_equity": "103.99",
            },
        ],
        "markers": [{"event": 12345678901234567890, "type": "RECOVERY_RELEASE"}],
        "releases": [],
        "replenishments": [],
    }
    audit_path = artifact / "audit.json"
    audit_path.write_text(json.dumps(audit), encoding="utf-8")
    digest = hashlib.sha256(audit_path.read_bytes()).hexdigest()
    (artifact / "completed.json").write_text(
        json.dumps({"artifact_hashes": {"audit.json": digest}}), encoding="utf-8"
    )
    report = tmp_path / "report.json"
    report.write_text(
        json.dumps(
            {
                "artifact_root": str(tmp_path / "artifact"),
                "scenarios": [
                    {
                        "scenario_id": "SCENARIO",
                        "total_final_equity": "103.99",
                        "final_operating_equity": "99",
                        "reserve_final": "4.99",
                    }
                ],
                "baseline": {},
                "identity": {
                    "git_commit_sha": "a" * 40,
                    "start": "2026-01-01",
                    "end": "2026-01-02",
                },
            }
        ),
        encoding="utf-8",
    )
    return report, audit_path


def test_renderer_reads_fixture_and_preserves_event_as_string(tmp_path: Path):
    report, _audit = _fixture(tmp_path)
    output = tmp_path / "dashboard.html"
    render(report, "SCENARIO", output)
    html = output.read_text(encoding="utf-8")
    assert '"event": "12345678901234567890"' in html
    assert html.count("operating_bank") >= 1
    assert html.count("reserve") >= 1
    assert html.count("total_equity") >= 1
    assert "fetch(" not in html and "XMLHttpRequest" not in html


def test_renderer_fails_closed_on_audit_hash(tmp_path: Path):
    report, audit = _fixture(tmp_path)
    audit.write_text(audit.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="DASHBOARD_AUDIT_HASH_MISMATCH"):
        render(report, "SCENARIO", tmp_path / "dashboard.html")
