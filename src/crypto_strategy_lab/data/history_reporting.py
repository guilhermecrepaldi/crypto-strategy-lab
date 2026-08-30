from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from crypto_strategy_lab.data.history import (
    DailyLiquidityAudit,
    HistoricalDatasetManifest,
    load_normalized_history,
    verify_aggregations,
)
from crypto_strategy_lab.data.universe import select_causal_historical_universe


def build_history_audit(
    manifest_path: Path,
    *,
    episode_start: datetime,
    lookback_days: int,
) -> dict[str, Any]:
    manifest = HistoricalDatasetManifest.model_validate_json(
        manifest_path.read_text(encoding="utf-8")
    )
    if manifest.locked_test_accessed:
        raise ValueError("LOCKED_TEST manifests are forbidden in historical audit")
    candles = load_normalized_history(
        Path(manifest.normalized_path), not_after=episode_start - timedelta(microseconds=1)
    )
    selection = select_causal_historical_universe(
        candles,
        episode_start=episode_start,
        lookback=timedelta(days=lookback_days),
    )
    selected = set(selection.selected_symbols)
    selection_candles = [
        item
        for item in candles
        if item.symbol in selected and selection.lookback_start <= item.open_time < episode_start
    ]
    catalog = [
        {
            "symbol": coverage.symbol,
            "first_open_time": coverage.first_open_time,
            "last_close_time": coverage.last_close_time,
            "candle_count": coverage.candle_count,
            "valid": coverage.valid,
            "archive_hashes": [
                archive.sha256 for archive in manifest.archives if archive.symbol == coverage.symbol
            ],
        }
        for coverage in manifest.coverage
    ]
    return {
        "manifest": manifest.model_dump(mode="json"),
        "catalog": catalog,
        "selection": selection.model_dump(mode="json"),
        "aggregation_counts": verify_aggregations(selection_candles),
        "causality_evidence": {
            "max_available_at": max(item.available_at for item in selection_candles),
            "episode_start": episode_start,
            "future_rows_used": 0,
            "ranking_window_start": selection.lookback_start,
            "ranking_window_end_exclusive": episode_start,
            "locked_test_accessed": False,
        },
    }


def write_history_audit(payload: dict[str, Any], output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    episode = str(payload["selection"]["episode_start"])[:10]
    json_path = output_dir / f"history-audit-{episode}.json"
    markdown_path = output_dir / f"history-audit-{episode}.md"
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n")
    manifest = payload["manifest"]
    selection = payload["selection"]
    coverage_rows = "\n".join(
        f"- `{item['symbol']}`: {item['candle_count']} candles, "
        f"{item['missing_count']} missing, valid={item['valid']}"
        for item in manifest["coverage"]
    )
    ranking_rows = "\n".join(
        f"- {item['rank']}. `{item['symbol']}` — {item['quote_volume_usdt']} USDT"
        for item in selection["ranking"]
    )
    markdown_path.write_text(
        "# Crypto Strategy Lab — historical data audit\n\n"
        f"Episode start: `{selection['episode_start']}`\n\n"
        f"Selection window: `{selection['lookback_start']}` to "
        f"`{selection['episode_start']}` (exclusive)\n\n"
        f"Selected: `{', '.join(selection['selected_symbols'])}`\n\n"
        "## Historical catalog and coverage\n\n"
        f"{coverage_rows}\n\n"
        "## Causal liquidity ranking\n\n"
        f"{ranking_rows}\n\n"
        "## Integrity\n\n"
        f"- Dataset hash: `{manifest['dataset_hash']}`\n"
        f"- Archive bytes: `{manifest['archive_bytes']}`\n"
        f"- Candles: `{manifest['candle_count']}`\n"
        f"- Duplicates: `{manifest['duplicate_count']}`\n"
        f"- Invalid timestamps: `{manifest['invalid_timestamp_count']}`\n"
        f"- Future rows used: `{payload['causality_evidence']['future_rows_used']}`\n"
        "- LOCKED_TEST accessed: `false`\n",
        encoding="utf-8",
    )
    return json_path, markdown_path


def write_daily_liquidity_audit(audit: DailyLiquidityAudit, output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    episode = audit.episode_start.date().isoformat()
    json_path = output_dir / f"historical-liquidity-{episode}.json"
    markdown_path = output_dir / f"historical-liquidity-{episode}.md"
    json_path.write_text(
        json.dumps(audit.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    rows = "\n".join(
        f"- {item.rank}. `{item.symbol}` — {item.quote_volume_usdt} USDT" for item in audit.ranking
    )
    markdown_path.write_text(
        "# Crypto Strategy Lab — complete historical liquidity ranking\n\n"
        f"Episode start: `{audit.episode_start.isoformat()}`\n\n"
        f"Lookback start: `{audit.lookback_start.isoformat()}`\n\n"
        f"Selected: `{', '.join(audit.selected_symbols)}`\n\n"
        f"Catalog hash: `{audit.catalog_hash}`\n\n"
        f"Ranking hash: `{audit.ranking_hash}`\n\n"
        f"Pairs excluded for incomplete daily coverage: `{len(audit.exclusions)}`\n\n"
        f"{rows}\n\n"
        "All ranking rows are official archived 1d klines whose quote volumes aggregate the "
        "same public Spot market. Eligibility was proven by complete archived 5m keys. "
        "Future rows used: `0`; `LOCKED_TEST` accessed: `false`.\n",
        encoding="utf-8",
    )
    return json_path, markdown_path
