"""Standalone retrospective visualization. Never imported by the experimental runtime."""

import argparse
import csv
import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal
from html import escape
from pathlib import Path


def collect_comparison(root: Path) -> dict:
    """Read lightweight evidence only. Never run a simulation or read giant replay files."""
    sources = {}

    def read(path: Path) -> dict:
        raw = path.read_bytes()
        sources[path.relative_to(root).as_posix()] = hashlib.sha256(raw).hexdigest()
        return json.loads(raw)

    registry = read(root / "reports/usdcusdt/model-registry.json")
    transition = read(root / "reports/usdcusdt/OWNER-strategy-transition-evidence.json")
    release_report = read(root / "reports/usdcusdt/M010-capital-release.json")
    strategies, rows, failures = [], [], []
    for model in registry["models"]:
        mid = model["model_id"]
        strategies.append(
            {
                "id": mid,
                "config": model["model"],
                "hypothesis": model["hypothesis"],
                "lineage": model["lineage"],
                "status": model["status"],
                "hash": model["model_hash"],
            }
        )
        evaluations = [
            e["payload"]
            for e in registry["events"]
            if e["event_type"] == "EVALUATION_RECORDED" and e["payload"]["model_id"] == mid
        ]
        for i, ev in enumerate(evaluations or [None]):
            row = {
                "id": mid,
                "strategy": mid,
                "family": "Modelos",
                "initial": model["model"].get("total_initial_equity", "100"),
                "status": model["status"],
                "group": "principal",
                "source": "registry",
                "note": "Capital inicial 100 USDT; sem reserva segregada.",
                "metrics": {},
            }
            if ev is None:
                row.update(status="NOT_RUN", note="Identidade registrada; sem avaliação publicada.")
                if model["status"] == "SUPERSEDED":
                    row.update(status="SUPERADO_SEM_EXECUÇÃO", group="historico")
                if mid == "M011":
                    row["note"] = "Pré-registro: 100 operacional + 5 reserva. Não executado."
                rows.append(row)
                continue
            directory = root / ev["artifact_directory"].replace("\\", "/")
            metrics = read(directory / "metrics.json")
            row.update(
                source=(directory / "metrics.json").relative_to(root).as_posix(),
                evaluation=ev["EVALUATION_HASH"],
                metrics=metrics,
            )
            if i != len(evaluations) - 1:
                row.update(
                    group="historico",
                    status="AVALIAÇÃO_ANTERIOR",
                    note="Avaliação anterior preservada; não duplicar na comparação principal.",
                )
            if model["status"] == "INVALIDATED":
                row.update(group="historico", note="Modelo invalidado; números não elegíveis.")
            row.update(
                cycles=metrics.get("completed_cycles"),
                equity=metrics.get("final_marked_equity"),
                operating=metrics.get("final_marked_equity"),
                reserve="0",
                releases=0,
                fees=metrics.get("fees_quote"),
            )
            daily_path = directory / "daily.csv"
            if daily_path.exists():
                raw = daily_path.read_bytes()
                sources[daily_path.relative_to(root).as_posix()] = hashlib.sha256(raw).hexdigest()
                daily = list(csv.DictReader(raw.decode("utf-8").splitlines()))
                counts = [int(d["completed_cycles"]) for d in daily]
                row.update(
                    zero=sum(c == 0 for c in counts),
                    active=sum(c > 0 for c in counts),
                    days=len(counts),
                    monthly={},
                    mean=str(Decimal(sum(counts)) / len(counts)) if counts else None,
                )
                for d in daily:
                    month = d["period"][:7]
                    row["monthly"][month] = row["monthly"].get(month, 0) + int(
                        d["completed_cycles"]
                    )
            if mid in release_report and i == len(evaluations) - 1:
                extra = release_report[mid]
                row.update(
                    lock=extra.get("HOURS_POSITION_OLDER_THAN_24H"),
                    hold=str(Decimal(extra["MAX_HOLD"]) / 3600),
                    drawdown=extra.get("MAX_DRAWDOWN"),
                    releases=extra.get("CAPITAL_RELEASE_COUNT"),
                    median=extra.get("MEDIAN_CYCLES_DAY"),
                )
            rows.append(row)

    invalid_identities = {}
    failure_paths = set((root / "reports/usdcusdt").glob("*technical-failure*.json"))
    failure_paths.update(
        root / "reports/usdcusdt" / name
        for name in ("M010-event-id-failure.json", "M011-recovery-reserve-precision-audit.json")
    )
    for path in sorted(failure_paths):
        failure = read(path)
        failure.setdefault("classification", "AUDITORIA_TÉCNICA")
        failures.append({"source": path.relative_to(root).as_posix(), "data": failure})
        if failure.get("artifact_identity"):
            invalid_identities[failure["artifact_identity"]] = failure.get(
                "scope_decision", "INVALIDATED_TECHNICAL"
            )
    current_identity = Path(transition["run"]["path"]).name
    for directory in sorted((root / "artifacts/usdcusdt/recovery-reserve").iterdir()):
        if not (directory / "identity.json").exists():
            continue
        identity = read(directory / "identity.json")
        rid = directory.name
        for path in sorted(directory.glob("*/completed.json")):
            completed = read(path)
            summary = completed["summary"]
            sid = path.parent.name
            key = f"{sid} · {rid[:8]}"
            config = completed["identity"].get("reserve_config", {})
            strategies.append(
                {
                    "id": key,
                    "config": config,
                    "hash": rid,
                    "status": "SUPERSEDED_BY_OWNER_STRATEGY_UPDATE",
                    "hypothesis": {
                        "description": (
                            "M007 + reserva: cobrir integralmente uma release, restaurar a banca "
                            "e esperar novo LOW. B = limite em basis points (10 bps = 0,10%, "
                            "não 10%). H = horas; F = piso da reserva em USDT. "
                            "Esta regra histórica não é o M011 dinâmico."
                        )
                    },
                    "lineage": {"parent_model_id": "M007", "schema": identity["schema"]},
                }
            )
            valid = summary.get("integrity_pass") is True
            hashes_ok = bool(completed.get("artifact_hashes"))
            for filename, expected in completed.get("artifact_hashes", {}).items():
                target = path.parent / filename
                # Existing lightweight sidecars only; never inflate replay/checkpoint payloads.
                if target.exists() and target.stat().st_size < 20_000_000:
                    hashes_ok &= hashlib.sha256(target.read_bytes()).hexdigest() == expected
                else:
                    hashes_ok = False
            good = rid == current_identity and valid and hashes_ok
            row = {
                "id": key,
                "strategy": key,
                "family": identity["schema"],
                "initial": identity.get("total_initial_equity", "105"),
                "group": "principal" if good else "historico",
                "status": "CONCLUÍDO_SUPERADO" if good else "HISTÓRICO_NÃO_ELEGÍVEL",
                "source": path.relative_to(root).as_posix(),
                "metrics": summary,
                "note": invalid_identities.get(
                    rid,
                    "Hipótese superada pelo OWNER; não é M011. Auditoria armazenada "
                    "+ hashes de sidecars, sem novo replay da contabilidade.",
                ),
                "cycles": summary.get("completed_cycles"),
                "zero": summary.get("zero_cycle_days"),
                "active": summary.get("active_days"),
                "releases": summary.get("release_count"),
                "operating": summary.get("final_operating_equity"),
                "reserve": summary.get("reserve_final"),
                "equity": summary.get("total_final_equity", summary.get("final_total_equity")),
                "hold": summary.get("max_hold_hours"),
                "lock": summary.get("lock_hours"),
                "drawdown": summary.get("maximum_drawdown"),
                "uptime": summary.get("operating_uptime"),
                "loss": summary.get("total_release_loss"),
                "integrity": valid,
                "sidecar_hashes": hashes_ok,
                "monthly": {
                    k: v["completed_cycles"] for k, v in summary.get("monthly", {}).items()
                },
            }
            rows.append(row)
        for partial in sorted(directory.glob("*/checkpoint.json")):
            if partial.with_name("completed.json").exists():
                continue
            partial_key = f"{partial.parent.name} · {rid[:8]}"
            configs = [
                c
                for c in identity.get("grid", [])
                if partial.parent.name
                == (
                    f"RRV2_H{c.get('lock_hours')}_B{c.get('max_loss_bps')}_F{c.get('reserve_floor')}"
                )
            ]
            strategies.append(
                {
                    "id": partial_key,
                    "hash": rid,
                    "status": "PARCIAL",
                    "config": configs[0]
                    if len(configs) == 1
                    else {"scenario": partial.parent.name},
                    "hypothesis": {
                        "description": "Recovery Reserve histórica; checkpoint parcial. "
                        "Sem resultado econômico final ou autorização de retomada."
                    },
                    "lineage": {"parent_model_id": "M007", "schema": identity["schema"]},
                }
            )
            rows.append(
                {
                    "id": partial_key,
                    "strategy": partial_key,
                    "family": identity["schema"],
                    "group": "historico",
                    "status": "PARCIAL",
                    "source": partial.relative_to(root).as_posix(),
                    "note": "Checkpoint preservado, sem conclusão. Não é resultado final; "
                    "não foi carregado para evitar reprocessamento pesado.",
                    "metrics": {"checkpoint_bytes": partial.stat().st_size},
                }
            )

    base = transition["baseline"]
    rows.append(
        {
            "id": "M007 + 5 parados",
            "strategy": "M007",
            "family": "Controle histórico",
            "initial": "105",
            "group": "principal",
            "status": "BASELINE_HISTÓRICO",
            "source": base["path"],
            "note": "Reserva sem funding: não é o futuro controle pareado de M011.",
            "cycles": base["cycles"],
            "zero": base["zero_cycle_days"],
            "active": base["active_days"],
            "releases": 0,
            "operating": base["operating_equity"],
            "reserve": base["reserve"],
            "equity": base["total_equity"],
            "hold": base["max_hold_hours"],
            "lock": base["lock_hours"],
            "uptime": base["operating_uptime"],
            "drawdown": base["maximum_drawdown"],
            "metrics": base,
        }
    )
    for row in rows:
        if row.get("cycles") is not None:
            row["multiplier"] = str(Decimal(row["cycles"]) / 344704)
    return {
        "generated": datetime.now(UTC).isoformat(),
        "rows": rows,
        "strategies": strategies,
        "failures": failures,
        "sources": sources,
        "protocol": (root / "docs/microstructure/RECOVERY_DYNAMIC_PREREGISTRATION.md").read_text(
            encoding="utf-8"
        ),
        "scope": "USDCUSDT · DEVELOPMENT · 01/01/2026 a 05/09/2026",
    }


