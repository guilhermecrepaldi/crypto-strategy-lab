import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

from crypto_strategy_lab.microstructure.replay_workflow import _persist_completed_replay


def test_completed_replay_is_persisted_immutably_before_downstream_failure(tmp_path: Path) -> None:
    result = SimpleNamespace(model_dump=lambda mode: {"completed_cycles": 7, "final": "raw"})
    path = _persist_completed_replay(
        result, run_root=tmp_path / "run", provenance={"run_hash": "failed", "code_commit": "sha"}
    )
    payload = json.loads(path.read_text(encoding="utf-8"))
    raw = json.dumps(payload["result"], sort_keys=True, separators=(",", ":")).encode()
    assert payload["status"] == "COMPUTATION_COMPLETE_PENDING_VALIDATION"
    assert payload["result_sha256"] == hashlib.sha256(raw).hexdigest()
    before = path.read_bytes()
    try:
        raise ValueError("downstream analysis failed")
    except ValueError:
        pass
    assert path.read_bytes() == before


def test_completed_replay_rejects_divergent_existing_content(tmp_path: Path) -> None:
    result = SimpleNamespace(model_dump=lambda mode: {"value": 1})
    path = _persist_completed_replay(result, run_root=tmp_path / "run", provenance={"run": "x"})
    path.write_text("tampered\n", encoding="utf-8")
    try:
        _persist_completed_replay(result, run_root=tmp_path / "run", provenance={"run": "x"})
    except ValueError as error:
        assert "different content" in str(error)
    else:
        raise AssertionError("divergent completed replay was silently overwritten")
