"""Frozen reserve-debt accounting diagnostics.

This module is deliberately a small, pure post-processing function.  It does not
make a release decision, run a replay, or compound a trading balance.  In
particular, reserve funding left over after paying a debt is reported as surplus
and is never allowed to pay a later release's debt.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import ROUND_CEILING, Decimal, localcontext
from typing import Any

D = Decimal
_HOUR_US = D(3_600_000_000)
_PRECISION = 128
_CLASSIFICATION = "FROZEN_FILL_ACCOUNTING_ONLY_NOT_COMPOUNDING_REPLAY"
_DEFAULT_INITIAL_RESERVE = D(10)


@dataclass
class _Tranche:
    start_us: int
    loss: Decimal
    remaining: Decimal
    creation_cycles: int
    recovery_time_us: int | None = None
    recovery_cycles: int | None = None
    new_releases_while_pending: int = 0


def _decimal(value: Any, name: str) -> Decimal:
    if isinstance(value, bool):
        raise ValueError(f"{name}_INVALID")
    try:
        result = D(str(value))
    except Exception as exc:
        raise ValueError(f"{name}_INVALID") from exc
    if not result.is_finite():
        raise ValueError(f"{name}_INVALID")
    return result


def _nearest_rank(values: Iterable[Decimal], fraction: Decimal) -> Decimal | None:
    ordered = sorted(values)
    if not ordered:
        return None
    rank = int((D(len(ordered)) * fraction).to_integral_value(rounding=ROUND_CEILING))
    return ordered[max(0, rank - 1)]


def _median(values: Iterable[Decimal]) -> Decimal | None:
    ordered = sorted(values)
    if not ordered:
        return None
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / D(2)


def _string(value: Decimal | None) -> str | None:
    return None if value is None else str(value)


def analyze_recovery(
    settlements: list[dict[str, Any]],
    funding: Decimal,
    end_us: int,
    initial_reserve: Decimal = _DEFAULT_INITIAL_RESERVE,
) -> dict[str, Any]:
    """Analyze release-loss debt and its FIFO recovery from settlement rows.

    ``funding`` is the fraction of each *positive* net profit assigned to the
    reserve.  A loss is the negative net profit of a release settlement.  The
    supplied ``reserve_consumption`` is always consumed from the effective
    reserve, independently of whether a debt is eventually recovered.

    Rows are copied before diagnostics are attached, so the source settlement
    fields (including their original string representations) remain unchanged.
    """
    if not isinstance(settlements, list):
        raise ValueError("SETTLEMENTS_INVALID")
    if isinstance(end_us, bool) or not isinstance(end_us, int) or end_us < 0:
        raise ValueError("END_US_INVALID")
    funding = _decimal(funding, "FUNDING")
    if not D(0) <= funding <= D(1):
        raise ValueError("FUNDING_OUT_OF_RANGE")
    initial_reserve = _decimal(initial_reserve, "INITIAL_RESERVE")
    if initial_reserve < 0:
        raise ValueError("INITIAL_RESERVE_NEGATIVE")

    previous_time: int | None = None
    reserve = initial_reserve
    minimum_reserve = reserve
    total_consumption = D(0)
    total_funding = D(0)
    total_loss = D(0)
    total_debt_payment = D(0)
    surplus_contributions = D(0)
    ordinary_positive_cycles = 0
    tranches: list[_Tranche] = []
    ledger: list[dict[str, Any]] = []

    with localcontext() as context:
        context.prec = _PRECISION
        for index, source in enumerate(settlements):
            if not isinstance(source, dict):
                raise ValueError("SETTLEMENT_INVALID")
            if "time_us" not in source or "release" not in source:
                raise ValueError("SETTLEMENT_FIELDS_MISSING")
            if "net_profit" not in source or "reserve_consumption" not in source:
                raise ValueError("SETTLEMENT_FIELDS_MISSING")
            raw_time = source["time_us"]
            if isinstance(raw_time, bool) or not isinstance(raw_time, int):
                raise ValueError("TIME_US_INVALID")
            time_us = raw_time
            if time_us < 0 or time_us > end_us:
                raise ValueError("TIME_US_OUT_OF_BOUNDS")
            if previous_time is not None and time_us < previous_time:
                raise ValueError("SETTLEMENTS_NOT_CHRONOLOGICAL")
            previous_time = time_us
            if not isinstance(source["release"], bool):
                raise ValueError("RELEASE_INVALID")
            net_profit = _decimal(source["net_profit"], "NET_PROFIT")
            consumption = _decimal(source["reserve_consumption"], "RESERVE_CONSUMPTION")
            if consumption < 0:
                raise ValueError("RESERVE_CONSUMPTION_NEGATIVE")

            # A new release is counted only against tranches that existed before
            # this event.  This makes overlapping-release counts deterministic.
            if source["release"]:
                for tranche in tranches:
                    if tranche.recovery_time_us is None:
                        tranche.new_releases_while_pending += 1

            contribution = max(D(0), net_profit) * funding
            loss = max(D(0), -net_profit) if source["release"] else D(0)
            is_ordinary_cycle = not source["release"] and net_profit > 0
            if is_ordinary_cycle:
                # The cycle whose positive profit pays a tranche is itself part
                # of that tranche's recovery-cycle count.
                ordinary_positive_cycles += 1
            prior_debt = sum(
                (tranche.remaining for tranche in tranches if tranche.recovery_time_us is None),
                D(0),
            )

            # Funding pays only debt that already exists.  If this is a release
            # loss, its tranche is created after this payment; earlier surplus
            # therefore cannot erase a future loss.
            payment = D(0)
            remaining_funding = contribution
            for tranche in tranches:
                if tranche.recovery_time_us is not None or remaining_funding <= 0:
                    continue
                paid = min(tranche.remaining, remaining_funding)
                tranche.remaining -= paid
                remaining_funding -= paid
                payment += paid
                if tranche.remaining == 0:
                    tranche.recovery_time_us = time_us
                    tranche.recovery_cycles = ordinary_positive_cycles - tranche.creation_cycles
            if remaining_funding > 0:
                surplus_contributions += remaining_funding
            total_funding += contribution
            total_loss += loss
            total_debt_payment += payment

            if loss > 0:
                tranches.append(
                    _Tranche(
                        start_us=time_us,
                        loss=loss,
                        remaining=loss,
                        creation_cycles=ordinary_positive_cycles,
                    )
                )

            debt_after = sum(
                (
                    tranche.remaining
                    for tranche in tranches
                    if tranche.recovery_time_us is None
                ),
                D(0),
            )
            total_consumption += consumption
            reserve += contribution - consumption
            minimum_reserve = min(minimum_reserve, reserve)

            event = dict(source)
            accounting = {
                "event_index": index,
                "reserve_before": str(reserve - contribution + consumption),
                "reserve_funding": str(contribution),
                "loss": str(loss),
                "debt_before": str(prior_debt),
                "reserve_payment_to_debt": str(payment),
                "reserve_surplus_contribution": str(remaining_funding),
                "effective_reserve": str(reserve),
                "reserve_after": str(reserve),
                "outstanding_debt": str(debt_after),
                "debt_after": str(debt_after),
                "ordinary_positive_cycle_count": ordinary_positive_cycles,
            }
            # Required/source settlement fields are authoritative.  In the
            # unlikely event a caller already uses an accounting key, preserve
            # that source field rather than silently rewriting it.
            for key, value in accounting.items():
                event.setdefault(key, value)
            ledger.append(event)

    # A tranche recovered on the final event is complete; all others are
    # right-censored at end_us.
    tranche_rows: list[dict[str, Any]] = []
    recovered_cycles: list[Decimal] = []
    recovered_hours: list[Decimal] = []
    censored_cycles: list[Decimal] = []
    for tranche in tranches:
        if tranche.recovery_time_us is not None:
            elapsed = D(tranche.recovery_time_us - tranche.start_us) / _HOUR_US
            recovery_cycles = D(tranche.recovery_cycles or 0)
            recovered_cycles.append(recovery_cycles)
            recovered_hours.append(elapsed)
            age_hours = None
            recovery_timestamp: int | None = tranche.recovery_time_us
        else:
            elapsed = None
            recovery_cycles = None
            age_hours = D(end_us - tranche.start_us) / _HOUR_US
            censored_cycles.append(D(ordinary_positive_cycles - tranche.creation_cycles))
            recovery_timestamp = None
        tranche_rows.append(
            {
                "start_time_us": tranche.start_us,
                "starttime": tranche.start_us,
                "loss": str(tranche.loss),
                "remaining": str(tranche.remaining),
                "recovery_timestamp_us": recovery_timestamp,
                "recovery_timestamp": recovery_timestamp,
                "recoverytimestamp": recovery_timestamp,
                "recovery_cycles": (
                    int(recovery_cycles) if recovery_cycles is not None else None
                ),
                "elapsed_hours": _string(elapsed),
                "elapsedhours": _string(elapsed),
                "age_hours": _string(age_hours),
                "agehours": _string(age_hours),
                "new_release_while_pending_count": tranche.new_releases_while_pending,
                "newreleasewhilependingcount": tranche.new_releases_while_pending,
            }
        )

    outstanding = sum(
        (tranche.remaining for tranche in tranches if tranche.recovery_time_us is None),
        D(0),
    )
    p90_cycles = _nearest_rank(recovered_cycles, D("0.9"))
    p90_hours = _nearest_rank(recovered_hours, D("0.9"))
    median_cycles = _median(recovered_cycles)
    median_hours = _median(recovered_hours)
    result: dict[str, Any] = {
        "classification": _CLASSIFICATION,
        "funding": str(funding),
        "funding_rate": str(funding),
        "initial_reserve": str(initial_reserve),
        "effective_reserve": str(reserve),
        "final_reserve": str(reserve),
        "minimum_reserve": str(minimum_reserve),
        "min_reserve": str(minimum_reserve),
        "total_consumption": str(total_consumption),
        "total_reserve_consumption": str(total_consumption),
        "total_funding": str(total_funding),
        "total_release_loss": str(total_loss),
        "total_debt_payment": str(total_debt_payment),
        "surplus_contributions": str(surplus_contributions),
        "outstanding_debt": str(outstanding),
        "ordinary_positive_cycle_count": ordinary_positive_cycles,
        "recovered_count": len(recovered_cycles),
        "censored_count": len(censored_cycles),
        "p90_recovery_cycles": (
            int(p90_cycles) if p90_cycles is not None else None
        ),
        "p90_recovery_hours": _string(p90_hours),
        "median_recovery_cycles": (
            int(median_cycles) if median_cycles is not None and median_cycles == int(median_cycles)
            else _string(median_cycles)
        ),
        "median_recovery_hours": _string(median_hours),
        "median_recovery_cycles_conditional_on_recovered": True,
        "median_recovery_hours_conditional_on_recovered": True,
        "recovery_cycles_cohort": "RECOVERED_ONLY",
        "recovery_hours_cohort": "RECOVERED_ONLY",
        "settlements": [dict(row) for row in settlements],
        "reserve_ledger": ledger,
        "tranches": tranche_rows,
    }
    return result


__all__ = ["analyze_recovery"]
