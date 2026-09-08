"""Read-only economic autopsy; writes derived reports, never changes execution."""
# HTML prose and typographic punctuation are intentionally preserved verbatim.
# ruff: noqa: E501, RUF001

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from collections import Counter
from decimal import Decimal as D
from decimal import localcontext
from html import escape
from pathlib import Path
from typing import Any

from crypto_strategy_lab.domain import canonical_hash
from crypto_strategy_lab.microstructure.b10_reality import _decode
from crypto_strategy_lab.microstructure.recovery_reserve_study import file_sha, write_json
from crypto_strategy_lab.microstructure.reserve_recovery_diagnostics import analyze_recovery

ROOT = Path("artifacts/usdcusdt/l2-monthly-samples/SYNTHETIC_CONSECUTIVE_12D")
M015_ROOT = ROOT / "PRICE_PRIORITY"
M016_ROOT = ROOT.parent / "M016" / "SYNTHETIC_CONSECUTIVE_12D" / "PRICE_PRIORITY"
M017_ROOT = ROOT.parent / "M017" / "SYNTHETIC_CONSECUTIVE_12D" / "PRICE_PRIORITY"
M017_SPEC = Path("docs/microstructure/M017_MODEL_SPEC.json")
MODEL_REGISTRY = Path("artifacts/usdcusdt/models/registry.jsonl")
OWNER_WINDOW_DOC = Path("docs/microstructure/OWNER_GATED_REPLAY_WINDOW.md")
MODEL_IDS = ("M015", "M016", "M017")
MODEL_COLORS = {"M015": "#175cd3", "M016": "#c2410c", "M017": "#15803d"}
OUTPUT = Path("reports/usdcusdt/reserve-rotation-analysis.json")
HTML = Path("reports/usdcusdt/B10-execution-research.html")
FUNDING = ("0.10", "0.25", "0.50", "0.70", "0.80", "1.00")
UNAVAILABLE = "UNAVAILABLE"
NOT_IMPLEMENTED = "NOT_IMPLEMENTED"
DAY_US = 86_400_000_000


def _approved_comparison_days() -> int:
    """Read the current OWNER gate; fail closed to one day if the gate is absent."""
    try:
        for line in OWNER_WINDOW_DOC.read_text(encoding="utf-8").splitlines():
            if line.startswith("APPROVED_COMPARISON_DAYS="):
                value = int(line.partition("=")[2])
                if value >= 1:
                    return value
    except (OSError, TypeError, ValueError):
        pass
    return 1


CURRENT_APPROVED_DAYS = _approved_comparison_days()


