from __future__ import annotations

from decimal import Decimal
from statistics import median
from typing import Any

from crypto_strategy_lab.analytics.schemas import LearningGateReport

SURVIVAL_NO_EDGE = "SURVIVAL LEARNED — NO TRADING EDGE"


def classify_learning_gates(
    runs: list[dict[str, Any]],
    baselines: list[dict[str, Any]],
    *,
    technical_complete: bool,
) -> LearningGateReport:
    reasons: dict[str, list[str]] = {"technical": [], "survival": [], "value": []}
    technical = "PASS" if technical_complete else "FAIL"
    if not technical_complete:
        reasons["technical"].append("training/checkpoint/reproducibility gate incomplete")
    if not runs:
        return LearningGateReport(
            technical=technical,
            survival="PENDING",
            value="PENDING",
            classification="NO VALIDATION EVIDENCE",
            reasons=reasons,
        )
    survival_count = sum(not item["ruined"] for item in runs)
    turnover_median = median(Decimal(str(item["turnover"])) for item in runs)
    costs_median = median(Decimal(str(item["costs_usdt"])) for item in runs)
    survival_pass = (
        survival_count > len(runs) / 2
        and turnover_median < Decimal("1000")
        and costs_median < Decimal("40")
    )
    survival = "PASS" if survival_pass else "FAIL"
    if survival_count <= len(runs) / 2:
        reasons["survival"].append("a maioria das seeds não sobreviveu")
    if turnover_median >= 1000:
        reasons["survival"].append("turnover mediano não ficou abaixo do smoke original")
    if costs_median >= 40:
        reasons["survival"].append("custos medianos ainda dominam metade do capital inicial")
    returns = [Decimal(str(item["return_percent"])) for item in runs]
    cash_returns = [
        Decimal(str(item["return_percent"])) for item in baselines if item["policy"] == "cash"
    ] or [Decimal("0")]
    agent_median = median(returns)
    cash_median = median(cash_returns)
    usdt_median = median(Decimal(str(item["time_in_usdt_ratio"])) for item in runs)
    non_cash_baselines = [
        Decimal(str(item["return_percent"])) for item in baselines if item["policy"] != "cash"
    ]
    baseline_median = median(non_cash_baselines) if non_cash_baselines else cash_median
    stable = max(returns) - min(returns) <= Decimal("30")
    value_pass = (
        survival_pass
        and agent_median > cash_median
        and agent_median >= baseline_median
        and stable
        and usdt_median < Decimal("0.95")
    )
    value = "PASS" if value_pass else "FAIL"
    if agent_median <= cash_median:
        reasons["value"].append("retorno mediano não superou caixa")
    if agent_median < baseline_median:
        reasons["value"].append("retorno mediano não superou os baselines não-caixa")
    if not stable:
        reasons["value"].append("dispersão entre seeds excedeu 30 pontos percentuais")
    if usdt_median >= Decimal("0.95"):
        reasons["value"].append("política permaneceu pelo menos 95% do tempo em USDT")
    classification = (
        "TRADING EDGE CANDIDATE"
        if value_pass
        else SURVIVAL_NO_EDGE
        if survival_pass and usdt_median >= Decimal("0.95")
        else "SURVIVAL WITHOUT VALIDATED VALUE"
        if survival_pass
        else "SURVIVAL GATE FAILED"
    )
    return LearningGateReport(
        technical=technical,
        survival=survival,
        value=value,
        classification=classification,
        reasons=reasons,
    )
