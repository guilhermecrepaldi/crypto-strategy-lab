import runpy
from pathlib import Path

import pytest

SUMMARIZE = runpy.run_path(
    str(Path(__file__).parents[1] / "scripts/report_b10_opportunity_funnel.py")
)["summarize"]


def test_order_funnel_does_not_fabricate_original_cycle_mapping():
    rows = [
        {"kind": "SUBMIT", "order_id": 1, "side": "BUY", "release": False, "quantity": "100"},
        {"kind": "ORDER_ACTIVE", "order_id": 1},
        {"kind": "QUEUE_FLOW", "order_id": 1, "queue_after": "0"},
        {"kind": "FILL", "order_id": 1, "quantity": "100"},
        {"kind": "SUBMIT", "order_id": 2, "side": "SELL", "release": False, "quantity": "100"},
        {"kind": "ORDER_ACTIVE", "order_id": 2},
        {"kind": "QUEUE_FLOW", "order_id": 2, "queue_after": "0"},
        {"kind": "FILL", "order_id": 2, "quantity": "100"},
        {"kind": "SETTLEMENT", "release": False, "net_profit": "-0.01"},
    ]
    board = {"FULLY_FILLED_CYCLES": 1, "NET_POSITIVE_CYCLES": 0, "EXECUTION_PROFILE": "FIXTURE"}
    result = SUMMARIZE(iter(rows), 3580880, board)
    assert result["Q1_aggregate_full_fill_cycles"] == 1
    assert result["net_positive_cycles"] == 0
    assert result["actual_order_funnels"]["BUY"]["full_fill"] == 1
    assert result["original_opportunity_mapping"]["original_buy_full"] is None
    assert "NOT AN IDENTIFIED" in result["ratio_semantics"]
    with pytest.raises(ValueError, match="CYCLE_MISMATCH"):
        SUMMARIZE(iter(rows), 3580880, {**board, "FULLY_FILLED_CYCLES": 2})
