"""Independent auditor detects corrupted accounting and unsupported raw fills."""

import copy
import json
import runpy
import zipfile
from pathlib import Path

import pytest

AUDITOR = runpy.run_path(str(Path(__file__).parents[1] / "scripts/audit_b10_reality.py"))
FIXTURE = runpy.run_path(str(Path(__file__).with_name("test_b10_reality.py")))


@pytest.mark.parametrize("fee", ["0", "0.0001", "0.001"])
def test_independent_ledger_reconstructs_actual_kernel_and_detects_money_change(fee):
    subject = FIXTURE["engine"](fee)
    FIXTURE["buy"](subject)
    FIXTURE["sell"](subject)
    profile = {"maker_fee": fee, "taker_fee": fee}
    independent = AUDITOR["reconstruct"](iter(subject.audit), profile)
    assert independent["cash"] == subject.cash
    assert independent["reserve"] == subject.reserve
    assert independent["dust"] == subject.dust
    corrupted = copy.deepcopy(subject.audit)
    corrupted[-1]["reserve"] = "999"
    with pytest.raises(ValueError, match="reserve"):
        AUDITOR["reconstruct"](iter(corrupted), profile)


def test_independent_raw_flow_checks_real_zip_queue_and_aggressor(tmp_path):
    subject = FIXTURE["engine"]()
    FIXTURE["buy"](subject)
    FIXTURE["sell"](subject)
    ledger = AUDITOR["reconstruct"](iter(subject.audit), {"maker_fee": "0", "taker_fee": "0"})
    archive = tmp_path / "USDCUSDT-trades-1970-01-01.zip"

    def history(buy_quantity="105", buyer="True"):
        with zipfile.ZipFile(archive, "w") as stream:
            stream.writestr(
                "USDCUSDT-trades-1970-01-01.csv",
                f"11,1,{buy_quantity},105,11,{buyer},True\n23,1.001,105,105.105,23,False,True\n",
            )
        return {
            "archives": [
                {
                    "utc_date": "1970-01-01",
                    "local_path": str(archive),
                    "sha256": AUDITOR["digest"](archive),
                }
            ]
        }

    arguments = (ledger["orders"], ledger["fills"], {1, 2}, [], {}, [])
    result = AUDITOR["audit_raw_support"](history(), *arguments)
    assert result["queue_cumulative_checks"] == 2
    assert result["raw_source_ids_found"] == 2
    with pytest.raises(ValueError, match="QUEUE_CLEARANCE"):
        AUDITOR["audit_raw_support"](history(buy_quantity="100"), *arguments)
    with pytest.raises(ValueError, match=r"QUEUE_CLEARANCE|AGGRESSOR"):
        AUDITOR["audit_raw_support"](history(buyer="False"), *arguments)


def test_auditor_streams_jsonl_without_loading_trace_array(tmp_path):
    subject = FIXTURE["engine"]()
    FIXTURE["buy"](subject)
    FIXTURE["sell"](subject)
    path = tmp_path / "execution-audit.jsonl"
    path.write_text("".join(json.dumps(row, default=str) + "\n" for row in subject.audit))
    result = AUDITOR["reconstruct"](
        AUDITOR["iter_rows"](path), {"maker_fee": "0", "taker_fee": "0"}
    )
    assert len(result["settlements"]) == 1
    assert result["cash"] == subject.cash
