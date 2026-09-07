"""Read-only comparison rendering and status/precision separation."""

import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/render_recovery_reserve_dashboard.py"
SPEC = importlib.util.spec_from_file_location("recovery_dashboard", SCRIPT)
assert SPEC and SPEC.loader
dashboard = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(dashboard)


@pytest.fixture
def evidence(tmp_path):
    def put(name, value):
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding="utf-8")

    models = [
        {
            "model_id": mid,
            "model": config,
            "hypothesis": {},
            "lineage": {},
            "status": status,
            "model_hash": mid,
        }
        for mid, status, config in [
            ("M001", "SUPERSEDED", {}),
            ("M011", "CREATED", {"total_initial_equity": "105"}),
        ]
    ]
    put("reports/usdcusdt/model-registry.json", {"models": models, "events": []})
    base = {
        key: "0"
        for key in [
            "operating_equity",
            "reserve",
            "total_equity",
            "max_hold_hours",
            "lock_hours",
            "operating_uptime",
            "maximum_drawdown",
        ]
    }
    base.update(path="baseline.json", cycles=344704, zero_cycle_days=193, active_days=55)
    put(
        "reports/usdcusdt/OWNER-strategy-transition-evidence.json",
        {"run": {"path": "artifacts/usdcusdt/recovery-reserve/current"}, "baseline": base},
    )
    for filename in [
        "M010-capital-release.json",
        "M010-event-id-failure.json",
        "M011-recovery-reserve-precision-audit.json",
    ]:
        put("reports/usdcusdt/" + filename, {})
    protocol = tmp_path / "docs/microstructure/RECOVERY_DYNAMIC_PREREGISTRATION.md"
    protocol.parent.mkdir(parents=True)
    protocol.write_text("<script>not code</script>", encoding="utf-8")
    summary = {
        "completed_cycles": 7,
        "integrity_pass": True,
        "final_total_equity": "1000000000000000000000.123456789",
        "monthly": {},
    }
    for identity in ["current", "older"]:
        directory = "artifacts/usdcusdt/recovery-reserve/" + identity
        put(directory + "/identity.json", {"schema": "recovery-reserve-study-2"})
        put(
            directory + "/RR_TEST/completed.json",
            {"summary": summary, "identity": {"reserve_config": {}}, "artifact_hashes": {}},
        )
    put("artifacts/usdcusdt/recovery-reserve/current/PARTIAL/checkpoint.json", {})
    return tmp_path


def test_unrun_models_are_not_zero_performance(evidence):
    rows = dashboard.collect_comparison(evidence)["rows"]
    new = next(r for r in rows if r["id"] == "M011")
    assert new["initial"] == "105"
    assert new["status"] == "NOT_RUN"
    assert "cycles" not in new and "equity" not in new
    old = next(r for r in rows if r["id"] == "M001")
    assert old["group"] == "historico"


def test_old_attempts_and_partials_are_separate(evidence):
    rows = dashboard.collect_comparison(evidence)["rows"]
    assert next(r for r in rows if "older" in r["id"])["group"] == "historico"
    partial = next(r for r in rows if r["status"] == "PARCIAL")
    assert "equity" not in partial and "cycles" not in partial


def test_renderer_preserves_exact_values_and_escapes_script(evidence):
    before = {p: p.read_bytes() for p in evidence.rglob("*.json")}
    output = evidence / "comparison.html"
    result = dashboard.render_comparison(evidence, output)
    text = output.read_text(encoding="utf-8")
    assert "1000000000000000000000.123456789" in text
    assert "&lt;script&gt;not code&lt;/script&gt;" in text
    assert "__PAYLOAD__" not in text
    assert 'type="radio" name="strategy"' in text
    assert '<tbody id="results"><tr ' in text
    assert 'class="strategy-panel"' in text
    assert "Resultado exato" in text
    assert "1000000000000000000000.123456789" in text.split("</main>")[0]
    assert len(result["failures"]) == 2
    assert all(p.read_bytes() == content for p, content in before.items())


def test_graphs_are_populated_without_running_javascript(evidence):
    data = dashboard.collect_comparison(evidence)
    data["rows"].append(
        {
            "id": "fixture",
            "strategy": "M011",
            "family": "fixture",
            "group": "principal",
            "status": "CONCLUÍDO",
            "cycles": 123,
            "zero": 4,
            "lock": "7.5",
            "note": "fixture",
        }
    )
    template = SCRIPT.with_name("recovery_comparison.html").read_text(encoding="utf-8")
    text = dashboard.static_comparison(data, template).split("</main>")[0]
    assert text.count('class="chart"') == 3
    assert text.count('class="bar"') >= 3
    assert "fixture" in text and "123" in text
    assert "<strong>4</strong>" in text
    assert "<strong>7,5</strong>" in text
    assert "document.createElement" not in text
