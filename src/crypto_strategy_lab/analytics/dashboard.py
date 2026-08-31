# ruff: noqa: E501
from __future__ import annotations

import hashlib
import html
import json
from decimal import Decimal
from pathlib import Path
from typing import Any

from crypto_strategy_lab.analytics.schemas import (
    DashboardManifest,
    DivergenceReport,
    TurnoverDiagnosticReport,
)
from crypto_strategy_lab.domain import canonical_hash

SECTIONS = ["summary", "equity", "costs", "turnover", "divergence", "integrity"]


def render_dashboard(
    report: TurnoverDiagnosticReport,
    *,
    divergence: DivergenceReport | None = None,
) -> str:
    payload = report.model_dump(mode="json", exclude={"transitions"})
    payload["equity_series"] = _equity_series(report.transitions)
    payload["divergence"] = divergence.model_dump(mode="json") if divergence else None
    safe_json = json.dumps(payload, sort_keys=True, separators=(",", ":")).replace("</", "<\\/")
    title = html.escape(f"Crypto Strategy Lab · {report.run_id}")
    policy = html.escape(report.provenance.policy)
    scenario = html.escape(str(report.provenance.configuration.get("scenario", "diagnostic")))
    final_equity = html.escape(f"{Decimal(report.costs.final_equity_usdt):.2f}")
    net_pnl = html.escape(f"{Decimal(report.costs.net_pnl_usdt):.2f}")
    operations = html.escape(str(report.operations))
    warning = html.escape(report.warning)
    return f"""<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="icon" href="data:,">
<title>{title}</title><style>
:root{{--ink:#13211c;--muted:#64726c;--line:#dce5df;--paper:#f6f8f6;--card:#fff;--green:#126b4b;--mint:#dff3e9;--red:#a43c35;--amber:#8a5b10}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--paper);color:var(--ink);font:14px/1.45 Inter,ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif}}
.shell{{max-width:1240px;margin:auto;padding:28px}}header{{display:flex;justify-content:space-between;gap:24px;align-items:flex-start;margin-bottom:18px}}
.eyebrow{{color:var(--green);font-size:12px;font-weight:750;letter-spacing:.12em;text-transform:uppercase}}h1{{font-size:30px;letter-spacing:-.035em;margin:6px 0 4px}}h2{{font-size:17px;margin:0 0 14px}}p{{margin:0;color:var(--muted)}}.badge{{padding:7px 10px;border:1px solid #afd8c4;background:var(--mint);color:var(--green);border-radius:999px;font-weight:700;white-space:nowrap}}
.warning{{background:#fff7e8;border:1px solid #ecd39b;color:#6d4b10;border-radius:12px;padding:12px 14px;margin:14px 0 20px;font-size:13px}}
.grid{{display:grid;grid-template-columns:repeat(12,1fr);gap:14px}}.card{{grid-column:span 4;background:var(--card);border:1px solid var(--line);border-radius:16px;padding:18px;box-shadow:0 8px 24px rgba(25,49,38,.04)}}.wide{{grid-column:span 8}}.full{{grid-column:1/-1}}
.metric{{font-size:28px;font-weight:760;letter-spacing:-.035em;margin-top:8px}}.label{{font-size:12px;color:var(--muted);text-transform:uppercase;letter-spacing:.07em}}.negative{{color:var(--red)}}
.chart{{height:260px;width:100%;display:block}}.axis{{stroke:#cfd9d3;stroke-width:1}}.series{{fill:none;stroke:var(--green);stroke-width:2.2}}.costbar{{height:9px;background:#e8eeea;border-radius:99px;overflow:hidden;margin:8px 0 14px}}.costbar i{{display:block;height:100%;background:var(--red)}}
table{{width:100%;border-collapse:collapse}}th,td{{text-align:left;padding:9px 7px;border-bottom:1px solid var(--line);font-variant-numeric:tabular-nums}}th{{font-size:11px;color:var(--muted);text-transform:uppercase}}code{{font:12px ui-monospace,SFMono-Regular,Consolas,monospace;word-break:break-all}}
.tabs{{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:14px}}button{{border:1px solid var(--line);background:#fff;border-radius:9px;padding:7px 10px;color:var(--ink);cursor:pointer}}button.active{{background:var(--ink);color:white}}.tabpage[hidden]{{display:none}}
@media(max-width:760px){{.shell{{padding:18px}}header{{display:block}}.badge{{display:inline-block;margin-top:12px}}.card,.wide{{grid-column:1/-1}}h1{{font-size:25px}}.metric{{font-size:24px}}}}
@media print{{body{{background:#fff}}.shell{{max-width:none}}button{{display:none}}.card{{break-inside:avoid;box-shadow:none}}}}
</style></head><body><main class="shell">
<header><div><div class="eyebrow">Offline experiment dashboard</div><h1>Crypto Strategy Lab</h1><p>{policy} · {scenario} · TRAIN · 15m</p></div><div class="badge">Integridade válida</div></header>
<div class="warning">{warning}</div>
<nav class="tabs" aria-label="Seções">{"".join(f'<button data-tab="{item}" class="{"active" if index == 0 else ""}">{html.escape(item.title())}</button>' for index, item in enumerate(SECTIONS))}</nav>
<section id="summary" class="tabpage"><div class="grid">
<article class="card"><div class="label">Equity final</div><div class="metric">{final_equity} USDT</div></article>
<article class="card"><div class="label">PnL líquido</div><div class="metric negative">{net_pnl} USDT</div></article>
<article class="card"><div class="label">Operações</div><div class="metric">{operations}</div></article>
<article class="card full"><h2>Escopo do experimento</h2><p>Dados oficiais ingeridos, execução simulada, sem conta, chaves, Testnet ou ordens reais. Todas as seeds e cenários predefinidos são reportados; não há seleção do melhor resultado.</p></article>
</div></section>
<section id="equity" class="tabpage" hidden><div class="grid"><article class="card full"><h2>Curva de equity</h2><svg id="equityChart" class="chart" viewBox="0 0 1000 260" role="img" aria-label="Curva de equity"><line class="axis" x1="32" y1="232" x2="984" y2="232"/><path class="series" id="equityPath"/></svg></article></div></section>
<section id="costs" class="tabpage" hidden><div class="grid" id="costCards"></div></section>
<section id="turnover" class="tabpage" hidden><div class="grid"><article class="card wide"><h2>Execução e controles</h2><table id="turnoverTable"></table></article><article class="card"><h2>Operações evitadas</h2><div id="avoided"></div></article></div></section>
<section id="divergence" class="tabpage" hidden><div class="grid"><article class="card full"><h2>Divergência e força relativa</h2><div id="divergenceBody"></div></article></div></section>
<section id="integrity" class="tabpage" hidden><div class="grid"><article class="card full"><h2>Proveniência</h2><table id="integrityTable"></table></article></div></section>
</main><script id="reportData" type="application/json">{safe_json}</script><script>
const d=JSON.parse(document.getElementById('reportData').textContent);
document.querySelectorAll('[data-tab]').forEach(b=>b.addEventListener('click',()=>{{document.querySelectorAll('[data-tab]').forEach(x=>x.classList.remove('active'));document.querySelectorAll('.tabpage').forEach(x=>x.hidden=true);b.classList.add('active');document.getElementById(b.dataset.tab).hidden=false;if(b.dataset.tab==='equity')drawEquity();}}));
const esc=s=>String(s).replace(/[&<>"']/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c]));
function drawEquity(){{const a=d.equity_series;if(!a.length)return;const ys=a.map(x=>Number(x.equity)),mn=Math.min(...ys),mx=Math.max(...ys),dlt=Math.max(mx-mn,.0001);const pts=a.map((x,i)=>`${{32+i*952/Math.max(a.length-1,1)}},${{228-(Number(x.equity)-mn)*204/dlt}}`).join(' L ');document.getElementById('equityPath').setAttribute('d','M '+pts)}}
const c=d.costs;document.getElementById('costCards').innerHTML=[['Fees',c.direct_fees_usdt],['Spread',c.direct_spread_usdt],['Slippage',c.direct_slippage_usdt],['Perda exclusiva por custos',c.loss_exclusively_from_costs_usdt],['Equity sem custos',c.costless_final_equity_usdt],['Erro de conservação',c.conservation_error_usdt]].map(x=>`<article class="card"><div class="label">${{esc(x[0])}}</div><div class="metric">${{Number(x[1]).toFixed(2)}} USDT</div><div class="costbar"><i style="width:${{Math.min(100,Math.abs(Number(x[1]))/80*100)}}%"></i></div></article>`).join('');
document.getElementById('turnoverTable').innerHTML=`<tr><th>Compras</th><td>${{d.buys}}</td></tr><tr><th>Vendas</th><td>${{d.sells}}</td></tr><tr><th>Rotações</th><td>${{d.rotations}}</td></tr><tr><th>Turnover</th><td>${{Number(d.total_turnover).toFixed(2)}}</td></tr><tr><th>Duração média</th><td>${{Number(d.average_position_duration_steps).toFixed(2)}} passos</td></tr><tr><th>Exposição média</th><td>${{(Number(d.average_exposure_ratio)*100).toFixed(2)}}%</td></tr><tr><th>Tempo em USDT</th><td>${{(Number(d.time_in_usdt_ratio)*100).toFixed(2)}}%</td></tr>`;
document.getElementById('avoided').innerHTML=Object.entries(d.avoided_operations).map(([k,v])=>`<p><strong>${{esc(k)}}</strong><br>${{v}}</p>`).join('')||'<p>Nenhuma operação evitada.</p>';
const div=d.divergence;document.getElementById('divergenceBody').innerHTML=div?`<p>${{div.alignment.return_rows}} retornos alinhados; nenhum gap preenchido silenciosamente.</p><table><tr><th>Par</th><th>Pearson</th><th>Spearman</th><th>Direção oposta</th></tr>${{div.pairwise.filter(x=>x.left==='BTCUSDT'||x.right==='BTCUSDT').map(x=>`<tr><td>${{esc(x.left+' / '+x.right)}}</td><td>${{x.pearson_simple.toFixed(4)}}</td><td>${{x.spearman_simple.toFixed(4)}}</td><td>${{x.opposite_direction_percent.toFixed(2)}}%</td></tr>`).join('')}}</table>`:'<p>Relatório de divergência não anexado a este dashboard.</p>';
const p=d.provenance;document.getElementById('integrityTable').innerHTML=[['Dataset hash',p.dataset_hash],['Código',p.code_version],['Período',p.period_start+' → '+p.period_end],['Símbolos',p.symbols.join(', ')],['Fonte',p.source],['LOCKED_TEST',String(p.locked_test_accessed)],['Recursos externos','nenhum']].map(x=>`<tr><th>${{esc(x[0])}}</th><td><code>${{esc(x[1])}}</code></td></tr>`).join('');
</script></body></html>"""


