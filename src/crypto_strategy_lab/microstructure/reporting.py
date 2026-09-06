from __future__ import annotations

import csv
import html
import json
from collections import Counter
from collections.abc import Sequence
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from crypto_strategy_lab.microstructure.data import HistoryManifest
from crypto_strategy_lab.microstructure.price_path import BacktestCampaign, PeriodBacktest


def write_history_audit(manifest: HistoryManifest, output: str | Path) -> Path:
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    incomplete = [
        item
        for item in manifest.archives
        if item.first_event_offset_seconds > 0 or item.last_event_before_day_end_seconds > 0
    ]
    lines = [
        f"# {manifest.symbol} historical data audit",
        "",
        f"- Source: official Binance public daily `{manifest.kind}` archives",
        f"- Requested coverage: `{manifest.requested_start}` to "
        f"`{manifest.requested_end}` inclusive",
        f"- Observed coverage: `{manifest.first_timestamp}` to `{manifest.last_timestamp}`",
        f"- Archives: `{len(manifest.archives)}`",
        f"- Records: `{manifest.total_records}`",
        f"- Compressed bytes: `{manifest.total_size_bytes}`",
        f"- Dataset hash: `{manifest.dataset_hash}`",
        f"- Missing dates: `{len(manifest.missing_dates)}`",
        f"- Missing date ranges: `{len(manifest.missing_date_ranges)}`",
        f"- Within-archive ID gaps: `{sum(len(item.gaps) for item in manifest.archives)}`",
        f"- Duplicate IDs: `{sum(len(item.duplicates) for item in manifest.archives)}`",
        f"- Cross-archive gaps: `{len(manifest.cross_archive_gaps)}`",
        f"- Cross-archive overlaps: `{len(manifest.cross_archive_overlaps)}`",
        f"- Days with non-zero boundary silence: `{len(incomplete)}`",
        f"- Integrity: **{manifest.integrity_status}**",
        f"- Invalidity reasons: `{', '.join(manifest.invalidity_reasons) or 'none'}`",
        "",
        "Boundary silence is reported rather than silently filled. It can reflect ordinary periods "
        "without trades; IDs and timestamps are the continuity authority. Every local ZIP is "
        "checksum-verified against Binance before ingestion and is re-verifiable offline.",
        "",
        "This dataset contains public trades only. It does not contain our queue position and "
        "cannot prove hypothetical order fills.",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def write_backtest_reports(
    campaign: BacktestCampaign,
    output_dir: str | Path,
    *,
    markdown_output: str | Path = Path("docs/microstructure/BACKTEST_REPORT.md"),
) -> dict[str, Path]:
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    summary = root / "backtest-summary.json"
    periods = root / "backtest-periods.csv"
    cycles = root / "backtest-cycles.csv"
    page = root / "backtest-report.html"
    markdown = Path(markdown_output)
    markdown.parent.mkdir(parents=True, exist_ok=True)
    summary.write_text(
        json.dumps(_jsonable(campaign.model_dump(mode="python")), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    all_periods = (*campaign.horizon_results, *campaign.rolling_results)
    _write_csv(periods, all_periods)
    _write_csv(cycles, campaign.cycles)
    markdown.write_text(_markdown(campaign), encoding="utf-8")
    page.write_text(_html(campaign), encoding="utf-8")
    return {
        "summary": summary,
        "periods": periods,
        "cycles": cycles,
        "html": page,
        "markdown": markdown,
    }


def _markdown(campaign: BacktestCampaign) -> str:
    maximum = campaign.horizon_results[-1]
    primary = _primary_outcome(maximum)
    rows = [
        "| Period | Cycles | Cycles/day | Max hold (s) | Open at end |",
        "| --- | ---: | ---: | ---: | --- |",
    ]
    for item in campaign.horizon_results:
        rows.append(
            f"| {item.label} | {item.completed_serial_cycles} | {item.cycles_per_day} | "
            f"{item.holding_time_seconds.maximum or 0} | "
            f"{'YES' if item.carried_out_position else 'NO'} |"
        )
    return "\n".join(
        [
            "# S0_FROZEN_LEVELS-v1 backtest",
            "",
            f"Dataset `{campaign.dataset_hash}` covers `{campaign.first_timestamp}` through "
            f"`{campaign.last_timestamp}` ({campaign.total_records} records).",
            "",
            *rows,
            "",
            "## Primary mathematical scenario",
            "",
            "The primary comparison below uses 1,000 USDC and the explicit zero-maker-fee "
            "scenario; every other capital/fee combination is retained in the JSON and CSV.",
            "",
            f"- Completed serial price paths: `{maximum.completed_serial_cycles}`",
            f"- Fixed-lot final capital: `{primary.final_capital_fixed_lot}`",
            f"- Compounded final capital: `{primary.final_capital_compounding}`",
            f"- Compounded return: `{primary.return_compounding}`",
            f"- Longest completed hold (seconds): `{maximum.holding_time_seconds.maximum}`",
            f"- Open position at dataset end: `{'YES' if maximum.open_position_at_end else 'NO'}`",
            f"- Classification: **{campaign.backtest_classification}**",
            "",
            campaign.classification_reason,
            "",
            "## Interpretation boundary",
            "",
            "A trade observed at LOW or HIGH is a price-path event, not evidence that our passive "
            "order filled. Queue position and L2 reconstruction are absent, so execution remains "
            "`INCONCLUSIVE`. No timeout exit or forced terminal sale is introduced.",
            "",
        ]
    )


def _html(campaign: BacktestCampaign) -> str:
    periods = campaign.horizon_results
    daily = Counter(item.exit_timestamp.date().isoformat() for item in campaign.cycles)
    weekly = Counter(
        f"{item.exit_timestamp.isocalendar().year}-W{item.exit_timestamp.isocalendar().week:02d}"
        for item in campaign.cycles
    )
    equity = [(item.label, _primary_outcome(item).final_capital_compounding) for item in periods]
    holding = periods[-1].holding_time_seconds
    hold_points = [
        ("p50", holding.p50 or Decimal("0")),
        ("p90", holding.p90 or Decimal("0")),
        ("p95", holding.p95 or Decimal("0")),
        ("p99", holding.p99 or Decimal("0")),
        ("max", holding.maximum or Decimal("0")),
    ]
    rows = "".join(_period_row(item) for item in periods)
    styles = """
    :root{color-scheme:light;font-family:Inter,ui-sans-serif,system-ui;color:#15231b;background:#f4f7f4}
    body{max-width:1180px;margin:auto;padding:36px}h1{font-size:28px}h2{margin-top:32px}
    .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:18px}
    .card{background:white;border:1px solid #dce5de;border-radius:14px;padding:18px;overflow:auto}
    .metric{font-size:24px;font-weight:700}.muted{color:#607067}table{width:100%;border-collapse:collapse}
    th,td{text-align:right;padding:8px;border-bottom:1px solid #e8eee9}
    th:first-child,td:first-child{text-align:left}
    svg{width:100%;height:180px}.bar{fill:#2f7d4a}.line{fill:none;stroke:#185c37;stroke-width:3}
    """
    maximum = periods[-1]
    return (
        "<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' "
        f"content='width=device-width'><title>S0 backtest</title><style>{styles}</style>"
        "</head><body>"
        f"<h1>{html.escape(campaign.strategy_id)}</h1><p class='muted'>Price-path evidence only · "
        f"execution {campaign.execution_status} · dataset {html.escape(campaign.dataset_hash)}</p>"
        f"<div class='grid'><section class='card'><div class='muted'>Completed cycles</div>"
        f"<div class='metric'>{maximum.completed_serial_cycles:,}</div></section>"
        f"<section class='card'><div class='muted'>Classification</div><div class='metric'>"
        f"{campaign.backtest_classification}</div></section></div>"
        "<div class='grid'><section class='card'><h2>Equity by horizon</h2>"
        f"{_line_chart(equity)}</section>"
        f"<section class='card'><h2>Cycles by day</h2>{_bar_chart(list(daily.items()))}</section>"
        f"<section class='card'><h2>Cycles by week</h2>{_bar_chart(list(weekly.items()))}</section>"
        "<section class='card'><h2>Holding-time distribution</h2>"
        f"{_bar_chart(hold_points)}</section></div>"
        "<section class='card'><h2>Period table</h2><table><thead><tr>"
        "<th>Period</th><th>Cycles</th>"
        "<th>Cycles/day</th><th>Max hold (s)</th><th>Fixed final</th><th>Compound final</th>"
        f"<th>Open</th></tr></thead><tbody>{rows}</tbody></table></section>"
        f"<p class='muted'>{html.escape(campaign.classification_reason)}</p></body></html>"
    )


def _period_row(item: PeriodBacktest) -> str:
    outcome = _primary_outcome(item)
    return (
        f"<tr><td>{html.escape(item.label)}</td><td>{item.completed_serial_cycles}</td>"
        f"<td>{item.cycles_per_day:.6f}</td><td>{item.holding_time_seconds.maximum or 0}</td>"
        f"<td>{outcome.final_capital_fixed_lot:.6f}</td>"
        f"<td>{outcome.final_capital_compounding:.6f}</td>"
        f"<td>{'YES' if item.carried_out_position else 'NO'}</td></tr>"
    )


def _primary_outcome(item: PeriodBacktest) -> Any:
    return next(
        outcome
        for outcome in item.capital_outcomes
        if outcome.initial_capital == Decimal("1000")
        and outcome.fee_scenario.name == "SCENARIO_ZERO_MAKER"
    )


def _line_chart(points: list[tuple[str, Decimal]]) -> str:
    if not points:
        return "<p>No observations</p>"
    values = [float(value) for _, value in points]
    low, high = min(values), max(values)
    span = high - low or 1.0
    width = 600
    coords = []
    for index, value in enumerate(values):
        x = 10 + index * (width - 20) / max(1, len(values) - 1)
        y = 165 - (value - low) / span * 145
        coords.append(f"{x:.1f},{y:.1f}")
    labels = "".join(f"<title>{html.escape(label)}: {value}</title>" for label, value in points)
    return (
        f"<svg viewBox='0 0 600 180'>{labels}<polyline class='line' "
        f"points='{' '.join(coords)}'/></svg>"
    )


def _bar_chart(points: Sequence[tuple[str, int | Decimal]]) -> str:
    if not points:
        return "<p>No observations</p>"
    sampled = points if len(points) <= 120 else points[:: max(1, len(points) // 120)]
    maximum = max(float(value) for _, value in sampled) or 1.0
    bar_width = 600 / len(sampled)
    bars = []
    for index, (label, value) in enumerate(sampled):
        height = float(value) / maximum * 155
        bars.append(
            f"<rect class='bar' x='{index * bar_width:.2f}' y='{170 - height:.2f}' "
            f"width='{max(1, bar_width - 1):.2f}' height='{height:.2f}'>"
            f"<title>{html.escape(label)}: {value}</title></rect>"
        )
    return f"<svg viewBox='0 0 600 180'>{''.join(bars)}</svg>"


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def _write_csv(path: Path, records: tuple[Any, ...]) -> None:
    rows = [_jsonable(record.model_dump(mode="python")) for record in records]
    fields = sorted({key for row in rows for key in row}) if rows else []
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        if fields:
            writer.writeheader()
            writer.writerows(
                {
                    key: json.dumps(value, sort_keys=True)
                    if isinstance(value, (dict, list))
                    else value
                    for key, value in row.items()
                }
                for row in rows
            )
