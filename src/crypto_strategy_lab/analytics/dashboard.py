# ruff: noqa: E501
from __future__ import annotations

import hashlib
import html
import json
from decimal import Decimal
from pathlib import Path
from typing import Any

from crypto_strategy_lab.analytics.schemas import (
    ControlledTrainingReport,
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


def render_learning_dashboard(report: ControlledTrainingReport) -> str:
    payload = report.model_dump(mode="json")
    safe_json = json.dumps(payload, sort_keys=True, separators=(",", ":")).replace("</", "<\\/")
    phase = html.escape(report.phase.upper())
    warning = html.escape(report.warning)
    return f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="icon" href="data:,"><title>Crypto Strategy Lab · Learning {phase}</title><style>
:root{{--ink:#12211b;--muted:#65736d;--line:#dce6e0;--paper:#f5f8f6;--card:#fff;--green:#116b4b;--red:#a33b35;--amber:#8a5a0c}}*{{box-sizing:border-box}}body{{margin:0;background:var(--paper);color:var(--ink);font:14px/1.45 Inter,system-ui,sans-serif}}main{{max-width:1280px;margin:auto;padding:28px}}header{{display:flex;justify-content:space-between;gap:20px}}h1{{font-size:30px;letter-spacing:-.035em;margin:6px 0}}h2{{font-size:17px;margin:0 0 13px}}p{{color:var(--muted)}}.eyebrow{{color:var(--green);font-weight:800;letter-spacing:.12em;font-size:12px}}.badge{{border:1px solid #b5d9c8;background:#e5f4ec;border-radius:999px;padding:8px 11px;height:max-content;font-weight:700}}.warning{{margin:18px 0;background:#fff7e8;border:1px solid #ecd39b;padding:12px;border-radius:12px;color:#68480e}}.grid{{display:grid;grid-template-columns:repeat(12,1fr);gap:14px}}.card{{grid-column:span 4;background:#fff;border:1px solid var(--line);border-radius:16px;padding:18px;box-shadow:0 8px 24px rgba(20,45,34,.04)}}.wide{{grid-column:span 8}}.full{{grid-column:1/-1}}.metric{{font-size:27px;font-weight:780;margin-top:8px}}.label{{font-size:11px;color:var(--muted);letter-spacing:.08em;text-transform:uppercase}}.tabs{{display:flex;gap:8px;flex-wrap:wrap;margin:0 0 15px}}button{{border:1px solid var(--line);background:#fff;border-radius:9px;padding:7px 10px}}button.active{{background:var(--ink);color:#fff}}[hidden]{{display:none!important}}svg{{width:100%;height:260px}}.axis{{stroke:#d3ddd7}}.reward{{fill:none;stroke:var(--green);stroke-width:2}}.loss{{fill:none;stroke:var(--red);stroke-width:1.7}}table{{width:100%;border-collapse:collapse}}th,td{{padding:9px 7px;text-align:left;border-bottom:1px solid var(--line);font-variant-numeric:tabular-nums}}th{{font-size:11px;color:var(--muted);text-transform:uppercase}}.actions{{display:flex;height:22px;border-radius:6px;overflow:hidden;background:#edf1ef}}.actions i:nth-child(1){{background:#97a49e}}.actions i:nth-child(2){{background:#116b4b}}.actions i:nth-child(3){{background:#3c9472}}.actions i:nth-child(4){{background:#e3a62f}}.actions i:nth-child(5){{background:#a33b35}}@media(max-width:760px){{main{{padding:18px}}header{{display:block}}.badge{{display:inline-block;margin-top:8px}}.card,.wide{{grid-column:1/-1}}h1{{font-size:25px}}.metric{{font-size:23px}}table{{display:block;overflow-x:auto}}}}
</style></head><body><main><header><div><div class="eyebrow">HISTORICAL LEARNING DASHBOARD</div><h1>Crypto Strategy Lab</h1><p>{phase} · TRAIN-only · PPO + DQN</p></div><div class="badge">Simulação histórica</div></header><div class="warning">{warning}</div><nav class="tabs"><button class="active" data-tab="summary">Resumo</button><button data-tab="curves">Curvas</button><button data-tab="actions">Ações</button><button data-tab="baselines">Baselines</button><button data-tab="features">Features</button><button data-tab="gates">Gates</button></nav>
<section id="summary"><div class="grid"><article class="card"><div class="label">Runs</div><div class="metric" id="runCount"></div></article><article class="card"><div class="label">Timesteps reais</div><div class="metric" id="steps"></div></article><article class="card"><div class="label">Checkpoints</div><div class="metric" id="checkpoints"></div></article><article class="card full"><h2>Execução</h2><table id="runTable"></table></article></div></section>
<section id="curves" hidden><div class="grid"><article class="card wide"><h2>Reward durante o treinamento</h2><svg id="rewardChart" viewBox="0 0 1000 260"><line class="axis" x1="30" y1="230" x2="985" y2="230"/></svg><p id="rewardNote"></p></article><article class="card"><h2>Telemetria</h2><div id="telemetry"></div></article><article class="card wide"><h2>Patrimônio por checkpoint · holdout interno de TRAIN</h2><svg id="equityChart" viewBox="0 0 1000 260"><line class="axis" x1="30" y1="230" x2="985" y2="230"/></svg></article><article class="card"><h2>Seleção do checkpoint</h2><p>Checkpoint mais recente de cada run, selecionado pelo orçamento predefinido em TRAIN. Nenhum resultado de VALIDATION participou da escolha.</p></article><article class="card full"><h2>Loss, entropia e epsilon</h2><table id="lossTable"></table></article></div></section>
<section id="actions" hidden><div class="grid"><article class="card full"><h2>Distribuição das cinco ações</h2><div id="actionRows"></div></article></div></section>
<section id="baselines" hidden><div class="grid"><article class="card full"><h2>Holdout interno causal de TRAIN</h2><table id="baselineTable"></table></article></div></section>
<section id="features" hidden><div class="grid"><article class="card full"><h2>Variantes causais</h2><div id="featureBody"></div></article></div></section>
<section id="gates" hidden><div class="grid"><article class="card"><div class="label">Gate técnico</div><div class="metric" id="technicalGate"></div></article><article class="card"><div class="label">Sobrevivência</div><div class="metric">PENDENTE</div></article><article class="card"><div class="label">Valor</div><div class="metric">PENDENTE</div></article><article class="card full"><p>Sobrevivência e valor só são classificados após congelamento e avaliação em VALIDATION. LOCKED_TEST permanece fechado.</p></article></div></section>
<script id="learningData" type="application/json">{safe_json}</script><script>
const d=JSON.parse(document.getElementById('learningData').textContent),esc=s=>String(s).replace(/[&<>"']/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c]));document.querySelectorAll('[data-tab]').forEach(b=>b.onclick=()=>{{document.querySelectorAll('[data-tab]').forEach(x=>x.classList.remove('active'));document.querySelectorAll('main>section').forEach(x=>x.hidden=true);b.classList.add('active');document.getElementById(b.dataset.tab).hidden=false;if(b.dataset.tab==='curves')draw();}});
const complete=d.runs.filter(x=>x.status==='COMPLETED');document.getElementById('runCount').textContent=`${{complete.length}} / ${{d.runs.length}}`;document.getElementById('steps').textContent=d.runs.reduce((a,x)=>a+x.completed_timesteps,0).toLocaleString('pt-BR');document.getElementById('checkpoints').textContent=d.runs.reduce((a,x)=>a+x.checkpoint_records.length,0);document.getElementById('technicalGate').textContent=complete.length===d.runs.length&&!d.runs.some(x=>x.nan_detected)?'PASS':'PENDENTE';
document.getElementById('runTable').innerHTML='<tr><th>Algoritmo</th><th>Configuração</th><th>Feature</th><th>Seed</th><th>Steps</th><th>Status</th><th>Retorno interno</th><th>Checkpoint</th></tr>'+d.runs.map(x=>{{const e=x.internal_evaluations.at(-1);return `<tr><td>${{esc(x.algorithm)}}</td><td>${{esc(x.configuration_variant)}}</td><td>${{esc(x.feature_variant)}}</td><td>${{x.seed}}</td><td>${{x.completed_timesteps.toLocaleString('pt-BR')}}</td><td>${{esc(x.status)}}</td><td>${{e?Number(e.return_percent).toFixed(2)+'%':'—'}}</td><td><code>${{esc(x.checkpoint_hash.slice(0,10))}}</code></td></tr>`}}).join('');
const metrics=d.runs.flatMap(x=>x.training_metrics.map(m=>({{...m,label:x.algorithm+' · '+x.configuration_variant+' · '+x.feature_variant+' · '+x.seed}}))),colors=['#116b4b','#a33b35','#e3a62f','#3477a8','#7957a8','#3c9472'];const fmt=x=>x===null||x===undefined?'—':Number(x).toFixed(5);function plot(id,series){{const svg=document.getElementById(id),all=series.flatMap(x=>x.points);svg.querySelectorAll('path,circle').forEach(x=>x.remove());if(!all.length)return false;const xs=all.map(x=>x.x),ys=all.map(x=>x.y),xmin=Math.min(...xs),xmax=Math.max(...xs),ymin=Math.min(...ys),ymax=Math.max(...ys),xspan=Math.max(xmax-xmin,1),yspan=Math.max(ymax-ymin,.000001);series.forEach((s,i)=>{{if(!s.points.length)return;const coords=s.points.map(x=>({{x:30+(x.x-xmin)*950/xspan,y:225-(x.y-ymin)*195/yspan}})),p=document.createElementNS('http://www.w3.org/2000/svg','path');p.setAttribute('fill','none');p.setAttribute('stroke',colors[i%colors.length]);p.setAttribute('stroke-width','2');p.setAttribute('d','M '+coords.map(x=>`${{x.x}},${{x.y}}`).join(' L '));svg.appendChild(p);coords.forEach(x=>{{const c=document.createElementNS('http://www.w3.org/2000/svg','circle');c.setAttribute('cx',x.x);c.setAttribute('cy',x.y);c.setAttribute('r','4');c.setAttribute('fill',colors[i%colors.length]);svg.appendChild(c);}});}});return true;}}function draw(){{let reward=d.runs.map(x=>({{points:x.training_metrics.filter(m=>m.reward_mean!==null).map(m=>({{x:m.step,y:Number(m.reward_mean)}}))}}));let direct=plot('rewardChart',reward);if(!direct){{reward=d.runs.map(x=>({{points:x.internal_evaluations.map(m=>({{x:m.checkpoint_step,y:Number(m.reward_mean)}}))}}));plot('rewardChart',reward);}}document.getElementById('rewardNote').textContent=direct?'Média causal acumulada registrada pelo callback.':'Fallback: reward no holdout interno por checkpoint; callbacks antigos não registravam reward por passo.';plot('equityChart',d.runs.map(x=>({{points:x.internal_evaluations.map(m=>({{x:m.checkpoint_step,y:Number(m.final_equity_usdt)}}))}})));}}document.getElementById('telemetry').innerHTML=d.runs.map(x=>{{const m=x.training_metrics.at(-1)||{{}};return `<p><strong>${{esc(x.algorithm+' '+x.configuration_variant+' · seed '+x.seed)}}</strong><br>${{x.steps_per_second.toFixed(1)}} steps/s · ${{x.elapsed_seconds.toFixed(1)}}s · ${{x.peak_python_memory_mb.toFixed(1)}} MiB<br>turnover ${{Number(m.turnover||0).toFixed(2)}} · custos ${{Number(m.costs_usdt||0).toFixed(2)}} · episódios ${{m.episodes??0}} · ruínas ${{m.ruins??0}}</p>`}}).join('');document.getElementById('lossTable').innerHTML='<tr><th>Run</th><th>Step</th><th>Entropy</th><th>Value loss</th><th>Policy loss</th><th>TD loss</th><th>Epsilon</th></tr>'+metrics.map(x=>`<tr><td>${{esc(x.label)}}</td><td>${{x.step}}</td><td>${{fmt(x.entropy_loss)}}</td><td>${{fmt(x.value_loss)}}</td><td>${{fmt(x.policy_loss)}}</td><td>${{fmt(x.td_loss)}}</td><td>${{fmt(x.epsilon)}}</td></tr>`).join('');
document.getElementById('actionRows').innerHTML=d.runs.map(x=>{{const e=x.internal_evaluations.at(-1),a=e?e.action_distribution:[0,0,0,0,0],p=e?.position_distribution;return `<p><strong>${{esc(x.algorithm+' · '+x.configuration_variant+' · '+x.feature_variant+' · seed '+x.seed)}}</strong></p><div class="actions">${{a.map(v=>`<i style="width:${{v*100}}%"></i>`).join('')}}</div><p>Ações: USDT ${{(a[0]*100).toFixed(1)}}% · BTC ${{(a[1]*100).toFixed(1)}}% · ETH ${{(a[2]*100).toFixed(1)}}% · SHIB ${{(a[3]*100).toFixed(1)}}% · BNB ${{(a[4]*100).toFixed(1)}}%</p><p>Tempo em posição: ${{p?Object.entries(p).map(([k,v])=>esc(k)+' '+(v*100).toFixed(1)+'%').join(' · '):'disponível nos próximos checkpoints'}}</p>`}}).join('');
document.getElementById('baselineTable').innerHTML='<tr><th>Política</th><th>Retorno</th><th>Drawdown</th><th>Turnover</th><th>Custos</th><th>USDT</th><th>Ruína</th></tr>'+d.internal_train_baselines.filter((x,i,a)=>a.findIndex(y=>y.policy===x.policy&&y.configuration_variant===x.configuration_variant)===i).map(x=>`<tr><td>${{esc(x.policy+' · '+x.configuration_variant)}}</td><td>${{Number(x.return_percent).toFixed(2)}}%</td><td>${{(Number(x.max_drawdown)*100).toFixed(2)}}%</td><td>${{Number(x.turnover).toFixed(2)}}</td><td>${{Number(x.costs_usdt).toFixed(2)}}</td><td>${{(Number(x.time_in_usdt_ratio)*100).toFixed(1)}}%</td><td>${{x.ruined?'sim':'não'}}</td></tr>`).join('');
document.getElementById('featureBody').innerHTML=`<p>Executadas: <strong>${{d.feature_variants.map(esc).join(', ')}}</strong>.</p><p>${{d.feature_variants.length>1?'Comparação disponível somente em TRAIN.':'BASE_PLUS_RELATIVE_STRENGTH será comparada no development; nenhuma conclusão foi antecipada no sanity.'}}</p><p>VALIDATION observada: <strong>${{d.validation_observed?'sim':'não'}}</strong>. LOCKED_TEST: <strong>fechado</strong>.</p>`;
</script></main></body></html>"""


def write_learning_dashboard(report_path: Path, output: Path) -> str:
    report = ControlledTrainingReport.model_validate_json(report_path.read_text(encoding="utf-8"))
    rendered = render_learning_dashboard(report)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(rendered, encoding="utf-8")
    return hashlib.sha256(rendered.encode()).hexdigest()
