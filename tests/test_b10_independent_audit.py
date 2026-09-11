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


@pytest.mark.parametrize(
    "buy,sell,queue,expected",
    [
        ("0", "0", "100", 1),
        ("1000", "199", "100", 2),
        ("334635375", "380627166", "2330544", 144),
        ("239063710", "289157032", "2330544", 103),
    ],
)
def test_passive_bound_allows_carry_in_and_ignores_own_size(buy, sell, queue, expected):
    assert AUDITOR["passive_cycle_upper_bound"](buy, sell, queue) == expected


def test_passive_bound_rejects_invalid_queue():
    with pytest.raises(ValueError, match="INVALID_PASSIVE_CAPACITY_INPUT"):
        AUDITOR["passive_cycle_upper_bound"]("100", "100", "0")


@pytest.mark.parametrize(
    "buy,sell,queue,bid_down,ask_up,expected",
    [
        ("0", "0", "100", 0, 0, 1),
        ("1000", "199", "100", 1, 0, 2),
        ("334635375", "380627166", "2330544", 35, 33, 179),
    ],
)
def test_priority_capacity_bound_counts_asymmetric_quote_movements(
    buy, sell, queue, bid_down, ask_up, expected
):
    assert AUDITOR["priority_capacity_upper_bound"](buy, sell, queue, bid_down, ask_up) == expected


def test_priority_capacity_boundary_carry_is_one_relaxation():
    assert AUDITOR["priority_capacity_upper_bound"]("100", "100", "100", 1, 0) == 2
    assert AUDITOR["hybrid_priority_capacity_upper_bound"]("100", "100", "100", 1, 0) == 3


def test_priority_capacity_hybrid_bound_adds_disjoint_quote_moves():
    assert (
        AUDITOR["hybrid_priority_capacity_upper_bound"]("334635375", "380627166", "2330544", 35, 33)
        == 212
    )


@pytest.mark.parametrize(
    "args,error",
    [
        (("NaN", "1", "1", 0, 0), "INVALID_PRIORITY_CAPACITY_INPUT"),
        (("1", "1", "0", 0, 0), "INVALID_PRIORITY_CAPACITY_INPUT"),
        (("1", "1", "1", -1, 0), "INVALID_PRIORITY_CAPACITY_MOVEMENT_COUNT"),
        (("1", "1", "1", 0, True), "INVALID_PRIORITY_CAPACITY_MOVEMENT_COUNT"),
    ],
)
def test_priority_capacity_rejects_invalid_inputs(args, error):
    with pytest.raises(ValueError, match=error):
        AUDITOR["priority_capacity_upper_bound"](*args)


def test_priority_quote_reconstructs_one_tick_spread():
    quote = AUDITOR["_priority_book_quote"](D("1.00015"), D("0.0001"), False, D("0.000005"))
    assert quote == (D("1.0001"), D("1.0002"))
    assert (quote[1] - quote[0]) / D("0.0001") == 1


@pytest.mark.parametrize(
    "fault,expected",
    [
        ("spread", "SPREAD_NOT_ONE_TICK"),
        ("grid", "RAW_PRICE_OFF_GRID"),
        ("time", "TIME_REGRESSION"),
        ("rebate", "NONNEGATIVE_FEES_REQUIRED"),
        ("symbol", "USDCUSDT_TRADES_REQUIRED"),
    ],
)
def test_priority_diagnostic_fails_closed_when_bound_premises_break(tmp_path, fault, expected):
    start = 1767225600000000
    archives = []
    for day in range(1, 8):
        path = tmp_path / f"day-{day}.zip"
        price = "1.00015" if fault == "grid" else "1.0001"
        stamp = start if fault == "time" else start + 2
        payload = f"1,{price},100,100,{start + 1},true,true\n"
        payload += f"2,1.0001,100,100,{stamp},true,true\n"
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("trades.csv", payload if day == 1 else "")
        archives.append(
            {
                "utc_date": f"2026-01-{day:02}",
                "local_path": str(path),
                "sha256": AUDITOR["digest"](path),
            }
        )
    history = tmp_path / "history.json"
    history.write_text(
        json.dumps(
            {
                "symbol": "WRONG" if fault == "symbol" else "USDCUSDT",
                "kind": "trades",
                "archives": archives,
            }
        )
    )
    config = tmp_path / "config.json"
    config.write_text(
        json.dumps(
            {
                "history_manifest": str(history),
                "history_manifest_sha256": AUDITOR["digest"](history),
                "profiles": [
                    {
                        "profile": {
                            "name": "B_REALISTIC_CONSERVATIVE",
                            "queue_ahead": "100",
                            "maker_fee": "-0.001" if fault == "rebate" else "0",
                            "taker_fee": "0",
                        },
                        "envelope": {"half_spread": "0.0001" if fault == "spread" else "0.000005"},
                    }
                ],
                "rules": [
                    {
                        "start_us": start,
                        "end_us": start + 7 * 86400000000,
                        "rule": {"tick_size": "0.0001"},
                    }
                ],
            }
        )
    )
    with pytest.raises(ValueError, match=expected):
        AUDITOR["audit_priority_capacity_week1"](config)


