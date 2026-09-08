"""Read-only economic autopsy; writes derived reports, never changes execution."""
# HTML prose and typographic punctuation are intentionally preserved verbatim.
# ruff: noqa: E501, RUF001

from __future__ import annotations

import argparse
import json
import subprocess
from collections import Counter
from decimal import Decimal as D
from decimal import localcontext
from html import escape
from pathlib import Path

from crypto_strategy_lab.domain import canonical_hash
from crypto_strategy_lab.microstructure.b10_reality import _decode
from crypto_strategy_lab.microstructure.recovery_reserve_study import file_sha, write_json
from crypto_strategy_lab.microstructure.reserve_recovery_diagnostics import analyze_recovery

ROOT = Path("artifacts/usdcusdt/l2-monthly-samples/SYNTHETIC_CONSECUTIVE_12D")
OUTPUT = Path("reports/usdcusdt/reserve-rotation-analysis.json")
HTML = Path("reports/usdcusdt/B10-execution-research.html")
FUNDING = ("0.10", "0.25", "0.50", "0.70", "0.80", "1.00")


def inspect_run(root):
    summary = json.loads((root / "summary.json").read_bytes())
    terminal = json.loads((root / "terminal-engine-state.json").read_bytes())
    if (
        summary["RUN_STATUS"] != "COMPLETE"
        or canonical_hash(terminal["state"]) != terminal["sha256"]
    ):
        raise ValueError("COMPLETE_HASH_BOUND_STATE_REQUIRED")
    state = _decode(terminal["state"])
    audit = json.loads((root / "all-fill-audit.json").read_bytes())
    if audit["status"] != "PASS_AUTOMATED_ALL_FILLS":
        raise ValueError("ALL_FILL_RECONCILIATION_REQUIRED")
    ledger = root / "execution-audit.jsonl"
    if ledger.stat().st_size != audit["journal"]["bytes"]:
        raise ValueError("CLOSED_LEDGER_SIZE_CHANGED")
    # One bounded projection through rg; no full book JSON deserialization.
    result = subprocess.run(
        [
            "rg",
            "--no-line-number",
            "-e",
            '"kind":"FILL"',
            "-e",
            '"kind":"RELEASE_SIGNAL"',
            str(ledger),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    evidence = [json.loads(line) for line in result.stdout.splitlines()]
    fills = [r for r in evidence if r["kind"] == "FILL"]
    if len(fills) != audit["fills_checked"]:
        raise ValueError("FILL_PROJECTION_COUNT_MISMATCH")
    settlements = state["settlements"]
    if sum(D(r["reserve_consumption"]) for r in settlements) != D(summary["RESERVE_CONSUMPTION"]):
        raise ValueError("CONSUMPTION_MISMATCH")
    if sum(D(r["reserve_contribution"]) for r in settlements) != D(summary["RESERVE_FUNDING"]):
        raise ValueError("FUNDING_MISMATCH")
    positions, previous = [], 0
    for index, row in enumerate(settlements):
        stamp = row["time_us"]
        part = [r for r in fills if previous < r["time_us"] <= stamp]
        buys = [r for r in part if r["side"] == "BUY"]
        if not buys:
            raise ValueError("SETTLEMENT_WITHOUT_FIRST_BUY")
        entry = min(r["time_us"] for r in buys)
        signals = [
            r for r in evidence if r["kind"] == "RELEASE_SIGNAL" and entry <= r["time_us"] <= stamp
        ]
        signal = signals[-1] if signals else None
        positions.append(
            {
                "index": index + 1,
                "entry_us": entry,
                "exit_us": stamp,
                "hold_hours": str(D(stamp - entry) / D(3_600_000_000)),
                "exceeds_two_hours": stamp - entry > 7_200_000_000,
                "release": row["release"],
                "net_profit": row["net_profit"],
                "reserve_consumption": row["reserve_consumption"],
                "reserve_after": row["reserve"],
                "fees": row["realized_fees_quote"],
                "release_signal": signal,
                "signal_to_settlement_seconds": str(D(stamp - signal["time_us"]) / D(1_000_000))
                if signal
                else None,
                "first_buy_source_id": buys[0]["source_id"],
                "execution_sources": sorted({r["source"] for r in part}),
                "hourly_veto_reasons": "UNAVAILABLE_NOT_PERSISTED_IN_OLD_RUN",
            }
        )
        previous = stamp
    end = int(summary["SIMULATION_TIMESTAMP_US"])
    open_hold = None
    if state["entry_us"] is not None:
        open_hold = {
            "entry_us": state["entry_us"],
            "age_hours": str(D(end - state["entry_us"]) / D(3_600_000_000)),
            "exceeds_two_hours": end - state["entry_us"] > 7_200_000_000,
            "censored": True,
        }
    recoveries = {f: analyze_recovery(settlements, D(f), end) for f in FUNDING}
    daily = [json.loads((root / "daily" / f"{i:02}.json").read_bytes()) for i in range(1, 13)]
    gains = [D(r["net_profit"]) for r in settlements if not r["release"] and D(r["net_profit"]) > 0]
    return {
        "summary": summary,
        "settlements": settlements,
        "positions": positions,
        "open_hold": open_hold,
        "two_hour_violations": sum(r["exceeds_two_hours"] for r in positions)
        + int(bool(open_hold and open_hold["exceeds_two_hours"])),
        "positive_profit_distribution": dict(Counter(str(g) for g in gains)),
        "positive_profit_total": str(sum(gains)),
        "daily_positive_cycles": [r["DAILY_NET_POSITIVE_CYCLES"] for r in daily],
        "recovery_sensitivity": recoveries,
        "evidence": {
            "terminal_sha256": file_sha(root / "terminal-engine-state.json"),
            "summary_sha256": file_sha(root / "summary.json"),
            "ledger_sha256_from_closed_audit": audit["journal"]["sha256"],
            "audit_sha256": file_sha(root / "all-fill-audit.json"),
            "fills_checked": len(fills),
            "source_commit": summary["published_config_sha"],
        },
    }


def render(data):
    out = [
        '<section id="reserva-equilibrio"><div class="eyebrow muted">OWNER / Reserva, recuperação e rotação</div>',
        "<h2>Quanto reservar não pode ser separado de quanto o motor perde.</h2>",
        "<p>Autópsia dos 12 dias encerrados. A sensibilidade abaixo redistribui lucros dos MESMOS fills: "
        "<strong>não é novo replay composto, não altera ciclos e não escolhe funding ótimo.</strong></p>",
        '<div class="callout amber"><p>Próxima etapa: contrato de saída protegida em duas horas, '
        "sem veto de oportunidade futura na emergência. Funding e reserva ficam inicialmente em 10% e 10 USDT "
        "para isolar o efeito. M015 permanece preservado. Execução nova somente após pré-registro, testes e revisão.</p></div>",
    ]
    for name, run in data["runs"].items():
        s = run["summary"]
        losses = D(s["RESERVE_CONSUMPTION"])
        gains = D(run["positive_profit_total"])
        out += [
            f"<h3>{escape(name)}</h3>",
            f"<p>Com 10% para reserva: {s['NET_POSITIVE_CYCLES']} ciclos positivos em 12 dias; "
            f"perda média por release {losses / D(s['RELEASES']):.5f} USDT; "
            f"reserva 10 → {D(s['RESERVE_FINAL']):.5f}; "
            f"patrimônio 110 → {D(s['TOTAL_EQUITY']):.5f}; "
            f"<strong>{run['two_hour_violations']} posições excederam duas horas</strong> "
            "(incluindo aberta censurada, quando houver).</p>",
            '<p class="note">O modelo histórico não possuía deadline de 2h. Estas violações são avaliação '
            "descritiva pelo novo objetivo, não invalidação técnica retroativa. Taxas zero no profile.</p>",
            f"<p>Lucros positivos: {gains:.5f} USDT. Releases: {losses:.5f} USDT. "
            f"Mesmo destinar 100% destes lucros não reporia todo o consumo. "
            f"A razão consumo/lucros foi {losses / gains:.2f}.</p>",
            '<div class="table-wrap"><table><thead><tr><th>Funding</th><th>Aporte total</th>'
            "<th>Reserva final · mesmos fills</th><th>Parte retida operacional</th></tr></thead><tbody>",
        ]
        for f in FUNDING:
            funding = D(f)
            out.append(
                f"<tr><td>{funding * 100:.0f}%</td><td>{gains * funding:.5f}</td>"
                f"<td>{D(10) + gains * funding - losses:.5f}</td><td>{gains * (1 - funding):.5f}</td></tr>"
            )
        out.append(
            '</tbody></table></div><div class="table-wrap"><table><thead><tr>'
            "<th>Funding</th><th>Releases recuperados / total</th><th>Ciclos mediana / P90</th>"
            "<th>Tempo mediano h</th><th>Dívida aberta USDT</th></tr></thead><tbody>"
        )
        for f, rec in run["recovery_sensitivity"].items():
            time = rec["median_recovery_hours"]
            shown_time = f"{D(time):.3f}" if time is not None else "—"
            out.append(
                f"<tr><td>{D(f) * 100:.0f}%</td><td>{rec['recovered_count']} / {s['RELEASES']}</td>"
                f"<td>{rec['median_recovery_cycles'] if rec['median_recovery_cycles'] is not None else '—'}"
                f" / {rec['p90_recovery_cycles'] if rec['p90_recovery_cycles'] is not None else '—'}</td>"
                f"<td>{shown_time}</td><td>{D(rec['outstanding_debt']):.5f}</td></tr>"
            )
        out.append(
            '</tbody></table></div><p class="note">Medianas/P90 são somente dos releases quitados; '
            "os restantes continuam abertos. Reposição FIFO: cada aporte paga a dívida mais antiga; "
            "não reutilizamos o mesmo lucro em vários releases. Excedentes anteriores permanecem no saldo, "
            "mas não apagam a obrigação de recuperação de uma perda futura.</p><h3>Ciclos positivos por dia lógico</h3>"
        )
        maximum = max(run["daily_positive_cycles"]) or 1
        for i, count in enumerate(run["daily_positive_cycles"], 1):
            out.append(
                f'<div style="display:flex;align-items:center;gap:10px;margin:5px 0">'
                f'<span style="width:55px">Dia {i}</span><div style="flex:1;background:#eef3f8">'
                f'<div style="width:{count / maximum * 100:.2f}%;height:16px;background:#175cd3"></div></div>'
                f'<strong style="width:25px">{count}</strong></div>'
            )
        out.append(
            '<div class="table-wrap"><table><thead><tr><th>Release</th><th>Perda USDT</th>'
            "<th>Posição aberta h</th><th>Sinal → encerramento s</th></tr></thead><tbody>"
        )
        for row in run["positions"]:
            if row["release"]:
                out.append(
                    f"<tr><td>Posição {row['index']}</td><td>{D(row['reserve_consumption']):.5f}</td>"
                    f"<td>{D(row['hold_hours']):.4f}</td><td>{row['signal_to_settlement_seconds']}</td></tr>"
                )
        out.append("</tbody></table></div>")
    out += [
        "<p><strong>Causa identificada:</strong> H1 significava revisão horária, não timeout. "
        "A regra exigia perda dentro de 10 bps e destino causal com ciclos suficientes. No hold de 132h, "
        "havia reserva acima do piso, mas perdas marcadas nos fechamentos dos dias 2–6 excediam 10 bps. "
        "Não há registro de todos os motivos dos vetos horários antigos.</p>",
        '<p><a href="reserve-rotation-analysis.json">Dados completos: recuperação FIFO, casos censurados, '
        "aportes, dívida e proveniência</a>. Valores em USDT; nenhum retorno em dólar é garantido.</p></section>",
    ]
    return "\n".join(out)


def main():
    argparse.ArgumentParser(description=__doc__).parse_args()
    with localcontext() as ctx:
        ctx.prec = 128
        data = {
            "classification": "FROZEN_FILL_ACCOUNTING_ONLY_NOT_COMPOUNDING_REPLAY",
            "runs": {
                name: inspect_run(ROOT / name) for name in ("CONSERVATIVE_QUEUE", "PRICE_PRIORITY")
            },
        }
        write_json(OUTPUT, data)
        start, end = "<!-- RESERVE_ROTATION_START -->", "<!-- RESERVE_ROTATION_END -->"
        html = HTML.read_text(encoding="utf-8")
        block = start + "\n" + render(data) + "\n" + end
        if start in html:
            left, tail = html.split(start, 1)
            html = left + block + tail.split(end, 1)[1]
        else:
            html = html.replace('<section id="conclusao">', block + '\n<section id="conclusao">', 1)
        HTML.write_text(html, encoding="utf-8")
        print(json.dumps({"output": str(OUTPUT), "envelopes": list(data["runs"])}))


if __name__ == "__main__":
    main()
