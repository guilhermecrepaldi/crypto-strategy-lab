"""Pure, post-replay metrics for the preregistered recovery-reserve study.

This module deliberately does not inspect a tape or make a release decision.  The
runner supplies release accounting and, where available, the main replay's exact
drawdown measurement.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from .serial_replay import SerialReplayResult

D = Decimal
_DAY = D(24)


def _dec(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = D(str(value))
        return parsed if parsed.is_finite() else None
    except Exception:
        return None


def _duration_hours(start: Any, end: Any) -> Decimal | None:
    if start is None or end is None:
        return None
    try:
        seconds = D(str((end - start).total_seconds()))
        return seconds / D(3600)
    except Exception:
        return None


def summarize_replay(
    result: SerialReplayResult,
    reserve_final: Decimal,
    reserve_min: Decimal,
    total_skim: Decimal,
    releases: list[dict[str, Any]],
    maximum_drawdown: Decimal | None = None,
) -> dict[str, Any]:
    """Return deterministic accounting/lock metrics for one replay.

    Missing values are represented by ``None``.  In particular this function never
    estimates drawdown from terminal fields: the full tape is required for that.
    """
    if result.initial_quote != D(100):
        raise ValueError("INITIAL_CAPITAL_INVARIANT_VIOLATION")
    reserve_final = D(str(reserve_final))
    reserve_min = D(str(reserve_min))
    total_skim = D(str(total_skim))
    episodes = [*result.cycles, *result.release_closures]
    holds: list[Decimal] = []
    for item in episodes:
        hours = _duration_hours(item.entry_timestamp, item.exit_timestamp)
        if hours is not None:
            holds.append(max(D(0), hours))
    if result.open_entry_timestamp is not None:
        open_hours = _duration_hours(result.open_entry_timestamp, result.end_exclusive)
        if open_hours is not None:
            holds.append(max(D(0), open_hours))
    interval = _duration_hours(result.start, result.end_exclusive)
    lock_hours = sum((max(D(0), h - _DAY) for h in holds), D(0))
    inventory_hours = sum(holds, D(0))
    uptime = None if interval is None or interval <= 0 else D(1) - lock_hours / interval
    inventory_fraction = None if interval is None or interval <= 0 else inventory_hours / interval
    release_losses_raw = [_dec(r.get("loss_usdt")) for r in releases]
    release_losses: list[Decimal] = [x for x in release_losses_raw if x is not None and x > 0]
    depletion = 0
    for row in releases:
        before = _dec(row.get("reserve_before"))
        after = _dec(row.get("reserve_after"))
        if before is not None and after is not None and before != 0 and after == 0:
            depletion += 1
    final_operating = result.final_cash + result.final_inventory * result.last_price
    total_equity = final_operating + reserve_final
    return {
        "initial_capital": D(100),
        "currency": "USDT",
        "capital_mode": "COMPOUNDING",
        "initial_recovery_reserve": D(5),
        "total_initial_equity": D(105),
        "final_cash": result.final_cash,
        "final_inventory": result.final_inventory,
        "final_operating_equity": final_operating,
        "final_total_equity": total_equity,
        "total_final_equity": total_equity,
        "total_return": total_equity / D(105) - D(1),
        "completed_cycles": result.completed_cycles,
        "normal_completed_cycles": result.completed_cycles,
        "release_count": len(releases),
        "zero_cycle_days": result.zero_cycle_days,
        "lock_hours": lock_hours,
        "hours_gt24h": lock_hours,
        "operating_uptime": uptime,
        "inventory_open_fraction": inventory_fraction,
        "max_hold_hours": max(holds, default=D(0)),
        "reserve_final": reserve_final,
        "minimum_reserve_balance": reserve_min,
        "min_reserve_balance": reserve_min,
        "total_skim": total_skim,
        "reserve_depletion_events": depletion,
        "reserve_dollars_consumed": sum(release_losses, D(0)),
        "maximum_drawdown": maximum_drawdown,
        "integrity_pass": None,
    }


_AXES = ("skim_rate", "lock_hours_threshold", "max_loss_bps")


def _config(row: dict[str, Any]) -> dict[str, Any]:
    return {key: row.get(key) for key in (*_AXES, "scenario_id") if key in row}


def _gate(row: dict[str, Any], baseline: dict[str, Any]) -> tuple[bool, dict[str, bool]]:
    def n(key: str) -> Decimal | None:
        return _dec(row.get(key))

    def b(key: str) -> Decimal | None:
        return _dec(baseline.get(key))

    ne, be = n("total_final_equity"), b("total_final_equity")
    nu, bu = n("operating_uptime"), b("operating_uptime")
    nl, bl = n("lock_hours"), b("lock_hours")
    nc, bc = n("completed_cycles"), b("completed_cycles")
    nd, bd = n("maximum_drawdown"), b("maximum_drawdown")
    nr, nde = n("min_reserve_balance"), n("reserve_depletion_events")
    checks = {
        "total_final_equity": ne is not None and be is not None and ne >= be + D("0.01"),
        "operating_uptime": nu is not None and bu is not None and nu > bu,
        "lock_hours": nl is not None and bl is not None and nl < bl,
        "completed_cycles": nc is not None and bc is not None and nc >= bc * D("0.95"),
        "min_reserve_balance": nr is not None and nr >= D(1),
        "reserve_depletion_events": nde is not None and nde == 0,
        "maximum_drawdown": nd is not None and bd is not None and nd <= bd + D("0.01"),
        "integrity_pass": row.get("integrity_pass") is True,
    }
    return all(checks.values()), checks


def robust_regions(rows: list[dict[str, Any]], baseline: dict[str, Any]) -> dict[str, Any]:
    """Apply preregistered gates and immediate-neighbor robustness checks."""
    evaluated: dict[str, tuple[bool, dict[str, bool]]] = {}
    prereg = {
        "skim_rate": {D("0"), D("0.01"), D("0.05")},
        "lock_hours_threshold": {D("1"), D("6"), D("24")},
        "max_loss_bps": {D("2"), D("5"), D("10")},
    }
    for row in rows:
        sid = row.get("scenario_id")
        if sid is not None:
            evaluated[str(sid)] = _gate(row, baseline)
    observed_configs = {tuple(_dec(row.get(axis)) for axis in _AXES) for row in rows}
    expected_configs = {
        (skim, lock, loss)
        for skim in prereg["skim_rate"]
        for lock in prereg["lock_hours_threshold"]
        for loss in prereg["max_loss_bps"]
    }
    valid_grid = (
        len(rows) == 27
        and len({str(r.get("scenario_id")) for r in rows}) == 27
        and observed_configs == expected_configs
    )

    def axis_values(axis: str) -> list[Decimal]:
        return sorted({x for r in rows if (x := _dec(r.get(axis))) is not None})

    centers: list[dict[str, Any]] = []
    for row in rows:
        sid = row.get("scenario_id")
        if not valid_grid or sid is None or not evaluated.get(str(sid), (False, {}))[0]:
            continue
        neighbors: list[dict[str, Any]] = []
        axis_pass: dict[str, bool] = {}
        for axis in _AXES:
            vals = axis_values(axis)
            val = _dec(row.get(axis))
            idx = vals.index(val) if val in vals else -1
            candidates = (
                []
                if idx < 0
                else [
                    v
                    for v in (
                        vals[idx - 1] if idx else None,
                        vals[idx + 1] if idx + 1 < len(vals) else None,
                    )
                    if v is not None
                ]
            )
            axis_rows = [
                r
                for r in rows
                if _dec(r.get(axis)) in candidates
                and all(_dec(r.get(a)) == _dec(row.get(a)) for a in _AXES if a != axis)
            ]
            axis_pass[axis] = (
                valid_grid
                and bool(axis_rows)
                and all(evaluated.get(str(r.get("scenario_id")), (False, {}))[0] for r in axis_rows)
            )
            neighbors.extend({str(r.get("scenario_id")): r for r in axis_rows}.values())
        robust = all(axis_pass.values())
        centers.append(
            {
                "config": _config(row),
                "scenario_id": sid,
                "qualifies": robust,
                "axis_neighbors_pass": axis_pass,
                "neighbors": [_config(r) for r in neighbors],
            }
        )
    qualifying = [c for c in centers if c["qualifies"]]
    # Connected components use the already identified immediate-neighbor graph.
    qids = {str(c["scenario_id"]) for c in qualifying}
    center_by_id = {str(c["scenario_id"]): c for c in qualifying}
    regions: list[dict[str, Any]] = []
    while qids:
        root = min(qids)
        qids.remove(root)
        pending = {root}
        component: set[str] = set(pending)
        while pending:
            current = min(pending)
            pending.remove(current)
            center = center_by_id[current]
            adjacent = {str(n.get("scenario_id")) for n in center["neighbors"]} & qids
            qids -= adjacent
            pending |= adjacent
            component |= adjacent
        regions.append(
            {
                "scenario_ids": sorted(component),
                "configs": [
                    next(c["config"] for c in qualifying if str(c["scenario_id"]) == sid)
                    for sid in sorted(component)
                ],
            }
        )
    regions.sort(key=lambda region: region["scenario_ids"])
    baseline_equity = _dec(baseline.get("total_final_equity"))
    baseline_uptime = _dec(baseline.get("operating_uptime"))

    def ranking(center: dict[str, Any]) -> tuple[Decimal, Decimal, Decimal, Decimal, Decimal]:
        peers = [center["config"], *center["neighbors"]]
        peer_rows = [
            next(r for r in rows if r.get("scenario_id") == p.get("scenario_id")) for p in peers
        ]
        equity = [_dec(r.get("total_final_equity")) for r in peer_rows]
        uptime = [_dec(r.get("operating_uptime")) for r in peer_rows]
        me = min(
            (x - baseline_equity for x in equity if x is not None and baseline_equity is not None),
            default=D("-Infinity"),
        )
        mu = min(
            (x - baseline_uptime for x in uptime if x is not None and baseline_uptime is not None),
            default=D("-Infinity"),
        )
        loss = _dec(center["config"].get("max_loss_bps")) or D(0)
        lock = _dec(center["config"].get("lock_hours_threshold")) or D(0)
        skim = _dec(center["config"].get("skim_rate")) or D(0)
        return (me, mu, -loss, lock, -skim)

    selected = max(qualifying, key=ranking)["config"] if qualifying else None
    return {
        "qualifying_centers": qualifying,
        "selected_config": selected,
        "eligibility_pending_astra_review": bool(selected),
        "regions": regions,
        "actual_checks": {
            "rows": len(rows),
            "baseline_present": bool(baseline),
            "complete_preregistered_grid": valid_grid,
            "single_win_not_robust": bool(rows) and not qualifying,
        },
        "overfit_warnings": [
            c["scenario_id"]
            for c in centers
            if not c["qualifies"] and evaluated.get(str(c["scenario_id"]), (False, {}))[0]
        ],
    }


__all__ = ["robust_regions", "summarize_replay"]
