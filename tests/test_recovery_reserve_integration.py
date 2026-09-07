import itertools
from datetime import UTC, datetime, timedelta
from decimal import Decimal as D

import pytest

from crypto_strategy_lab.microstructure import recovery_reserve_study as study
from crypto_strategy_lab.microstructure.recovery_reserve import ReserveConfig
from crypto_strategy_lab.microstructure.recovery_reserve_audit import audit_ledger
from crypto_strategy_lab.microstructure.serial_replay import (
    SerialModelConfig,
    SerialScenarioConfig,
    SerialStrategy,
    SerialTape,
)


def setup():
    start = datetime(2026, 1, 1, tzinfo=UTC)
    raw = []
    for i in range(20):
        raw.extend([(-100 + 2 * i, "1"), (-99 + 2 * i, "1.0001")])
    raw.append((0, "1"))
    for i in range(30):
        raw.extend([(30 + i * 60, "0.9998"), (31 + i * 60, "0.9999")])
    raw.extend([(3599, "0.9999"), (3601, "0.9998"), (3602, "0.9999"), (7200, "1")])
    tape = SerialTape.from_events(
        [(start + timedelta(seconds=t), D(p)) for t, p in raw], tick_size=D("0.0001")
    )
    parent = SerialModelConfig(
        model_id="M007",
        parent_model_id=None,
        strategy=SerialStrategy.ALWAYS_BEST,
        lookback_minutes=1440,
        decision_interval_minutes=1,
    )
    return tape, parent, SerialScenarioConfig(tick_size=tape.tick_size), start


@pytest.mark.parametrize("crash_second", [60, 3660])
def test_real_selector_release_and_midrun_restart(monkeypatch, tmp_path, crash_second):
    tape, parent, scenario, start = setup()
    timelines = tape.timelines((1,))
    config = ReserveConfig(D("0.01"), 1, D(2))
    kwargs = {"start": start, "end": start + timedelta(seconds=7200), "catalog": None}
    reference, runtime = study.run_scenario(tape, timelines, parent, scenario, config, **kwargs)
    assert len(runtime.releases) == 1
    assert reference.cycles[0].entry_timestamp == start + timedelta(seconds=3601)
    assert D(runtime.releases[0]["reserve_transfer"]) == D("0.01")
    audit = audit_ledger(reference, tape, config.skim_rate, runtime.reserve, runtime.releases)
    assert audit["integrity_pass"] is True
    assert D(audit["total_release_loss"]) > 0
    clock = itertools.count(step=301)
    monkeypatch.setattr(study.time, "monotonic", lambda: next(clock))
    original_write = study.write_json

    def crash_after_checkpoint(path, data):
        original_write(path, data)
        cursor = study._event_to_datetime(data["payload"]["cursor"])
        if cursor >= start + timedelta(seconds=crash_second):
            raise RuntimeError("simulated crash after atomic checkpoint")

    checkpoint = tmp_path / "checkpoint.json"
    monkeypatch.setattr(study, "write_json", crash_after_checkpoint)
    with pytest.raises(RuntimeError, match="simulated crash"):
        study.run_scenario(
            tape,
            timelines,
            parent,
            scenario,
            config,
            checkpoint=checkpoint,
            identity={"fixture": 1},
            **kwargs,
        )
    monkeypatch.setattr(study, "write_json", original_write)
    resumed, recovered = study.run_scenario(
        tape,
        timelines,
        parent,
        scenario,
        config,
        checkpoint=checkpoint,
        identity={"fixture": 1},
        **kwargs,
    )
    assert resumed == reference
    assert recovered.snapshot() == runtime.snapshot()