def _sha256_lf(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def _validated_m017_configuration(run_root: Path | None = None) -> dict[str, Any]:
    """Expose M017 policy metadata only when the registry binds its spec hash."""
    try:
        spec = json.loads(M017_SPEC.read_bytes())
        spec_hash = _sha256_lf(M017_SPEC)
        registry_entry = None
        for line in MODEL_REGISTRY.read_text(encoding="utf-8").splitlines():
            payload = json.loads(line).get("payload", {})
            if payload.get("model_id") == "M017" and isinstance(payload.get("model"), dict):
                registry_entry = payload
        registry_model = (registry_entry or {}).get("model", {})
        if (
            spec.get("model_id") != "M017"
            or registry_model.get("model_id") != "M017"
            or registry_model.get("spec_sha256_lf") != spec_hash
        ):
            return {"status": "UNKNOWN_SPEC_REGISTRY_BINDING"}
        metadata = {
            "status": "VALIDATED_SPEC_REGISTRY",
            "policy": spec.get("strategy", UNAVAILABLE),
            "initial_capital": spec.get("initial_capital", UNAVAILABLE),
            "initial_operating": spec.get("initial_operating", UNAVAILABLE),
            "initial_reserve": spec.get("initial_reserve", UNAVAILABLE),
            "reserve_floor": spec.get("reserve_floor_absolute", UNAVAILABLE),
            "profit_funding": spec.get("profit_funding", UNAVAILABLE),
            "executable_loss_cap_bps": spec.get("executable_loss_cap_bps", UNAVAILABLE),
            "spec_sha256_lf": spec_hash,
            "registry_model_hash": registry_entry.get("model_hash", UNAVAILABLE) if registry_entry else UNAVAILABLE,
        }
        if run_root is None or not run_root.exists():
            metadata["run_binding"] = "NOT_PRESENT"
        else:
            manifest_path = run_root / "run-manifest.json"
            try:
                manifest = json.loads(manifest_path.read_bytes())
                metadata["run_binding"] = (
                    "VALIDATED_RUN_MANIFEST"
                    if manifest.get("model_id") == "M017"
                    and manifest.get("model_hash") == metadata["registry_model_hash"]
                    else "UNKNOWN_RUN_MANIFEST_BINDING"
                )
            except (OSError, TypeError, ValueError, KeyError, json.JSONDecodeError):
                metadata["run_binding"] = "UNKNOWN_RUN_MANIFEST_BINDING"
        return metadata
    except (OSError, TypeError, ValueError, KeyError, json.JSONDecodeError):
        return {"status": "UNKNOWN_SPEC_REGISTRY_BINDING"}


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
            '-e',
            '"kind":"DEADLINE_EXIT_SIGNAL"',
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
            r
            for r in evidence
            if r["kind"] in {"RELEASE_SIGNAL", "DEADLINE_EXIT_SIGNAL"}
            and entry <= r["time_us"] <= stamp
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
                "hourly_veto_reasons": "NOT_REPORTED_BY_THIS_REPORTER",
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
    gains = [D(r["net_profit"]) for r in settlements if D(r["net_profit"]) > 0]
    ordinary_gains = [
        D(r["net_profit"])
        for r in settlements
        if not r["release"] and D(r["net_profit"]) > 0
    ]
    return {
        "summary": summary,
        "settlements": settlements,
        "positions": positions,
        "open_hold": open_hold,
        "two_hour_violations": sum(r["exceeds_two_hours"] for r in positions)
        + int(bool(open_hold and open_hold["exceeds_two_hours"])),
        "positive_profit_distribution": dict(Counter(str(g) for g in gains)),
        "positive_profit_total": str(sum(gains)),
        "ordinary_positive_profit_total": str(sum(ordinary_gains)),
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


def _daily_rows(root: Path, max_day: int = 12) -> list[dict[str, Any]]:
    """Read the twelve daily checkpoints without filling missing values."""
    rows: list[dict[str, Any]] = []
    for day in range(1, max_day + 1):
        path = root / "daily" / f"{day:02}.json"
        if not path.exists():
            rows.append({"logical_day": day, "status": UNAVAILABLE})
            continue
        try:
            value = json.loads(path.read_bytes())
        except (OSError, json.JSONDecodeError):
            rows.append({"logical_day": day, "status": "INVALID"})
            continue
        if not isinstance(value, dict):
            rows.append({"logical_day": day, "status": "INVALID"})
            continue
        rows.append({"logical_day": day, **value})
    return rows


def _daily_series(rows: list[dict[str, Any]], key: str) -> list[str | None]:
    values: list[str | None] = []
    for row in rows:
        value = row.get(key)
        if value is None or row.get("status") in {UNAVAILABLE, "INVALID"}:
            values.append(None)
        else:
            values.append(str(value))
    return values


def _last_closed_day(rows: list[dict[str, Any]]) -> int:
    return max(
        (int(row["logical_day"]) for row in rows if row.get("status") not in {UNAVAILABLE, "INVALID"}),
        default=0,
    )


def _load_checkpoint_state(root: Path, day: int) -> dict[str, Any] | None:
    if day <= 0:
        return None
    path = root / "daily" / f"{day:02}-engine-state.json"
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_bytes())
        state = payload.get("state", payload)
        if "sha256" in payload and canonical_hash(state) != payload["sha256"]:
            return None
        return _decode(state) if isinstance(state, dict) else None
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None


def _checkpoint_cutoff(root: Path, day: int) -> int | None:
    if day <= 0:
        return None
    path = root / "run-manifest.json"
    try:
        manifest = json.loads(path.read_bytes())
        mapping = manifest["source_day_mapping"]
        logical_start = int(mapping[day - 1]["logical_start_us"])
        return logical_start + DAY_US
    except (OSError, KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError):
        return None


def _prefix_summary(
    summary: dict[str, Any],
    daily: list[dict[str, Any]],
    state: dict[str, Any] | None,
    day: int,
    cutoff_us: int | None = None,
) -> dict[str, Any]:
    """Prefer the last closed daily checkpoint, with state-derived totals."""
    rows = [row for row in daily if int(row["logical_day"]) <= day and row.get("status") not in {UNAVAILABLE, "INVALID"}]
    latest = rows[-1] if rows else {}
    result = dict(summary)
    prefix_only_keys = (
        "NET_PNL", "NET_POSITIVE_CYCLES", "FULL_FILL_CYCLES", "RELEASES", "TOTAL_EQUITY_FINAL",
        "RESERVE_FINAL", "MIN_RESERVE", "RESERVE_FUNDING", "RESERVE_CONSUMPTION", "OPERATING_FINAL",
        "OPERATING_BANK", "OPERATING_CASH", "MOTOR_UPTIME", "HOLDING_HOURS", "FLAT_HOURS",
        "FULL_STOP_HOURS", "MAX_DRAWDOWN_PCT", "HARD_LOCK_VIOLATIONS", "ZERO_CYCLE_DAYS", "TRADES",
        "L2_ROWS", "AUDIT_STATUS", "REALIZED_FEES_QUOTE", "UNREALIZED_PNL", "VERDICT",
    )
    if day < 12:
        for key in prefix_only_keys:
            result.pop(key, None)
    aliases = {
        "CUMULATIVE_NET_PNL": "NET_PNL",
        "CUMULATIVE_NET_POSITIVE_CYCLES": "NET_POSITIVE_CYCLES",
        "OPERATING_FINAL": "OPERATING_FINAL",
        "RESERVE_FINAL": "RESERVE_FINAL",
        "TOTAL_EQUITY_FINAL": "TOTAL_EQUITY_FINAL",
    }
    for source, target in aliases.items():
        if source in latest:
            result[target] = latest[source]
    if rows:
        result["FULL_FILL_CYCLES"] = sum(
            int(row.get("FULLY_FILLED_CYCLES", row.get("FULL_FILL_CYCLES", 0))) for row in rows
        )
        result["ZERO_CYCLE_DAYS"] = sum(
            int(row.get("DAILY_NET_POSITIVE_CYCLES", row.get("NET_POSITIVE_CYCLES", 0))) == 0
            for row in rows
        )
        result["VERDICT"] = latest.get("VERDICT", "PENDING")
    if state is not None:
        settlements = state.get("settlements", [])
        if isinstance(settlements, list):
            result["RELEASES"] = sum(bool(row.get("release")) for row in settlements if isinstance(row, dict))
            if all("reserve_consumption" in row for row in settlements if isinstance(row, dict)):
                result["RESERVE_CONSUMPTION"] = str(
                    sum((D(str(row["reserve_consumption"])) for row in settlements), D(0))
                )
            result["RESERVE_FUNDING"] = str(
                state.get("reserve_funding", latest.get("RESERVE_FUNDING", UNAVAILABLE))
            )
            settlement_fee_rows = [row for row in settlements if isinstance(row, dict)]
            if all("realized_fees_quote" in row for row in settlement_fee_rows):
                settlement_fees = sum(
                    (D(str(row["realized_fees_quote"])) for row in settlement_fee_rows), D(0)
                )
                if "realized_cycle_fees" in state:
                    result["REALIZED_FEES_QUOTE"] = str(
                        settlement_fees + D(str(state["realized_cycle_fees"]))
                    )
                else:
                    result["REALIZED_FEES_QUOTE"] = str(settlement_fees)
            result["SIMULATION_TIMESTAMP_US"] = result.get("CUTOFF_US", latest.get("CAPTURE_TIME_US", 0))
            result["NET_POSITIVE_CYCLES"] = sum(
                not bool(row.get("release")) and D(str(row.get("net_profit", "0"))) > 0
                for row in settlements
                if isinstance(row, dict)
            )
        result["MIN_RESERVE"] = str(state.get("reserve_min", latest.get("MIN_RESERVE", UNAVAILABLE)))
        result["RESERVE_FLOOR"] = str(state.get("reserve_floor", latest.get("RESERVE_FLOOR", UNAVAILABLE)))
        result["RESERVE_FINAL"] = str(state.get("reserve", latest.get("RESERVE_FINAL", UNAVAILABLE)))
        result["OPERATING_CASH"] = str(state.get("cash", latest.get("OPERATING_CASH", UNAVAILABLE)))
        if all(key in state for key in ("cash", "cost", "dust_cost")):
            result["OPERATING_BANK"] = str(
                D(str(state["cash"]))
                + D(str(state["cost"]))
                + D(str(state["dust_cost"]))
            )
        else:
            result["OPERATING_BANK"] = UNAVAILABLE
    result["LOGICAL_DAYS"] = day
    if cutoff_us is not None:
        result["CUTOFF_US"] = cutoff_us
        result["SIMULATION_TIMESTAMP_US"] = cutoff_us
    result["PERIOD_LABEL"] = f"dias 1–{day}"
    return result


def _prefix_positions(
    root: Path,
    settlements: list[dict[str, Any]],
    cutoff_us: int | None,
) -> list[dict[str, Any]]:
    """Project fills/signals without parsing ledger events beyond the prefix cutoff."""
    ledger = root / "execution-audit.jsonl"
    if not settlements:
        return []
    if cutoff_us is None or not ledger.exists():
        raise ValueError("PREFIX_POSITION_EVIDENCE_UNAVAILABLE")
    evidence: list[dict[str, Any]] = []
    try:
        with ledger.open("r", encoding="utf-8") as stream:
            for line in stream:
                row = json.loads(line)
                if not isinstance(row, dict):
                    raise ValueError("PREFIX_POSITION_EVIDENCE_UNAVAILABLE")
                event_time = row.get("time_us", row.get("local_us"))
                if row.get("kind") == "SYNTHETIC_SAMPLE_SEAM":
                    if event_time is None or int(event_time) >= cutoff_us:
                        break
                elif event_time is not None and int(event_time) >= cutoff_us:
                    break
                if row.get("kind") in {"FILL", "RELEASE_SIGNAL", "DEADLINE_EXIT_SIGNAL"}:
                    evidence.append(row)
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError("PREFIX_POSITION_EVIDENCE_UNAVAILABLE") from exc
    fills = [row for row in evidence if row.get("kind") == "FILL"]
    positions: list[dict[str, Any]] = []
    previous = 0
    for index, settlement in enumerate(settlements, 1):
        stamp = int(settlement["time_us"])
        part = [row for row in fills if previous < int(row["time_us"]) <= stamp]
        buys = [row for row in part if row.get("side") == "BUY"]
        if not buys:
            raise ValueError("SETTLEMENT_WITHOUT_FIRST_BUY")
        entry = min(int(row["time_us"]) for row in buys)
        signals = [
            row
            for row in evidence
            if row.get("kind") in {"RELEASE_SIGNAL", "DEADLINE_EXIT_SIGNAL"}
            and entry <= int(row["time_us"]) <= stamp
        ]
        positions.append(
            {
                "index": index,
                "entry_us": entry,
                "exit_us": stamp,
                "hold_hours": str(D(stamp - entry) / D(3_600_000_000)),
                "release": bool(settlement.get("release")),
                "release_signal": signals[-1] if signals else None,
            }
        )
        previous = stamp
    return positions


def _include_open_hold(
    positions: list[dict[str, Any]],
    state: dict[str, Any] | None,
    settlements: list[dict[str, Any]],
    cutoff_us: int | None,
) -> list[dict[str, Any]]:
    if not state or state.get("entry_us") is None or cutoff_us is None:
        return positions
    end_us = int(cutoff_us)
    entry_us = int(state["entry_us"])
    if entry_us > end_us:
        return positions
    positions.append(
        {
            "index": len(positions) + 1,
            "entry_us": entry_us,
            "exit_us": end_us,
            "hold_hours": str(D(end_us - entry_us) / D(3_600_000_000)),
            "release": False,
            "open_censored": True,
            "release_signal": None,
        }
    )
    return positions


def _checkpoint_positions(
    root: Path,
    state: dict[str, Any] | None,
    settlements: list[dict[str, Any]],
    cutoff_us: int | None,
) -> tuple[list[dict[str, Any]], bool]:
    if state is None:
        return [], False
    try:
        positions = _prefix_positions(root, settlements, cutoff_us)
    except ValueError:
        return [], False
    return _include_open_hold(positions, state, settlements, cutoff_us), True


def _checkpoint_run(root: Path, label: str, max_day: int = 12) -> dict[str, Any]:
    """Return a complete run or an explicitly labelled partial checkpoint.

    Complete runs retain the existing closed-ledger validation.  A pending run
    uses the latest closed daily engine checkpoint for prefix accounting; only
    policy/deadline state remains deferred.
    """
    not_started = label.startswith("M017")
    scope_paused = not_started and max_day < 12
    daily = _daily_rows(root, max_day=max_day)
    summary_path = root / "summary.json"
    if not root.exists():
        return {
            "label": label,
            "model_id": label,
            "status": "NOT_STARTED" if not_started else UNAVAILABLE,
            "checkpoint": True,
            "summary": {},
            "daily": daily,
            "daily_positive_cycles": _daily_series(daily, "DAILY_NET_POSITIVE_CYCLES"),
            "daily_equity": _daily_series(daily, "TOTAL_EQUITY_FINAL"),
            "daily_reserve": _daily_series(daily, "RESERVE_FINAL"),
            "debt_states": "DEFERRED_UNAVAILABLE",
            "recovery_sensitivity": {},
            "error": "ARTIFACT_NOT_STARTED" if not_started else "ARTIFACT_ROOT_UNAVAILABLE",
        }
    day = _last_closed_day(daily)
    if not_started and day == 0 and not summary_path.exists():
        return {
            "label": label,
            "model_id": label,
            "status": "NOT_STARTED",
            "checkpoint": True,
            "summary": {},
            "daily": daily,
            "daily_positive_cycles": _daily_series(daily, "DAILY_NET_POSITIVE_CYCLES"),
            "daily_equity": _daily_series(daily, "TOTAL_EQUITY_FINAL"),
            "daily_reserve": _daily_series(daily, "RESERVE_FINAL"),
            "debt_states": "NOT_STARTED",
            "recovery_sensitivity": {},
            "error": "ARTIFACT_NOT_STARTED",
        }
    state = _load_checkpoint_state(root, day)
    cutoff_us = _checkpoint_cutoff(root, day)
    if scope_paused:
        # The global summary may include post-gate days; the bounded prefix is authoritative.
        summary = {}
    else:
        try:
            summary = json.loads(summary_path.read_bytes()) if summary_path.exists() else {}
        except (OSError, json.JSONDecodeError):
            return {
                "label": label,
                "model_id": label,
                "status": "INVALID",
                "checkpoint": True,
                "summary": {},
                "daily": daily,
                "daily_positive_cycles": _daily_series(daily, "DAILY_NET_POSITIVE_CYCLES"),
                "daily_equity": _daily_series(daily, "TOTAL_EQUITY_FINAL"),
                "daily_reserve": _daily_series(daily, "RESERVE_FINAL"),
                "debt_states": "DEFERRED_UNAVAILABLE",
                "recovery_sensitivity": {},
                "error": "SUMMARY_INVALID",
            }
    if not isinstance(summary, dict):
        summary = {}
    if not scope_paused and not summary_path.exists():
        summary = _prefix_summary(summary, daily, state, day, cutoff_us)
    model_id = str(summary.get("MODEL_ID", summary.get("model_id", label)))
    status = str(summary.get("RUN_STATUS", "PENDING"))
    if scope_paused:
        status = "M017_OWNER_PAUSED_AFTER_SCOPE"
    base: dict[str, Any] = {
        "label": label,
        "model_id": model_id,
        "status": status,
        "checkpoint": status != "COMPLETE",
        "summary": summary,
        "daily": daily,
        "daily_positive_cycles": _daily_series(daily, "DAILY_NET_POSITIVE_CYCLES"),
        "daily_equity": _daily_series(daily, "TOTAL_EQUITY_FINAL"),
        "daily_reserve": _daily_series(daily, "RESERVE_FINAL"),
        "debt_states": "DEFERRED_UNAVAILABLE",
        "recovery_sensitivity": {},
    }
    if status != "COMPLETE":
        summary = _prefix_summary(summary, daily, state, day, cutoff_us)
        base["summary"] = summary
        base["period_label"] = summary.get("PERIOD_LABEL", f"days 1–{day}")
        base["closed_day"] = day
        if state is not None:
            settlements = state.get("settlements", [])
            base["settlements"] = settlements
            base["positions"], base["positions_evidence_available"] = _checkpoint_positions(
                root, state, settlements, cutoff_us
            )
            if not settlements:
                base["debt_states"] = "AVAILABLE_PREFIX_ACCOUNTING_NO_SETTLEMENTS_POLICY_DEFERRED"
            elif cutoff_us is None:
                base["debt_states"] = "POLICY_DEFERRED_MISSING_CUTOFF"
                base["status"] = "M017_OWNER_PAUSED_AFTER_SCOPE" if scope_paused else "CHECKPOINT_PARTIAL"
                base["checkpoint"] = True
                base["error"] = "RUN_MANIFEST_CUTOFF_UNAVAILABLE"
                return base
            else:
                end_us = int(cutoff_us)
                base["recovery_sensitivity"] = {
                    f: analyze_recovery(settlements, D(f), end_us) for f in FUNDING
                }
                base["debt_states"] = "AVAILABLE_PREFIX_ACCOUNTING_POLICY_DEFERRED"
        else:
            base["debt_states"] = "POLICY_DEFERRED_NO_CHECKPOINT_STATE"
        base["status"] = "M017_OWNER_PAUSED_AFTER_SCOPE" if scope_paused else "CHECKPOINT_PARTIAL"
        base["checkpoint"] = True
        base["error"] = "OWNER_SCOPE_LIMIT" if scope_paused else "RUN_NOT_COMPLETE"
        return base
    try:
        complete = inspect_run(root)
    except (OSError, KeyError, ValueError, json.JSONDecodeError) as exc:
        base["status"] = "NO_COMPLETE_BOUND_STATE" if status == "COMPLETE" else "INVALID"
        base["checkpoint"] = True
        base["debt_states"] = base["status"]
        base["error"] = str(exc)
        return base
    base.update(complete)
    base["label"] = label
    base["model_id"] = model_id
    base["status"] = "COMPLETE"
    base["checkpoint"] = False
    base["debt_states"] = "AVAILABLE_COMPLETE_CLOSED_AUDIT"
    base["period_label"] = "complete 12-day period"
    base["closed_day"] = 12
    base["daily"] = daily
    base["daily_positive_cycles"] = _daily_series(daily, "DAILY_NET_POSITIVE_CYCLES")
    base["daily_equity"] = _daily_series(daily, "TOTAL_EQUITY_FINAL")
    base["daily_reserve"] = _daily_series(daily, "RESERVE_FINAL")
    return base


def _prefix_view(run: dict[str, Any], root: Path, day: int) -> dict[str, Any]:
    if day <= 0 or run.get("status") in {UNAVAILABLE, "NOT_STARTED", "NO_COMPLETE_BOUND_STATE"}:
        return run
    if day >= 12 and run.get("status") == "COMPLETE":
        return run
    state = _load_checkpoint_state(root, day)
    view = dict(run)
    view["daily"] = [row for row in run.get("daily", []) if int(row["logical_day"]) <= day]
    view["daily_positive_cycles"] = _daily_series(view["daily"], "DAILY_NET_POSITIVE_CYCLES")
    view["daily_equity"] = _daily_series(view["daily"], "TOTAL_EQUITY_FINAL")
    view["daily_reserve"] = _daily_series(view["daily"], "RESERVE_FINAL")
    cutoff_us = _checkpoint_cutoff(root, day)
    view["summary"] = _prefix_summary(run.get("summary", {}), run.get("daily", []), state, day, cutoff_us)
    view["period_label"] = f"dias 1–{day} (mesmo prefixo comparável)"
    view["closed_day"] = day
    view["settlements"] = []
    view["positions"] = []
    view["open_hold"] = None
    view["recovery_sensitivity"] = {}
    if state is None:
        view["debt_states"] = "INVALID_PREFIX_ENGINE_STATE"
        view["status"] = "INVALID"
        view["checkpoint"] = True
        return view
    if state is not None:
        settlements = state.get("settlements", [])
        view["settlements"] = settlements
        view["positions"], view["positions_evidence_available"] = _checkpoint_positions(
            root, state, settlements, cutoff_us
        )
        if not settlements:
            view["debt_states"] = "AVAILABLE_PREFIX_ACCOUNTING_NO_SETTLEMENTS_POLICY_DEFERRED"
            return view
        if cutoff_us is None:
            view["debt_states"] = "POLICY_DEFERRED_MISSING_CUTOFF"
            return view
        end_us = int(cutoff_us)
        view["recovery_sensitivity"] = {
            f: analyze_recovery(settlements, D(f), end_us) for f in FUNDING
        }
        view["debt_states"] = (
            "AVAILABLE_PREFIX_ACCOUNTING_POLICY_DEFERRED"
            if run.get("status") != "COMPLETE"
            else "AVAILABLE_PREFIX_ACCOUNTING"
        )
    if run.get("status") == "COMPLETE":
        view["status"] = "COMPLETE_PREFIX"
    return view


def _quantile(values: list[D], fraction: D) -> D | None:
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, int((D(len(ordered)) * fraction).to_integral_value(rounding="ROUND_CEILING")))
    return ordered[rank - 1]


