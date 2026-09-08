"""Report rendering uses explicit frozen-fill labels and includes censoring."""

from decimal import Decimal as D

from crypto_strategy_lab.microstructure.reserve_recovery_diagnostics import analyze_recovery
from scripts.analyze_reserve_rotation import FUNDING, render


def test_report_exposes_censoring_not_just_recovered_average():
    rows = [
        {"time_us": 1, "release": True, "net_profit": "-.03", "reserve_consumption": ".03"},
        {"time_us": 2, "release": False, "net_profit": ".01", "reserve_consumption": "0"},
    ]
    summary = {
        "RESERVE_CONSUMPTION": ".03",
        "RELEASES": 1,
        "NET_POSITIVE_CYCLES": 1,
        "RESERVE_FINAL": "9.971",
        "TOTAL_EQUITY": "109.98",
    }
    run = {
        "summary": summary,
        "positive_profit_total": ".01",
        "two_hour_violations": 1,
        "daily_positive_cycles": [1] + [0] * 11,
        "positions": [],
        "recovery_sensitivity": {f: analyze_recovery(rows, D(f), 3) for f in FUNDING},
    }
    html = render({"runs": {"CONTROL": run}})
    assert "não é novo replay composto" in html
    assert "Dívida aberta USDT" in html and "0 / 1" in html
    assert "somente dos releases quitados" in html
    assert "Dia 12" in html and "0.02200" in html
