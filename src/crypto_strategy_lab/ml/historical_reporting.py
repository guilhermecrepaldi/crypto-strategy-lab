from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def write_historical_smoke(payload: dict[str, Any], output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "historical-smoke.json"
    markdown_path = output_dir / "historical-smoke.md"
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n")
    rows = "\n".join(
        f"| {item['duration_days']} | {item['policy']} | {item['seed_count']} | "
        f"{item['return_percent']['mean']} | {item['max_drawdown']['mean']} | "
        f"{item['turnover']['mean']} | {item['fees_usdt']['mean']} | "
        f"{item['spread_usdt']['mean']} | {item['slippage_usdt']['mean']} | "
        f"{item['time_in_usdt_ratio']['mean']} |"
        for item in payload["distributions"]
    )
    markdown_path.write_text(
        "# Crypto Strategy Lab — historical smoke tests\n\n"
        f"Dataset: `{payload['dataset_hash']}`\n\n"
        f"Symbols: `{', '.join(payload['symbols'])}`\n\n"
        f"Seeds: `{payload['seeds']}`. No best-seed selection was performed.\n\n"
        "| Days | Policy | Seeds | Mean return % | Mean max DD | Mean turnover | "
        "Fees | Spread | Slippage | Mean USDT time |\n"
        "|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|\n"
        f"{rows}\n\n"
        "Fees, spread and slippage are enabled. This is a smoke test, not profitability "
        "evidence. `LOCKED_TEST` was not accessed.\n",
        encoding="utf-8",
    )
    return json_path, markdown_path
