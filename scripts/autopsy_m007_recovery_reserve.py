"""Write the retrospective M007 zero-cycle-day autopsy."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from crypto_strategy_lab.microstructure.recovery_reserve_baseline import (
    build_baseline_autopsy,
    write_autopsy_outputs,
)
from crypto_strategy_lab.microstructure.serial_replay import SerialReplayResult


def _load_result(path: Path) -> SerialReplayResult:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict) and isinstance(payload.get("result"), dict):
        payload = payload["result"]
    result = SerialReplayResult.model_validate(payload)
    if result.model_id != "M007":
        raise ValueError("M007_AUTOPSY_REQUIRES_M007")
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("replay_positional", type=Path, nargs="?", help="physical M007 replay JSON")
    parser.add_argument("--replay", dest="replay_option", type=Path)
    parser.add_argument(
        "--json",
        dest="json_path",
        type=Path,
        default=Path("reports/usdcusdt/M011-zero-day-autopsy.json"),
    )
    parser.add_argument(
        "--csv",
        dest="csv_path",
        type=Path,
        default=Path("reports/usdcusdt/M011-zero-day-autopsy.csv"),
    )
    args = parser.parse_args()
    replay_path = args.replay_option or args.replay_positional
    if replay_path is None:
        parser.error("a physical M007 replay JSON is required")
    payload = build_baseline_autopsy(_load_result(replay_path))
    write_autopsy_outputs(payload, args.json_path, args.csv_path)


if __name__ == "__main__":
    main()
