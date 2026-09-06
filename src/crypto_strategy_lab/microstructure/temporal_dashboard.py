# ruff: noqa: E501
"""Self-contained offline dashboard for full-replay temporal evidence."""

from __future__ import annotations

import hashlib
import html
import json
from pathlib import Path

from crypto_strategy_lab.microstructure.temporal_analysis import (
    MarketProductivityRegime,
    TemporalReplayAnalysis,
)

_COLORS = {
    "HOT": "#16a34a",
    "NORMAL": "#94a3b8",
    "COLD": "#f59e0b",
    "FAILURE": "#dc2626",
    "UNKNOWN": "#e2e8f0",
}


def write_temporal_dashboard(
    analyses: list[TemporalReplayAnalysis],
    cohort: MarketProductivityRegime | None,
    output: Path,
) -> str:
    """Render model-by-time and model-by-month matrices without external dependencies."""
    if not analyses:
        raise ValueError("at least one temporal analysis is required")
    analyses = sorted(analyses, key=lambda item: item.model_id)
    month_labels = sorted({str(row["period"]) for item in analyses for row in item.monthly})
    daily_by_model = {
        item.model_id: next(
            horizon for horizon in item.horizons if horizon.horizon_hours == 24
        ).blocks
        for item in analyses
    }
    cards = "".join(
        _card(
            item.model_id,
            str(item.productivity_fingerprint.get("BEST_MONTH") or "—"),
            str(item.temporal_stability.get("aggregate") or "—"),
            str(item.concentration.get("PROFIT_CONCENTRATION_WARNING", "UNKNOWN")),
        )
        for item in analyses
    )
    time_rows = "".join(
        "<tr><th>"
        + html.escape(model_id)
        + "</th><td><div class='timeline'>"
        + "".join(
            f"<span style='background:{_COLORS[block.classification]}' "
            f"title='{block.start.date()} · {block.classification} · "
            f"{block.completed_cycles} cycles'></span>"
            for block in blocks
        )
        + "</div></td></tr>"
        for model_id, blocks in daily_by_model.items()
    )
    monthly_rows = "".join(_monthly_row(item, month_labels) for item in analyses)
    payload = {
        "models": [item.model_id for item in analyses],
        "start": min(item.start for item in analyses),
        "end_exclusive": max(item.end_exclusive for item in analyses),
        "cohort_hash": cohort.cohort_hash if cohort is not None else None,
    }
    content = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>USDCUSDT temporal productivity</title><style>
:root{{--ink:#0f172a;--muted:#64748b;--line:#e2e8f0;--paper:#fff;--bg:#f8fafc}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font:14px Inter,system-ui}}
main{{max-width:1400px;margin:auto;padding:40px}}h1{{font-size:28px;margin:0 0 8px}}p{{color:var(--muted)}}
.cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:12px;margin:24px 0}}
.card,section{{background:var(--paper);border:1px solid var(--line);border-radius:14px;padding:18px}}
.card strong{{font-size:18px}}section{{margin-top:16px;overflow:auto}}table{{border-collapse:collapse;width:100%}}
th,td{{border-bottom:1px solid var(--line);padding:10px;text-align:left;vertical-align:top;white-space:nowrap}}
.timeline{{display:flex;min-width:900px;height:26px;gap:1px}}.timeline span{{flex:1;min-width:2px;border-radius:2px}}
.month{{min-width:150px}}.metric{{display:block;color:var(--muted);font-size:12px;margin-top:3px}}
.legend{{display:flex;gap:14px;flex-wrap:wrap}}.dot{{display:inline-block;width:10px;height:10px;border-radius:3px;margin-right:5px}}
</style></head><body><main><h1>USDCUSDT temporal productivity</h1>
<p>Complete DEVELOPMENT replay. Price-path evidence only; not fill or live-trading evidence.</p>
<div class="cards">{cards}</div><section><h2>Model &times; time</h2>
<div class="legend">{_legend()}</div><table>{time_rows}</table></section>
<section><h2>Model &times; month</h2><table><thead><tr><th>Model</th>{"".join(f"<th>{html.escape(month)}</th>" for month in month_labels)}</tr></thead>
<tbody>{monthly_rows}</tbody></table></section>
<script type="application/json" id="provenance">{html.escape(json.dumps(payload, default=str, sort_keys=True))}</script>
</main></body></html>"""
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(content, encoding="utf-8")
    return hashlib.sha256(content.encode()).hexdigest()


def _card(model: str, month: str, stability: str, warning: str) -> str:
    return (
        "<div class='card'><strong>"
        + html.escape(model)
        + "</strong><span class='metric'>Best complete month: "
        + html.escape(month)
        + "</span><span class='metric'>Temporal stability: "
        + html.escape(stability)
        + "</span><span class='metric'>Concentration warning: "
        + html.escape(warning)
        + "</span></div>"
    )


def _monthly_row(analysis: TemporalReplayAnalysis, labels: list[str]) -> str:
    by_month = {str(row["period"]): row for row in analysis.monthly}
    cells: list[str] = []
    for label in labels:
        row = by_month.get(label)
        if row is None:
            cells.append("<td class='month'>UNKNOWN</td>")
            continue
        cells.append(
            "<td class='month'><strong>"
            + html.escape(str(row["return_fraction"]))
            + "</strong><span class='metric'>cycles "
            + html.escape(str(row["completed_cycles"]))
            + "</span><span class='metric'>idle h "
            + html.escape(str(row["idle_hours"]))
            + "</span><span class='metric'>days ≥2000 "
            + html.escape(str(row["days_at_least_2000_cycles"]))
            + "</span></td>"
        )
    return f"<tr><th>{html.escape(analysis.model_id)}</th>{''.join(cells)}</tr>"


def _legend() -> str:
    return "".join(
        f"<span><i class='dot' style='background:{color}'></i>{name}</span>"
        for name, color in _COLORS.items()
    )


__all__ = ["write_temporal_dashboard"]
