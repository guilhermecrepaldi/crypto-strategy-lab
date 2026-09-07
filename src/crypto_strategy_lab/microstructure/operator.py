"""Frozen M007 operator contract; no streaming, persistence or order execution."""

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from types import MappingProxyType
from typing import NoReturn

from crypto_strategy_lab.microstructure.serial_replay import (
    SerialModelConfig,
    preregistered_corrected_block,
)

M007_OPERATOR_STRATEGY_HASH = "2cb6c755cad4b805eb6b79e7b7e04fd271e660f285a8c1d6aca4c643dded934f"


class OperatorMode(StrEnum):
    SHADOW = "SHADOW"
    TESTNET = "TESTNET"
    LIVE = "LIVE"


class OperatorState(StrEnum):
    BOOT = "BOOT"
    RECONCILING = "RECONCILING"
    FLAT = "FLAT"
    BUY_INTENT = "BUY_INTENT"
    BUY_WORKING = "BUY_WORKING"
    BUY_PARTIAL = "BUY_PARTIAL"
    LONG = "LONG"
    SELL_WORKING = "SELL_WORKING"
    SELL_PARTIAL = "SELL_PARTIAL"
    CYCLE_COMPLETE = "CYCLE_COMPLETE"
    DISCONNECTED = "DISCONNECTED"
    RECOVERING = "RECOVERING"
    HALTED = "HALTED"
    ERROR = "ERROR"


def frozen_m007_strategy() -> SerialModelConfig:
    """Return a fresh validated canonical config; never accept a caller override."""
    matches = [item for item in preregistered_corrected_block() if item.model_id == "M007"]
    if len(matches) != 1:
        raise ValueError("M007_OPERATOR_IDENTITY_VIOLATION")
    strategy = SerialModelConfig.model_validate(matches[0].model_dump())
    if strategy.parent_model_id != "M006":
        raise ValueError("M007_OPERATOR_IDENTITY_VIOLATION")
    if strategy.model_hash != M007_OPERATOR_STRATEGY_HASH:
        raise ValueError("M007_OPERATOR_STRATEGY_HASH_VIOLATION")
    return strategy


@dataclass(frozen=True, slots=True)
class M007OperatorSpec:
    """Configuration gate, not a running operator or an authorization boundary for Python."""

    mode: OperatorMode = OperatorMode.SHADOW
    initial_capital: Decimal = Decimal("100")
    currency: str = "USDT"
    symbol: str = "USDCUSDT"
    model_id: str = "M007"
    banks: int = 1
    lots: int = 1
    trading_enabled: bool = False
    strategy_hash: str = M007_OPERATOR_STRATEGY_HASH

    def __post_init__(self) -> None:
        self.assert_ready()

    def assert_ready(self) -> None:
        """Revalidate at use boundaries, including copies/objects changed outside normal APIs."""
        if self.mode is not OperatorMode.SHADOW or self.trading_enabled is not False:
            raise PermissionError("SHADOW_ONLY_TRADING_DISABLED")
        if (
            not isinstance(self.initial_capital, Decimal)
            or not self.initial_capital.is_finite()
            or self.initial_capital != Decimal("100")
        ):
            raise ValueError("INITIAL_CAPITAL_INVARIANT_VIOLATION")
        if (
            self.currency != "USDT"
            or self.symbol != "USDCUSDT"
            or self.model_id != "M007"
            or type(self.banks) is not int
            or self.banks != 1
            or type(self.lots) is not int
            or self.lots != 1
        ):
            raise ValueError("M007_OPERATOR_IDENTITY_VIOLATION")
        if self.strategy_hash != M007_OPERATOR_STRATEGY_HASH:
            raise ValueError("M007_OPERATOR_STRATEGY_HASH_VIOLATION")
        frozen_m007_strategy()

    @property
    def strategy_config(self) -> SerialModelConfig:
        self.assert_ready()
        return frozen_m007_strategy()

    def authorize_order_submission(self) -> NoReturn:
        """No mode, environment variable or constructor flag can enable submission."""
        self.assert_ready()
        raise PermissionError("TRADING_DISABLED_SHADOW_ONLY")


# Topology only: the semantic guards in STATE_MACHINE.md remain mandatory.
# A permitted edge is NOT proof of a fill, cancellation, recovery or permission to trade.
S = OperatorState
OPERATOR_TRANSITIONS = MappingProxyType(
    {
        S.BOOT: frozenset({S.RECONCILING, S.HALTED, S.ERROR}),
        S.RECONCILING: frozenset(
            {
                S.FLAT,
                S.BUY_INTENT,
                S.BUY_WORKING,
                S.BUY_PARTIAL,
                S.LONG,
                S.SELL_WORKING,
                S.SELL_PARTIAL,
                S.CYCLE_COMPLETE,
                S.DISCONNECTED,
                S.HALTED,
                S.ERROR,
            }
        ),
        S.FLAT: frozenset({S.BUY_INTENT, S.DISCONNECTED, S.HALTED, S.ERROR}),
        S.BUY_INTENT: frozenset({S.BUY_WORKING, S.FLAT, S.DISCONNECTED, S.HALTED, S.ERROR}),
        S.BUY_WORKING: frozenset(
            {S.BUY_PARTIAL, S.LONG, S.FLAT, S.DISCONNECTED, S.HALTED, S.ERROR}
        ),
        S.BUY_PARTIAL: frozenset({S.BUY_PARTIAL, S.LONG, S.DISCONNECTED, S.HALTED, S.ERROR}),
        S.LONG: frozenset({S.SELL_WORKING, S.DISCONNECTED, S.HALTED, S.ERROR}),
        S.SELL_WORKING: frozenset(
            {S.SELL_PARTIAL, S.CYCLE_COMPLETE, S.LONG, S.DISCONNECTED, S.HALTED, S.ERROR}
        ),
        S.SELL_PARTIAL: frozenset(
            {S.SELL_PARTIAL, S.CYCLE_COMPLETE, S.LONG, S.DISCONNECTED, S.HALTED, S.ERROR}
        ),
        S.CYCLE_COMPLETE: frozenset({S.FLAT, S.DISCONNECTED, S.HALTED, S.ERROR}),
        S.DISCONNECTED: frozenset({S.RECOVERING, S.HALTED, S.ERROR}),
        S.RECOVERING: frozenset({S.RECONCILING, S.DISCONNECTED, S.HALTED, S.ERROR}),
        S.HALTED: frozenset({S.RECOVERING}),
        S.ERROR: frozenset({S.RECOVERING, S.HALTED}),
    }
)
