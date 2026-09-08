import hashlib
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest

from crypto_strategy_lab.ml.model_registry import compute_model_hash
from scripts import run_high_uptime_recovery as runner
from scripts.run_high_uptime_recovery import (
    due_boundaries,
    lf_sha,
    preserve_failure,
    runtime_class_evidence,
    validate_registered_design,
    validate_review,
)


def test_registered_design_binds_prereg_and_compounding(tmp_path):
    spec, prereg = tmp_path / "spec.json", tmp_path / "prereg.md"
    design = {"capital_mode": "COMPOUNDING", "position_sizing": "USE_AVAILABLE_OPERATING_BANK"}
    spec.write_text(json.dumps(design))
    prereg.write_bytes(b"frozen\r\n")
    fields = {**design, "spec_sha256_lf": lf_sha(spec), "preregistration_sha256_lf": lf_sha(prereg)}
    model = SimpleNamespace(model=fields, model_hash=compute_model_hash(fields))
    assert (
        validate_registered_design(model, spec, prereg)["preregistration_sha256_lf"]
        == hashlib.sha256(b"frozen\n").hexdigest()
    )
    prereg.write_text("changed")
    with pytest.raises(ValueError, match="HASH_MISMATCH"):
        validate_registered_design(model, spec, prereg)
    review = tmp_path / "review.md"
    review.write_text(
        "STATUS=PASS_CONDITIONAL_PRE_RUN\n"
        f"REVIEWED_SOURCE_SHA256_LF[{spec.as_posix()}]={lf_sha(spec)}\n"
    )
    validate_review(review, (spec,))
    spec.write_text("changed")
    with pytest.raises(ValueError, match="REVIEW_SOURCE_BINDING"):
        validate_review(review, (spec,))


def test_boundaries_all_before_equal_next_trade_without_future_processing():
    milestones = [1, 7, 30, 90]
    assert list(due_boundaries(milestones, 30)) == [1, 7, 30]
    assert milestones == [90]


def test_failure_preserves_last_valid_checkpoint_bytes(tmp_path):
    checkpoint = tmp_path / "checkpoint.json"
    checkpoint.write_bytes(b'{"durable":true}')
    original = checkpoint.read_bytes()
    preserve_failure(tmp_path, ValueError("partial step invalid"), {"run": "identity"})
    assert checkpoint.read_bytes() == original
    failure = json.loads((tmp_path / "failure.json").read_text())
    assert failure["last_durable_checkpoint_sha256"] == hashlib.sha256(original).hexdigest()
    assert failure["status"] == "TECHNICAL_ERROR"
    assert "uncheckpointed suffix untrusted" in failure["economic_scope"]


def test_runtime_class_cannot_silently_resolve_to_other_file(tmp_path):
    with pytest.raises(ValueError, match="ACTUAL_RUNTIME_CLASS_SOURCE_MISMATCH"):
        runtime_class_evidence(SimpleNamespace, tmp_path / "wrong.py")


def test_weekly_scope_rejects_automatic_extension():
    design = json.loads(runner.SPEC.read_text())
    assert runner.validate_weekly_scope(design)[1] == datetime(2026, 1, 8, tzinfo=UTC)
    for changes in (
        {"end_exclusive": "2026-01-15T00:00:00+00:00"},
        {"model_id": "M013"},
        {"daily_positive_cycle_target": 1000},
    ):
        with pytest.raises(ValueError, match="OWNER_WEEK_1_SCOPE_REQUIRED"):
            runner.validate_weekly_scope({**design, **changes})


def test_campaign_lock_excludes_second_writer_and_releases_after_failure(tmp_path):
    with pytest.raises(RuntimeError, match="fixture"), runner.campaign_writer_lock(tmp_path):
        with pytest.raises(OSError), runner.campaign_writer_lock(tmp_path):
            pytest.fail("second writer acquired the campaign lock")
        raise RuntimeError("fixture")
    with runner.campaign_writer_lock(tmp_path):
        pass


def test_actual_week_stream_saves_seven_strict_boundaries_and_preserves_state(
    tmp_path, monkeypatch
):
    start = datetime(2026, 1, 1, tzinfo=UTC)
    end = datetime(2026, 1, 8, tzinfo=UTC)
    times = [start + timedelta(hours=1), start + timedelta(days=1), end - timedelta(microseconds=1)]
    stamps = [runner._datetime_to_micros(t) for t in times]
    tape = SimpleNamespace(
        events=[t * 4096 for t in stamps], price_ticks=[100] * 3, tick_size=Decimal("0.01")
    )
    calls = []

    def history_reader(history, *, start, end_exclusive):
        assert end_exclusive <= end
        calls.append((start, end_exclusive))
        return iter(
            [
                SimpleNamespace(
                    timestamp=t,
                    trade_id=i + 1,
                    price=Decimal(1),
                    quantity=Decimal(1),
                    buyer_is_maker=True,
                )
                for i, t in enumerate(times)
                if start <= t < end_exclusive
            ]
        )

    monkeypatch.setattr(runner, "iter_history", history_reader)

    class Replay:
        def __init__(self):
            self.processed_trades = 0
            self.last_us = runner._datetime_to_micros(start)
            self.execution = SimpleNamespace(audit=[])
            self.completed = False

        def advance_to(self, boundary):
            self.execution.audit.append({"boundary": boundary, "count": self.processed_trades})

        def step(self, event):
            self.last_us = event.time_us
            self.processed_trades += 1

        def checkpoint(self):
            return {
                "sha256": "fixture",
                "payload": {"count": self.processed_trades, "open_position_preserved": True},
            }

        def metrics(self, as_of_us=None):
            return {
                "SIMULATION_TIMESTAMP": str(self.last_us if as_of_us is None else as_of_us),
                "RUN_STATUS": "COMPLETE" if self.completed else "RUNNING",
            }

        def finish(self):
            assert self.processed_trades == 3
            self.completed = True

    identity = {
        "start": start.isoformat(),
        "end_exclusive": end.isoformat(),
        "model_hash": "model",
        "run_hash": "run",
        "published_config_sha": "source",
    }
    runner.stream_week(None, tape, 0, Replay(), identity, tmp_path)
    for day in range(1, 8):
        score = json.loads((tmp_path / "capital-checkpoints" / f"DAY_{day}.json").read_bytes())
        assert score["PROCESSED_TRADES"] == (1 if day == 1 else 3 if day == 7 else 2)
        assert score["SIMULATION_TIMESTAMP"] == str(
            runner._datetime_to_micros(start + timedelta(days=day))
        )
        assert score["NEXT_WEEK_AUTHORIZED"] is False
    final = json.loads((tmp_path / "scoreboard.json").read_bytes())
    assert final["RUN_STATUS"] == "COMPLETE"
    assert final["EXTENSION_STATUS"] == "AWAITING_OWNER_APPROVAL"
    saved = json.loads((tmp_path / "checkpoint.json").read_bytes())
    assert saved["replay"]["payload"]["open_position_preserved"]
    assert (
        hashlib.sha256((tmp_path / "checkpoint.json").read_bytes()).hexdigest()
        == final["CHECKPOINT_SHA256"]
    )
    assert (
        saved["capital_curve"]["sha256"]
        == hashlib.sha256((tmp_path / "capital-curve.jsonl").read_bytes()).hexdigest()
    )
    assert calls == [(datetime(2025, 12, 31, tzinfo=UTC), start), (start, end)]
