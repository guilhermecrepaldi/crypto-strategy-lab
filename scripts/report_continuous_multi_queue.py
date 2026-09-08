"""Report the bounded M013 multi-queue scoreboard from immutable run evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from scripts.report_high_uptime_recovery import curve_svg, read_curve_prefix

ROOT = Path("reports/usdcusdt")
CHECKPOINTS = ("DAY_1", "DAY_7", "DAY_30", "DAY_60", "DAY_90", "DAY_120", "FINAL_5_MONTH")
FIELDS = (
    "OPERATING_CAPITAL",
    "RECOVERY_RESERVE",
    "RESERVE_RATIO",
    "CORE_RESERVE",
    "ACTIVE_RESERVE_CAPITAL",
    "TOTAL_EQUITY",
    "TOTAL_PROFIT",
    "OPERATING_QUEUES_ACTIVE",
    "RESERVE_QUEUE_ACTIVE",
    "CYCLES",
    "NET_POSITIVE_CYCLES",
    "MOTOR_UPTIME",
    "CAPITAL_WEIGHTED_UPTIME",
    "FULL_STOP_HOURS",
    "ZERO_CYCLE_DAYS",
    "MAX_HOLD",
    "LOCK_HOURS_GT24",
    "HARD_LOCK_VIOLATIONS",
    "RELEASE_COUNT",
    "TOTAL_RELEASE_LOSS",
    "RESERVE_CONTRIBUTIONS",
    "ACTIVE_RESERVE_PROFIT",
    "RESERVE_CONSUMPTION",
    "RESERVE_SELF_SUSTAINABILITY_RATIO",
    "CAPACITY_PRESSURE_EVENTS",
    "VERDICT",
)
CURVE_KEYS = {
    "operating-capital": ("OPERATING_CAPITAL", "Operating capital"),
    "recovery-reserve": ("RECOVERY_RESERVE", "Recovery reserve"),
    "total-equity": ("TOTAL_EQUITY", "Total equity"),
    "q1": ("Q1_CAPITAL", "Queue Q1"),
    "q2": ("Q2_CAPITAL", "Queue Q2"),
    "q3": ("Q3_CAPITAL", "Queue Q3"),
    "q4": ("Q4_CAPITAL", "Queue Q4"),
}


def monthly_results(rows):
    """Month-end balances are observed snapshots; monthly cycles are differences, not sums."""
    closes = {row["MONTH_CLOSED"]: row for row in rows if row.get("MONTH_CLOSED")}
    result = []
    previous = {"ORDINARY_OPERATING_CYCLES": 0, "ACTIVE_RESERVE_CYCLES": 0, "RELEASE_COUNT": 0}
    previous_month = 0
    for month, row in sorted(closes.items()):
        current_month = int(month.split("-")[1])
        contiguous = current_month == previous_month + 1
        values = {}
        for cumulative, monthly in (
            ("ORDINARY_OPERATING_CYCLES", "OPERATING_CYCLES_MONTH"),
            ("ACTIVE_RESERVE_CYCLES", "RESERVE_CYCLES_MONTH"),
            ("RELEASE_COUNT", "RELEASES_MONTH"),
        ):
            value = row.get(cumulative)
            prior = previous.get(cumulative)
            values[monthly] = (
                value - prior if contiguous and value is not None and prior is not None else None
            )
            if values[monthly] is not None and values[monthly] < 0:
                raise ValueError("MONTHLY_CYCLE_COUNTER_WENT_BACKWARDS")
            previous[cumulative] = value
        operating, reserve = values["OPERATING_CYCLES_MONTH"], values["RESERVE_CYCLES_MONTH"]
        result.append(
            {
                "MONTH": month,
                "STATUS": "CLOSED",
                "OPERATING_CAPITAL": row.get("OPERATING_CAPITAL"),
                "RECOVERY_RESERVE": row.get("RECOVERY_RESERVE"),
                "TOTAL_EQUITY": row.get("TOTAL_EQUITY"),
                "CYCLES_MONTH": operating + reserve
                if operating is not None and reserve is not None
                else None,
                **values,
            }
        )
        previous_month = current_month
    return result


def value(record: dict[str, Any], key: str) -> Any:
    return record.get(key)


def display(value: Any) -> str:
    if value is None:
        return "UNAVAILABLE"
    if isinstance(value, bool):
        return str(value)
    try:
        number = Decimal(str(value))
    except InvalidOperation:
        return str(value)
    if not number.is_finite():
        return str(value)
    if number and (abs(number) >= Decimal("1e12") or abs(number) < Decimal("0.000001")):
        return format(number, ".6g")
    return format(number, ".6f").rstrip("0").rstrip(".") or "0"


def checkpoint_rows(
    folder: Path, scoreboard: dict[str, Any], curve_rows: list[dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for name in CHECKPOINTS:
        candidates = [row for row in curve_rows if row.get("CHECKPOINT_REASON") == name]
        rows[name] = candidates[-1] if candidates else {}
    return rows


def publish(
    folder: Path,
    output_root: Path = ROOT,
    current_state: Path = Path("docs/research/CURRENT_STATE.md"),
) -> dict[str, Any]:
    scoreboard_path = folder / "scoreboard.json"
    raw = scoreboard_path.read_bytes()
    scoreboard = json.loads(raw)
    if not isinstance(scoreboard, dict):
        raise ValueError("SCOREBOARD_OBJECT_REQUIRED")
    if scoreboard.get("MODEL_ID") != "M013":
        raise ValueError("MODEL_ID_MUST_BE_M013")
    if scoreboard.get("CAPITAL_MODE") != "COMPOUNDING":
        raise ValueError("CAPITAL_MODE_MUST_BE_COMPOUNDING")
    rows = read_curve_prefix(folder / "capital-curve.jsonl", scoreboard.get("CAPITAL_CURVE_PREFIX"))
    physical = (folder / "checkpoint.json").read_bytes()
    if hashlib.sha256(physical).hexdigest() != scoreboard.get("CHECKPOINT_SHA256"):
        raise ValueError(
            "SCOREBOARD_CHECKPOINT_BINDING_MISMATCH; retry after atomic writer settles"
        )
    checkpoint = json.loads(physical)
    if checkpoint.get("capital_curve") != scoreboard.get("CAPITAL_CURVE_PREFIX"):
        raise ValueError("CHECKPOINT_CURVE_BINDING_MISMATCH")
    if not rows or any(scoreboard.get(key) != val for key, val in rows[-1].items()):
        raise ValueError("SCOREBOARD_DIFFERS_FROM_HASH_BOUND_CURVE")
    if any(
        row.get("RUN_ID") != scoreboard.get("RUN_ID")
        or row.get("MODEL_HASH") != scoreboard.get("MODEL_HASH")
        for row in rows
    ):
        raise ValueError("CURVE_CONTAINS_OTHER_RUN_IDENTITY")
    checkpoints = checkpoint_rows(folder, scoreboard, rows)
    output: dict[str, Any] = dict(scoreboard)
    output["MONTHLY_RESULTS"] = monthly_results(rows)
    output.update(
        {
            "SCHEMA": "M013_CONTINUOUS_MULTI_QUEUE_REPORT_V1",
            "SOURCE_SCOREBOARD_SHA256": hashlib.sha256(raw).hexdigest(),
            "STAGE": scoreboard.get("STAGE", "STAGE_1"),
            "CHECKPOINTS": {
                name: {key: value(record, key) for key in FIELDS}
                for name, record in checkpoints.items()
            },
            "OWNER_PRINCIPAL": {
                "INITIAL_EQUITY": scoreboard.get("INITIAL_EQUITY", 110),
                **{
                    f"{name}_TOTAL_EQUITY": checkpoints[name].get("TOTAL_EQUITY")
                    for name in CHECKPOINTS
                    if name != "DAY_60" and name != "DAY_120"
                },
            },
            "STAGE_1_DECISION": scoreboard.get("STAGE_1_DECISION", "PENDING")
            if scoreboard.get("STAGE") == "STAGE_2"
            else "PENDING",
            "VERDICT": "PENDING_INDEPENDENT_AUDIT"
            if scoreboard.get("RUN_STATUS") == "COMPLETE"
            else "PENDING",
        }
    )
    if output["OWNER_PRINCIPAL"].get("INITIAL_EQUITY") is None:
        output["OWNER_PRINCIPAL"]["INITIAL_EQUITY"] = 110
    audit_path = folder / "stage1-independent-audit.json"
    current_audit_status = "PENDING"
    if scoreboard.get("STAGE") == "STAGE_1" and scoreboard.get("RUN_STATUS") == "COMPLETE":
        from scripts.run_continuous_multi_queue import stage1_decision

        audit = json.loads(audit_path.read_bytes()) if audit_path.exists() else {}
        output["STAGE_1_DECISION"] = stage1_decision(scoreboard, audit)
        output["VERDICT"] = output["STAGE_1_DECISION"]
        current_audit_status = audit.get("status", "PENDING")
    output_root.mkdir(parents=True, exist_ok=True)
    (output_root / "M013-scoreboard.json").write_text(
        json.dumps(output, indent=2) + "\n", encoding="utf-8"
    )
    for stem, (key, title) in CURVE_KEYS.items():
        (output_root / f"M013-{stem}.svg").write_text(curve_svg(rows, key, title), encoding="utf-8")
    table = (
        "| Checkpoint | Total equity | Operating capital | Reserve | Cycles | Verdict |\n"
        "|---|---:|---:|---:|---:|---|\n"
    )
    for name in CHECKPOINTS:
        row = output["CHECKPOINTS"][name]
        table += (
            f"| {name} | {row['TOTAL_EQUITY']} | {row['OPERATING_CAPITAL']} | "
            f"{row['RECOVERY_RESERVE']} | {row['CYCLES']} | {row['VERDICT']} |\n"
        )
    all_fields = (
        "| Métrica | " + " | ".join(CHECKPOINTS) + " |\n|---|" + "---|" * len(CHECKPOINTS) + "\n"
    )
    for key in FIELDS:
        all_fields += (
            f"| {key} | "
            + " | ".join(display(output["CHECKPOINTS"][name][key]) for name in CHECKPOINTS)
            + " |\n"
        )
    latest_table = "| Métrica atual | Valor |\n|---|---|\n" + "".join(
        f"| {key} | {display(output.get(key))} |\n" for key in FIELDS
    )
    monthly_table = (
        "| Mês fechado | Banca operacional USDT | Reserva USDT | Patrimônio USDT | "
        "Ciclos do mês | Releases |\n|---|---:|---:|---:|---:|---:|\n"
    )
    for row in output["MONTHLY_RESULTS"]:
        monthly_table += (
            "| "
            + " | ".join(
                display(row.get(key))
                for key in (
                    "MONTH",
                    "OPERATING_CAPITAL",
                    "RECOVERY_RESERVE",
                    "TOTAL_EQUITY",
                    "CYCLES_MONTH",
                    "RELEASES_MONTH",
                )
            )
            + " |\n"
        )
    if not output["MONTHLY_RESULTS"]:
        monthly_table += "| Nenhum mês concluído | — | — | — | — | — |\n"
    monthly_table += (
        "\nCiclos do mês = ciclos ordinários completos operacionais + Q4, sem somar releases. "
        "Saldos de fechamento, sem reset; mês ainda aberto não é projetado. "
        "Valores visuais arredondados; JSON preserva precisão integral.\n"
    )
    report = (
        f"# M013 CONTINUOUS MULTI-QUEUE — {output['STAGE']}\n\n"
        "## PROGRESSO\n\n"
        f"RUN_ID={display(output.get('RUN_ID'))}; "
        f"STAGE={display(output.get('STAGE'))}; "
        f"RUN_STATUS={display(output.get('RUN_STATUS'))}.\n\n"
        "## RESULTADO ECONÔMICO PARCIAL\n\n"
        + (
            "Composição contínua. Extensão autorizada pelo Stage 1, sem reset de capital.\n\n"
            if output["STAGE"] == "STAGE_2"
            else "Composição contínua. Cinco meses; extensão condicionada a PASS_TO_EXTENSION.\n\n"
        )
        + monthly_table
        + "\nPlacar atual:\n\n"
        + latest_table
        + "\nMarcos observados:\n\n"
        + all_fields
        + "\nCheckpoint summary:\n\n"
        + table
        + "\n## TESTES DO SOFTWARE\n\n"
        f"TESTS_PASSED=null; TESTS_FAILED=null; INDEPENDENT_AUDIT={current_audit_status}.\n\n"
        "## RESULTADO FINAL\n\n"
        f"{output['VERDICT']}. Nenhum PASS é derivado sem auditoria "
        "independente e gates do runner.\n\n"
        "Evidence-only curves:\n\n"
        + "\n".join(f"![{title}](M013-{stem}.svg)" for stem, (_, title) in CURVE_KEYS.items())
        + "\nMissing fields remain null/UNAVAILABLE.\n"
    )
    (output_root / "M013-report.md").write_text(report, encoding="utf-8")
    current_state.parent.mkdir(parents=True, exist_ok=True)
    state_lines = ["# CURRENT STATE", "", "ACTIVE_RESEARCH_MODEL=CONTINUOUS_MULTI_QUEUE_RECOVERY"]
    state_lines.extend(
        f"{key}={display(output.get(key))}"
        for key in (
            "MODEL_ID",
            "MODEL_HASH",
            "RUN_ID",
            "CAPITAL_MODE",
            "STAGE",
            "RUN_STATUS",
            "SIMULATION_TIMESTAMP",
            "PROGRESS_PERCENT",
            "CALENDAR_DAYS_PROCESSED",
            "CALENDAR_DAYS_TOTAL",
            "STAGE_1_DECISION",
            "VERDICT",
        )
    )
    state_lines.extend(f"{key}={display(output.get(key))}" for key in FIELDS)
    current_state.write_text("\n".join(state_lines) + "\n", encoding="utf-8")
    journal = current_state.parent / "M013_JOURNAL.md"
    marker = f"SOURCE_SCOREBOARD_SHA256={output['SOURCE_SCOREBOARD_SHA256']}"
    existing = journal.read_text(encoding="utf-8") if journal.exists() else ""
    if marker not in existing:
        with journal.open("a", encoding="utf-8") as stream:
            stream.write(
                "\n## M013 checkpoint\n\nTYPE=TWO_STAGE\n"
                + marker
                + "\n"
                + latest_table
                + "\n"
                + monthly_table
                + "\nVERDICT="
                + output["VERDICT"]
                + "\n"
            )
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(publish(args.run), indent=2))
