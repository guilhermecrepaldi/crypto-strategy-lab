import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal as D

import pytest

from crypto_strategy_lab.microstructure.recovery_reserve import ReserveConfig
from crypto_strategy_lab.microstructure.recovery_reserve_audit import audit_ledger
from crypto_strategy_lab.microstructure.recovery_reserve_study import run_scenario
from crypto_strategy_lab.microstructure.serial_replay import (
    SerialModelConfig,
    SerialScenarioConfig,
    SerialStrategy,
    SerialTape,
    replay_serial_model,
)

START = datetime(2026, 1, 1, tzinfo=UTC)


def fixture():
    events = [
        (START + timedelta(seconds=offset), D(price))
        for offset, price in [
            (-60, "1"),
            (-59, "1.0001"),
            (0, "1"),
            (1, "1.0001"),
            (10, "1"),
            (11, "1.0001"),
            (65, "1"),
            (70, "1.0001"),
            (120, "1"),
        ]
    ]
    tape = SerialTape.from_events(events, tick_size=D("0.0001"))
    parent = SerialModelConfig(
        model_id="M007",
        parent_model_id=None,
        strategy=SerialStrategy.ALWAYS_BEST,
        lookback_minutes=1440,
        decision_interval_minutes=1,
    )
    scenario = SerialScenarioConfig(tick_size=tape.tick_size)
    return tape, parent, scenario


def test_shared_engine_no_release_no_skim_exactly_equals_canonical():
    tape, parent, scenario = fixture()
    end = START + timedelta(seconds=120)
    reference = replay_serial_model(tape, parent, scenario, start=START, end_exclusive=end)
    result, runtime = run_scenario(
        tape,
        tape.timelines((1,)),
        parent,
        scenario,
        ReserveConfig(D(0), 24, D(2)),
        start=START,
        end=end,
        catalog=None,
    )
    assert result == reference
    assert runtime.reserve == 5 and not runtime.releases
    audit = audit_ledger(result, tape, D(0), runtime.reserve, runtime.releases)
    assert audit["integrity_pass"] is True
    assert D(audit["series"][-1]["total_equity"]) == reference.final_marked_equity + 5


def test_restart_same_config_and_segregated_profit(tmp_path):
    tape, parent, scenario = fixture()
    timelines = tape.timelines((1,))
    config = ReserveConfig(D("0.01"), 1, D(2))
    identity = {"config": config.payload()}
    end = START + timedelta(seconds=120)
    result, runtime = run_scenario(
        tape,
        timelines,
        parent,
        scenario,
        config,
        start=START,
        end=end,
        catalog=None,
        checkpoint=tmp_path / "checkpoint.json",
        identity=identity,
    )
    repeat, recovered = run_scenario(
        tape,
        timelines,
        parent,
        scenario,
        config,
        start=START,
        end=end,
        catalog=None,
        checkpoint=tmp_path / "checkpoint.json",
        identity=identity,
    )
    assert repeat == result
    assert recovered.snapshot() == runtime.snapshot()
    assert runtime.total_skim > 0 and runtime.reserve > 5
    audit = audit_ledger(result, tape, config.skim_rate, runtime.reserve, runtime.releases)
    assert D(audit["total_skim"]) == runtime.total_skim
    raw = json.loads((tmp_path / "checkpoint.json").read_text())
    raw["payload"]["state"]["cash"] = "105"
    (tmp_path / "checkpoint.json").write_text(json.dumps(raw))
    with pytest.raises(ValueError, match="CHECKPOINT_IDENTITY_OR_HASH"):
        run_scenario(
            tape,
            timelines,
            parent,
            scenario,
            config,
            start=START,
            end=end,
            catalog=None,
            checkpoint=tmp_path / "checkpoint.json",
            identity=identity,
        )
