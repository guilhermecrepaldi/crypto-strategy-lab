"""Report independent monthly L2 experiments without inventing missing outcomes."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from statistics import median

ENVELOPES = ("CONSERVATIVE_QUEUE", "PRICE_PRIORITY")
MODEL_HASH = "4231670b19b1ca5c2b5032b1476b83b3182d1463750ea944da5efb867d81a8fa"
METRICS = [
    "OPERATING_FINAL",
    "RESERVE_FINAL",
    "TOTAL_EQUITY_FINAL",
    "NET_PNL",
    "ORDINARY_CYCLES",
    "NET_POSITIVE_CYCLES",
    "CYCLES_PER_HOUR",
    "FULL_STOP_HOURS",
    "MOTOR_UPTIME",
    "CAPITAL_WEIGHTED_UPTIME",
    "ZERO_CYCLE_DAY",
    "BUY_ORDERS",
    "BUY_FULL",
    "BUY_PARTIAL",
    "BUY_ZERO_FILL",
    "SELL_FULL",
    "SELL_PARTIAL",
    "SELL_ZERO_FILL",
    "RELEASES",
    "RELEASE_LOSS",
    "MAX_HOLD",
    "HARD_LOCK_VIOLATIONS",
    "DISPLAYED_QUEUE_P50",
    "DISPLAYED_QUEUE_P90",
    "DISPLAYED_QUEUE_P99",
    "DEPTH_BEST_P50",
    "DEPTH_BEST_P90",
    "SPREAD_P50",
    "SPREAD_P90",
    "CAPACITY_PRESSURE",
    "OLD_PROXY_TO_OBSERVED_MEDIAN",
    "OLD_PROXY_ASSESSMENT",
]


def candidates():
    return [
        date(year, month, 1).isoformat()
        for year in (2025, 2026)
        for month in range(1, 13 if year == 2025 else 10)
    ]


def file_hash(path):
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def quantile(values, numerator):
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, (len(ordered) * numerator + 99) // 100 - 1)]


def aggregate(rows):
    completed = [
        row
        for row in rows
        if row["RUN_STATUS"] == "COMPLETE" and row.get("AUDIT_STATUS") == "PASS_CONDITIONAL"
    ]
    cycles = [int(row["NET_POSITIVE_CYCLES"]) for row in completed]

    def middle(key):
        values = [Decimal(str(row[key])) for row in completed if row.get(key) is not None]
        return str(median(values)) if values else None

    best = (
        min(completed, key=lambda row: (-int(row["NET_POSITIVE_CYCLES"]), row["DATE"]))
        if completed
        else None
    )
    worst = (
        min(completed, key=lambda row: (int(row["NET_POSITIVE_CYCLES"]), row["DATE"]))
        if completed
        else None
    )
    return {
        "STATISTIC_CLASS": "CROSS_SECTIONAL_INDEPENDENT_DAY_STATISTIC",
        "TOTAL_INDEPENDENT_DAYS": len(rows),
        "VALID_L2_DAYS": sum(row["L2_VALID"] is True for row in rows),
        "AUDITED_COMPLETED_DAYS": len(completed),
        "MEDIAN_CYCLES_PER_DAY": median(cycles) if cycles else None,
        "P10_CYCLES_PER_DAY": quantile(cycles, 10),
        "P90_CYCLES_PER_DAY": quantile(cycles, 90),
        "MIN_CYCLES_DAY": min(cycles) if cycles else None,
        "MAX_CYCLES_DAY": max(cycles) if cycles else None,
        "DAYS_GE500": sum(value >= 500 for value in cycles),
        "DAYS_GE2000": sum(value >= 2000 for value in cycles),
        "DAYS_WITH_ZERO_CYCLES": cycles.count(0),
        "MEDIAN_MOTOR_UPTIME": middle("MOTOR_UPTIME"),
        "MEDIAN_CAPITAL_WEIGHTED_UPTIME": middle("CAPITAL_WEIGHTED_UPTIME"),
        "MEDIAN_NET_RETURN": middle("DAILY_RETURN"),
        "MEDIAN_MAX_HOLD": middle("MAX_HOLD"),
        "MEDIAN_QUEUE": middle("DISPLAYED_QUEUE_P50"),
        "HARD_LOCK_VIOLATION_DAYS": sum(
            int(row.get("HARD_LOCK_VIOLATIONS") or 0) > 0 for row in completed
        ),
        "BEST_DAY": best["DATE"] if best else None,
        "WORST_DAY": worst["DATE"] if worst else None,
    }


def build(manifest, validation=None, *, results_root):
    expected = candidates()
    entries = {item["date"]: item for item in manifest["dates"]}
    if len(manifest["dates"]) != 21 or set(entries) != set(expected):
        raise ValueError("EXACT_21_CANDIDATES_REQUIRED")
    checks = {item["date"]: item for item in (validation or {}).get("days", [])}
    rows = []
    for day in expected:
        source, check = entries[day], checks.get(day, {})
        for envelope in ENVELOPES:
            row = {key: None for key in METRICS}
            row.update(
                {
                    "DATE": day,
                    "ENVELOPE": envelope,
                    "YEAR_ROLE": "CALIBRATION" if day.startswith("2025") else "EVALUATION",
                    "STRATEGY_MODEL_USED": "M015",
                    "MODEL_HASH": MODEL_HASH,
                    "L2_VALID": check.get("L2_DAY_VALID"),
                    "L2_ROWS": source.get("rows"),
                    "TRADES": check.get("TRADES"),
                    "OPERATING_START": "100",
                    "RESERVE_START": "10",
                    "REPLAY_MODE": "INDEPENDENT_24H",
                    "CAPITAL_MODE": "COMPOUNDING_WITHIN_DAY",
                    "RUN_STATUS": "NOT_STARTED",
                    "AUDIT_STATUS": "NOT_RUN",
                    "VERDICT": "PENDING_DATA_VALIDATION",
                    "UNAVAILABLE_UNTIL": "VALIDATED_NATIVE_DATA_AND_REPLAY",
                }
            )
            if source["status"] != "AVAILABLE" or row["L2_VALID"] is False:
                row.update(RUN_STATUS="DATA_BLOCKED", VERDICT="INCONCLUSIVE_DATA")
            result_file = results_root / day / envelope / "summary.json"
            if result_file.exists():
                result = json.loads(result_file.read_bytes())
                for key in ("DATE", "ENVELOPE", "STRATEGY_MODEL_USED", "MODEL_HASH"):
                    if result.get(key) != row[key]:
                        raise ValueError(f"RESULT_IDENTITY_MISMATCH:{day}:{key}")
                if (
                    row["L2_VALID"] is not True
                    or not check.get("input_sha256")
                    or result.get("VALIDATION_INPUT_SHA256") != check["input_sha256"]
                ):
                    raise ValueError(f"RESULT_VALIDATION_BINDING_MISMATCH:{day}")
                row.update(result)
                row["RESULT_FILE_SHA256"] = file_hash(result_file)
                if result.get("NET_PNL") is not None:
                    row["DAILY_RETURN"] = str(Decimal(result["NET_PNL"]) / Decimal(110))
            rows.append(row)
    raw_slices = [part for item in entries.values() for part in item.get("raw_slices", [])]
    return {
        "schema": "usdcusdt-l2-monthly-scoreboard-v1",
        "GENERATED_AT": datetime.now(UTC).isoformat(),
        "L2_CANDIDATE_DATES": len(expected),
        "L2_AVAILABLE_FREE": sum(item["status"] == "AVAILABLE" for item in entries.values()),
        "L2_UNAVAILABLE": sum(item["status"] == "UNAVAILABLE" for item in entries.values()),
        "CSV_TOTAL_BYTES": sum(item.get("bytes", 0) for item in entries.values()),
        "TOTAL_BYTES": sum(item.get("bytes", 0) for item in entries.values())
        + sum(item.get("bytes", 0) for item in raw_slices),
        "TOTAL_ROWS": sum(item.get("rows", 0) for item in entries.values()),
        "RAW_SLICES_COLLECTED": len(raw_slices),
        "RAW_SLICES_EXPECTED": 3024,
        "RAW_STATUSES": dict(Counter(item["status"] for item in raw_slices)),
        "INTEGRITY_PASS": sum(item.get("L2_DAY_VALID") is True for item in checks.values()),
        "STRATEGY_MODEL_USED": "M015",
        "REPLAY_MODE": "INDEPENDENT_24H",
        "QUEUE_MODEL": "OBSERVED_L2",
        "WEEK_2_CONTINUOUS_EXECUTED": False,
        "rows": rows,
        "aggregates": {
            envelope: {
                role: aggregate(
                    [
                        row
                        for row in rows
                        if row["ENVELOPE"] == envelope
                        and (role == "COMBINED" or row["YEAR_ROLE"] == role)
                    ]
                )
                for role in ("CALIBRATION", "EVALUATION", "COMBINED")
            }
            for envelope in ENVELOPES
        },
    }


def render(score):
    lines = [
        "# L2 mensal — ciclos por dia independente",
        "",
        f"CSV disponíveis: {score['L2_AVAILABLE_FREE']}/21. "
        f"Dias com integridade completa aprovada: {score['INTEGRITY_PASS']}/21.",
        "",
        "Cada dia/envelope começa com100 USDT +10 de reserva, FLAT. "
        "Não existe composição entre meses. — significa indisponível, não zero.",
        "",
    ]
    for envelope in ENVELOPES:
        lines += [f"## {envelope}", ""]
        for role in ("CALIBRATION", "EVALUATION"):
            lines += [
                f"### {'2025 — calibração' if role == 'CALIBRATION' else '2026 — avaliação'}",
                "",
                "| Data | Ciclos positivos | PnL USDT | Reserva | Max hold | "
                "Uptime | Fila P50 | Veredito |",
                "|---|---:|---:|---:|---:|---:|---:|---|",
            ]
            for row in score["rows"]:
                if row["ENVELOPE"] == envelope and row["YEAR_ROLE"] == role:
                    keys = (
                        "DATE",
                        "NET_POSITIVE_CYCLES",
                        "NET_PNL",
                        "RESERVE_FINAL",
                        "MAX_HOLD",
                        "MOTOR_UPTIME",
                        "DISPLAYED_QUEUE_P50",
                        "VERDICT",
                    )
                    lines.append(
                        "| "
                        + " | ".join("—" if row.get(key) is None else str(row[key]) for key in keys)
                        + " |"
                    )
            lines.append("")
        lines += [
            "### Distribuição dos dias independentes",
            "",
            "| Grupo | Auditados | Mediana ciclos | P10 / P90 | Mín / Máx | ≥500 | ≥2.000 | "
            "Retorno diário mediano |",
            "|---|---:|---:|---:|---:|---:|---:|---:|",
        ]
        for role in ("CALIBRATION", "EVALUATION", "COMBINED"):
            group = score["aggregates"][envelope][role]

            def show(key, group=group):
                value = group[key]
                return "—" if value is None else str(value)

            lines.append(
                f"| {role} | {show('AUDITED_COMPLETED_DAYS')} | "
                f"{show('MEDIAN_CYCLES_PER_DAY')} | {show('P10_CYCLES_PER_DAY')} / "
                f"{show('P90_CYCLES_PER_DAY')} | {show('MIN_CYCLES_DAY')} / "
                f"{show('MAX_CYCLES_DAY')} | {show('DAYS_GE500')} | "
                f"{show('DAYS_GE2000')} | {show('MEDIAN_NET_RETURN')} |"
            )
        lines += [
            "",
            "COMBINED é distribuição transversal, não trajetória composta. "
            "Retorno é fração de110 USDT iniciais; uptime é fração das24h.",
            "",
        ]
    lines += [
        "## Interpretação",
        "",
        "Software aprovado não é estratégia aprovada. "
        "L2 mostra quantidade exibida, não a posição exata da ordem na fila. "
        "Resultados sem auditoria não entram nos agregados.",
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
            {key: value for key, value in score.items() if key not in {"rows", "aggregates"}}
        )
    )


if __name__ == "__main__":
    main()
