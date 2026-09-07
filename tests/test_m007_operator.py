from dataclasses import FrozenInstanceError, replace
from decimal import Decimal
from itertools import pairwise

import pytest
from pydantic import ValidationError

from crypto_strategy_lab.microstructure import operator
from crypto_strategy_lab.microstructure.operator import (
    M007_OPERATOR_STRATEGY_HASH,
    OPERATOR_TRANSITIONS,
    M007OperatorSpec,
    OperatorMode,
    OperatorState,
    frozen_m007_strategy,
)
from crypto_strategy_lab.microstructure.serial_replay import preregistered_corrected_block


def test_m007_operator_cannot_mutate_strategy_configuration() -> None:
    spec = M007OperatorSpec()
    canonical = preregistered_corrected_block()[2]
    assert spec.strategy_config == canonical
    assert spec.strategy_hash == canonical.model_hash == M007_OPERATOR_STRATEGY_HASH
    with pytest.raises(FrozenInstanceError):
        spec.strategy_hash = "changed"  # type: ignore[misc]
    with pytest.raises(ValidationError):
        spec.strategy_config.lookback_minutes = 1
    changed_copy = spec.strategy_config.model_copy(update={"lookback_minutes": 1})
    assert changed_copy.model_hash != spec.strategy_hash
    assert spec.strategy_config == canonical
    assert spec.strategy_config is not spec.strategy_config
    with pytest.raises(TypeError):
        M007OperatorSpec(**{"strategy_config": changed_copy})  # type: ignore[arg-type]


@pytest.mark.parametrize("mode", [OperatorMode.TESTNET, OperatorMode.LIVE, "SHADOW", "LIVE"])
def test_non_shadow_modes_fail_closed(mode: OperatorMode) -> None:
    with pytest.raises(PermissionError, match="SHADOW_ONLY"):
        M007OperatorSpec(mode=mode)


def test_order_submission_always_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TRADING_ENABLED", "true")
    spec = M007OperatorSpec()
    with pytest.raises(PermissionError, match="TRADING_DISABLED"):
        spec.authorize_order_submission()
    with pytest.raises(PermissionError):
        replace(spec, trading_enabled=True)
    object.__setattr__(spec, "mode", OperatorMode.LIVE)
    with pytest.raises(PermissionError):
        spec.assert_ready()
    with pytest.raises(PermissionError):
        spec.authorize_order_submission()


@pytest.mark.parametrize("capital", ["0", "99", "101", "900637402983.4181046", "NaN", "Infinity"])
def test_initial_capital_cannot_inherit_backtest_or_parent(capital: str) -> None:
    with pytest.raises(ValueError, match="INITIAL_CAPITAL_INVARIANT_VIOLATION"):
        M007OperatorSpec(initial_capital=Decimal(capital))
    assert M007OperatorSpec().initial_capital == Decimal("100")


@pytest.mark.parametrize(
    "field,value",
    [
        ("symbol", "BTCUSDT"),
        ("model_id", "M010"),
        ("currency", "USDC"),
        ("banks", 2),
        ("lots", 2),
        ("lots", True),
        ("strategy_hash", "changed"),
        ("initial_capital", 100),
    ],
)
def test_forged_config_revalidated_at_use(field: str, value: object) -> None:
    spec = M007OperatorSpec()
    object.__setattr__(spec, field, value)
    with pytest.raises(ValueError):
        spec.assert_ready()
    with pytest.raises(ValueError):
        _ = spec.strategy_config


@pytest.mark.parametrize(
    "update", [{"lookback_minutes": 1}, {"model_id": "M011"}, {"parent_model_id": "M009"}]
)
def test_canonical_drift_fails_closed(
    monkeypatch: pytest.MonkeyPatch, update: dict[str, object]
) -> None:
    block = list(preregistered_corrected_block())
    block[2] = block[2].model_copy(update=update)
    monkeypatch.setattr(operator, "preregistered_corrected_block", lambda: tuple(block))
    with pytest.raises(ValueError, match="M007_OPERATOR"):
        frozen_m007_strategy()


def test_state_topology_is_complete_and_immutable() -> None:
    assert len(OperatorState) == 14
    assert set(OPERATOR_TRANSITIONS) == set(OperatorState)
    assert all(isinstance(targets, frozenset) for targets in OPERATOR_TRANSITIONS.values())
    with pytest.raises(TypeError):
        OPERATOR_TRANSITIONS[OperatorState.LONG] = frozenset()  # type: ignore[index]
    for state in (
        OperatorState.LONG,
        OperatorState.BUY_PARTIAL,
        OperatorState.SELL_PARTIAL,
        OperatorState.DISCONNECTED,
        OperatorState.RECOVERING,
    ):
        assert OperatorState.FLAT not in OPERATOR_TRANSITIONS[state]
    path = [
        OperatorState.BOOT,
        OperatorState.RECONCILING,
        OperatorState.FLAT,
        OperatorState.BUY_INTENT,
        OperatorState.BUY_WORKING,
        OperatorState.BUY_PARTIAL,
        OperatorState.LONG,
        OperatorState.SELL_WORKING,
        OperatorState.SELL_PARTIAL,
        OperatorState.CYCLE_COMPLETE,
        OperatorState.FLAT,
    ]
    assert all(right in OPERATOR_TRANSITIONS[left] for left, right in pairwise(path))
