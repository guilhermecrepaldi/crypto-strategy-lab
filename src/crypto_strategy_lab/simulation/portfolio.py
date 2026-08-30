from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import ROUND_DOWN, Decimal

from crypto_strategy_lab.domain import Fill, PortfolioState


class ExecutionRejected(ValueError):
    pass


@dataclass(frozen=True)
class ExecutionCosts:
    fee_rate: Decimal = Decimal("0.001")
    spread_rate: Decimal = Decimal("0.0002")
    slippage_rate: Decimal = Decimal("0.0003")


@dataclass
class ExecutionResult:
    fills: list[Fill] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)


class SpotPortfolio:
    def __init__(
        self,
        initial_usdt: Decimal,
        *,
        max_exposure: Decimal = Decimal("0.75"),
        reserve_ratio: Decimal = Decimal("0.25"),
    ) -> None:
        if initial_usdt <= 0:
            raise ValueError("initial capital must be positive")
        if max_exposure + reserve_ratio > 1:
            raise ValueError("exposure plus reserve cannot exceed 100%")
        self.max_exposure = max_exposure
        self.reserve_ratio = reserve_ratio
        self.state = PortfolioState(usdt=initial_usdt, peak_equity=initial_usdt)

    def equity(self, prices: dict[str, Decimal]) -> Decimal:
        asset_value = Decimal("0")
        if self.state.asset_symbol and self.state.asset_quantity:
            if self.state.asset_symbol not in prices:
                raise ExecutionRejected(f"missing mark price for {self.state.asset_symbol}")
            asset_value = self.state.asset_quantity * prices[self.state.asset_symbol]
        return self.state.usdt + asset_value

    def buy(
        self,
        *,
        symbol: str,
        market_price: Decimal,
        allocation_percent: Decimal,
        simulated_time: datetime,
        costs: ExecutionCosts,
        marks: dict[str, Decimal],
        min_notional: Decimal = Decimal("0"),
    ) -> Fill:
        if self.state.asset_symbol is not None:
            raise ExecutionRejected("portfolio already holds a crypto asset")
        if market_price <= 0:
            raise ExecutionRejected("market price must be positive")
        allocation = min(allocation_percent / Decimal("100"), self.max_exposure)
        equity = self.equity(marks)
        reserve = equity * self.reserve_ratio
        quote_budget = min(equity * allocation, max(Decimal("0"), self.state.usdt - reserve))
        execution_price = market_price * (
            Decimal("1") + costs.spread_rate / Decimal("2") + costs.slippage_rate
        )
        quantity = (quote_budget / (execution_price * (Decimal("1") + costs.fee_rate))).quantize(
            Decimal("0.000000000000000001"), rounding=ROUND_DOWN
        )
        quote_value = quantity * execution_price
        fee = quote_value * costs.fee_rate
        if quote_value < min_notional or quantity <= 0:
            raise ExecutionRejected("buy does not meet minimum notional")
        total = quote_value + fee
        if total > self.state.usdt:
            raise ExecutionRejected("insufficient USDT")
        self.state.usdt -= total
        self.state.asset_symbol = symbol
        self.state.asset_quantity = quantity
        self.state.average_cost = total / quantity
        self.state.fees += fee
        self._assert_invariants()
        return Fill(
            simulated_time=simulated_time,
            symbol=symbol,
            side="BUY",
            price=execution_price,
            quantity=quantity,
            quote_value=quote_value,
            fee=fee,
            spread_cost=quantity * market_price * costs.spread_rate / Decimal("2"),
            slippage_cost=quantity * market_price * costs.slippage_rate,
        )

    def sell(
        self,
        *,
        symbol: str,
        market_price: Decimal,
        simulated_time: datetime,
        costs: ExecutionCosts,
    ) -> Fill:
        if self.state.asset_symbol != symbol or self.state.asset_quantity <= 0:
            raise ExecutionRejected(f"portfolio does not hold {symbol}")
        execution_price = market_price * (
            Decimal("1") - costs.spread_rate / Decimal("2") - costs.slippage_rate
        )
        quantity = self.state.asset_quantity
        quote_value = quantity * execution_price
        fee = quote_value * costs.fee_rate
        proceeds = quote_value - fee
        cost_basis = self.state.average_cost * quantity
        self.state.usdt += proceeds
        self.state.realized_pnl += proceeds - cost_basis
        self.state.fees += fee
        self.state.asset_symbol = None
        self.state.asset_quantity = Decimal("0")
        self.state.average_cost = Decimal("0")
        self._assert_invariants()
        return Fill(
            simulated_time=simulated_time,
            symbol=symbol,
            side="SELL",
            price=execution_price,
            quantity=quantity,
            quote_value=quote_value,
            fee=fee,
            spread_cost=quantity * market_price * costs.spread_rate / Decimal("2"),
            slippage_cost=quantity * market_price * costs.slippage_rate,
            realized_pnl=proceeds - cost_basis,
        )

    def rotate(
        self,
        *,
        from_symbol: str,
        to_symbol: str,
        prices: dict[str, Decimal],
        allocation_percent: Decimal,
        simulated_time: datetime,
        costs: ExecutionCosts,
        min_notionals: dict[str, Decimal] | None = None,
    ) -> ExecutionResult:
        result = ExecutionResult()
        result.fills.append(
            self.sell(
                symbol=from_symbol,
                market_price=prices[from_symbol],
                simulated_time=simulated_time,
                costs=costs,
            )
        )
        try:
            result.fills.append(
                self.buy(
                    symbol=to_symbol,
                    market_price=prices[to_symbol],
                    allocation_percent=allocation_percent,
                    simulated_time=simulated_time,
                    costs=costs,
                    marks=prices,
                    min_notional=(min_notionals or {}).get(to_symbol, Decimal("0")),
                )
            )
        except ExecutionRejected as error:
            result.failures.append(str(error))
        return result

    def snapshot(self, prices: dict[str, Decimal]) -> dict[str, Decimal | str | None]:
        equity = self.equity(prices)
        self.state.peak_equity = max(self.state.peak_equity, equity)
        drawdown = (
            (self.state.peak_equity - equity) / self.state.peak_equity
            if self.state.peak_equity
            else Decimal("0")
        )
        self.state.max_drawdown = max(self.state.max_drawdown, drawdown)
        unrealized = Decimal("0")
        if self.state.asset_symbol:
            unrealized = self.state.asset_quantity * (
                prices[self.state.asset_symbol] - self.state.average_cost
            )
        return {
            "usdt": self.state.usdt,
            "asset_symbol": self.state.asset_symbol,
            "asset_quantity": self.state.asset_quantity,
            "equity_usdt": equity,
            "realized_pnl": self.state.realized_pnl,
            "unrealized_pnl": unrealized,
            "fees": self.state.fees,
            "drawdown": drawdown,
        }

    def _assert_invariants(self) -> None:
        if self.state.usdt < 0 or self.state.asset_quantity < 0:
            raise AssertionError("negative balances are forbidden")
        if (self.state.asset_symbol is None) != (self.state.asset_quantity == 0):
            raise AssertionError("asset symbol and quantity must change atomically")