def _median_decimal(values: list[D]) -> D | None:
    if not values:
        return None
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / D(2)


def _augment_metrics(run: dict[str, Any]) -> dict[str, Any]:
    summary = dict(run.get("summary", {}))
    daily = run.get("daily", [])
    cycles = [D(str(row["DAILY_NET_POSITIVE_CYCLES"])) for row in daily if row.get("DAILY_NET_POSITIVE_CYCLES") is not None]
    summary["DAILY_CYCLES_MIN"] = int(min(cycles)) if cycles else UNAVAILABLE
    summary["DAILY_CYCLES_MEDIAN"] = str(sorted(cycles)[len(cycles) // 2] if len(cycles) % 2 else (sorted(cycles)[len(cycles) // 2 - 1] + sorted(cycles)[len(cycles) // 2]) / D(2)) if cycles else UNAVAILABLE
    summary["DAILY_CYCLES_MAX"] = int(max(cycles)) if cycles else UNAVAILABLE
    for threshold in (500, 1000, 2000):
        summary[f"DAYS_BELOW_{threshold}"] = sum(value < threshold for value in cycles) if cycles else UNAVAILABLE
    settlements = [row for row in run.get("settlements", []) if isinstance(row, dict)]
    positive_pnl = [D(str(row["net_profit"])) for row in settlements if not row.get("release") and D(str(row.get("net_profit", "0"))) > 0]
    release_losses = [
        D(str(row.get("reserve_consumption", "0")))
        for row in settlements
        if row.get("release")
    ]
    summary["RELEASE_LOSS_MEAN"] = str(sum(release_losses, D(0)) / D(len(release_losses))) if release_losses else UNAVAILABLE
    if positive_pnl:
        summary["PNL_PER_CYCLE_DISTRIBUTION"] = dict(Counter(str(value) for value in positive_pnl))
        summary["PNL_PER_CYCLE_MIN"] = str(min(positive_pnl))
        summary["PNL_PER_CYCLE_MEDIAN"] = str(_median_decimal(positive_pnl))
        summary["PNL_PER_CYCLE_P90"] = str(_quantile(positive_pnl, D("0.9")))
        summary["PNL_PER_CYCLE_MAX"] = str(max(positive_pnl))
    else:
        summary["PNL_PER_CYCLE_DISTRIBUTION"] = UNAVAILABLE
        for key in ("PNL_PER_CYCLE_MIN", "PNL_PER_CYCLE_MEDIAN", "PNL_PER_CYCLE_P90", "PNL_PER_CYCLE_MAX"):
            summary[key] = UNAVAILABLE
    has_evidence = run.get("status") not in {UNAVAILABLE, "NOT_STARTED", "NO_COMPLETE_BOUND_STATE"}
    initial_default = "100" if has_evidence else UNAVAILABLE
    reserve_default = "10" if has_evidence else UNAVAILABLE
    funding_default = "0.10" if has_evidence else UNAVAILABLE
    summary.setdefault("INITIAL_CAPITAL", summary.get("OPERATING_START", initial_default))
    summary.setdefault("INITIAL_BANK", summary.get("OPERATING_START", initial_default))
    summary.setdefault("INITIAL_RESERVE", summary.get("RESERVE_START", reserve_default))
    summary["REAL_FUNDING_RATE"] = summary.get("REAL_FUNDING_RATE", funding_default)
    summary["NOTIONAL_CAP"] = summary.get("NOTIONAL_CAP", UNAVAILABLE)
    if summary["INITIAL_CAPITAL"] != UNAVAILABLE and summary["INITIAL_RESERVE"] != UNAVAILABLE:
        summary["INITIAL_EQUITY"] = str(
            D(str(summary["INITIAL_CAPITAL"])) + D(str(summary["INITIAL_RESERVE"]))
        )
    else:
        summary["INITIAL_EQUITY"] = UNAVAILABLE
    summary["FINAL_BANK"] = summary.get("OPERATING_FINAL", summary.get("OPERATING_BANK", UNAVAILABLE))
    summary["FINAL_CAPITAL"] = summary.get("TOTAL_EQUITY_FINAL", summary.get("TOTAL_EQUITY", UNAVAILABLE))
    summary["REALIZED_FEES_QUOTE"] = summary.get("REALIZED_FEES_QUOTE", summary.get("FEES", UNAVAILABLE))
    summary["UNREALIZED_PNL"] = summary.get("UNREALIZED_PNL", UNAVAILABLE)
    summary["RESERVE_FLOOR"] = summary.get("RESERVE_FLOOR", UNAVAILABLE)
    summary["CAPITAL_MODE"] = summary.get("CAPITAL_MODE", "COMPOUNDING" if has_evidence else UNAVAILABLE)
    positions = run.get("positions", [])
    holds = [D(str(row["hold_hours"])) for row in positions if row.get("hold_hours") is not None]
    open_hold = run.get("open_hold")
    if open_hold and not any(row.get("open_censored") for row in positions) and open_hold.get("age_hours") is not None:
        holds.append(D(str(open_hold["age_hours"])))
    if not run.get("positions_evidence_available", True):
        for key in ("HOLD_GT_2H_COUNT", "HOLD_GT_2H_EXCESS_HOURS", "HOLD_GT_2H_EXCESS_SECONDS", "MAX_HOLD_HOURS"):
            summary[key] = UNAVAILABLE
    elif holds:
        excess = sum((max(D(0), hold - D(2)) for hold in holds), D(0))
        summary["HOLD_GT_2H_COUNT"] = sum(hold > 2 for hold in holds)
        summary["HOLD_GT_2H_EXCESS_HOURS"] = str(excess)
        summary["HOLD_GT_2H_EXCESS_SECONDS"] = str(excess * D(3600))
        summary["MAX_HOLD_HOURS"] = str(max(holds))
    else:
        for key in ("HOLD_GT_2H_COUNT", "HOLD_GT_2H_EXCESS_HOURS", "HOLD_GT_2H_EXCESS_SECONDS", "MAX_HOLD_HOURS"):
            summary[key] = summary.get(key, UNAVAILABLE)
    summary["CAPITAL_PRODUCTIVE_UPTIME"] = UNAVAILABLE
    summary["PROTECTION_TIME"] = NOT_IMPLEMENTED
    recovery = run.get("recovery_sensitivity", {}).get("0.10")
    if recovery:
        completed = [tranche for tranche in recovery.get("tranches", []) if tranche.get("recovery_cycles") is not None]
        summary["RECOVERY_CENSORED_COUNT"] = recovery.get("censored_count", UNAVAILABLE)
        summary["DEBT_FINAL"] = recovery.get("outstanding_debt", UNAVAILABLE)
        summary["RESERVE_SURPLUS_CONTRIBUTION"] = recovery.get("surplus_contributions", UNAVAILABLE)
        summary["RECOVERY_OVERLAP_COUNT"] = sum(int(tranche.get("new_release_while_pending_count", 0)) for tranche in recovery.get("tranches", []))
        if completed:
            cycle_values = [D(str(tranche["recovery_cycles"])) for tranche in completed]
            hour_values = [D(str(tranche["elapsed_hours"])) for tranche in completed]
            summary["RECOVERY_P90_CYCLES"] = str(_quantile(cycle_values, D("0.9")))
            summary["RECOVERY_P90_HOURS"] = str(_quantile(hour_values, D("0.9")))
            summary["RECOVERY_MAX_CYCLES"] = str(max(cycle_values))
            summary["RECOVERY_MAX_HOURS"] = str(max(hour_values))
            summary["RECOVERY_MEDIAN_CYCLES"] = str(_median_decimal(cycle_values))
            summary["RECOVERY_MEDIAN_HOURS"] = str(_median_decimal(hour_values))
        else:
            for key in ("RECOVERY_P90_CYCLES", "RECOVERY_P90_HOURS", "RECOVERY_MAX_CYCLES", "RECOVERY_MAX_HOURS", "RECOVERY_MEDIAN_CYCLES", "RECOVERY_MEDIAN_HOURS"):
                summary[key] = UNAVAILABLE
    else:
        for key in ("RECOVERY_CENSORED_COUNT", "DEBT_FINAL", "RESERVE_SURPLUS_CONTRIBUTION", "RECOVERY_OVERLAP_COUNT", "RECOVERY_P90_CYCLES", "RECOVERY_P90_HOURS", "RECOVERY_MAX_CYCLES", "RECOVERY_MAX_HOURS", "RECOVERY_MEDIAN_CYCLES", "RECOVERY_MEDIAN_HOURS"):
            summary[key] = UNAVAILABLE
    run["summary"] = summary
    return run


def build_model_comparison(
    m015_root: Path = M015_ROOT,
    m016_root: Path = M016_ROOT,
    m017_root: Path = M017_ROOT,
) -> dict[str, Any]:
    """Build a reporting-only M015/M016/M017 comparison.

    This compares artifacts and checkpoints; it never invokes a runner or treats
    fixed-funding sensitivity as a new replay.
    """
    roots = {"M015": m015_root, "M016": m016_root, "M017": m017_root}
    full_models = {
        model_id: _checkpoint_run(
            root,
            f"{model_id}_PRICE_PRIORITY",
            max_day=CURRENT_APPROVED_DAYS if model_id == "M017" else 12,
        )
        for model_id, root in roots.items()
    }
    comparable = all(
        full_models[model_id].get("status") not in {UNAVAILABLE, "NOT_STARTED"}
        and int(full_models[model_id].get("closed_day", 0)) > 0
        for model_id in MODEL_IDS
    )
    comparison_day = (
        min(int(full_models[model_id]["closed_day"]) for model_id in MODEL_IDS)
        if comparable
        else 0
    )
    models = {
        model_id: _augment_metrics(_prefix_view(full_models[model_id], roots[model_id], comparison_day))
        for model_id in MODEL_IDS
    }
    metric_keys = (
        "REAL_FUNDING_RATE",
        "RELEASE_LOSS_MEAN",
        "RECOVERY_MEDIAN_CYCLES",
        "RECOVERY_MEDIAN_HOURS",
        "RECOVERY_CENSORED_COUNT",
        "NET_POSITIVE_CYCLES",
        "FULL_FILL_CYCLES",
        "RELEASES",
        "NET_PNL",
        "TOTAL_EQUITY_FINAL",
        "RESERVE_FINAL",
        "MIN_RESERVE",
        "RESERVE_FUNDING",
        "RESERVE_CONSUMPTION",
        "RESERVE_SURPLUS_CONTRIBUTION",
        "OPERATING_FINAL",
        "OPERATING_BANK",
        "OPERATING_CASH",
        "MOTOR_UPTIME",
        "HOLDING_HOURS",
        "FLAT_HOURS",
        "FULL_STOP_HOURS",
        "MAX_DRAWDOWN_PCT",
        "HARD_LOCK_VIOLATIONS",
        "ZERO_CYCLE_DAYS",
        "TRADES",
        "L2_ROWS",
        "AUDIT_STATUS",
        "VERDICT",
        "INITIAL_CAPITAL",
        "INITIAL_BANK",
        "INITIAL_RESERVE",
        "INITIAL_EQUITY",
        "NOTIONAL_CAP",
        "FINAL_BANK",
        "FINAL_CAPITAL",
        "REALIZED_FEES_QUOTE",
        "UNREALIZED_PNL",
        "RESERVE_FLOOR",
        "CAPITAL_MODE",
        "DAILY_CYCLES_MIN",
        "DAILY_CYCLES_MEDIAN",
        "DAILY_CYCLES_MAX",
        "DAYS_BELOW_500",
        "DAYS_BELOW_1000",
        "DAYS_BELOW_2000",
        "PNL_PER_CYCLE_MIN",
        "PNL_PER_CYCLE_MEDIAN",
        "PNL_PER_CYCLE_P90",
        "PNL_PER_CYCLE_MAX",
        "PNL_PER_CYCLE_DISTRIBUTION",
        "HOLD_GT_2H_COUNT",
        "HOLD_GT_2H_EXCESS_HOURS",
        "HOLD_GT_2H_EXCESS_SECONDS",
        "MAX_HOLD_HOURS",
        "RECOVERY_P90_CYCLES",
        "RECOVERY_P90_HOURS",
        "RECOVERY_MAX_CYCLES",
        "RECOVERY_MAX_HOURS",
        "DEBT_FINAL",
        "RECOVERY_OVERLAP_COUNT",
        "CAPITAL_PRODUCTIVE_UPTIME",
        "PROTECTION_TIME",
    )
    metrics: dict[str, dict[str, Any]] = {}
    for key in metric_keys:
        metrics[key] = {
            model_id: models[model_id]["summary"].get(key, UNAVAILABLE) for model_id in MODEL_IDS
        }
    for key in ("QUEUE_POSITION", "PROSPECTIVE_VALIDATION"):
        metrics[key] = {model_id: NOT_IMPLEMENTED for model_id in MODEL_IDS}
    m017_status = full_models["M017"].get("status")
    if comparison_day:
        comparison_period = f"mesmo prefixo lógico, dias 1–{comparison_day}"
        historical_control_period = (
            "M015/M016 12D completos preservados como controles históricos"
            if comparison_day < 12
            else "M015/M016 12D completos"
        )
    elif m017_status in {UNAVAILABLE, "NOT_STARTED"}:
        comparison_period = "M017 NOT_STARTED; M015/M016 12D permanecem controles históricos"
        historical_control_period = "M015/M016 12D completos preservados como controles históricos"
    else:
        comparison_period = "NO_COMMON_CLOSED_PREFIX"
        historical_control_period = UNAVAILABLE
    return {
        "classification": "REPORTING_COMPARISON_OF_THREE_REAL_REPLAYS",
        "scenario_kind": "THREE_REAL_REPLAYS_FUNDING_REAL_10_PERCENT_SENSITIVITY_DIAGNOSTIC_ONLY",
        "approved_window_days": CURRENT_APPROVED_DAYS,
        "comparison_period": comparison_period,
        "historical_control_period": historical_control_period,
        "model_ids": MODEL_IDS,
        "models": models,
        "full_models": full_models,
        "configuration": {"M017": _validated_m017_configuration(m017_root)},
        "metrics": metrics,
        "debt_states": {model_id: models[model_id]["debt_states"] for model_id in MODEL_IDS},
    }


def render(data):
    out = [
        '<section id="reserva-equilibrio"><div class="eyebrow muted">OWNER / Reserva, recuperação e rotação</div>',
        "<h2>Quanto reservar não pode ser separado de quanto o motor perde.</h2>",
        "<p>Autópsia dos 12 dias encerrados. A sensibilidade abaixo redistribui lucros dos MESMOS fills: "
        "<strong>não é novo replay composto, não altera ciclos e não escolhe funding ótimo.</strong></p>",
        '<div class="callout amber"><p>M015 é diagnóstico histórico; sua preparação está superada. '
        "M016 já foi executado e a comparação abaixo reporta seus artifacts com funding de 10%; "
        "esta seção não autoriza novo runtime, tuning ou contrato de saída.</p></div>",
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
            "<th>Funding</th><th>Perdas recuperadas / com dívida</th><th>Releases sem perda</th>"
            "<th>Ciclos mediana / P90</th>"
            "<th>Tempo mediano h</th><th>Dívida aberta USDT</th></tr></thead><tbody>"
        )
        for f, rec in run["recovery_sensitivity"].items():
            time = rec["median_recovery_hours"]
            shown_time = f"{D(time):.3f}" if time is not None else "—"
            debt_tranches = len(rec.get("tranches", []))
            releases = s.get("RELEASES", UNAVAILABLE)
            no_loss_releases = max(0, releases - debt_tranches) if isinstance(releases, int) else UNAVAILABLE
            out.append(
                f"<tr><td>{D(f) * 100:.0f}%</td><td>{rec['recovered_count']} / {debt_tranches}</td>"
                f"<td>{no_loss_releases}</td>"
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


def _chart_svg(title: str, series: dict[str, list[str | None]], colors: dict[str, str]) -> str:
    """Render a small static SVG; missing checkpoints remain visibly missing."""
    width, height = 560, 190
    left, top, plot_width, plot_height = 80, 24, 450, 125
    numeric = [D(value) for values in series.values() for value in values if value is not None]
    if not numeric:
        return (
            f'<div class="chart"><h4>{escape(title)}</h4>'
            f'<p class="note">{UNAVAILABLE}: daily checkpoint values are not available.</p></div>'
        )
    lower, upper = min(numeric), max(numeric)
    if "ciclos" in title.lower():
        lower = min(D(0), lower)
    integer_axis = "ciclos" in title.lower()
    format_axis = (lambda value: f"{D(value):.0f}") if integer_axis else (lambda value: f"{D(value):.6f}")
    if lower == upper:
        lower -= D(1)
        upper += D(1)
    paths: list[str] = []
    marks: list[str] = []
    for name, values in series.items():
        points: list[str] = []
        for index, value in enumerate(values):
            if value is None:
                if points:
                    paths.append(
                        f'<polyline fill="none" stroke="{colors[name]}" stroke-width="2" '
                        f'points="{" ".join(points)}" />'
                    )
                points = []
                continue
            x = D(left) + D(index) * D(plot_width) / D(11)
            y = D(top + plot_height) - (D(value) - lower) * D(plot_height) / (upper - lower)
            points.append(f"{x:.2f},{y:.2f}")
            marks.append(
                f'<circle cx="{x:.2f}" cy="{y:.2f}" r="2.8" fill="{colors[name]}">'
                f'<title>{escape(name)} dia {index + 1}: {format_axis(value)}</title></circle>'
            )
        if points:
            paths.append(
                f'<polyline fill="none" stroke="{colors[name]}" stroke-width="2" '
                f'points="{" ".join(points)}" />'
            )
    labels = "".join(
        f'<text x="{D(left) + D(index) * D(plot_width) / D(11):.2f}" y="166" '
        f'font-size="10" text-anchor="middle">{index + 1}</text>'
        for index in range(12)
    )
    legend = " ".join(
        f'<span style="color:{colors[name]}">■ {escape(name)}</span>' for name in series
    )
    return (
        f'<div class="chart"><h4>{escape(title)}</h4><svg viewBox="0 0 {width} {height}" '
        f'role="img" aria-label="{escape(title)}">'
        f'<title>{escape(title)}: min={format_axis(lower)}, max={format_axis(upper)}</title>'
        f'<line x1="{left}" y1="{top + plot_height}" x2="{left + plot_width}" '
        f'y2="{top + plot_height}" stroke="#cbd5e1" />'
        f'<text x="2" y="{top + 4}" font-size="12">{format_axis(upper)}</text>'
        f'<text x="2" y="{top + plot_height}" font-size="12">{format_axis(lower)}</text>'
        f'{labels}{"".join(paths)}{"".join(marks)}</svg>'
        f'<div class="legend">{legend}</div></div>'
    )


_COUNT_METRIC_KEYS = {
    "NET_POSITIVE_CYCLES",
    "FULL_FILL_CYCLES",
    "RELEASES",
    "HOLD_GT_2H_COUNT",
    "RECOVERY_CENSORED_COUNT",
    "RECOVERY_OVERLAP_COUNT",
    "RECOVERY_P90_CYCLES",
    "RECOVERY_MAX_CYCLES",
    "RECOVERY_MEDIAN_CYCLES",
    "DAILY_CYCLES_MIN",
    "DAILY_CYCLES_MEDIAN",
    "DAILY_CYCLES_MAX",
    "DAYS_BELOW_500",
    "DAYS_BELOW_1000",
    "DAYS_BELOW_2000",
    "ZERO_CYCLE_DAYS",
    "TRADES",
    "L2_ROWS",
    "HARD_LOCK_VIOLATIONS",
    "executable_loss_cap_bps",
}
_MONEY_METRIC_KEYS = {
    "NET_PNL",
    "TOTAL_EQUITY_FINAL",
    "RESERVE_FINAL",
    "RESERVE_FUNDING",
    "RESERVE_CONSUMPTION",
    "RESERVE_SURPLUS_CONTRIBUTION",
    "OPERATING_FINAL",
    "OPERATING_BANK",
    "OPERATING_CASH",
    "INITIAL_CAPITAL",
    "INITIAL_BANK",
    "INITIAL_RESERVE",
    "INITIAL_EQUITY",
    "RELEASE_LOSS_MEAN",
    "FINAL_BANK",
    "FINAL_CAPITAL",
    "REALIZED_FEES_QUOTE",
    "UNREALIZED_PNL",
    "RESERVE_FLOOR",
    "PNL_PER_CYCLE_MIN",
    "PNL_PER_CYCLE_MEDIAN",
    "PNL_PER_CYCLE_P90",
    "PNL_PER_CYCLE_MAX",
}


def _display_metric(value: Any, key: str | None = None) -> str:
    if value is None or value == "" or value == UNAVAILABLE:
        return UNAVAILABLE
    try:
        parsed = D(str(value))
    except Exception:
        return escape(str(value))
    if parsed.is_finite() and key == "REAL_FUNDING_RATE":
        return escape(f"{parsed * 100:.0f}%")
    if parsed.is_finite() and key in _COUNT_METRIC_KEYS:
        return escape(f"{parsed:.0f}")
    if parsed.is_finite() and key in _MONEY_METRIC_KEYS:
        return escape(f"{parsed:.6f}")
    if parsed.is_finite():
        return escape(f"{parsed:.6f}")
    return escape(str(value))


_METRIC_LABELS = {
    "NET_POSITIVE_CYCLES": "ciclos positivos",
    "FULL_FILL_CYCLES": "ciclos completos",
    "RELEASES": "releases",
    "NET_PNL": "PnL líquido",
    "TOTAL_EQUITY_FINAL": "patrimônio final",
    "RESERVE_FINAL": "reserva final",
    "MIN_RESERVE": "reserva mínima",
    "RESERVE_FUNDING": "aporte de reserva",
    "RESERVE_CONSUMPTION": "consumo de reserva",
    "RESERVE_SURPLUS_CONTRIBUTION": "aporte excedente (não quita dívida futura)",
    "OPERATING_FINAL": "banca operacional final",
    "OPERATING_BANK": "banca operacional (cash+cost+dust)",
    "OPERATING_CASH": "caixa operacional",
    "MOTOR_UPTIME": "uptime de ordem ordinária ativa (não uptime produtivo)",
    "CAPITAL_PRODUCTIVE_UPTIME": "uptime produtivo de capital",
    "PROTECTION_TIME": "tempo em proteção",
    "HOLDING_HOURS": "horas em posição",
    "FLAT_HOURS": "horas flat",
    "FULL_STOP_HOURS": "horas sem ordem ordinária ativa (não proteção)",
    "MAX_DRAWDOWN_PCT": "drawdown máximo",
    "HARD_LOCK_VIOLATIONS": "hard-lock legado (>24h; não é violação de 2h)",
    "HOLD_GT_2H_COUNT": "posições >2h",
    "HOLD_GT_2H_EXCESS_HOURS": "excesso sobre 2h (horas)",
    "HOLD_GT_2H_EXCESS_SECONDS": "excesso sobre 2h (segundos)",
    "MAX_HOLD_HOURS": "hold máximo (horas)",
    "INITIAL_CAPITAL": "capital operacional inicial",
    "INITIAL_BANK": "banca inicial",
    "INITIAL_RESERVE": "reserva inicial",
    "INITIAL_EQUITY": "equity inicial",
    "REAL_FUNDING_RATE": "funding real",
    "RELEASE_LOSS_MEAN": "perda média por release",
    "RECOVERY_MEDIAN_CYCLES": "recuperação mediana (ciclos)",
    "RECOVERY_MEDIAN_HOURS": "recuperação mediana (horas)",
    "NOTIONAL_CAP": "cap de notional",
    "FINAL_BANK": "banca final",
    "FINAL_CAPITAL": "capital total final",
    "REALIZED_FEES_QUOTE": "taxas realizadas",
    "UNREALIZED_PNL": "PnL não realizado",
    "RESERVE_FLOOR": "piso de reserva",
    "CAPITAL_MODE": "modo de capital",
    "DAILY_CYCLES_MIN": "ciclos/dia mínimo",
    "DAILY_CYCLES_MEDIAN": "ciclos/dia mediana",
    "DAILY_CYCLES_MAX": "ciclos/dia máximo",
    "DAYS_BELOW_500": "dias <500 ciclos",
    "DAYS_BELOW_1000": "dias <1000 ciclos",
    "DAYS_BELOW_2000": "dias <2000 ciclos",
    "PNL_PER_CYCLE_MIN": "PnL/ciclo mínimo",
    "PNL_PER_CYCLE_MEDIAN": "PnL/ciclo mediana",
    "PNL_PER_CYCLE_P90": "PnL/ciclo P90",
    "PNL_PER_CYCLE_MAX": "PnL/ciclo máximo",
    "PNL_PER_CYCLE_DISTRIBUTION": "distribuição de PnL/ciclo",
    "RECOVERY_CENSORED_COUNT": "recuperações censuradas",
    "RECOVERY_P90_CYCLES": "recuperação P90 (ciclos)",
    "RECOVERY_P90_HOURS": "recuperação P90 (horas)",
    "RECOVERY_MAX_CYCLES": "recuperação máxima (ciclos)",
    "RECOVERY_MAX_HOURS": "recuperação máxima (horas)",
    "DEBT_FINAL": "dívida final",
    "RECOVERY_OVERLAP_COUNT": "sobreposições de releases",
    "QUEUE_POSITION": "posição na fila",
    "PROSPECTIVE_VALIDATION": "validação prospectiva",
    "AUDIT_STATUS": "auditoria",
    "VERDICT": "veredito",
}


def _owner_summary(comparison: dict[str, Any]) -> str:
    """Build the owner-facing headline from the newest available run prefix."""
    model_ids = comparison.get("model_ids", MODEL_IDS)
    selected = next(
        (
            model_id
            for model_id in reversed(model_ids)
            if model_id in comparison["models"]
            and comparison["models"][model_id].get("status")
            not in {UNAVAILABLE, "NOT_STARTED", "NO_COMPLETE_BOUND_STATE"}
        ),
        "M016",
    )
    model = comparison["models"].get(selected, {})
    summary = model.get("summary", {})
    recovery = model.get("recovery_sensitivity", {}).get("0.10")

    def count(value: Any) -> str:
        if value is None or value == UNAVAILABLE:
            return UNAVAILABLE
        try:
            return f"{D(str(value)):.0f}"
        except Exception:
            return UNAVAILABLE

    def money(value: Any) -> str:
        if value is None or value == UNAVAILABLE:
            return UNAVAILABLE
        try:
            return f"{D(str(value)):.6f}"
        except Exception:
            return UNAVAILABLE

    funding = summary.get("REAL_FUNDING_RATE", UNAVAILABLE)
    try:
        funding_label = f"{D(str(funding)) * 100:.0f}%"
    except Exception:
        funding_label = UNAVAILABLE
    if recovery is None:
        recovery_label = UNAVAILABLE
        recovery_note = "N/T não estimáveis"
    else:
        recovered = count(recovery.get("recovered_count"))
        debt_cohort = count(len(recovery.get("tranches", [])))
        recovery_label = f"{recovered}/{debt_cohort} recuperados"
        recovery_note = "N/T não estimáveis" if recovery.get("recovered_count", 0) == 0 else "coorte recuperada"
    daily_min = summary.get("DAILY_CYCLES_MIN", UNAVAILABLE)
    daily_max = summary.get("DAILY_CYCLES_MAX", UNAVAILABLE)
    status = model.get("status", UNAVAILABLE)
    if status == "CHECKPOINT_PARTIAL":
        status_label = "checkpoint parcial; veredito PENDING"
    elif status == "M017_OWNER_PAUSED_AFTER_SCOPE":
        status_label = "OWNER_PAUSED_AFTER_SCOPE; veredito PENDING"
    elif status in {"COMPLETE", "COMPLETE_PREFIX"}:
        status_label = f"runtime {status}; não é STRATEGY_PASS"
    else:
        status_label = str(status)
    return (
        f"<strong>OWNER: {escape(selected)} {escape(status_label)}</strong> — "
        f"funding {funding_label}; perda média por release {money(summary.get('RELEASE_LOSS_MEAN'))} USDT; "
        f"{recovery_label}, {recovery_note}; "
        f"{count(summary.get('NET_POSITIVE_CYCLES'))} ciclos positivos "
        f"({count(daily_min)}–{count(daily_max)}/dia); "
        f"banca {money(summary.get('INITIAL_BANK'))} → {money(summary.get('FINAL_BANK'))} USDT; "
        f"reserva {money(summary.get('INITIAL_RESERVE'))} → {money(summary.get('RESERVE_FINAL'))} USDT; "
        f"{count(summary.get('HOLD_GT_2H_COUNT'))} posições >2h; "
        f"equity final {money(summary.get('FINAL_CAPITAL'))} USDT."
    )


def _owner_m016_summary(comparison: dict[str, Any]) -> str:
    """Backward-compatible test helper for the generic owner headline."""
    return _owner_summary(comparison)


def render_model_comparison(comparison: dict[str, Any]) -> str:
    """Render the M015/M016 artifact comparison as an additive HTML section."""
    models = comparison["models"]
    model_ids = tuple(comparison.get("model_ids", tuple(models)))
    model_title = " × ".join(f"{model_id} PRICE_PRIORITY" for model_id in model_ids)
    classification = str(comparison["classification"]).replace("REAL_REPLAYS", "SIMULATED_REPLAYS")
    scenario_kind = str(comparison["scenario_kind"]).replace("REAL_REPLAYS", "SIMULATED_REPLAYS")
    out = [
        '<section id="m015-m016-comparacao">',
        f'<div class="eyebrow muted">OWNER / {escape(" × ".join(model_ids))} · comparação de artifacts</div>',
        f"<h2>{escape(model_title)}</h2>",
        f'<p class="owner-summary">{_owner_summary(comparison)}</p>',
        f'<p class="note">São {len(model_ids)} replays simulados, todos com funding real de 10%. '
        'A sensibilidade de funding abaixo é somente diagnóstico dos mesmos settlements; não é um novo replay.</p>',
        f'<p class="note">Classificação: <code>{escape(classification)}</code>. '
        f'Cenário: <code>{escape(scenario_kind)}</code>. '
        f'Período comparável: <code>{escape(comparison["comparison_period"])}</code>. '
        f'Histórico: <code>{escape(comparison.get("historical_control_period", UNAVAILABLE))}</code>. '
        f'Janela OWNER aprovada: <code>1–{comparison.get("approved_window_days", UNAVAILABLE)} dias</code>; '
        'qualquer resultado M017 além dela está fora do escopo desta entrega.</p>',
        '<p class="note">Recuperar em quatro ciclos só ajuda se esses quatro ciclos realmente ocorrerem logo; '
        'enquanto a posição está travada, a fila serial não produz os próximos ciclos. Maior funding não acelera '
        'esse relógio. Os limites de 2h aparecem como excesso em horas e segundos; hard-lock de 24h é uma régua legada distinta.</p>',
        '<p class="note">Aritmética ilustrativa, não previsão nem replay novo: um lucro de 0.0099 USDT a 80% '
        'aporta 0.00792; uma perda de 0.1683 exigiria 22 desses ciclos, enquanto quatro aportariam 0.03168. '
        'Isto separa o cap financeiro da frequência causal de novos ciclos.</p>',
    ]
    out.append('<div class="comparison-charts">')
    out.append(
        _chart_svg(
            "Ciclos positivos por dia lógico",
            {name: models[name]["daily_positive_cycles"] for name in model_ids},
            {name: MODEL_COLORS.get(name, "#475569") for name in model_ids},
        )
    )
    out.append(
        _chart_svg(
            "Patrimônio final diário",
            {name: models[name]["daily_equity"] for name in model_ids},
            {name: MODEL_COLORS.get(name, "#475569") for name in model_ids},
        )
    )
    out.append(
        _chart_svg(
            "Reserva final diária",
            {name: models[name]["daily_reserve"] for name in model_ids},
            {name: MODEL_COLORS.get(name, "#475569") for name in model_ids},
        )
    )
    out.append("</div>")
    out.append(
        '<details><summary>Placar completo e definições</summary>'
        '<div class="table-wrap"><table><thead><tr><th>Métrica</th>'
        + "".join(
            f'<th>{escape(model_id)} · {escape(str(models[model_id].get("period_label", "UNAVAILABLE")))}</th>'
            for model_id in model_ids
        )
        + "</tr></thead><tbody>"
    )
    for key, values in comparison["metrics"].items():
        out.append(
            f"<tr><td>{escape(_METRIC_LABELS.get(key, key))}</td>"
            + "".join(f"<td>{_display_metric(values[model_id], key)}</td>" for model_id in model_ids)
            + "</tr>"
        )
    out.append("</tbody></table></div>")
    out.append(
        '<div class="table-wrap"><table><thead><tr><th>Estado</th>'
        + "".join(f"<th>{escape(model_id)}</th>" for model_id in model_ids)
        + "</tr></thead><tbody>"
        + "<tr><td>artifact</td>"
        + "".join(f"<td>{_display_metric(models[model_id]['status'])}</td>" for model_id in model_ids)
        + "</tr><tr><td>estado de dívida/política</td>"
        + "".join(
            f"<td>{_display_metric(comparison['debt_states'][model_id])}</td>" for model_id in model_ids
        )
        + "</tr></tbody></table></div>"
    )
    configuration = comparison.get("configuration", {})
    config_rows = (
        ("policy", "policy"),
        ("capital inicial", "initial_capital"),
        ("reserva inicial", "initial_reserve"),
        ("piso absoluto", "reserve_floor"),
        ("funding de lucro", "profit_funding"),
        ("cap protegido (bps)", "executable_loss_cap_bps"),
        ("vínculo spec/registry", "status"),
        ("vínculo run-manifest", "run_binding"),
        ("aplicado ao resultado", "applied_to_result"),
    )
    out.append(
        '<div class="table-wrap"><table><thead><tr><th>Configuração validada</th>'
        + "".join(f"<th>{escape(model_id)}</th>" for model_id in model_ids)
        + "</tr></thead><tbody>"
    )
    for label, key in config_rows:
        values = []
        for model_id in model_ids:
            config = configuration.get(model_id, {})
            if key == "applied_to_result":
                value = "YES" if config.get("run_binding") == "VALIDATED_RUN_MANIFEST" else "NO"
            else:
                value = config.get(key, UNAVAILABLE)
            display_key = "REAL_FUNDING_RATE" if key == "profit_funding" else key
            values.append(_display_metric(value, display_key))
        out.append(
            f"<tr><td>{escape(label)}</td>"
            + "".join(f"<td>{value}</td>" for value in values)
            + "</tr>"
        )
    out.append("</tbody></table></div>")
    out.append(
        '<h3>Recuperação FIFO</h3><p class="note">Médias/medianas de recuperação só aparecem '
        'quando há releases quitados. Sem quitados: UNAVAILABLE; estados NORMAL/RECUPERAÇÃO/PROTEÇÃO '
        'ainda não implementados; deadlines executados são medidos por runtime, enquanto a contabilidade '
        'de settlements do prefixo pode estar disponível. Dívida aberta é o ledger FIFO, não '
        '10 menos a reserva final; o aporte excedente pré-perda aparece separado e não quita dívida futura.</p>'
        '<div class="table-wrap"><table><thead><tr><th>Funding</th>'
        + "".join(f"<th>{model_id} perdas recuperadas / com dívida</th>" for model_id in model_ids)
        + "".join(f"<th>{model_id} releases sem perda</th>" for model_id in model_ids)
        + "".join(f"<th>{model_id} mediana ciclos / h</th>" for model_id in model_ids)
        + "".join(f"<th>{model_id} P90/max ciclos</th>" for model_id in model_ids)
        + "".join(f"<th>{model_id} censurados</th>" for model_id in model_ids)
        + "".join(f"<th>{model_id} dívida aberta</th>" for model_id in model_ids)
        + "</tr></thead><tbody>"
    )
    for funding in FUNDING:
        cells: list[str] = [f"<td>{D(funding) * 100:.0f}%</td>"]
        for name in model_ids:
            run = models[name]
            recovery = run.get("recovery_sensitivity", {}).get(funding)
            if recovery is None:
                cells.append(f"<td>{UNAVAILABLE}</td>")
                continue
            debt_tranches = len(recovery.get("tranches", []))
            cells.append(f"<td>{recovery.get('recovered_count', UNAVAILABLE)} / {debt_tranches}</td>")
        for name in model_ids:
            run = models[name]
            recovery = run.get("recovery_sensitivity", {}).get(funding)
            if recovery is None:
                cells.append(f"<td>{UNAVAILABLE}</td>")
                continue
            releases = run["summary"].get("RELEASES", UNAVAILABLE)
            debt_tranches = len(recovery.get("tranches", []))
            if isinstance(releases, int):
                no_loss_releases: int | str = max(0, releases - debt_tranches)
            else:
                no_loss_releases = UNAVAILABLE
            cells.append(f"<td>{no_loss_releases}</td>")
        for name in model_ids:
            recovery = models[name].get("recovery_sensitivity", {}).get(funding)
            if not recovery or recovery.get("recovered_count", 0) == 0:
                cells.append(f"<td>{UNAVAILABLE}</td>")
            else:
                cells.append(
                    f"<td>{_display_metric(recovery.get('median_recovery_cycles'), 'RECOVERY_MEDIAN_CYCLES')} / "
                    f"{_display_metric(recovery.get('median_recovery_hours'), 'RECOVERY_MEDIAN_HOURS')}</td>"
                )
        for name in model_ids:
            recovery = models[name].get("recovery_sensitivity", {}).get(funding)
            if not recovery or recovery.get("recovered_count", 0) == 0:
                cells.append(f"<td>{UNAVAILABLE}</td>")
            else:
                cycles = [D(str(row["recovery_cycles"])) for row in recovery.get("tranches", []) if row.get("recovery_cycles") is not None]
                cells.append(
                    f"<td>{_display_metric(recovery.get('p90_recovery_cycles'), 'RECOVERY_P90_CYCLES')} / "
                    f"{_display_metric(max(cycles) if cycles else None, 'RECOVERY_MAX_CYCLES')}</td>"
                )
        for name in model_ids:
            recovery = models[name].get("recovery_sensitivity", {}).get(funding)
            cells.append(
                f"<td>{_display_metric(recovery.get('censored_count'), 'RECOVERY_CENSORED_COUNT') if recovery else UNAVAILABLE}</td>"
            )
        for name in model_ids:
            recovery = models[name].get("recovery_sensitivity", {}).get(funding)
            cells.append(
                f"<td>{_display_metric(recovery.get('outstanding_debt')) if recovery else UNAVAILABLE}</td>"
            )
        out.append("<tr>" + "".join(cells) + "</tr>")
    out.append(
        "</tbody></table></div>"
        '<p class="note">Fonte: summary.json, daily/NN.json e, quando COMPLETE, terminal state e closed audit. '
        'Nenhum valor ausente foi estimado; campos não persistidos permanecem UNAVAILABLE/NOT_IMPLEMENTED.</p>'
        "</details></section>"
    )
    return "\n".join(out)


def main():
    argparse.ArgumentParser(description=__doc__).parse_args()
    with localcontext() as ctx:
        ctx.prec = 128
        data = {
            "classification": "MIXED_REPLAY_RESULTS_AND_FROZEN_FILL_DIAGNOSTICS",
            "runs": {
                name: inspect_run(ROOT / name) for name in ("CONSERVATIVE_QUEUE", "PRICE_PRIORITY")
            },
        }
        comparison = build_model_comparison()
        data["m015_m016_comparison"] = comparison
        write_json(OUTPUT, data)
        start, end = "<!-- RESERVE_ROTATION_START -->", "<!-- RESERVE_ROTATION_END -->"
        html = HTML.read_text(encoding="utf-8")
        block = start + "\n" + render(data) + "\n" + end
        if start in html:
            left, tail = html.split(start, 1)
            html = left + block + tail.split(end, 1)[1]
        else:
            html = html.replace('<section id="conclusao">', block + '\n<section id="conclusao">', 1)
        comparison_start, comparison_end = "<!-- M015_M016_COMPARISON_START -->", "<!-- M015_M016_COMPARISON_END -->"
        comparison_block = comparison_start + "\n" + render_model_comparison(comparison) + "\n" + comparison_end
        if comparison_start in html:
            left, tail = html.split(comparison_start, 1)
            html = left + tail.split(comparison_end, 1)[1]
        html = html.replace(start, comparison_block + "\n" + start, 1)
        HTML.write_text(html, encoding="utf-8")
        print(json.dumps({"output": str(OUTPUT), "envelopes": list(data["runs"])}))


if __name__ == "__main__":
    main()
