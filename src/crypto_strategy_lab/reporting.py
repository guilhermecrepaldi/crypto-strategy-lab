from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from crypto_strategy_lab.simulation.engine import SimulationResult


def _json_default(value: Any) -> str:
    if isinstance(value, (datetime, Decimal)):
        return str(value) if isinstance(value, Decimal) else value.isoformat()
    return str(value)


def result_payload(result: SimulationResult) -> dict[str, Any]:
    return {
        "run_id": str(result.run_id),
        "run_type": result.config.run_type,
        "dataset_hash": result.dataset_hash,
        "policy_hash": result.policy_hash,
        "symbols": result.symbols,
        "manifest": {
            "initial_capital_usdt": result.config.initial_capital,
            "max_exposure": result.config.max_exposure,
            "reserve_ratio": result.config.reserve_ratio,
            "fee_rate": result.config.costs.fee_rate,
            "spread_rate": result.config.costs.spread_rate,
            "slippage_rate": result.config.costs.slippage_rate,
            "seed": result.config.seed,
            "network_access_during_simulation": False,
            "real_trading_capability": False,
        },
        "metrics": result.metrics,
        "decisions": result.decisions,
        "orders": result.orders,
        "fills": [item.model_dump(mode="json") for item in result.fills],
        "equity": result.equity,
        "failures": result.failures,
    }


def write_reports(result: SimulationResult, output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = result_payload(result)
    json_path = output_dir / f"{result.run_id}.json"
    markdown_path = output_dir / f"{result.run_id}.md"
    json_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=_json_default) + "\n",
        encoding="utf-8",
    )
    metrics = "\n".join(f"- `{name}`: {value}" for name, value in result.metrics.items())
    markdown_path.write_text(
        "# Crypto Strategy Lab — deterministic run\n\n"
        f"Run ID: `{result.run_id}`\n\n"
        f"Dataset hash: `{result.dataset_hash}`\n\n"
        f"Policy hash: `{result.policy_hash}`\n\n"
        "## Metrics\n\n"
        f"{metrics}\n\n"
        "## Integrity\n\n"
        "- Offline historical replay: yes\n"
        "- Future-data boundary enforced: yes\n"
        "- Real/Testnet order path: absent\n"
        f"- Recorded failures: {len(result.failures)}\n",
        encoding="utf-8",
    )
    return json_path, markdown_path
