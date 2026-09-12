#!/usr/bin/env python3
"""Validate and bind the two physical M035 tapes without inspecting strategy PnL."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from crypto_strategy_lab.microstructure.m035_data import validate_dual_tape


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("reports/m035/M035_DUAL_TAPE_VALIDATION.json"),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = args.root.resolve()
    report = validate_dual_tape(root)
    report["sources"] = {
        "L2": "TARDIS_BINANCE_NATIVE_DEPTH_AND_SNAPSHOT",
        "TRADES_NATIVE": "TARDIS_BINANCE_NATIVE_TRADE",
        "TRADES_CANONICAL_BINDING": "BINANCE_VISION_INDIVIDUAL_TRADES",
        "MIXED_SOURCE_DISCLOSURE": True,
    }
    output = args.output if args.output.is_absolute() else root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "window_hash": report["window_hash"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
