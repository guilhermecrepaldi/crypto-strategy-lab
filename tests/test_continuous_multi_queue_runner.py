"""Mechanical gates for the M013 two-stage runner; no market data or engine run."""

import hashlib
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest

from crypto_strategy_lab.microstructure.serial_replay import EVENT_ORDER_SCALE, _datetime_to_micros
from scripts import run_continuous_multi_queue as runner


def design():
    return json.loads(runner.SPEC.read_text(encoding="utf-8"))


@pytest.mark.parametrize("mode", ["prepare", "run", "extend"])
def test_retired_m013_cannot_prepare_run_or_extend_before_touching_data(tmp_path, mode):
    target = tmp_path / "untouched"
    with pytest.raises(ValueError, match="M013_RETIRED_TECHNICAL"):
        if mode == "prepare":
            runner.prepare_only(target)
        else:
            runner.run(target, extend=mode == "extend")
    assert not target.exists()


def score(**updates):
    result = {
        "RUN_STATUS": "COMPLETE",
        "STAGE": "STAGE_1",
        "RUN_ID": "run",
        "CHECKPOINT_SHA256": "checkpoint",
        "MODEL_HASH": "model",
        "CALENDAR_DAYS_PROCESSED": 151,
        "SIMULATION_TIMESTAMP": "2026-06-01T00:00:00+00:00",
        "ACCOUNTING_VIOLATIONS": 0,
        "FUTURE_LEAKAGE_EVENTS": 0,
        "LIQUIDITY_DUPLICATION_EVENTS": 0,
        "MOTOR_UPTIME": "0.995",
        "CAPITAL_WEIGHTED_UPTIME": "0.90",
        "DEPLOYABLE_CAPITAL_WEIGHTED_UPTIME": "0.99",
        "FULL_STOP_DAYS": 0,
        "ZERO_CYCLE_DAYS": 0,
        "MAX_OPERATING_HOLD_HOURS": "24",
        "MAX_ACTIVE_RESERVE_HOLD_HOURS": "6",
        "HARD_LOCK_VIOLATIONS": 0,
        "RESERVE_MIN": "1",
        "RESERVE_DEPLETION_EVENTS": 0,
        "TOTAL_EQUITY": "111",
        "NET_REALIZED_PNL": "1",
        "CORE_RESERVE_VIOLATIONS": 0,
        "OPERATING_RESTORATION_VIOLATIONS": 0,
        "RESERVE_CONSUMPTION": "1",
        "RESERVE_SELF_SUSTAINABILITY_RATIO": "1",
        "ACTIVE_RESERVE_PROFIT": "0",
        "ACTIVE_RESERVE_LOSSES": "0",
        "ACTIVE_RESERVE_NET_PNL": "0",
    }
    result.update(updates)
    return result


def audit(**updates):
    result = {
        "status": "PASS",
        "run_id": "run",
        "checkpoint_sha256": "checkpoint",
        "model_hash": "model",
        "execution_evidence_sufficient": True,
        "ordinary_samples": 100,
        "all_release_events_audited": True,
        "all_active_reserve_fills_audited": True,
        "all_traded_queues_represented": True,
    }
    result.update(updates)
    return result


def test_stage1_decision_states():
    assert runner.stage1_decision({"RUN_STATUS": "RUNNING"}, {}) == "PENDING"
    assert runner.stage1_decision(score(), audit(), design=design()) == "PASS_TO_EXTENSION"
    assert runner.stage1_decision(score(NET_REALIZED_PNL="-1"), audit(), design=design()) == "FAIL"
    assert (
        runner.stage1_decision(score(NET_REALIZED_PNL="NaN"), audit(), design=design())
        == "INCONCLUSIVE"
    )
    assert (
        runner.stage1_decision(score(), audit(ordinary_samples=99), design=design())
        == "INCONCLUSIVE"
    )
    assert (
        runner.stage1_decision(score(ACCOUNTING_VIOLATIONS=1), audit(), design=design())
        == "INCONCLUSIVE"
    )
    incomplete = score()
    incomplete.pop("TOTAL_EQUITY")
    assert runner.stage1_decision(incomplete, audit(), design=design()) == "INCONCLUSIVE"
    assert (
        runner.stage1_decision(score(RESERVE_CONSUMPTION="0"), audit(), design=design())
        == "PASS_TO_EXTENSION"
    )
    assert (
        runner.stage1_decision(
            score(
                RESERVE_CONSUMPTION="0",
                ACTIVE_RESERVE_LOSSES="1",
                ACTIVE_RESERVE_NET_PNL="-1",
                RESERVE_SELF_SUSTAINABILITY_RATIO="0",
            ),
            audit(),
            design=design(),
        )
        == "FAIL"
    )


def test_extension_artifacts_bind_checkpoint_and_require_audit_sample_floor(tmp_path):
    folder = tmp_path
    checkpoint = folder / "stage1-final-checkpoint.json"
    checkpoint.write_text("{}", encoding="utf-8")
    final = score(CHECKPOINT_SHA256=hashlib.sha256(b"{}").hexdigest())
    (folder / "capital-checkpoints").mkdir()
    (folder / "capital-checkpoints" / "FINAL_5_MONTH.json").write_text(
        json.dumps(final), encoding="utf-8"
    )
    (folder / "stage1-independent-audit.json").write_text(
        json.dumps(audit(ordinary_samples=99)), encoding="utf-8"
    )
    with pytest.raises(ValueError, match="SEALED_EXTENSION_GATE_CLOSED"):
        runner.validate_extension_artifacts(folder)
    final["CHECKPOINT_SHA256"] = "0" * 64
    (folder / "capital-checkpoints" / "FINAL_5_MONTH.json").write_text(
        json.dumps(final), encoding="utf-8"
    )
    with pytest.raises(ValueError, match="STAGE_1_FINAL_CHECKPOINT_BINDING_MISMATCH"):
        runner.validate_extension_artifacts(folder)