def test_priority_independent_audit_partial_then_equal_and_own_limit(tmp_path):
    from test_priority_trade_through import engine

    from crypto_strategy_lab.microstructure.b10_reality import Trade

    value = engine()
    value._advance(11)
    value.trade(Trade(12, 2, D(".9998"), D(30), True))
    value.trade(Trade(13, 3, D(1), D(70), True))
    value.submit("SELL", D("1.001"), 14)
    value._advance(25)
    value.trade(Trade(26, 4, D("1.002"), D(100), False))
    profile = {"maker_fee": "0", "taker_fee": "0"}
    ledger = AUDITOR["reconstruct"](
        iter(value.audit), profile, owner_reserve=True, price_priority=True
    )
    assert ledger["cash"] == value.cash == D("100.09")
    assert ledger["reserve"] == value.reserve == D("10.01")
    assert len(ledger["priority_inferences"]) == 2
    with pytest.raises(ValueError, match="INVALID_PRICE_PRIORITY_ACTIVATION"):
        AUDITOR["reconstruct"](iter(value.audit), profile, owner_reserve=True)
    archive = tmp_path / "trades.zip"
    with zipfile.ZipFile(archive, "w") as zipped:
        zipped.writestr(
            "trades.csv",
            "2,.9998,30,29.994,12,true,true\n"
            "3,1,70,70,13,true,true\n4,1.002,100,100.2,26,false,true\n",
        )
    history = {
        "archives": [
            {
                "utc_date": "1970-01-01",
                "local_path": str(archive),
                "sha256": AUDITOR["digest"](archive),
            }
        ]
    }
    support = AUDITOR["audit_raw_support"](
        history,
        ledger["orders"],
        ledger["fills"],
        {1, 2},
        [],
        {},
        [],
        priority_inferences=ledger["priority_inferences"],
    )
    assert support["raw_source_ids_found"] == 3
    bad = copy.deepcopy(value.audit)
    next(row for row in bad if row["kind"] == "PRICE_THROUGH_PRIORITY_INFERENCE")[
        "activation_evaluated_us"
    ] = 12
    with pytest.raises(ValueError, match="INVALID_PRICE_PRIORITY_ACTIVATION"):
        AUDITOR["reconstruct"](iter(bad), profile, owner_reserve=True, price_priority=True)
    impossible = copy.deepcopy(value.audit)
    next(row for row in impossible if row["kind"] == "ORDER_ACTIVE")["evaluated_at_us"] = -999
    next(row for row in impossible if row["kind"] == "PRICE_THROUGH_PRIORITY_INFERENCE")[
        "activation_evaluated_us"
    ] = -999
    with pytest.raises(ValueError, match="IMPOSSIBLE_ORDER_ACTIVATION_TIMESTAMP"):
        AUDITOR["reconstruct"](iter(impossible), profile, owner_reserve=True, price_priority=True)
    first_inference = next(
        i for i, row in enumerate(value.audit) if row["kind"] == "PRICE_THROUGH_PRIORITY_INFERENCE"
    )
    with pytest.raises(ValueError, match="ORPHAN_PRICE_PRIORITY_INFERENCE"):
        AUDITOR["reconstruct"](
            iter(value.audit[: first_inference + 1]),
            profile,
            owner_reserve=True,
            price_priority=True,
        )


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
    config.write_text(
        json.dumps(
            {
                "profiles": [{"profile": profile, "envelope": asdict(value.envelope)}],
                "history_manifest": str(history),
                "history_manifest_sha256": AUDITOR["digest"](history),
                "rules": [],
            },
            default=str,
        )
    )
    value.identity.update(
        model_hash="model", run_hash="run", profile_config_sha256=AUDITOR["digest"](config)
    )
    (folder / "run-manifest.json").write_text(json.dumps(value.identity))
    trace = folder / "execution-audit.jsonl"
    trace.write_bytes(b"")
    binding = {"bytes": 0, "sha256": AUDITOR["digest"](trace)}
    checkpoint = folder / "checkpoint.json"
    checkpoint.write_text(json.dumps({"replay": value.checkpoint(), "audit": binding}))
    score = value.metrics()
    score.update(
        MODEL_HASH="model",
        RUN_ID="run",
        RUN_STATUS="COMPLETE",
        CHECKPOINT_SHA256=AUDITOR["digest"](checkpoint),
        AUDIT_PREFIX=binding,
    )
    (folder / "scoreboard.json").write_text(json.dumps(score))
    result = AUDITOR["audit_m014"](config, folder)
    assert result["ordinary_audited_raw"] == 0
    assert "fewer than 100" in result["limitations"][-1]
    score["OPERATING_BANK"] = "99"
    (folder / "scoreboard.json").write_text(json.dumps(score))
    with pytest.raises(ValueError, match="OPERATING_BANK"):
        AUDITOR["audit_m014"](config, folder)
