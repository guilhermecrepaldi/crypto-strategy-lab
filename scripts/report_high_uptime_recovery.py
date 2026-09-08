"""Publish M012 compound capital, prefix economics and four evidence-only curves."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

from scripts.b10_checkpoint_scoreboard import reference_count

ROOT = Path("reports/usdcusdt")
FIELDS = (
    "SIMULATION_TIMESTAMP",
    "OPERATING_BANK",
    "RESERVE",
    "TOTAL_EQUITY",
    "CURRENT_POSITION_NOTIONAL",
    "FULL_FILL_CYCLES",
    "NET_POSITIVE_CYCLES",
    "CUMULATIVE_NET_PROFIT",
    "CUMULATIVE_RESERVE_FUNDING",
    "CUMULATIVE_RELEASE_LOSS",
    "ZERO_DAYS",
    "ACTIVE_DAYS",
    "MAX_HOLD_HOURS",
    "HARD_LOCK_VIOLATIONS",
    "REALITY_RETENTION",
    "MOTOR_UPTIME",
    "TARGET_RESERVE_AT_T",
    "RESERVE_MIN",
    "RESERVE_RATIO",
    "RESERVE_CONSUMPTION",
    "RELEASE_ATTEMPTS",
    "RELEASE_FILLED",
    "RELEASE_PARTIAL",
    "RELEASE_FAILED",
    "RELEASE_BLOCKED_BY_RESERVE",
    "LOCK_HOURS_GT12",
    "LOCK_HOURS_GT18",
    "LOCK_HOURS_GT24",
    "CAPACITY_LIMIT_REACHED",
)


def display(value):
    return "UNAVAILABLE" if value is None else str(value)


def read_curve_prefix(path, binding):
    if binding is None:
        raise ValueError("CAPITAL_CURVE_BINDING_REQUIRED")
    with path.open("rb") as stream:
        raw = stream.read(int(binding["bytes"]))
    if len(raw) != int(binding["bytes"]) or hashlib.sha256(raw).hexdigest() != binding["sha256"]:
        raise ValueError("CAPITAL_CURVE_PREFIX_HASH_MISMATCH")
    return [json.loads(line) for line in raw.splitlines() if line.strip()]


def curve_svg(rows, key, title):
    points = [
        (datetime.fromisoformat(row["SIMULATION_TIMESTAMP"]).timestamp(), float(row[key]))
        for row in rows
        if row.get("SIMULATION_TIMESTAMP") and row.get(key) is not None
    ]
    header = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 900 280" role="img">'
        f'<title>{html.escape(title)}</title><rect width="900" height="280" fill="white"/>'
        '<g font-family="sans-serif" fill="#172b4d" font-size="13">'
        f'<text x="80" y="24">{html.escape(title)} — USDT</text>'
    )
    if not points:
        return header + (
            '<text x="80" y="140">Sem observações publicadas. Nenhuma cur'
            "va estimada.</text></g></svg>"
        )
    xmin, xmax = min(p[0] for p in points), max(p[0] for p in points)
    ymin, ymax = min(p[1] for p in points), max(p[1] for p in points)
    pad = max((ymax - ymin) * 0.08, abs(ymax) * 0.001, 0.000001)
    ymin, ymax = ymin - pad, ymax + pad

    def x(v):
        return 85 + 775 * (v - xmin) / max(1, xmax - xmin)

    def y(v):
        return 225 - 175 * (v - ymin) / (ymax - ymin)

    body = '<path d="M85 45V225H860" stroke="#9aaac0" fill="none"/>'
    for i in range(5):
        value = ymin + (ymax - ymin) * i / 4
        body += f'<text x="77" y="{y(value) + 4:.2f}" text-anchor="end">{value:.6g}</text>'
    path = " ".join(
        f"{'M' if i == 0 else 'L'}{x(a):.2f},{y(b):.2f}" for i, (a, b) in enumerate(points)
    )
    body += f'<path d="{path}" stroke="#2365c7" stroke-width="2" fill="none"/>'
    body += (
        f'<circle cx="{x(points[-1][0]):.2f}" cy="{y(points[-1][1]):.2f}" r="3" fill="#2365c7"/>'
    )
    body += (
        f'<text x="85" y="250">{html.escape(rows[0]["SIMULATION_TIMESTAMP"][:10])}</text>'
        '<text x="860" y="250" text-anchor="end">'
        f"{html.escape(rows[-1]['SIMULATION_TIMESTAMP'][:10])}</text>"
        '<text x="470" y="272" text-anchor="middle">'
        "Data simulada UTC · pontos observados, não projeção</text>"
    )
    return header + body + "</g></svg>"


def publish(folder, tests_passed=None, tests_failed=None):
    raw = (folder / "scoreboard.json").read_bytes()
    score = json.loads(raw)
    if score.get("CAPITAL_MODE") != "COMPOUNDING":
        raise ValueError("FIXED_NOTIONAL_PRIMARY_FORBIDDEN")
    score["SOURCE_SCOREBOARD_SHA256"] = hashlib.sha256(raw).hexdigest()
    model_id = score.get("MODEL_ID", "M012")
    if model_id not in ("M012", "M014"):
        raise ValueError("UNSUPPORTED_REPORT_MODEL")
    if model_id == "M014":
        from scripts.run_high_uptime_recovery import file_sha

        if file_sha(folder / "checkpoint.json") != score.get("CHECKPOINT_SHA256"):
            raise ValueError("CHECKPOINT_SCOREBOARD_BINDING_MISMATCH")
    event = score.get("CANONICAL_CUTOFF_EVENT")
    count = reference_count(event) if event and model_id == "M012" else None
    score["PRICE_PATH_OPPORTUNITIES_SAME_PREFIX"] = count
    cycles = score.get("FULL_FILL_CYCLES")
    score["REALITY_RETENTION"] = (
        str(Decimal(cycles) / count) if count and cycles is not None else None
    )
    score["RETENTION_SEMANTICS"] = (
        f"{model_id} ordinary full cycles / B10 historical ordinary opportun"
        "ities at same canonical event; productivity ratio, not match"
        "ed survivors or compound-return ratio."
    )
    score["SOFTWARE_VALIDATION"] = {
        "tests_passed": tests_passed,
        "tests_failed": tests_failed,
        "TEST_SUITE_PASS_IS_STRATEGY_PASS": False,
    }
    score["INDEPENDENT_RUN_AUDIT"] = "PENDING; preflight review is not full-run audit"
    score["VERDICT"] = (
        "PENDING" if score.get("RUN_STATUS") != "COMPLETE" else "PENDING_INDEPENDENT_AUDIT"
    )
    stamp = score.get("SIMULATION_TIMESTAMP")
    curve_path = folder / "capital-curve.jsonl"
    rows = []
    if curve_path.exists():
        for row in read_curve_prefix(curve_path, score.get("CAPITAL_CURVE_PREFIX")):
            if row.get("SIMULATION_TIMESTAMP") and stamp and row["SIMULATION_TIMESTAMP"] <= stamp:
                rows.append(row)
    ROOT.mkdir(parents=True, exist_ok=True)
    (ROOT / f"{model_id}-reality-scoreboard.json").write_text(
        json.dumps(score, indent=2) + "\n", encoding="utf-8"
    )
    fields = (
        FIELDS
        if model_id == "M012"
        else (
            "SIMULATION_TIMESTAMP",
            "RUN_STATUS",
            "OPERATING_BANK",
            "RESERVE",
            "TOTAL_EQUITY",
            "FULL_FILL_CYCLES",
            "NET_POSITIVE_CYCLES",
            "NET_REALIZED_PNL",
            "RESERVE_FUNDING",
            "RESERVE_CONSUMPTION",
            "MIN_RESERVE",
            "RELEASE_FILLED",
            "ZERO_CYCLE_DAYS",
            "MAX_HOLD_HOURS",
            "HOLDS_OVER_24H",
            "FLAT_HOURS",
            "HOLDING_HOURS",
            "WORKING_ORDER_HOURS",
            "MAX_DRAWDOWN_PCT",
            "EXTENSION_STATUS",
        )
    )
    table = "| Métrica | Valor |\n|---|---|\n" + "".join(
        f"| {key} | {display(score.get(key))} |\n" for key in fields
    )
    report = (
        "# M012 REALITY — CURRENT SCOREBOARD\n\nCOMPOUNDING ·100 USDT i"
        "niciais +5 de reserva ·95% reinvestimento /5% reserva.\n\n"
    ) + table
    if model_id == "M014":
        report = (
            "# M014 — B10 F2.5 com reserva reforçada\n\n"
            "Primeira semana somente · 100 USDT operacionais + 10 de reserva · "
            "COMPOUNDING · 10% dos lucros positivos para a reserva.\n\n"
        ) + table
        daily = {}
        for row in rows:
            if row.get("CHECKPOINT_REASON", "").startswith("DAY_"):
                day = (
                    (datetime.fromisoformat(row["SIMULATION_TIMESTAMP"]) - timedelta(days=1))
                    .date()
                    .isoformat()
                )
                daily[day] = row
        score["DAILY_CLOSES"] = daily
        report += (
            "\n## Fechamentos diários\n\n"
            "| Dia UTC | Banca USDT | Reserva USDT | Patrimônio USDT | "
            "Ciclos completos | Positivos | Releases |\n"
            "|---|---:|---:|---:|---:|---:|---:|\n"
        )
        previous_releases = 0
        for day, row in sorted(daily.items()):
            releases = row.get("RELEASE_FILLED", 0)
            report += (
                f"| {day} | {Decimal(row['OPERATING_BANK']):.6f} | {Decimal(row['RESERVE']):.6f} | "
                f"{Decimal(row['TOTAL_EQUITY']):.6f} | "
                f"{row.get('DAILY_FULL_CYCLES', {}).get(day, 0)} | "
                f"{row.get('DAILY_NET_POSITIVE_CYCLES', {}).get(day, 0)} | "
                f"{releases - previous_releases} |\n"
            )
            previous_releases = releases
        score["DAYS_MEETING_2000_TARGET"] = sum(
            row.get("DAILY_NET_POSITIVE_CYCLES", {}).get(day, 0) >= 2000
            for day, row in daily.items()
        )
        report += (
            f"\nMeta de 2.000 ciclos positivos: {score['DAYS_MEETING_2000_TARGET']} de "
            f"{len(daily)} dias fechados. Releases não entram na meta.\n\n"
            "O resultado é condicional às hipóteses de execução; não é uma operação real. "
            "Próxima semana NÃO autorizada, mesmo que a meta seja atingida.\n"
        )
        (ROOT / f"{model_id}-reality-scoreboard.json").write_text(
            json.dumps(score, indent=2) + "\n", encoding="utf-8"
        )
    report += (
        "\n## Curvas de capital\n\nValores observados no replay condicional; não são projeções.\n\n"
    )
    for key, name, title in (
        ("TOTAL_EQUITY", "equity", "Patrimônio total"),
        ("OPERATING_BANK", "operating", "Banca operacional — custo contábil"),
        ("RESERVE", "reserve", "Reserva de recuperação"),
        ("CYCLE_NOTIONAL", "notional", "Orçamento do ciclo"),
    ):
        (ROOT / f"{model_id}-{name}-curve.svg").write_text(
            curve_svg(rows, key, title), encoding="utf-8"
        )
        report += f"![{title}]({model_id}-{name}-curve.svg)\n\n"
    report += (
        "\n## Testes do software\n\n"
        + json.dumps(score["SOFTWARE_VALIDATION"])
        + "\n\nTEST_SUITE_PASS != STRATEGY_PASS. Auditoria independente do replay: PENDING.\n"
    )
    report += (
        "\n## Resultado final\n\n"
        + score["VERDICT"]
        + (
            ". Custos/L2 históricos incompletos; perfil parametrizado con"
            "dicional, não promessa de crescimento real.\n"
        )
    )
    (ROOT / f"{model_id}-reality-report.md").write_text(report, encoding="utf-8")
    current = (
        "# CURRENT STATE\n\nHISTORICAL_STRATEGY=B10_FROZEN\nACTIVE_RESEA"
        "RCH_MODEL=M012\nCAPITAL_MODE=COMPOUNDING\nRESERVE_FUNDING=5%\nR"
        "ESERVE_TARGET=5%\nMAX_POSITION_LOCK=24h\n"
    )
    if model_id == "M014":
        current = (
            "# CURRENT STATE\n\nRESEARCH_PROTOCOL=WEEKLY_OWNER_GATED\n"
            "ACTIVE_RESEARCH_MODEL=M014\nCAPITAL_MODE=COMPOUNDING\n"
            "INITIAL_OPERATING=100\nINITIAL_RESERVE=10\nRESERVE_FUNDING=10%\n"
            "DAILY_TARGET=2000\nNEXT_WEEK_AUTHORIZED=false\nAUTOMATIC_EXTENSION_ALLOWED=false\n"
        )
    current += "\n".join(
        f"{key}={display(score.get(key))}" for key in ("RUN_ID", "RUN_STATUS", *fields, "VERDICT")
    )
    current += (
        "\nNEXT_ACTION=Continuar configuração congelada; publicar marc"
        "os materiais e auditar.\nFIXED_100_RESULT_NOT_OWNER_STRATEGY_"
        "RETURN=YES\n"
    )
    if model_id == "M014":
        current += (
            "\nOWNER_GATE=First week only; preserve all state and await explicit approval "
            "before any following week.\nM013=INVALIDATED_TECHNICAL_PRESERVED\n"
        )
    Path("docs/research/CURRENT_STATE.md").write_text(current, encoding="utf-8")
    journal = Path(f"docs/research/{model_id}_JOURNAL.md")
    if not journal.exists():
        journal.write_text(f"# {model_id} JOURNAL\n", encoding="utf-8")
    marker = "SOURCE_SCOREBOARD_SHA256=" + score["SOURCE_SCOREBOARD_SHA256"]
    if marker not in journal.read_text(encoding="utf-8"):
        with journal.open("a", encoding="utf-8") as stream:
            stream.write(
                "\n## Capital checkpoint\n\nTYPE=CAPITAL_CHECKPOINT\n"
                + marker
                + "\n"
                + "\n".join(
                    f"{key}={display(score.get(key))}"
                    for key in (
                        "RUN_ID",
                        "EXECUTION_SOURCE_COMMIT",
                        "CHECKPOINT_REASON",
                        *fields,
                        "VERDICT",
                    )
                )
                + "\nCOMMIT=Containing publication commit.\n"
            )
    return score


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--run", type=Path, default=Path("artifacts/usdcusdt/models/M014/reality-primary")
    )
    parser.add_argument("--tests-passed", type=int)
    parser.add_argument("--tests-failed", type=int)
    args = parser.parse_args()
    result = publish(args.run, args.tests_passed, args.tests_failed)
    print(
        json.dumps(
            {
                key: result.get(key)
                for key in (
                    "SIMULATION_TIMESTAMP",
                    "OPERATING_BANK",
                    "RESERVE",
                    "TOTAL_EQUITY",
                    "FULL_FILL_CYCLES",
                    "VERDICT",
                )
            }
        )
    )
