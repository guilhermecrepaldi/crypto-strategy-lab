"""Owner scoreboard for the single, explicit consecutive synthetic L2 experiment."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from statistics import median

ENVELOPES = ("CONSERVATIVE_QUEUE", "PRICE_PRIORITY")
SYNTHETIC_SOURCE_DATES = (
    "2025-01-01",
    "2025-02-01",
    "2025-03-01",
    "2025-04-01",
    "2025-06-01",
    "2025-08-01",
    "2026-01-01",
    "2026-02-01",
    "2026-03-01",
    "2026-04-01",
    "2026-05-01",
    "2026-07-01",
)
SYNTHETIC_STATE = "SYNTHETIC_CONSECUTIVE_12D"
MODEL_HASH = "4231670b19b1ca5c2b5032b1476b83b3182d1463750ea944da5efb867d81a8fa"
DAILY_METRICS = (
    "OPERATING_START",
    "RESERVE_START",
    "OPERATING_FINAL",
    "RESERVE_FINAL",
    "TOTAL_EQUITY_FINAL",
    "DAILY_NET_PNL",
    "CUMULATIVE_NET_PNL",
    "DAILY_NET_POSITIVE_CYCLES",
    "CUMULATIVE_NET_POSITIVE_CYCLES",
    "MAX_HOLD_HOURS",
    "MOTOR_UPTIME",
    "OPEN_POSITION",
)


def candidates():
    return [
        f"{year}-{month:02d}-01"
        for year in (2025, 2026)
        for month in range(1, 13 if year == 2025 else 10)
    ]


def file_hash(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def quantile(values, percent):
    ordered = sorted(values)
    return ordered[max(0, (len(ordered) * percent + 99) // 100 - 1)] if ordered else None


def aggregate(rows, terminal):
    if not terminal or terminal.get("AUDIT_STATUS") != "PASS_CONDITIONAL":
        return {"AUDIT_STATUS": "AUDIT_PENDING", "AUDITED_DAYS": 0}
    if len(rows) != 12 or any(row["DAILY_NET_POSITIVE_CYCLES"] is None for row in rows):
        raise ValueError("INCOMPLETE_TERMINAL_DAILY_REPORT")
    final = Decimal(rows[-1]["TOTAL_EQUITY_FINAL"])
    if final != Decimal(terminal["TOTAL_EQUITY_FINAL"]):
        raise ValueError("TERMINAL_DAILY_EQUITY_MISMATCH")
    cycles = [int(row["DAILY_NET_POSITIVE_CYCLES"]) for row in rows]
    best = min(rows, key=lambda row: (-row["DAILY_NET_POSITIVE_CYCLES"], row["LOGICAL_DAY"]))
    worst = min(rows, key=lambda row: (row["DAILY_NET_POSITIVE_CYCLES"], row["LOGICAL_DAY"]))
    return {
        "STATISTIC_CLASS": "DEPENDENT_DAYS_OF_SYNTHETIC_STRESS_PATH",
        "AUDIT_STATUS": "PASS_CONDITIONAL",
        "AUDITED_DAYS": 12,
        "TOTAL_CYCLES": sum(cycles),
        "MEDIAN_CYCLES": median(cycles),
        "P10_CYCLES": quantile(cycles, 10),
        "P90_CYCLES": quantile(cycles, 90),
        "MIN_CYCLES": min(cycles),
        "MAX_CYCLES": max(cycles),
        "DAYS_GE500": sum(value >= 500 for value in cycles),
        "DAYS_GE2000": sum(value >= 2000 for value in cycles),
        "ZERO_CYCLE_DAYS": cycles.count(0),
        "BEST_DAY": best["LOGICAL_DAY"],
        "WORST_DAY": worst["LOGICAL_DAY"],
        "FINAL_EQUITY": str(final),
        "SYNTHETIC_STRESS_RETURN": str(final / Decimal(110) - 1),
    }


def read_envelope(results_root, envelope):
    root = results_root / SYNTHETIC_STATE / envelope
    terminal_path = root / "summary.json"
    terminal = json.loads(terminal_path.read_bytes()) if terminal_path.exists() else None
    if terminal:
        if (
            terminal.get("MODEL_HASH") != MODEL_HASH
            or terminal.get("ENVELOPE") != envelope
            or terminal.get("RUN_STATUS") != "COMPLETE"
            or [item["source_date"] for item in terminal.get("source_day_mapping", [])]
            != list(SYNTHETIC_SOURCE_DATES)
        ):
            raise ValueError("TERMINAL_IDENTITY_MISMATCH")
        if file_hash(root / "all-fill-audit.json") != terminal.get("AUDIT_SHA256"):
            raise ValueError("TERMINAL_AUDIT_BINDING_MISMATCH")
    rows = []
    for number, day in enumerate(SYNTHETIC_SOURCE_DATES, 1):
        row = dict.fromkeys(DAILY_METRICS)
        row.update(
            LOGICAL_DAY=number,
            SOURCE_DATE=day,
            ENVELOPE=envelope,
            RUN_STATUS="NOT_STARTED",
            VERDICT="PENDING",
            AUDIT_STATUS="AUDIT_PENDING",
        )
        if number == 1:
            row.update(OPERATING_START="100", RESERVE_START="10")
        path = root / "daily" / f"{number:02d}.json"
        if path.exists():
            observed = json.loads(path.read_bytes())
            if any(
                observed.get(key) != row[key] for key in ("LOGICAL_DAY", "SOURCE_DATE", "ENVELOPE")
            ):
                raise ValueError("SYNTHETIC_IDENTITY_MISMATCH")
            if number > 1 and rows[-1]["OPERATING_FINAL"] is None:
                raise ValueError("DAILY_SEQUENCE_HAS_HOLE")
            if number > 1 and (
                Decimal(observed["OPERATING_START"]) != Decimal(rows[-1]["OPERATING_FINAL"])
                or Decimal(observed["RESERVE_START"]) != Decimal(rows[-1]["RESERVE_FINAL"])
            ):
                raise ValueError("DAILY_CAPITAL_CARRY_MISMATCH")
            row.update(observed)
            row["FILE_SHA256"] = file_hash(path)
            row["AUDIT_STATUS"] = "AUDIT_PENDING"
            if terminal and terminal.get("AUDIT_STATUS") == "PASS_CONDITIONAL":
                row.update(
                    AUDIT_STATUS="PASS_CONDITIONAL",
                    RUN_STATUS="COMPLETE",
                    VERDICT=terminal.get("VERDICT", "COMPLETE_CONDITIONAL_SYNTHETIC_STRESS"),
                )
        rows.append(row)
    progress_path, failure_path = root / "progress.json", root / "failure.json"
    progress = json.loads(progress_path.read_bytes()) if progress_path.exists() else None
    failure = json.loads(failure_path.read_bytes()) if failure_path.exists() else None
    return rows, aggregate(rows, terminal), terminal, progress, failure


def build(manifest, validation=None, *, results_root):
    expected = candidates()
    entries = {row["date"]: row for row in manifest["dates"]}
    if len(manifest["dates"]) != 21 or set(entries) != set(expected):
        raise ValueError("EXACT_21_CANDIDATES_REQUIRED")
    checks = {row["date"]: row for row in (validation or {}).get("days", [])}
    inventory = []
    for day in expected:
        source, check = entries[day], checks.get(day, {})
        inventory.append(
            {
                "SOURCE_DATE": day,
                "SOURCE_STATUS": source["status"],
                "L2_VALID": check.get("L2_DAY_VALID"),
                "L2_ROWS": source.get("rows"),
                "TRADES": check.get("TRADES"),
                "SELECTED": day in SYNTHETIC_SOURCE_DATES,
                "VALIDATION_STATUS": check.get("status", "PENDING"),
                "DATA_GATE_DETAILS": {
                    "errors": check.get("errors", []),
                    "native_counts": check.get("raw", {}).get("counts", {}),
                    "binding_errors": check.get("binding", {}).get("errors", []),
                    "trade_counts": check.get("trades", {}).get("counts", {}),
                },
            }
        )
    rows, groups, terminals, progress, failures = [], {}, {}, {}, {}
    for envelope in ENVELOPES:
        daily, stats, terminal, current, failure = read_envelope(results_root, envelope)
        rows.extend(daily)
        groups[envelope], terminals[envelope] = stats, terminal
        progress[envelope], failures[envelope] = current, failure
    raw = [part for item in entries.values() for part in item.get("raw_slices", [])]
    return {
        "schema": "usdcusdt-l2-monthly-scoreboard-v1",
        "GENERATED_AT": datetime.now(UTC).isoformat(),
        "L2_CANDIDATE_DATES": 21,
        "L2_AVAILABLE_FREE": sum(x["status"] == "AVAILABLE" for x in entries.values()),
        "L2_UNAVAILABLE": sum(x["status"] == "UNAVAILABLE" for x in entries.values()),
        "INTEGRITY_PASS": sum(x.get("L2_DAY_VALID") is True for x in checks.values()),
        "SELECTED_SOURCE_DAYS": 12,
        "TOTAL_ROWS": sum(x.get("rows", 0) for x in entries.values()),
        "TOTAL_BYTES": sum(x.get("bytes", 0) for x in entries.values())
        + sum(x.get("bytes", 0) for x in raw),
        "RAW_SLICES_COLLECTED": len(raw),
        "RAW_SLICES_EXPECTED": 3024,
        "RAW_STATUSES": dict(Counter(x["status"] for x in raw)),
        "REPLAY_MODE": SYNTHETIC_STATE,
        "STRATEGY_MODEL_USED": "M015",
        "QUEUE_MODEL": "OBSERVED_L2",
        "WEEK_2_CONTINUOUS_EXECUTED": False,
        "INITIALIZATION": "100_PLUS_10_ONCE_PER_ENVELOPE",
        "inventory": inventory,
        "rows": rows,
        "aggregates": groups,
        "terminal": terminals,
        "progress": progress,
        "failures": failures,
    }


def render(score):
    lines = [
        "# B10 melhorado — 12 dias consecutivos sintéticos",
        "",
        f"Dados: {score['L2_AVAILABLE_FREE']}/21 disponíveis; {score['INTEGRITY_PASS']}/21 "
        "aprovados no inventário; exatamente12 selecionados.",
        "",
        "Uma única banca inicial de100 USDT +10 de reserva por envelope. Capital, posições "
        "e ordens seguem entre dias. A sequência é artificial: "
        "não é retorno mensal histórico real.",
        "— significa resultado ainda indisponível, nunca zero. "
        "Banca e total são marcados a mercado.",
        "",
    ]
    for envelope in ENVELOPES:
        lines += [
            f"## {envelope}",
            "",
            "| Dia | Origem | Ciclos positivos | Banca | Reserva | Total | "
            "PnL dia | Max hold h | Uptime |",
            "|---:|---|---:|---:|---:|---:|---:|---:|---:|",
        ]
        for row in score["rows"]:
            if row["ENVELOPE"] != envelope:
                continue
            keys = (
                "LOGICAL_DAY",
                "SOURCE_DATE",
                "DAILY_NET_POSITIVE_CYCLES",
                "OPERATING_FINAL",
                "RESERVE_FINAL",
                "TOTAL_EQUITY_FINAL",
                "DAILY_NET_PNL",
                "MAX_HOLD_HOURS",
                "MOTOR_UPTIME",
            )
            lines.append(
                "| " + " | ".join("—" if row.get(k) is None else str(row[k]) for k in keys) + " |"
            )
        stats = score["aggregates"][envelope]
        lines += ["", f"Auditoria: {stats['AUDIT_STATUS']}.", ""]
        if stats["AUDIT_STATUS"] == "PASS_CONDITIONAL":
            lines += [
                f"Ciclos: {stats['TOTAL_CYCLES']}; mediana diária: {stats['MEDIAN_CYCLES']}. "
                f"Dias≥500: {stats['DAYS_GE500']}; dias≥2.000: {stats['DAYS_GE2000']}. "
                f"Equity final: {stats['FINAL_EQUITY']} USDT. Retorno sintético: "
                f"{Decimal(stats['SYNTHETIC_STRESS_RETURN']) * 100}%.",
                f"Melhor/pior dia por ciclos: {stats['BEST_DAY']} / {stats['WORST_DAY']}.",
                "",
            ]
    lines += [
        "## Inventário de origem (não amplia a sequência automaticamente)",
        "",
        "| Origem | Disponível | Integridade | Selecionado |",
        "|---|---|---|---|",
    ]
    for row in score["inventory"]:
        lines.append(
            f"| {row['SOURCE_DATE']} | {row['SOURCE_STATUS']} | "
            f"{row['VALIDATION_STATUS']} | {'Sim' if row['SELECTED'] else 'Não'} |"
        )
    lines += [
        "",
        "Testes de software não aprovam a estratégia. Uptime é fração das24h do dia; "
        "hold é o máximo acumulado, incluindo posições abertas. Fills são simulações "
        "condicionais; L2 não demonstra a posição FIFO real.",
        "",
    ]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest", type=Path, default=Path("data/manifests/usdcusdt-tardis-free-l2.json")
    )
    parser.add_argument(
        "--validation",
        type=Path,
        default=Path("reports/usdcusdt/L2-monthly-sample-validation.json"),
    )
    parser.add_argument(
        "--results", type=Path, default=Path("artifacts/usdcusdt/l2-monthly-samples")
    )
    args = parser.parse_args()
    manifest_bytes = args.manifest.read_bytes()
    score = build(
        json.loads(manifest_bytes),
        json.loads(args.validation.read_bytes()) if args.validation.exists() else None,
        results_root=args.results,
    )
    score["SOURCE_MANIFEST_SHA256"] = hashlib.sha256(manifest_bytes).hexdigest()
    root = Path("reports/usdcusdt")
    root.mkdir(parents=True, exist_ok=True)
    (root / "L2-monthly-sample-scoreboard.json").write_text(
        json.dumps(score, indent=2) + "\n", encoding="utf-8"
    )
    (root / "L2-monthly-sample-report.md").write_text(render(score), encoding="utf-8")
    print(
        json.dumps(
            {
                key: value
                for key, value in score.items()
                if key
                not in {"rows", "inventory", "aggregates", "terminal", "progress", "failures"}
            }
        )
    )


if __name__ == "__main__":
    main()