def render_comparison(root: Path, output: Path) -> dict:
    data = collect_comparison(root)
    template = Path(__file__).with_name("recovery_comparison.html").read_text(encoding="utf-8")
    content = static_comparison(data, template)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(content, encoding="utf-8")
    return data


def display_number(value, percent=False) -> str:
    if value is None:
        return "—"
    number = Decimal(str(value)) * (100 if percent else 1)
    if not number.is_finite():
        return str(value)
    if abs(number) >= Decimal("1e15"):
        formatted = f"{number:.5E}"
    else:
        formatted = f"{number:,.4f}".rstrip("0").rstrip(".")
    return formatted.translate(str.maketrans({",": ".", ".": ","})) + ("%" if percent else "")


def static_comparison(data: dict, template: str) -> str:
    """Complete content at build time; scripts enhance sorting only, never supply evidence."""

    def details(title, value):
        text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2)
        return f"<details><summary>{escape(title)}</summary><pre>{escape(text)}</pre></details>"

    indexes = {s["id"]: i for i, s in enumerate(data["strategies"])}
    table = []
    for row in data["rows"]:
        cells = [
            f"<td>{escape(row['id'])}<small>{escape(row['family'])}</small></td>",
            f"<td>{escape(row['status'])}</td>",
        ]
        for key in [
            "initial",
            "cycles",
            "multiplier",
            "zero",
            "active",
            "uptime",
            "releases",
            "operating",
            "reserve",
            "equity",
            "hold",
            "lock",
            "drawdown",
        ]:
            value = row.get(key)
            cells.append(
                f'<td title="{escape(str(value))}">'
                f"{display_number(value, key in ('uptime', 'drawdown'))}</td>"
            )
        attrs = " ".join(
            f'data-{k}="{escape(str(row.get(k, "")))}"'
            for k in ("id", "group", "cycles", "zero", "equity")
        )
        table.append(f"<tr {attrs}>{''.join(cells)}</tr>")

    charts = []
    for key, title, explanation in [
        (
            "cycles",
            "Ciclos completos",
            "Mais ciclos indicam maior frequência; não provam execução.",
        ),
        ("zero", "Dias sem ciclos", "Menos é melhor neste objetivo. Meta M011: no máximo 9 dias."),
        (
            "lock",
            "Horas de capital travado",
            "Soma do tempo em posição além de 24 horas. Menos é melhor.",
        ),
    ]:
        eligible = [r for r in data["rows"] if r["group"] == "principal" and r.get(key) is not None]
        maximum = max((Decimal(str(r[key])) for r in eligible), default=Decimal(1)) or Decimal(1)
        bars = []
        for row in eligible:
            width = Decimal(str(row[key])) / maximum * 100
            bars.append(
                f'<div class="bar-row"><span title="{escape(row["id"])}">'
                f'{escape(row["id"])}</span><div class="track"><div class="bar" '
                f'style="width:{width:.6f}%"></div></div>'
                f"<strong>{display_number(row[key])}</strong></div>"
            )
        charts.append(
            f'<article class="chart"><h3>{title}</h3><p>{explanation}</p>'
            f"{''.join(bars) or '<p>Dados não publicados.</p>'}</article>"
        )

    descriptions = {
        "STATIC": "Seleciona uma faixa e mantém LOW/HIGH fixos, sem reseleção periódica.",
        "PERIODIC_RESELECT": "Reavalia a faixa no intervalo registrado; preserva um ciclo serial.",
        "ALWAYS_BEST": "Sem posição aberta, escolhe a faixa de maior score no prefixo causal. "
        "Depois da compra, mantém LOW/HIGH até a saída normal.",
        "RELATIVE_SCORE_HYSTERESIS": "Só troca de faixa quando a vantagem relativa do score "
        "satisfaz os parâmetros registrados.",
        "IDLE_TRIGGERED": "Usa ociosidade como gatilho de reseleção, com os controles registrados.",
        "DYNAMIC_CAUSAL_RECOVERY": "Banca de 100 USDT e reserva segregada de 5 USDT. Destina 2% "
        "de cada lucro positivo à reserva. Exige evidência causal, "
        "confiança crescente com a perda e cobertura integral para "
        "liberar a posição. Restaura a banca, fica sem posição e "
        "espera novo LOW. Ainda não executado.",
    }
    radios, labels, panels, css = [], [], [], []
    for strategy in data["strategies"]:
        sid = strategy["id"]
        i = indexes[sid]
        checked = " checked" if sid == "M011" else ""
        radios.append(
            f'<input class="tab-radio" type="radio" name="strategy" id="s{i}"'
            f' aria-label="{escape(sid)}"{checked}>'
        )
        labels.append(f'<label for="s{i}">{escape(sid)}</label>')
        css.append(
            f"#s{i}:checked~.panels #p{i}{{display:block}}"
            f"#s{i}:checked~.tabs label[for=s{i}]{{background:#172235;color:white}}"
            f"#s{i}:focus-visible~.tabs label[for=s{i}]{{outline:3px solid #245de8}}"
        )
        cfg = strategy["config"]
        description = descriptions.get(
            cfg.get("strategy"),
            strategy["hypothesis"].get(
                "description",
                "Recovery Reserve histórica; parâmetros originais preservados abaixo.",
            ),
        )
        extra = ""
        if sid == "M010":
            extra = (
                "<p>Acrescenta a regra congelada de capital release ao ancestral M007. "
                "O replay terminou com zero releases; resultado registrado como inconclusivo.</p>"
            )
        if "max_loss_bps" in cfg:
            extra += f"<p>Revisão após {escape(str(cfg.get('lock_hours')))} horas; limite de perda "
            extra += f"{escape(str(cfg['max_loss_bps']))} bps "
            extra += f"({display_number(Decimal(str(cfg['max_loss_bps'])) / 100)}%). "
            extra += "Esse limite histórico não é a política dinâmica de M011.</p>"
        body = f"<h3>{escape(sid)}</h3><p>{escape(description)}</p>{extra}"
        body += '<p class="flow">Selecionar faixa → esperar LOW → um lote → saída normal no HIGH; '
        body += "release somente quando prevista e aprovada pela regra desta estratégia.</p>"
        body += f"<p>Status: {escape(strategy['status'])} · Pai: "
        body += escape(str(strategy["lineage"].get("parent_model_id") or "sem pai")) + "</p>"
        for row in data["rows"]:
            if row["strategy"] != sid:
                continue
            body += f"<p>{escape(row['note'])}</p>"
            body += details("Resultado exato · " + row["id"], row)
            if row.get("monthly"):
                body += '<h4>Ciclos por mês</h4><div class="table-wrap"><table><tr>'
                body += "".join(f"<th>{escape(m)}</th>" for m in row["monthly"])
                body += (
                    "</tr><tr>"
                    + "".join(f"<td>{display_number(v)}</td>" for v in row["monthly"].values())
                    + "</tr></table></div>"
                )
        body += details("Parâmetros completos", cfg)
        body += details("Hipótese e linhagem originais", strategy)
        if sid == "M011":
            body += '<p class="warning">Funding de 2% não garante reserva de 5% da banca. '
            body += "Sem releases, a proporção tende a 2,0408%. Não há resultado novo.</p>"
            body += details("Pré-registro completo", data["protocol"])
        panels.append(f'<article class="strategy-panel" id="p{i}">{body}</article>')

    replacements = {
        "__SCOPE__": escape(data["scope"]),
        "__COUNT__": str(len(data["rows"])),
        "__MODEL_COUNT__": str(sum(s["id"].startswith("M") for s in data["strategies"])),
        "__RR_COUNT__": str(sum(r["status"] == "CONCLUÍDO_SUPERADO" for r in data["rows"])),
        "__TABLE__": "".join(table),
        "__CHARTS__": "".join(charts),
        "__RADIOS__": "".join(radios),
        "__TABS__": "".join(labels),
        "__PANELS__": "".join(panels),
        "__TAB_CSS__": "".join(css),
        "__FAILURES__": "".join(
            details(f["data"]["classification"] + " · " + Path(f["source"]).name, f)
            for f in data["failures"]
        ),
        "__SOURCES__": escape(json.dumps(data["sources"], indent=2)),
        "__GENERATED__": escape(data["generated"]),
    }
    # One-pass substitution: source text can never be mistaken for another template token.
    import re

    return re.sub(r"__[A-Z_]+__", lambda match: replacements[match.group()], template)


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
    parser.add_argument("--scenario")
    parser.add_argument("--all-results", action="store_true")
    parser.add_argument(
        "--report", type=Path, default=Path("reports/usdcusdt/M011-recovery-reserve-scenarios.json")
    )
    parser.add_argument(
        "--output", type=Path, default=Path("reports/usdcusdt/M011-recovery-reserve-dashboard.html")
    )
    args = parser.parse_args()
    if args.all_results:
        result = render_comparison(Path.cwd(), args.output)
        print(
            f"HTML={args.output}; RESULTS={len(result['rows'])}; "
            f"STRATEGIES={len(result['strategies'])}"
        )
    elif args.scenario:
        render(args.report, args.scenario, args.output)
    else:
        parser.error("use --scenario or --all-results")
