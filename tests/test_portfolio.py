from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from hypothesis import given
from hypothesis import strategies as st

from crypto_strategy_lab.simulation.portfolio import ExecutionCosts, SpotPortfolio

NOW = datetime(2022, 1, 1, tzinfo=UTC)
COSTS = ExecutionCosts()


def test_buy_sell_and_costs_are_decimal() -> None:
    portfolio = SpotPortfolio(Decimal("80"))
    buy = portfolio.buy(
        symbol="BTCUSDT",
        market_price=Decimal("47000"),
        allocation_percent=Decimal("75"),
        simulated_time=NOW,
        costs=COSTS,
        marks={"BTCUSDT": Decimal("47000")},
    )
    assert buy.fee == buy.quote_value * COSTS.fee_rate
    assert portfolio.state.usdt >= Decimal("20")
    sell = portfolio.sell(
        symbol="BTCUSDT",
        market_price=Decimal("48000"),
        simulated_time=NOW,
        costs=COSTS,
    )
    assert sell.side == "SELL"
    assert portfolio.state.asset_symbol is None
    assert portfolio.state.usdt > 0


def test_rotation_second_leg_failure_leaves_cash() -> None:
    portfolio = SpotPortfolio(Decimal("80"))
    prices = {"BTCUSDT": Decimal("47000"), "ETHUSDT": Decimal("3700")}
    portfolio.buy(
        symbol="BTCUSDT",
        market_price=prices["BTCUSDT"],
        allocation_percent=Decimal("75"),
        simulated_time=NOW,
        costs=COSTS,
        marks=prices,
    )
    result = portfolio.rotate(
        from_symbol="BTCUSDT",
        to_symbol="ETHUSDT",
        prices=prices,
        allocation_percent=Decimal("75"),
        simulated_time=NOW,
        costs=COSTS,
        min_notionals={"ETHUSDT": Decimal("1000")},
    )
    assert len(result.fills) == 1
    assert result.failures
    assert portfolio.state.asset_symbol is None
    assert portfolio.state.asset_quantity == 0


@given(
    capital=st.decimals(min_value="10", max_value="100000", places=4),
    price=st.decimals(min_value="0.01", max_value="100000", places=6),
    allocation=st.decimals(min_value="0.01", max_value="100", places=2),
)
def test_no_negative_balance_and_exposure_limit(
    capital: Decimal, price: Decimal, allocation: Decimal
) -> None:
    portfolio = SpotPortfolio(capital)
    fill = portfolio.buy(
        symbol="ASSETUSDT",
        market_price=price,
        allocation_percent=allocation,
        simulated_time=NOW,
        costs=COSTS,
        marks={"ASSETUSDT": price},
    )
    assert portfolio.state.usdt >= 0
    assert fill.quote_value + fill.fee <= capital * Decimal("0.75")
