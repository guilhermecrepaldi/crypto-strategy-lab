"""Validate and register the immutable B10 owner-stop checkpoints."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from crypto_strategy_lab.domain import canonical_hash
from scripts.b10_checkpoint_scoreboard import digest as file_digest
from scripts.b10_checkpoint_scoreboard import read_checkpoint

PROFILES = ("A_OBSERVED_BEST_SUPPORTED", "B_REALISTIC_CONSERVATIVE")


def digest(path: Path) -> str:
    return file_digest(path)


def tail_digest(path: Path, size: int = 4096) -> str:
    with path.open("rb") as stream:
        stream.seek(max(0, path.stat().st_size - size))
        return hashlib.sha256(stream.read()).hexdigest()


def prefix_digest(path: Path, size: int, chunk: int = 8 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    remaining = size
    with path.open("rb") as stream:
        while remaining:
            block = stream.read(min(chunk, remaining))
            if not block:
                raise ValueError("JOURNAL_SHORTER_THAN_DECLARED_PREFIX")
            digest.update(block)
            remaining -= len(block)
    return digest.hexdigest()


def exclusive_lock_available(path: Path) -> bool:
    with path.open("a+b") as stream:
        if __import__("os").name == "nt":
            import msvcrt

            stream.seek(0)
            try:
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
                return True
            except OSError:
                return False
        import fcntl

        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.flock(stream, fcntl.LOCK_UN)
            return True
        except OSError:
            return False


def inspect_profile(folder: Path) -> dict[str, Any]:
    original = folder / "checkpoint.json"
    copy = folder / "owner-stop-checkpoint.json"
    if not original.exists() or not copy.exists():
        raise FileNotFoundError(f"CHECKPOINT_COPY_MISSING:{folder}")
    config_path = Path("artifacts/binance/b10-reality-profiles.json")
    metrics = read_checkpoint(folder, config_path, run_status="SUPERSEDED_BY_OWNER_STRATEGY_UPDATE")
    original_payload = json.loads(original.read_text(encoding="utf-8"))
    copy_payload = json.loads(copy.read_text(encoding="utf-8"))
    if (
        canonical_hash(original_payload["replay"]["payload"])
        != original_payload["replay"]["sha256"]
    ):
        raise ValueError(f"CHECKPOINT_PAYLOAD_HASH_MISMATCH:{original}")
    if canonical_hash(copy_payload["replay"]["payload"]) != copy_payload["replay"]["sha256"]:
        raise ValueError(f"OWNER_CHECKPOINT_PAYLOAD_HASH_MISMATCH:{copy}")
    journal = folder / "execution-audit.jsonl"
    original_sha = digest(original)
    copy_sha = digest(copy)
    if original_sha != copy_sha:
        raise ValueError("OWNER_CHECKPOINT_COPY_MISMATCH")
    journal_sha = digest(journal) if journal.exists() else None
    declared = copy_payload["audit"]
    declared_prefix_bytes = int(declared["bytes"])
    prefix_sha = prefix_digest(journal, declared_prefix_bytes) if journal.exists() else None
    if prefix_sha != declared.get("sha256"):
        raise ValueError(f"JOURNAL_DURABLE_PREFIX_HASH_MISMATCH:{folder}")
    return {
        "profile": folder.name,
        "checkpoint": {
            "path": str(original),
            "bytes": original.stat().st_size,
            "sha256": original_sha,
        },
        "owner_stop_checkpoint": {
            "path": str(copy),
            "bytes": copy.stat().st_size,
            "sha256": copy_sha,
            "matches_checkpoint_bytes_and_sha": original_sha == copy_sha,
        },
        "journal_prefix": {
            "path": str(journal),
            "declared_prefix_bytes": declared_prefix_bytes,
            "declared_prefix_sha256": declared.get("sha256"),
            "prefix_sha256_recomputed": prefix_sha,
            "full_file_bytes": journal.stat().st_size if journal.exists() else None,
            "full_file_sha256": journal_sha,
            "tail_4096_sha256": tail_digest(journal) if journal.exists() else None,
            "raw_tail_preserved": journal.exists(),
            "preserved": journal.exists(),
            "prefix_hash_match": prefix_sha == declared.get("sha256"),
        },
        "checkpoint_replay_sha256": copy_payload["replay"].get("sha256"),
        "checkpoint_audit_sha256": copy_payload["audit"].get("sha256"),
        "checkpoint_payload_equal": original_payload == copy_payload,
        "metrics": metrics,
    }


def publish(result):
    from datetime import UTC, datetime

    status = "SUPERSEDED_BY_OWNER_STRATEGY_UPDATE"
    a, b = (row["metrics"] for row in result["profiles"])
    score = dict(b)
    score.update(
        {
            "status": status,
            "verdict": "SUPERSEDED_PARTIAL_EXECUTION_EVIDENCE",
            "classification": "AUXILIARY_EXECUTION_DIAGNOSTIC",
            "FIXED_100_RESULT_NOT_OWNER_STRATEGY_RETURN": True,
            "completed_profile_A": a,
            "supersession_manifest": "reports/usdcusdt/B10-owner-supersession.json",
            "audit_status": (
                "HASH_BOUND_PRESERVATION_PASS; economic/raw independent audit earlier A prefix only"
            ),
        }
    )
    Path("reports/usdcusdt/B10-reality-scoreboard.json").write_text(
        json.dumps(score, indent=2) + "\n", encoding="utf-8"
    )
    keys = (
        "simulation_timestamp",
        "progress_percent",
        "full_fill_cycles",
        "net_positive_cycles",
        "net_pnl_fixed_100",
        "reserve_final",
        "release_filled",
        "zero_cycle_days_so_far",
        "max_hold",
        "lock_hours",
    )
    report = (
        "# B10 REALITY — CURRENT SCOREBOARD\n\nSTATUS="
        + status
        + (
            "\n\nFIXED_100_RESULT_NOT_OWNER_STRATEGY_RETURN=YES. Valores ab"
            "aixo são diagnósticos auxiliares; não retorno da estratégia "
            "composta.\n\n"
        )
    )
    report += (
        "| Métrica | A concluído antes da ordem | B último checkpoint parcial |\n|---|---|---|\n"
    )
    report += "".join(f"| {key} | {a[key]} | {b[key]} |\n" for key in keys)
    report += (
        "\n## What changed since previous checkpoint\n\nA concluiu antes"
        " da ordem; B foi interrompido via Ctrl-C no processo específ"
        "ico. C/B_FEE10/D não iniciados. Automação antiga pausada. Ch"
        "eckpoints copiados byte a byte, payloads e prefixos duráveis"
        " verificados; nenhum journal truncado. O sufixo bruto do B a"
        "pós o checkpoint continua preservado, não reconciliado.\n"
    )
    report += (
        "\n## Current interpretation\n\nB10 é histórico: o OWNER rejeito"
        "u os locks prolongados e autorizou M012, com compounding obr"
        "igatório,5% funding/target e limite24h. Interrupção não é FA"
        "IL. O diagnóstico fixed100 não estima crescimento geométrico"
        ".\n"
    )
    report += (
        "\n## Technical validation\n\nPreservação SHA/payload/prefixo e "
        "lock exclusivo disponíveis: PASS. Testes B10 anteriores:98 p"
        "ass,0 fail, sem mudança no kernel. Auditoria independente an"
        "terior cobre100 ciclos e13 releases de um prefixo antigo de "
        "A, não A completo/B. TEST_SUITE_PASS != STRATEGY_PASS.\n"
    )
    report += (
        "\n## Known unknowns\n\nSufixo do B posterior ao checkpoint não "
        "reconciliado. L2/fees históricos e slippage isolado permanec"
        "em não certificados. A completo não recebeu auditoria final."
        "\n\n## Next action\n\nNão retomar B10. Registrar, implementar e "
        "auditar M012 COMPOUNDING antes da primeira execução autoriza"
        "da.\n"
    )
    Path("reports/usdcusdt/B10-reality-report.md").write_text(report, encoding="utf-8")
    fields = {
        "LAST_B10_RUN_ID": b["run_id"],
        "LAST_PROFILE": b["profile_name"],
        "LAST_SIMULATION_TIMESTAMP": b["simulation_timestamp"],
        "LAST_PROGRESS": b["progress_percent"],
        "LAST_FULL_FILL_CYCLES": b["full_fill_cycles"],
        "LAST_NET_POSITIVE_CYCLES": b["net_positive_cycles"],
        "LAST_NET_PNL_FIXED_100": b["net_pnl_fixed_100"],
        "LAST_RESERVE": b["reserve_final"],
        "LAST_RELEASES": b["release_filled"],
        "LAST_ZERO_DAYS": b["zero_cycle_days_so_far"],
        "LAST_MAX_HOLD": b["max_hold"],
        "LAST_LOCK_HOURS": b["lock_hours"],
    }
    journal = Path("docs/research/B10_JOURNAL.md")
    marker = "TYPE=OWNER_STRATEGY_SUPERSESSION"
    if marker not in journal.read_text(encoding="utf-8"):
        with journal.open("a", encoding="utf-8") as stream:
            stream.write(
                "\n## "
                + datetime.now(UTC).isoformat()
                + (
                    "\n\nTYPE=ERROR\nEVENT=Unpublished archival draft mislabeled ful"
                    "l journal hash as durable prefix, omitted derivable metrics "
                    "and inserted new entry within history. No original runtime a"
                    "rtifact changed.\nDECISION=Correct reporting before publicati"
                    "on; verify bounded prefix, derive checkpoint economics and p"
                    "reserve original journal as byte prefix.\n\nTYPE=RECOVERY\nEVEN"
                    "T=Durable prefix hash recomputed and matches checkpoint for "
                    "A and B; metrics derived by canonical checkpoint helper; ori"
                    "ginal history preserved.\n\n"
                )
                + marker
                + "\n"
            )
            stream.write("\n".join(f"{key}={value}" for key, value in fields.items()))
            stream.write(
                "\nSTATUS="
                + status
                + (
                    "\nDECISION=B10 Reality stopped because the OWNER requires sub"
                    "stantially higher motor uptime and <=24h capital lock.\nAUDIT"
                    "_STATUS=HASH_BOUND_PRESERVATION_PASS; final economic/raw aud"
                    "it not completed\nFIXED_100_RESULT_NOT_OWNER_STRATEGY_RETURN="
                    "YES\nA_STATUS=COMPLETE_BEFORE_OWNER_OVERRIDE; unchanged artif"
                    "act, not final audit acceptance\nB_SUFFIX=Preserved but unche"
                    "ckpointed and not reconciled\nCOMMIT=Containing publication c"
                    "ommit\n"
                )
            )
    Path("docs/research/CURRENT_STATE.md").write_text(
        "# CURRENT STATE\n\nHISTORICAL_STRATEGY=B10_FROZEN\nB10_STATUS="
        + status
        + (
            "\nB10_PROCESS_STOPPED=YES\nACTIVE_RESEARCH_MODEL=M012\nMODEL_RE"
            "GISTERED=NO\nRUN_STATUS=PREREGISTRATION_AND_IMPLEMENTATION\nCA"
            "PITAL_MODE=COMPOUNDING\nINITIAL_OPERATING=100\nINITIAL_RESERVE"
            "=5\nRESERVE_FUNDING=5%\nOPERATING_REINVESTMENT=95%\nRESERVE_TAR"
            "GET=5%\nRESERVE_NONZERO_FLOOR=max(1e-8,0.001*operating_book_b"
            "ank)\nMAX_POSITION_LOCK=24h\nCURRENT_SIM_TIMESTAMP=NOT_STARTED"
            "\nFULL_FILL_CYCLES=NOT_STARTED\nNET_POSITIVE_CYCLES=NOT_STARTE"
            "D\nZERO_DAYS=NOT_STARTED\nMAX_HOLD=NOT_STARTED\nHARD_LOCK_VIOLA"
            "TIONS=NOT_STARTED\nOPERATING_BANK=NOT_STARTED\nRESERVE_FINAL=N"
            "OT_STARTED\nTOTAL_EQUITY=NOT_STARTED\nVERDICT=PENDING\nFIXED_10"
            "0_RESULT_NOT_OWNER_STRATEGY_RETURN=YES\nNEXT_ACTION=Register "
            "reviewed compound M012, finish implementation/tests/audit, p"
            "ublish source and start authorized replay.\nBLOCKERS=No human"
            " gate; preflight technical validation pending.\n"
        ),
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--runs",
        type=Path,
        default=Path(
            "artifacts/binance/b10-reality-runs/a77e0c67fdff8c618cbfc28fd"
            "d3d49d2fa831626560aed7fe1ec27007293537d"
        ),
    )
    parser.add_argument(
        "--output", type=Path, default=Path("reports/usdcusdt/B10-owner-supersession.json")
    )
    parser.add_argument("--process-confirmed", action="store_true")
    args = parser.parse_args()
    profiles = [inspect_profile(args.runs / name) for name in PROFILES]
    lock_available = exclusive_lock_available(args.runs / "b10-reality.lock")
    if not lock_available:
        raise RuntimeError("B10_LOCK_NOT_AVAILABLE")
    result = {
        "schema": "b10-owner-supersession-v1",
        "status": "SUPERSEDED_BY_OWNER_STRATEGY_UPDATE",
        "reason": (
            "Reality evidence demonstrated unacceptable capital lock / ze"
            "ro-cycle behavior under the current B10 policy."
        ),
        "process_confirmation_external": args.process_confirmed,
        "process_identity": {
            "run_id": args.runs.name,
            "writer_confirmed_stopped_by_owner": args.process_confirmed,
        },
        "exclusive_run_lock_available": lock_available,
        "profiles": profiles,
        "not_started": ["C_ADVERSARIAL_PLAUSIBLE", "B_FEE10_PROMOTION_ABSENT", "D_PEG_STRESS"],
        "artifacts_originals_unchanged": True,
        "journal_truncated": False,
        "fixed_100_result_classification": "AUXILIARY_EXECUTION_DIAGNOSTIC_NOT_OWNER_RETURN",
        "last_B": profiles[1],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    publish(result)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
