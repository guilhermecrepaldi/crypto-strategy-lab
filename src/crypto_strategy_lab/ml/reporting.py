from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def write_ml_reports(payload: dict[str, Any], output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    model_id = str(payload["training"]["model_id"])
    json_path = output_dir / f"rl-{model_id}.json"
    markdown_path = output_dir / f"rl-{model_id}.md"
    json_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    evaluation = payload["evaluation"]
    baseline_lines = "\n".join(
        f"- `{item['policy']}`: {item['final_equity_usdt']} USDT" for item in payload["baselines"]
    )
    markdown_path.write_text(
        "# Crypto Strategy Lab — short RL run\n\n"
        f"Model: `{model_id}` ({payload['training']['algorithm']})\n\n"
        f"Training steps: `{payload['training']['timesteps']}`\n\n"
        "## Validation fixture\n\n"
        f"- Final equity: `{evaluation['final_equity_usdt']} USDT`\n"
        f"- Total reward: `{evaluation['total_reward']}`\n"
        f"- Actions: `{evaluation['actions']}`\n\n"
        "## Baselines\n\n"
        f"{baseline_lines}\n\n"
        "## Interpretation\n\n"
        "This is a deterministic plumbing test on a tiny synthetic fixture. It is not "
        "profitability evidence and the locked test partition was not used.\n",
        encoding="utf-8",
    )
    return json_path, markdown_path
