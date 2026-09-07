"""Standalone retrospective visualization. Never imported by the experimental runtime."""

import argparse
import hashlib
import json
from html import escape
from pathlib import Path


def render(report_path: Path, scenario_id: str, output: Path) -> None:
    if report_path.is_dir():
        # Read-only progress view: never publishes an incomplete grid as a final study.
        report = {
            "artifact_root": str(report_path),
            "identity": json.loads((report_path / "identity.json").read_text(encoding="utf-8")),
            "baseline": json.loads((report_path / "baseline.json").read_text(encoding="utf-8")),
            "scenarios": [
                json.loads(path.read_text(encoding="utf-8"))["summary"]
                for path in sorted(report_path.glob("*/completed.json"))
            ],
        }
    else:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    matching = [row for row in report["scenarios"] if row["scenario_id"] == scenario_id]
    if len(matching) != 1:
        raise ValueError("SELECT_EXACTLY_ONE_COMPLETED_SCENARIO")
    audit_path = Path(report["artifact_root"]) / scenario_id / "audit.json"
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    completed = json.loads(audit_path.with_name("completed.json").read_text(encoding="utf-8"))
    audit_hash = hashlib.sha256(audit_path.read_bytes()).hexdigest()
    if audit_hash != completed["artifact_hashes"]["audit.json"]:
        raise ValueError("DASHBOARD_AUDIT_HASH_MISMATCH")
    markers = [{**marker, "event": str(marker["event"])} for marker in audit["markers"]]
    payload = json.dumps(
        {
            "row": matching[0],
            "baseline": report["baseline"],
            "series": audit["series"],
            "markers": markers,
            "releases": audit["releases"],
            "replenishments": audit["replenishments"],
        }
    ).replace("<", "\\u003c")
    title = escape(scenario_id)
    html = r"""<!doctype html><html lang="pt-BR"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<link rel="icon" href="data:,">
<title>Recovery Reserve · desenvolvimento histórico</title>
<style>
*{box-sizing:border-box}body{font:15px system-ui;margin:0;background:#f8fafc;color:#172033}
main{max-width:1180px;margin:auto;padding:40px 24px}
h1{font-size:32px;letter-spacing:-1px;margin:8px 0}
h2{font-size:18px;margin:0 0 16px}.muted{color:#526079;line-height:1.6}.tag{font-size:12px;
letter-spacing:1.5px;color:#405a80}.cards{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;
margin:28px 0}
.card,section{background:white;border:1px solid #e2e8f0;border-radius:12px;padding:22px;
margin-bottom:18px}.value{font-size:25px;margin-top:8px;overflow-wrap:anywhere}.chart{width:100%;height:220px}
table{width:100%;border-collapse:collapse}
th,td{text-align:left;padding:10px;border-bottom:1px solid #e2e8f0}
.scroll{overflow:auto}
.note{padding:16px;background:#fff7ed;border:1px solid #fed7aa;border-radius:8px}
button{padding:10px 16px;border:1px solid #cbd5e1;background:white;border-radius:8px;cursor:pointer}
code{overflow-wrap:anywhere}
footer{font-size:12px;line-height:1.8;overflow-wrap:anywhere}
.chart text{font-size:12px;fill:#526079}
@media(max-width:700px){.cards{grid-template-columns:1fr}main{padding:24px 14px}
h1{font-size:26px}#charts{overflow-x:auto}.chart{min-width:680px}}
</style><main><div class="tag">USDCUSDT / HISTORICAL DEVELOPMENT ONLY</div>
<h1>Recovery Reserve</h1><p class="muted">SCENARIO · __TITLE__ · Parent M007</p>
<p class="muted">Cenários concluídos: __COUNT__/18. Revisão científica separada;
sem promoção automática.</p>
<p class="note">100 USDT operacionais + 5 USDT segregados. Resultado price-path teórico, sem
evidência de fills. Não é performance executável. Operador M007 inalterado.
Trading desabilitado.</p>
<div class="cards">
<div class="card">Patrimônio total final<div id="total" class="value"></div></div>
<div class="card">Banca operacional marcada<div id="operating" class="value"></div></div>
<div class="card">Reserva final<div id="reserve" class="value"></div></div></div>
<section><h2>Banca, reserva e patrimônio ao longo do tempo</h2>
<button id="scale">Alternar escala linear / logarítmica</button>
<p class="muted">Cada painel tem sua própria escala em USDT. Linhas verticais: lock, release,
transferência, nova faixa, dia zero e recomposição. Valores originais permanecem no relatório;
arredondamento ocorre somente na visualização.</p><div id="charts"></div></section>
<section><h2>Comparação com M007 + reserva parada</h2>
<div class="scroll"><table id="compare"></table></div></section>
<section><h2>Liberações e movimentos da reserva</h2>
<p class="muted">Ciclos futuros e retorno do HIGH
original são diagnósticos retrospectivos, nunca entradas de decisão.</p>
<div class="scroll"><table id="releases"></table></div></section>
<footer class="muted">Código do estudo: <code>__SHA__</code><br>Audit SHA256: <code>__AUDIT__</code>
<br>Intervalo: __START__ → __END__. Seleção deste cenário para visualização não representa promoção.
<br>Fonte completa: __PATH__. Gráficos amostrados em limites UTC diários e eventos contábeis;
drawdown calculado separadamente sobre todos os extremos do tape.</footer></main>
<script>
const data=__DATA__;let log=false;
function money(v){const m=/^(-?)(\d+)(?:\.(\d+))?$/.exec(String(v));
if(!m)return String(v)+' USDT';const frac=(m[3]||'').padEnd(5,'0');
let scaled=BigInt(m[2])*10000n+BigInt(frac.slice(0,4));
if(frac[4]>='5')scaled+=1n;
return m[1]+(scaled/10000n).toLocaleString('pt-BR')+','+
(scaled%10000n).toString().padStart(4,'0')+' USDT'}
for(const[id,key]of[['total','total_final_equity'],['operating','final_operating_equity'],['reserve','reserve_final']])
document.getElementById(id).textContent=money(data.row[key]);
const ns='http://www.w3.org/2000/svg';
function el(tag,attrs,text){
const e=document.createElementNS(ns,tag);
for(const[k,v]of Object.entries(attrs))e.setAttribute(k,v);
if(text)e.textContent=text;return e}
function charts(){const host=document.getElementById('charts');host.replaceChildren();
for(const[key,name,color]of[
['operating_bank','Banca operacional marcada','#2563eb'],
['reserve','Reserva segregada','#059669'],['total_equity','Patrimônio total','#7c3aed'],
['cumulative_cycles','Ciclos acumulados','#d97706']]){
const series=data.series;
const svg=el('svg',{viewBox:'0 0 1060 220',class:'chart',role:'img',
'aria-label':name});
const ts=series.map(p=>Date.parse(p.timestamp));const raw=series.map(p=>Number(p[key]));
const transform=v=>log?Math.log10(1+v):v;const vs=raw.map(transform);
const lo=Math.min(...vs),hi=Math.max(...vs);const x=t=>100+(t-ts[0])/(ts.at(-1)-ts[0]||1)*940;
const y=v=>175-(transform(v)-lo)/(hi-lo||1)*125;
svg.append(el('text',{x:0,y:18},name+(log?' (log1p)':'')));
for(const v of [Math.min(...raw),Math.max(...raw)])
svg.append(el('text',{x:0,y:y(v)},Number(v).toPrecision(5)));
for(const m of data.markers){const t=Number(BigInt(m.event)/4096n)/1000;
const line=el('line',{x1:x(t),x2:x(t),y1:40,y2:175,stroke:'#94a3b8','stroke-opacity':.25});
line.append(el('title',{},m.type+' '+new Date(t).toISOString()));svg.append(line)}
svg.append(el('polyline',{points:series.map((p,i)=>x(ts[i])+','+y(Number(p[key]))).join(' '),
fill:'none',stroke:color,'stroke-width':2}));
svg.append(el('text',{x:100,y:205},series[0].timestamp.slice(0,10)));
svg.append(el('text',{x:1040,y:205,'text-anchor':'end'},series.at(-1).timestamp.slice(0,10)));host.append(svg)}}
document.getElementById('scale').onclick=()=>{log=!log;charts()};charts();
function table(id,headers,rows){
const t=document.getElementById(id);const tr=document.createElement('tr');
for(const s of headers){const th=document.createElement('th');th.textContent=s;tr.append(th)}
t.append(tr);
for(const row of rows){const r=document.createElement('tr');
for(const s of row){const c=document.createElement('td');
c.textContent=s??'Não disponível';r.append(c)}
t.append(r)}}
table('compare',['Métrica','M007 + 5 parados','Cenário'],
[['Patrimônio inicial','105 USDT','105 USDT'],
...Object.entries({'total_final_equity':'Patrimônio final (USDT)',
'completed_cycles':'Ciclos completos','zero_cycle_days':'Dias sem ciclos',
'lock_hours':'Horas além de 24h em posição','operating_uptime':'Tempo operacional (fração)',
'inventory_open_fraction':'Tempo comprado (fração)','maximum_drawdown':'Drawdown máximo (fração)'})
.map(([k,label])=>[label,data.baseline[k],data.row[k]])]);
table('releases',['Timestamp','Perda USDT','Reserva antes','Transferência',
'Reserva depois','Nova faixa'],data.releases.map(r=>[
r.timestamp,r.loss_usdt,r.reserve_before,r.reserve_transfer,r.reserve_after,
r.new_low+' → '+r.new_high]));
</script></html>"""
    for key, value in {
        "__TITLE__": title,
        "__COUNT__": str(len(report["scenarios"])),
        "__DATA__": payload,
        "__SHA__": escape(report["identity"]["git_commit_sha"]),
        "__AUDIT__": audit_hash,
        "__START__": escape(report["identity"]["start"]),
        "__END__": escape(report["identity"]["end"]),
        "__PATH__": escape(str(audit_path)),
    }.items():
        html = html.replace(key, value)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(html, encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", required=True)
    parser.add_argument(
        "--report", type=Path, default=Path("reports/usdcusdt/M011-recovery-reserve-scenarios.json")
    )
    parser.add_argument(
        "--output", type=Path, default=Path("reports/usdcusdt/M011-recovery-reserve-dashboard.html")
    )
    args = parser.parse_args()
    render(args.report, args.scenario, args.output)