def test_same_timestamp_ordinal_is_causal_and_mismatch_rejected():
    stamp = datetime(2026, 1, 1, tzinfo=UTC)
    base = _datetime_to_micros(stamp) * EVENT_ORDER_SCALE
    tape = SimpleNamespace(
        events=[base, base + 1], price_ticks=[100, 100], tick_size=Decimal("0.01")
    )
    event = SimpleNamespace(timestamp=stamp, price=Decimal("1.00"))
    runner.assert_raw_matches(tape, 1, event, ordinal=1)
    with pytest.raises(ValueError, match="RAW_FLOW_CANONICAL_PRICE_TAPE_MISMATCH"):
        runner.assert_raw_matches(tape, 1, event, ordinal=2)


def test_prefix_archives_rejects_crossing_june(monkeypatch):
    item = SimpleNamespace(first_timestamp=runner.WARMUP_START, last_timestamp=runner.STAGE_1_END)
    monkeypatch.setattr(
        "crypto_strategy_lab.microstructure.data.select_history_archives",
        lambda *args, **kwargs: (item,),
    )
    with pytest.raises(ValueError, match="ARCHIVE_CROSSES_SEALED_BOUNDARY"):
        runner.prefix_archives(SimpleNamespace())


def test_real_stream_path_saves_all_boundaries_before_trade_and_never_opens_extension(
    tmp_path,
    monkeypatch,
):
    times = [
        runner.START + timedelta(days=1),
        runner.START + timedelta(days=60),
        runner.STAGE_1_END - timedelta(microseconds=1),
    ]
    tape = SimpleNamespace(
        events=[_datetime_to_micros(t) * EVENT_ORDER_SCALE for t in times],
        price_ticks=[100, 100, 100],
        tick_size=Decimal("0.01"),
    )
    calls = []

    def history_reader(history, *, start, end_exclusive):
        calls.append((start, end_exclusive))
        assert end_exclusive <= runner.STAGE_1_END
        for index, stamp in enumerate(times):
            if start <= stamp < end_exclusive:
                yield SimpleNamespace(
                    timestamp=stamp,
                    trade_id=index,
                    price=Decimal(1),
                    quantity=Decimal(1),
                    buyer_is_maker=True,
                )

    monkeypatch.setattr("crypto_strategy_lab.microstructure.data.iter_history", history_reader)

    class Replay:
        def __init__(self):
            self.audit = []
            self.processed_trades = 0
            self.last_us = _datetime_to_micros(runner.START)
            self.completed = False

        def step(self, trade):
            self.last_us = trade.time_us
            self.processed_trades += 1

        def advance_to(self, boundary):
            self.audit.append({"event": "TIMER_ONLY", "time_us": boundary})

        def checkpoint(self):
            return {"payload": {"count": self.processed_trades}, "sha256": "fixture"}

        def metrics(self, as_of_us=None):
            stamp = self.last_us if as_of_us is None else as_of_us
            return {
                "SIMULATION_TIMESTAMP": (
                    datetime(1970, 1, 1, tzinfo=UTC) + timedelta(microseconds=stamp)
                ).isoformat(),
                "RUN_STATUS": "COMPLETE" if self.completed else "RUNNING",
                "TOTAL_EQUITY": str(110 + self.processed_trades),
                "OPERATING_CAPITAL": "100",
                "RECOVERY_RESERVE": "10",
            }

        def finish(self):
            assert self.processed_trades == 3
            self.completed = True

    identity = {
        "stage": "STAGE_1",
        "run_hash": "fixture",
        "model_hash": "model",
        "published_config_sha": "source",
    }
    runner.stream_stage(None, tape, 0, Replay(), identity, tmp_path)
    for days, expected in ((1, 0), (7, 1), (30, 1), (60, 1), (90, 2), (120, 2)):
        checkpoint = json.loads(
            (tmp_path / "capital-checkpoints" / f"DAY_{days}.json").read_bytes()
        )
        assert checkpoint["PROCESSED_TRADES"] == expected
    final = json.loads((tmp_path / "capital-checkpoints" / "FINAL_5_MONTH.json").read_bytes())
    assert final["PROCESSED_TRADES"] == 3
    assert final["RUN_STATUS"] == "COMPLETE"
    assert final["MONTH_CLOSED"] == "2026-05"
    for month, reason, count in (
        ("01", "MONTH_2026-01", 1),
        ("02", "MONTH_2026-02", 1),
        ("03", "DAY_90", 2),
        ("04", "DAY_120", 2),
    ):
        close = json.loads((tmp_path / "capital-checkpoints" / f"{reason}.json").read_bytes())
        assert close["MONTH_CLOSED"] == f"2026-{month}"
        assert close["PROCESSED_TRADES"] == count
    assert (
        hashlib.sha256((tmp_path / "stage1-final-checkpoint.json").read_bytes()).hexdigest()
        == (final["CHECKPOINT_SHA256"])
    )
    assert calls == [(runner.WARMUP_START, runner.START), (runner.START, runner.STAGE_1_END)]
