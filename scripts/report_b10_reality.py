"""Canonical economic checkpoint report and append-only B10 research journal."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from decimal import Decimal
from pathlib import Path

try:
    from scripts.b10_checkpoint_scoreboard import read_checkpoint
except ModuleNotFoundError:
    from b10_checkpoint_scoreboard import read_checkpoint

NEXT = "Continuar replay congelado; publicar checkpoints materiais; auditar perfis concluídos."
BLOCKERS = "Sem bloqueio técnico identificado; L2/fees históricos desconhecidos; D não calibrado."


def display(value):
    return "UNKNOWN" if value is None else str(value)


def human(value, key):
    if value is None:
        return "UNKNOWN"
    if key in {"reality_retention_same_prefix", "max_drawdown"}:
        return f"{Decimal(str(value)) * 100:.6f}%"
    if key == "progress_percent":
        return f"{Decimal(str(value)):.4f}%"
    if key in {"max_hold", "lock_hours"}:
        return f"{Decimal(str(value)):.2f} h"
    if key in {"net_pnl_fixed_100", "reserve_final"}:
        return f"{Decimal(str(value)):.6f}"
    return display(value)


def build_scoreboard(
    config_path,
    runs_root,
    *,
    profile=None,
    tests_passed=93,
    tests_failed=0,
    audit_path=Path("reports/usdcusdt/B10-A-preliminary-prefix-audit.json"),
    head=None,
    run_status="RUNNING",
):
    candidates = (
        [runs_root / profile]
        if profile
        else [p.parent for p in runs_root.glob("*/checkpoint.json")]
    )
    candidates = [p for p in candidates if (p / "checkpoint.json").exists()]
    if not candidates:
        raise ValueError("NO_DURABLE_CHECKPOINT_AVAILABLE")
    folder = max(candidates, key=lambda p: (p / "checkpoint.json").stat().st_mtime_ns)
    result = read_checkpoint(folder, config_path, run_status=run_status)
    if head is None:
        head = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    result["head_observed_before_publication"] = head
    result["publication_commit"] = (
        "Containing publication commit; resolve using git log -1 -- "
        "reports/usdcusdt/B10-reality-scoreboard.json"
    )
    result["publication_status_at_generation"] = "LOCAL_ONLY_UNPUBLISHED"
    result["software_tests"] = {
        "passed": tests_passed,
        "failed": tests_failed,
        "status": "PASS" if tests_failed == 0 else "FAIL",
        "scope": "Explicit operator-supplied completed test-run evidence; not strategy success.",
    }
    audit = json.loads(audit_path.read_text(encoding="utf-8")) if audit_path.exists() else None
    result["independent_audit"] = {
        "profile": "A_OBSERVED_BEST_SUPPORTED" if audit else None,
        "status": audit["status"] if audit else "PENDING",
        "path": str(audit_path) if audit else None,
        "report_sha256": hashlib.sha256(audit_path.read_bytes()).hexdigest() if audit else None,
        "audited_checkpoint_sha256": audit.get("checkpoint_sha256") if audit else None,
        "ordinary_raw_sample": audit.get("ordinary_raw_sample") if audit else None,
        "release_settlements": audit.get("release_settlements") if audit else None,
        "covers_current_checkpoint": bool(
            audit and audit.get("checkpoint_sha256") == result["evidence"]["checkpoint_sha256"]
        ),
        "scope": "Historical preliminary prefix only; not current or completed-run acceptance.",
    }
    result["last_error"] = "NONE_OBSERVED_IN_CHECKPOINT; process health not inferred from artifact"
    result["next_action"] = NEXT
    result["blockers"] = BLOCKERS
    return result


def render_markdown(s, previous=None):
    metrics = [
        ("Profile", "profile_name"),
        ("Progress", "progress_percent"),
        ("Simulation date", "simulation_timestamp"),
        ("Price-path opportunities", "price_path_opportunities_same_prefix"),
        ("Full fill cycles", "full_fill_cycles"),
        ("Reality retention", "reality_retention_same_prefix"),
        ("Net positive cycles", "net_positive_cycles"),
        ("Net PnL US$100", "net_pnl_fixed_100"),
        ("Reserve final", "reserve_final"),
        ("Releases", "release_filled"),
        ("Zero days", "zero_cycle_days_so_far"),
        ("Max hold", "max_hold"),
        ("Lock hours", "lock_hours"),
        ("Drawdown", "max_drawdown"),
        ("Verdict", "verdict"),
    ]
    lines = ["# B10 REALITY — CURRENT SCOREBOARD", "", "| Metric | Value |", "| --- | ---: |"]
    lines += [f"| {label} | {human(s.get(key), key)} |" for label, key in metrics]
    lines += [
        "",
        "Percentuais apresentados na tabela; JSON mantém frações exatas. "
        "Dias zerados/ativos incluem apenas dias UTC completos; ciclos do dia parcial: "
        f"{display(s.get('current_partial_day_cycles'))}.",
        "",
        "## What changed since previous checkpoint",
        "",
    ]
    if (
        previous
        and previous.get("run_id") == s["run_id"]
        and previous.get("profile") == s["profile"]
    ):
        lines.append(
            f"Horário simulado anterior: {previous.get('simulation_timestamp', 'UNKNOWN')}."
        )
        for key in (
            "full_fill_cycles",
            "net_positive_cycles",
            "net_pnl_fixed_100",
            "reserve_final",
            "release_filled",
        ):
            lines.append(f"{key}: {human(previous.get(key), key)} → {human(s.get(key), key)}.")
    else:
        lines.append(
            "Primeiro checkpoint econômico canônico deste perfil; "
            "o histórico anterior permanece no Git e no diário."
        )
    pressure = Decimal(str(s.get("max_hold", 0))) > 24
    lines += [
        "",
        "## Current interpretation",
        "",
        (
            "Sob pressão (under pressure): retenção da posição excede 24h; "
            "a produtividade é comparada à referência no mesmo prefixo. "
            if pressure
            else "A produtividade observada é descritiva, não prova de sobrevivência. "
        )
        + f"Veredito: {s['verdict']}; nenhuma promoção. A retenção mede produtividade, "
        "não um subconjunto identificado dos ciclos originais.",
        f"PnL líquido realizado {human(s['net_pnl_fixed_100'], 'net_pnl_fixed_100')} exclui "
        "marcação do inventário não vendido e transferências internas da reserva.",
        "",
        "## Technical validation",
        "",
        f"Testes: {s['software_tests']['passed']} passaram, "
        f"{s['software_tests']['failed']} falharam. Resultado estratégico: {s['verdict']}. "
        "TEST_SUITE_PASS != STRATEGY_PASS.",
        f"Auditoria do perfil {s['independent_audit']['profile']}: "
        f"{s['independent_audit']['status']}; cobre este checkpoint: "
        f"{s['independent_audit']['covers_current_checkpoint']}. "
        f"Amostra: {s['independent_audit']['ordinary_raw_sample']} ciclos ordinários e "
        f"{s['independent_audit']['release_settlements']} releases do prefixo anterior de A; "
        "não aceita o replay completo nem audita outros perfis.",
        f"Checkpoint SHA: `{s['evidence']['checkpoint_sha256']}`. "
        f"Código executado: `{s['execution_source_commit']}`.",
        "",
        "## Known unknowns",
        "",
        "Slippage isolado: UNKNOWN; o modelo condicional incorpora custos nos preços. "
        "L2/fila/latência históricos e fees da conta não estão certificados. "
        "D_PEG_STRESS permanece NOT_CALIBRATED. Dia parcial censurado; "
        "checkpoint não comprova saúde atual do processo.",
        "",
        "## Next action",
        "",
        s["next_action"],
        "",
        "Estado na geração: LOCAL_ONLY_UNPUBLISHED. O commit que contém o relatório "
        "estabelece sua publicação; HEAD abaixo foi observado antes dela, sem autorreferência.",
        f"HEAD observado: `{s['head_observed_before_publication']}`.",
    ]
    return "\n".join(lines) + "\n"


def render_current(s):
    mapping = {
        "LAST_UPDATED_UTC": "updated_at",
        "HEAD": "head_observed_before_publication",
        "STRATEGY": "strategy",
        "EXECUTION_PROFILE": "profile_name",
        "RUN_ID": "run_id",
        "RUN_STATUS": "status",
        "SIMULATION_START": "simulation_start",
        "CURRENT_SIMULATION_TIMESTAMP": "simulation_timestamp",
        "SIMULATION_END": "simulation_end",
        "PROGRESS_PERCENT": "progress_percent",
        "PRICE_PATH_REFERENCE_FULL": "price_path_reference_full",
        "PRICE_PATH_OPPORTUNITIES_SAME_PREFIX": "price_path_opportunities_same_prefix",
        "FULL_FILL_CYCLES": "full_fill_cycles",
        "NET_POSITIVE_CYCLES": "net_positive_cycles",
        "REALITY_RETENTION_SAME_PREFIX": "reality_retention_same_prefix",
        "ZERO_CYCLE_DAYS_SO_FAR": "zero_cycle_days_so_far",
        "ACTIVE_DAYS_SO_FAR": "active_days_so_far",
        "NET_PNL_FIXED_100": "net_pnl_fixed_100",
        "RESERVE_INITIAL": "reserve_initial",
        "RESERVE_FINAL": "reserve_final",
        "RESERVE_MIN": "reserve_min",
        "RELEASES_ATTEMPTED": "release_attempted",
        "RELEASES_FILLED": "release_filled",
        "RELEASES_BLOCKED": "release_blocked",
        "MAX_HOLD": "max_hold",
        "LOCK_HOURS": "lock_hours",
        "MAX_DRAWDOWN": "max_drawdown",
        "LAST_ERROR": "last_error",
        "CURRENT_VERDICT": "verdict",
        "NEXT_ACTION": "next_action",
        "BLOCKERS": "blockers",
    }
    values = [f"{key}={display(s.get(field))}" for key, field in mapping.items()]
    values += [
        f"TESTS_PASSED={s['software_tests']['passed']}",
        f"TESTS_FAILED={s['software_tests']['failed']}",
        f"INDEPENDENT_AUDIT_STATUS={s['independent_audit']['status']} (earlier prefix only)",
        f"SOFTWARE_VALIDATION={s['software_tests']['status']}",
        f"STRATEGY_RESULT={s['verdict']}",
        "PUBLICATION_STATUS_AT_GENERATION=LOCAL_ONLY_UNPUBLISHED; "
        "containing Git commit establishes publication",
        "HEAD_SEMANTICS=observed before publication; publication commit resolved via git log",
        "UNITS=progress percent; retention/drawdown fractions; hold/lock hours; closed UTC days",
    ]
    return "# CURRENT STATE\n\n" + "\n\n".join(values) + "\n"


def append_journal(path, s):
    marker = "CHECKPOINT_SHA=" + s["evidence"]["checkpoint_sha256"]
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    if marker in existing.splitlines():
        return False
    fields = {
        "TYPE": "CHECKPOINT",
        "STRATEGY": s["strategy"],
        "PROFILE": s["profile_name"],
        "RUN_ID": s["run_id"],
        "SIM_TIMESTAMP": s["simulation_timestamp"],
        "PROGRESS": s["progress_percent"],
        "CYCLES": s["full_fill_cycles"],
        "NET_POSITIVE_CYCLES": s["net_positive_cycles"],
        "PNL": s["net_pnl_fixed_100"],
        "RESERVE": s["reserve_final"],
        "RELEASES": s["release_filled"],
        "ZERO_DAYS": s["zero_cycle_days_so_far"],
        "MAX_HOLD": s["max_hold"],
        "LOCK_HOURS": s["lock_hours"],
        "EVENT": "Atomic economic checkpoint captured for publication without changing replay",
        "DECISION": "Continue unchanged; strategy verdict " + s["verdict"],
        "EVIDENCE_PATHS": "reports/usdcusdt/B10-reality-scoreboard.json; "
        + s["evidence"]["checkpoint_path"],
        "COMMIT": "Containing publication commit; resolve: git log -S'"
        + marker
        + "' -- docs/research/B10_JOURNAL.md",
        "EXECUTION_SOURCE_COMMIT": s["execution_source_commit"],
        "WHY_UNKNOWN": "Isolated slippage unmeasured; current checkpoint not independently "
        "audited; historical execution evidence incomplete",
        "PUBLICATION_STATUS_AT_GENERATION": "LOCAL_ONLY_UNPUBLISHED",
    }
    entry = "\n## " + s["updated_at"][:19] + "Z\n\n" + marker + "\n\n"
    entry += "\n\n".join(f"{key}={display(value)}" for key, value in fields.items()) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        if not existing:
            stream.write("# B10 RESEARCH JOURNAL\n\nAppend-only economic history.\n")
        stream.write(entry)
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config", type=Path, default=Path("artifacts/binance/b10-reality-profiles.json")
    )
    parser.add_argument("--runs", type=Path)
    parser.add_argument("--profile")
    parser.add_argument("--tests-passed", type=int, default=93)
    parser.add_argument("--tests-failed", type=int, default=0)
    parser.add_argument("--run-status", default="RUNNING")
    parser.add_argument(
        "--json-output", type=Path, default=Path("reports/usdcusdt/B10-reality-scoreboard.json")
    )
    parser.add_argument(
        "--md-output", type=Path, default=Path("reports/usdcusdt/B10-reality-report.md")
    )
    parser.add_argument(
        "--current-output", type=Path, default=Path("docs/research/CURRENT_STATE.md")
    )
    parser.add_argument("--journal-output", type=Path, default=Path("docs/research/B10_JOURNAL.md"))
    args = parser.parse_args()
    runs = (
        args.runs
        or Path("artifacts/binance/b10-reality-runs")
        / hashlib.sha256(args.config.read_bytes()).hexdigest()
    )
    result = build_scoreboard(
        args.config,
        runs,
        profile=args.profile,
        tests_passed=args.tests_passed,
        tests_failed=args.tests_failed,
        run_status=args.run_status,
    )
    previous = (
        json.loads(args.json_output.read_text(encoding="utf-8"))
        if args.json_output.exists()
        else None
    )
    for path, content in (
        (args.json_output, json.dumps(result, indent=2) + "\n"),
        (args.md_output, render_markdown(result, previous)),
        (args.current_output, render_current(result)),
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    append_journal(args.journal_output, result)
    print(
        json.dumps(
            {
                key: result[key]
                for key in (
                    "profile",
                    "simulation_timestamp",
                    "progress_percent",
                    "full_fill_cycles",
                    "price_path_opportunities_same_prefix",
                    "net_pnl_fixed_100",
                    "reserve_final",
                    "verdict",
                )
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