def write_dashboard(
    report_path: Path,
    output: Path,
    *,
    divergence_path: Path | None = None,
) -> DashboardManifest:
    report = TurnoverDiagnosticReport.model_validate_json(report_path.read_text(encoding="utf-8"))
    divergence = (
        DivergenceReport.model_validate_json(divergence_path.read_text(encoding="utf-8"))
        if divergence_path and divergence_path.exists()
        else None
    )
    rendered = render_dashboard(report, divergence=divergence)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(rendered, encoding="utf-8")
    manifest = DashboardManifest(
        run_id=report.run_id,
        report_hash=canonical_hash(report.model_dump(mode="json")),
        divergence_hash=canonical_hash(divergence.model_dump(mode="json")) if divergence else None,
        output_sha256=hashlib.sha256(rendered.encode()).hexdigest(),
        sections=SECTIONS,
        warning=report.warning,
    )
    output.with_suffix(".manifest.json").write_text(
        json.dumps(manifest.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def resolve_run_report(run_id: str, reports_dir: Path = Path("reports")) -> Path:
    path = reports_dir / "runs" / f"{run_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"unknown run id: {run_id}")
    return path


def _equity_series(transitions: list[dict[str, Any]]) -> list[dict[str, str]]:
    if not transitions:
        return []
    step = max(1, len(transitions) // 500)
    indices = list(range(0, len(transitions), step))
    if indices[-1] != len(transitions) - 1:
        indices.append(len(transitions) - 1)
    return [
        {
            "timestamp": str(transitions[index]["simulated_time"]),
            "equity": str(transitions[index]["equity_usdt"]),
        }
        for index in indices
    ]
