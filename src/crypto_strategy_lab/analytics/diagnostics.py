from __future__ import annotations

from collections import Counter, defaultdict
from decimal import Decimal
from statistics import mean
from typing import Any

from crypto_strategy_lab.analytics.schemas import (
    CostBreakdownReport,
    ReportProvenance,
    TurnoverDiagnosticReport,
)
from crypto_strategy_lab.domain import canonical_hash
from crypto_strategy_lab.ml.evaluation import EvaluationResult

SMOKE_WARNING = (
    "SMOKE/DIAGNOSTIC ONLY: the policy is insufficiently trained and this report is not "
    "evidence of profitability or permission to trade. LOCKED_TEST was not accessed."
)


def build_turnover_diagnostic(
    result: EvaluationResult,
    costless_result: EvaluationResult,
    *,
    provenance: ReportProvenance,
    market_return_percent: dict[str, Decimal],
    initial_equity: Decimal = Decimal("80"),
) -> TurnoverDiagnosticReport:
    transitions = result.transitions
    fills = [fill for item in transitions for fill in item["fills"]]
    buys = sum(fill["side"] == "BUY" for fill in fills)
    sells = sum(fill["side"] == "SELL" for fill in fills)
    rotations = sum(
        len(item["fills"]) == 2 and [fill["side"] for fill in item["fills"]] == ["SELL", "BUY"]
        for item in transitions
    )
    operations = sum(bool(item["fills"]) for item in transitions)
    fees = _sum_transition(transitions, "fee_usdt")
    spread = _sum_transition(transitions, "spread_cost_usdt")
    slippage = _sum_transition(transitions, "slippage_cost_usdt")
    direct_costs = fees + spread + slippage
    cost_loss = costless_result.final_equity_usdt - result.final_equity_usdt
    per_asset_costs: dict[str, Decimal] = defaultdict(Decimal)
    per_asset_pnl: dict[str, Decimal] = defaultdict(Decimal)
    for fill in fills:
        symbol = str(fill["symbol"])
        per_asset_costs[symbol] += sum(
            Decimal(str(fill[key])) for key in ("fee", "spread_cost", "slippage_cost")
        )
        per_asset_pnl[symbol] += Decimal(str(fill["realized_pnl"]))

    conservation_errors = []
    for item in transitions:
        portfolio = item["portfolio"]
        equity = Decimal(str(item["equity_usdt"]))
        reconstructed = Decimal(str(portfolio["usdt"])) + Decimal(
            str(item["marked_asset_value_usdt"])
        )
        conservation_errors.append(abs(equity - reconstructed))

    reasons = Counter(
        str(item["avoided_operation_reason"])
        for item in transitions
        if item.get("avoided_operation_reason")
    )
    durations = _position_durations(transitions)
    exposure = [
        Decimal(str(item["marked_asset_value_usdt"])) / Decimal(str(item["equity_usdt"]))
        if Decimal(str(item["equity_usdt"])) > 0
        else Decimal("0")
        for item in transitions
    ]
    max_drawdown = max((Decimal(str(item["drawdown"])) for item in transitions), default=Decimal(0))
    ruin_reason = _ruin_reason(result, costless_result, initial_equity)
    costs = CostBreakdownReport(
        initial_equity_usdt=str(initial_equity),
        final_equity_usdt=str(result.final_equity_usdt),
        costless_final_equity_usdt=str(costless_result.final_equity_usdt),
        market_return_percent={key: str(value) for key, value in market_return_percent.items()},
        gross_pnl_usdt=str(costless_result.final_equity_usdt - initial_equity),
        net_pnl_usdt=str(result.final_equity_usdt - initial_equity),
        loss_exclusively_from_costs_usdt=str(cost_loss),
        direct_fees_usdt=str(fees),
        direct_spread_usdt=str(spread),
        direct_slippage_usdt=str(slippage),
        direct_costs_usdt=str(direct_costs),
        reconciliation_difference_usdt=str(cost_loss - direct_costs),
        conservation_error_usdt=str(max(conservation_errors, default=Decimal(0))),
        per_asset_realized_pnl_usdt={
            key: str(value) for key, value in sorted(per_asset_pnl.items())
        },
        per_asset_costs_usdt={key: str(value) for key, value in sorted(per_asset_costs.items())},
        ruin_reason=ruin_reason,
    )
    identity: dict[str, Any] = {
        "provenance": provenance.model_dump(mode="json"),
        "actions": result.actions,
        "transition_hash": canonical_hash(transitions),
    }
    return TurnoverDiagnosticReport(
        run_id=canonical_hash(identity)[:16],
        provenance=provenance,
        costs=costs,
        buys=buys,
        sells=sells,
        rotations=rotations,
        operations=operations,
        avoided_operations=dict(sorted(reasons.items())),
        total_turnover=str(_sum_transition(transitions, "turnover")),
        average_position_duration_steps=str(mean(durations) if durations else 0),
        average_exposure_ratio=str(mean(exposure) if exposure else 0),
        time_in_usdt_ratio=str(
            Decimal(sum(item["position"] == "USDT" for item in transitions))
            / Decimal(len(transitions))
            if transitions
            else Decimal("1")
        ),
        max_drawdown=str(max_drawdown),
        terminated=result.terminated,
        truncated=result.truncated,
        warning=SMOKE_WARNING,
        transitions=transitions,
    )


def _sum_transition(transitions: list[dict[str, Any]], key: str) -> Decimal:
    return sum((Decimal(str(item[key])) for item in transitions), Decimal("0"))


def _position_durations(transitions: list[dict[str, Any]]) -> list[int]:
    durations: list[int] = []
    current: str | None = None
    length = 0
    for item in transitions:
        position = str(item["position"])
        if position == current and position != "USDT":
            length += 1
        else:
            if current not in {None, "USDT"}:
                durations.append(length)
            current = position
            length = 1 if position != "USDT" else 0
    if current not in {None, "USDT"}:
        durations.append(length)
    return durations


def _ruin_reason(
    result: EvaluationResult, costless: EvaluationResult, initial_equity: Decimal
) -> str | None:
    if not result.terminated:
        return None
    threshold = initial_equity * Decimal("0.20")
    if costless.final_equity_usdt > threshold:
        return "COST_AMPLIFIED_TURNOVER"
    return "MARKET_AND_POLICY"
