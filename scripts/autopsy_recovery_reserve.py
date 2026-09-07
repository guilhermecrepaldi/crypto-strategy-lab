"""Post-process a completed recovery-reserve report (never mutates evidence)."""

from __future__ import annotations

import argparse
import gzip
import json
from decimal import Decimal
from pathlib import Path
from typing import Any

from crypto_strategy_lab.domain import canonical_hash
from crypto_strategy_lab.microstructure import recovery_reserve_autopsy
from crypto_strategy_lab.microstructure.recovery_reserve_study import file_sha, write_json
from crypto_strategy_lab.microstructure.serial_replay import SerialReplayResult


def _load_replay(path: Path) -> SerialReplayResult:
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        payload = json.load(stream)
    return SerialReplayResult.model_validate(payload)


def _scenario_id(config: dict[str, Any]) -> str:
    skim = Decimal(str(config["skim_rate"]))
    lock = int(config["lock_hours"])
    loss = Decimal(str(config["max_loss_bps"]))
    if "reserve_floor" in config:
        floor = Decimal(str(config["reserve_floor"]))
        return f"RRV2_H{lock}_B{loss:g}_F{floor:g}"
    return f"RR_S{skim * 100:g}_H{lock}_B{loss:g}"


def build_autopsy(report_path: Path) -> dict[str, Any]:
    report = json.loads(report_path.read_text(encoding="utf-8"))
    rows = report.get("scenarios")
    grid = report.get("identity", {}).get("grid")
    if not isinstance(rows, list) or not isinstance(grid, list) or len(rows) != len(grid):
        raise ValueError("AUTOPSY_REPORT_REQUIRES_COMPLETE_GRID")
    root = Path(report["artifact_root"])
    root_identity = json.loads((root / "identity.json").read_text(encoding="utf-8"))
    if root_identity != report["identity"]:
        raise ValueError("AUTOPSY_ROOT_IDENTITY_MISMATCH")
    configs = [dict(item) for item in grid]
    expected_ids = {_scenario_id(config) for config in configs}
    actual_ids = {str(row.get("scenario_id")) for row in rows}
    if actual_ids != expected_ids or len(actual_ids) != len(configs):
        raise ValueError("AUTOPSY_GRID_IDENTITY_MISMATCH")
    output_rows: list[dict[str, Any]] = []
    for config in configs:
        scenario_id = _scenario_id(config)
        row = next(item for item in rows if item.get("scenario_id") == scenario_id)
        path = root / scenario_id
        completion_path = path / "completed.json"
        completion = json.loads(completion_path.read_text(encoding="utf-8"))
        payload_hash = completion.get("payload_sha256")
        payload = {key: value for key, value in completion.items() if key != "payload_sha256"}
        if payload_hash != canonical_hash(payload):
            raise ValueError("AUTOPSY_COMPLETION_HASH_MISMATCH")
        expected_identity = {**report["identity"], "reserve_config": config}
        if payload.get("identity") != expected_identity:
            raise ValueError("AUTOPSY_SCENARIO_IDENTITY_MISMATCH")
        if payload.get("summary") != row:
            raise ValueError("AUTOPSY_SUMMARY_MISMATCH")
        artifact_hashes = payload.get("artifact_hashes", {})
        for filename in ("audit.json", "runtime.json"):
            if file_sha(path / filename) != artifact_hashes.get(filename):
                raise ValueError("AUTOPSY_ARTIFACT_HASH_MISMATCH")
        replay_hash = file_sha(path / "replay.json.gz")
        if replay_hash != payload.get("replay_sha256"):
            raise ValueError("AUTOPSY_REPLAY_HASH_MISMATCH")
        audit = json.loads((path / "audit.json").read_text(encoding="utf-8"))
        result = _load_replay(path / "replay.json.gz")
        diagnostics = recovery_reserve_autopsy.release_autopsy(
            result, audit["releases"], audit["replenishments"]
        )
        output_rows.append(
            {
                "scenario_id": scenario_id,
                "replay_sha256": replay_hash,
                "audit_sha256": file_sha(path / "audit.json"),
                "release_autopsy": diagnostics,
            }
        )
    return {
        "classification": "RETROSPECTIVE_DIAGNOSTIC_ONLY",
        "input_report_sha256": file_sha(report_path),
        "study_code_sha": report["identity"]["git_commit_sha"],
        "autopsy_cli_sha256": file_sha(Path(__file__)),
        "release_autopsy_module_sha256": file_sha(Path(recovery_reserve_autopsy.__file__)),
        "scenarios": output_rows,
        "NO_AGGREGATE_SUM": True,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("reports/usdcusdt/M011-recovery-reserve-scenarios.json"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("reports/usdcusdt/M011-recovery-reserve.json"),
    )
    args = parser.parse_args()
    write_json(args.output, build_autopsy(args.report))


if __name__ == "__main__":
    main()
