import hashlib
import json
import sys
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


def test_actual_runner_snapshots_strict_day_prefix_and_binds_curves(tmp_path, monkeypatch):
    start = datetime(2026, 1, 1, tzinfo=UTC)
    end = datetime(2026, 9, 5, 23, 59, 59, 783644, tzinfo=UTC)
    times = [
        start + timedelta(hours=1),
        start + timedelta(days=90),
        end - timedelta(microseconds=1),
    ]
    stamps = [runner._datetime_to_micros(t) for t in times]
    calls = []

    class Replay:
        def __init__(self, *args, **kwargs):
            assert kwargs["identity"]["capital_mode"] == "COMPOUNDING"
            self.processed_trades = 0
            self.last_us = runner._datetime_to_micros(start)
            self.execution = SimpleNamespace(audit=[], counts={})

        def advance_to(self, boundary):
            calls.append(("advance", boundary, self.processed_trades))

        def step(self, event):
            self.last_us = event.time_us
            self.processed_trades += 1
            calls.append(("trade", event.time_us, self.processed_trades))

        def checkpoint(self):
            return {"sha256": "testpayload", "payload": {"processed": self.processed_trades}}

        def metrics(self, as_of_us=None):
            timestamp = self.last_us if as_of_us is None else as_of_us
            return {
                "SIMULATION_TIMESTAMP": str(timestamp),
                "OPERATING_BANK": "100",
                "RESERVE": "5",
                "TOTAL_EQUITY": "105",
                "CURRENT_POSITION_NOTIONAL": "0",
            }

        def finish(self):
            assert self.processed_trades == 3

    class Registry:
        def get(self, *args):
            return SimpleNamespace(
                model={"strategy": "HIGH_UPTIME_DYNAMIC_RECOVERY"}, model_hash="b" * 64
            )

        def current_status(self, *args):
            return runner.ModelStatus.CREATED

        def append_scenario(self, *args):
            return {"payload": {"SCENARIO_HASH": "c" * 64}}

        def append_run(self, *args):
            return {"payload": {"RUN_HASH": "d" * 64}}

        def transition(self, *args, **kwargs):
            pass

    for name, value in {
        "published_sha": lambda: "a" * 40,
        "published_bytes": lambda *a: None,
        "runtime_class_evidence": lambda *a: {"class": "test.Replay"},
        "validate_registered_design": lambda *a: {},
        "validate_review": lambda *a: None,
        "ModelRegistry": Registry,
        "RecoveryReserveRuntime": lambda *a: None,
    }.items():
        monkeypatch.setattr(runner, name, value)
    monkeypatch.setitem(
        sys.modules,
        "crypto_strategy_lab.microstructure.high_uptime_recovery",
        SimpleNamespace(HighUptimeRecoveryReplay=Replay),
    )
    audit = tmp_path / "physical.json"
    audit.write_text(
        json.dumps(
            {
                "coverage_exact": True,
                "archive_count": 1,
                "fresh_aggregate": {
                    k: 1
                    for k in (
                        "existing_count",
                        "manifest_hash_match_count",
                        "manifest_size_match_count",
                        "sidecar_hash_match_count",
                        "zip_test_ok_count",
                    )
                },
            }
        )
    )
    config = json.loads(runner.PROFILE_CONFIG.read_text())
    for key in (
        "history_manifest",
        "physical_archive_audit",
        "calibration_manifest",
        "official_rule_manifest",
    ):
        config[key] = str(audit)
        config[key + "_sha256"] = runner.file_sha(audit)
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(config))
    monkeypatch.setattr(runner, "PROFILE_CONFIG", config_path)
    monkeypatch.setattr(runner, "PROFILE_CONFIG_SHA", runner.file_sha(config_path))
    review = tmp_path / "review.md"
    review.write_text("STATUS=PASS_CONDITIONAL_PRE_RUN\n")
    monkeypatch.setattr(runner, "REVIEW", review)
    history = SimpleNamespace(
        symbol="USDCUSDT", kind="trades", integrity_status="VALID", dataset_hash="e" * 64
    )
    monkeypatch.setattr(
        runner, "HistoryManifest", SimpleNamespace(model_validate_json=lambda *a: history)
    )
    tape = SimpleNamespace(
        events=[t * 4096 for t in stamps],
        price_ticks=[1, 1, 1],
        tick_size=Decimal(1),
        tape_hash=runner.TAPE_HASH,
        timelines=lambda *a: {},
    )
    monkeypatch.setattr(
        runner,
        "load_evaluated_run_evidence",
        lambda *a: SimpleNamespace(
            tape=tape, tape_manifest=SimpleNamespace(dataset_hash=history.dataset_hash)
        ),
    )
    monkeypatch.setattr(
        runner,
        "iter_history",
        lambda *a, **kw: iter(
            [
                SimpleNamespace(
                    timestamp=t,
                    trade_id=i + 1,
                    price=Decimal(1),
                    quantity=Decimal(1),
                    buyer_is_maker=True,
                )
                for i, t in enumerate(times)
            ]
        ),
    )
    output = tmp_path / "run"
    output.mkdir()
    runner.run(output)
    for day in (1, 7, 30, 90):
        point = json.loads((output / "capital-checkpoints" / f"DAY_{day}.json").read_text())
        boundary = runner._datetime_to_micros(start + timedelta(days=day))
        assert point["SIMULATION_TIMESTAMP"] == str(boundary)
        assert point["PROCESSED_TRADES"] == 1
        assert point["CANONICAL_CUTOFF_EVENT"] == stamps[0] * 4096
    assert calls.index(("advance", stamps[1], 1)) < calls.index(("trade", stamps[1], 2))
    checkpoint = json.loads((output / "checkpoint.json").read_text())
    curve = (output / "capital-curve.jsonl").read_bytes()
    assert checkpoint["capital_curve"] == {
        "bytes": len(curve),
        "sha256": hashlib.sha256(curve).hexdigest(),
    }
