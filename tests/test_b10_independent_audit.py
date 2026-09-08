"""Independent auditor detects corrupted accounting and unsupported raw fills."""

import copy
import json
import runpy
import zipfile
from decimal import Decimal as D
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


def test_owner_reserve_reconstructs_from_100_plus_10_and_funds_ten_percent():
    subject = FIXTURE["engine"](reserve="10")
    FIXTURE["buy"](subject)
    FIXTURE["sell"](subject)
    rows = copy.deepcopy(subject.audit)
    settlement = rows[-1]
    settlement.update({"reserve": "10.01000", "cash": "100.09000", "reserve_transfer": "0.01000"})
    ledger = AUDITOR["reconstruct"](
        iter(rows), {"maker_fee": "0", "taker_fee": "0"}, owner_reserve=True
    )
    assert ledger["reserve"] == D("10.01000")
    assert ledger["cash"] == D("100.09000")


def test_m014_wrapper_rejects_score_manifest_identity_before_ledger(tmp_path):
    folder = tmp_path / "m014"
    folder.mkdir()
    (folder / "execution-audit.jsonl").write_text("", encoding="utf-8")
    (folder / "checkpoint.json").write_text("{}", encoding="utf-8")
    (folder / "run-manifest.json").write_text(
        json.dumps(
            {
                "model_id": "M014",
                "model_hash": "model",
                "run_hash": "run",
                "capital_mode": "COMPOUNDING",
                "profile_config_sha256": "profile",
            }
        ),
        encoding="utf-8",
    )
    score = {
        "MODEL_ID": "M014",
        "MODEL_HASH": "wrong",
        "RUN_ID": "run",
        "CAPITAL_MODE": "COMPOUNDING",
        "RUN_STATUS": "COMPLETE",
        "PROFILE_CONFIG_SHA256": "profile",
    }
    (folder / "scoreboard.json").write_text(json.dumps(score), encoding="utf-8")
    config = tmp_path / "config.json"
    config.write_text(json.dumps({}), encoding="utf-8")
    with pytest.raises(ValueError, match="MODEL_HASH_IDENTITY_MISMATCH"):
        AUDITOR["audit_m014"](config, folder)


def test_m014_wrapper_real_checkpoint_shape_and_balance_gate(tmp_path):
    from dataclasses import asdict

    from test_b10_reserve_weekly import replay

    value, _ = replay()
    folder = tmp_path / "run"
    folder.mkdir()
    history = tmp_path / "history.json"
    history.write_text('{"archives": []}')
    config = tmp_path / "profile.json"
    profile = asdict(value.engine.profile)
    profile["name"] = "B_REALISTIC_CONSERVATIVE"
    from dataclasses import replace
    value.engine.profile = replace(value.engine.profile, name=profile["name"])
    config.write_text(json.dumps({
        "profiles": [{"profile": profile, "envelope": asdict(value.envelope)}],
        "history_manifest": str(history), "history_manifest_sha256": AUDITOR["digest"](history),
        "rules": [],
    }, default=str))
    value.identity.update(model_hash="model", run_hash="run",
                          profile_config_sha256=AUDITOR["digest"](config))
    (folder / "run-manifest.json").write_text(json.dumps(value.identity))
    trace = folder / "execution-audit.jsonl"
    trace.write_bytes(b"")
    binding = {"bytes": 0, "sha256": AUDITOR["digest"](trace)}
    checkpoint = folder / "checkpoint.json"
    checkpoint.write_text(json.dumps({"replay": value.checkpoint(), "audit": binding}))
    score = value.metrics()
    score.update(MODEL_HASH="model", RUN_ID="run", RUN_STATUS="COMPLETE",
                 CHECKPOINT_SHA256=AUDITOR["digest"](checkpoint), AUDIT_PREFIX=binding)
    (folder / "scoreboard.json").write_text(json.dumps(score))
    result = AUDITOR["audit_m014"](config, folder)
    assert result["ordinary_audited_raw"] == 0
    assert "fewer than 100" in result["limitations"][-1]
    score["OPERATING_BANK"] = "99"
    (folder / "scoreboard.json").write_text(json.dumps(score))
    with pytest.raises(ValueError, match="OPERATING_BANK"):
        AUDITOR["audit_m014"](config, folder)
