from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import timedelta
from decimal import Decimal
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import ValidationError

from crypto_strategy_lab.data.aggregation import aggregate_candles
from crypto_strategy_lab.data.binance import validate_candle_sequence
from crypto_strategy_lab.data.temporal import TemporalComplementaryData, TemporalMarketData
from crypto_strategy_lab.decision.providers import DecisionProvider
from crypto_strategy_lab.domain import (
    Action,
    Candle,
    DecisionRequest,
    DecisionResponse,
    Fill,
    canonical_hash,
)
from crypto_strategy_lab.simulation.clock import HistoricalClock
from crypto_strategy_lab.simulation.portfolio import (
    ExecutionCosts,
    ExecutionRejected,
    SpotPortfolio,
)


@dataclass(frozen=True)
class SimulationConfig:
    initial_capital: Decimal = Decimal("80")
    max_exposure: Decimal = Decimal("0.75")
    reserve_ratio: Decimal = Decimal("0.25")
    costs: ExecutionCosts = field(default_factory=ExecutionCosts)
    rotation_edge_margin: Decimal = Decimal("0.001")
    seed: int = 1
    policy_version: str = "fixture-v1"
    run_type: str = "LAB_REPLAY"


@dataclass
class PendingDecision:
    response: DecisionResponse
    execute_at: Any
    decision_index: int


@dataclass
class SimulationResult:
    run_id: UUID
    dataset_hash: str
    policy_hash: str
    config: SimulationConfig
    symbols: tuple[str, ...]
    decisions: list[dict[str, Any]] = field(default_factory=list)
    orders: list[dict[str, Any]] = field(default_factory=list)
    fills: list[Fill] = field(default_factory=list)
    equity: list[dict[str, Any]] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)
    metrics: dict[str, Decimal] = field(default_factory=dict)


class SimulationEngine:
    def __init__(
        self,
        candles: list[Candle],
        provider: DecisionProvider,
        config: SimulationConfig | None = None,
        complementary_data: TemporalComplementaryData | None = None,
    ) -> None:
        self.candles = candles
        self.provider = provider
        self.config = config or SimulationConfig()
        gaps = validate_candle_sequence(candles)
        if gaps:
            raise ValueError(f"simulation dataset contains {len(gaps)} relevant gap(s)")
        self.market = TemporalMarketData(candles)
        self.complementary_data = complementary_data
        if len(self.market.symbols) != 4:
            raise ValueError("the first vertical slice requires exactly four symbols")

    def run(self) -> SimulationResult:
        dataset_payload = [candle.model_dump(mode="json") for candle in self.candles]
        dataset_hash = canonical_hash(dataset_payload)
        policy_hash = canonical_hash(
            {"version": self.config.policy_version, "seed": self.config.seed}
        )
        run_id = uuid5(NAMESPACE_URL, f"{dataset_hash}:{policy_hash}")
        result = SimulationResult(
            run_id=run_id,
            dataset_hash=dataset_hash,
            policy_hash=policy_hash,
            config=self.config,
            symbols=self.market.symbols,
        )
        portfolio = SpotPortfolio(
            self.config.initial_capital,
            max_exposure=self.config.max_exposure,
            reserve_ratio=self.config.reserve_ratio,
        )
        grouped: dict[Any, list[Candle]] = defaultdict(list)
        for candle in self.candles:
            grouped[candle.open_time].append(candle)
        clock = HistoricalClock(list(grouped))
        pending: PendingDecision | None = None
        marks: dict[str, Decimal] = {}

        while (event_time := clock.advance()) is not None:
            current = sorted(grouped[event_time], key=lambda item: item.symbol)
            opens = {item.symbol: item.open for item in current}
            if pending is not None and pending.execute_at == event_time:
                self._execute(pending, portfolio, opens, result)
                pending = None

            marks.update({item.symbol: item.close for item in current})
            close_time = max(item.close_time for item in current)
            snapshot = portfolio.snapshot(marks)
            result.equity.append({"simulated_time": close_time, **snapshot})

            decision_time = close_time + timedelta(microseconds=1)
            if decision_time.minute % 15 != 0 or decision_time.second != 0:
                continue
            request = self._decision_request(decision_time, close_time, portfolio, marks)
            raw_response: Any = {"error": "provider did not return"}
            try:
                candidate = self.provider.decide(request)
                raw_response = (
                    candidate.model_dump(mode="json")
                    if isinstance(candidate, DecisionResponse)
                    else candidate
                )
                response = DecisionResponse.model_validate(candidate)
            except (ValidationError, TypeError, ValueError, RuntimeError) as error:
                raw_response = (
                    raw_response
                    if isinstance(raw_response, dict)
                    else {"value": str(raw_response), "error": str(error)}
                )
                response = DecisionResponse.hold("invalid or unavailable provider response")
            result.decisions.append(
                {
                    "simulated_time": decision_time,
                    "available_data_until": close_time,
                    "provider": self.provider.name,
                    "prompt_version": "decision-v1",
                    "input_hash": canonical_hash(request.model_dump(mode="json")),
                    "input_payload": request.model_dump(mode="json"),
                    "raw_response": raw_response,
                    "normalized_response": response.model_dump(mode="json"),
                }
            )
            pending = PendingDecision(response, decision_time, len(result.decisions) - 1)

        if result.equity:
            final = Decimal(str(result.equity[-1]["equity_usdt"]))
            sells = [fill.realized_pnl for fill in result.fills if fill.side == "SELL"]
            wins = [value for value in sells if value > 0]
            losses = [value for value in sells if value < 0]
            snapshots = result.equity
            exposures = [
                (Decimal(str(point["equity_usdt"])) - Decimal(str(point["usdt"])))
                / Decimal(str(point["equity_usdt"]))
                for point in snapshots
                if Decimal(str(point["equity_usdt"])) > 0
            ]
            usdt_points = sum(1 for point in snapshots if point["asset_symbol"] is None)
            gross_profit = sum(wins, Decimal("0"))
            gross_loss = abs(sum(losses, Decimal("0")))
            result.metrics = {
                "final_equity_usdt": final,
                "net_return": final / self.config.initial_capital - Decimal("1"),
                "realized_pnl": portfolio.state.realized_pnl,
                "unrealized_pnl": Decimal(str(result.equity[-1]["unrealized_pnl"])),
                "max_drawdown": portfolio.state.max_drawdown,
                "fees": portfolio.state.fees,
                "slippage": sum((fill.slippage_cost for fill in result.fills), Decimal("0")),
                "turnover": sum((fill.quote_value for fill in result.fills), Decimal("0"))
                / self.config.initial_capital,
                "fill_count": Decimal(len(result.fills)),
                "rotation_count": Decimal(
                    sum(1 for order in result.orders if order["action"] == Action.ROTATE_ASSET)
                ),
                "time_in_usdt_ratio": Decimal(usdt_points) / Decimal(len(snapshots)),
                "time_in_crypto_ratio": Decimal(len(snapshots) - usdt_points)
                / Decimal(len(snapshots)),
                "win_rate": Decimal(len(wins)) / Decimal(len(sells)) if sells else Decimal("0"),
                "payoff": (
                    (gross_profit / Decimal(len(wins))) / (gross_loss / Decimal(len(losses)))
                    if wins and losses
                    else Decimal("0")
                ),
                "expectancy": sum(sells, Decimal("0")) / Decimal(len(sells))
                if sells
                else Decimal("0"),
                "profit_factor": gross_profit / gross_loss if gross_loss else Decimal("0"),
                "average_exposure": sum(exposures, Decimal("0")) / Decimal(len(exposures)),
                "max_exposure_observed": max(exposures, default=Decimal("0")),
                "max_drawdown_duration_candles": Decimal(_max_drawdown_duration(snapshots)),
            }
        return result

    def _decision_request(
        self,
        decision_time: Any,
        cutoff: Any,
        portfolio: SpotPortfolio,
        marks: dict[str, Decimal],
    ) -> DecisionRequest:
        symbols: dict[str, Any] = {}
        for symbol in self.market.symbols:
            visible = self.market.visible_candles(
                symbol,
                simulated_time=decision_time,
                available_until=cutoff,
                lookback=timedelta(days=90),
            )
            contexts: dict[str, Any] = {
                "5m": [item.model_dump(mode="json") for item in visible[-12:]]
            }
            for minutes in (15, 30, 60):
                aggregated = aggregate_candles(visible, minutes)
                contexts[f"{minutes}m"] = [item.model_dump(mode="json") for item in aggregated[-4:]]
            symbols[symbol] = contexts
        market_context: dict[str, Any] = {
            "symbols": symbols,
            "timeframes": ["5m", "15m", "30m", "60m"],
        }
        if self.complementary_data is not None:
            market_context["complementary"] = self.complementary_data.visible(cutoff)
        return DecisionRequest(
            simulated_time=decision_time,
            available_data_until=cutoff,
            portfolio=portfolio.snapshot(marks),
            market_context=market_context,
            adaptive_memory={"checkpoint_version": 1},
            constraints={
                "max_exposure": str(self.config.max_exposure),
                "reserve_ratio": str(self.config.reserve_ratio),
                "long_only": True,
                "single_asset": True,
            },
        )

    def _execute(
        self,
        pending: PendingDecision,
        portfolio: SpotPortfolio,
        prices: dict[str, Decimal],
        result: SimulationResult,
    ) -> None:
        response = pending.response
        order: dict[str, Any] = {
            "simulated_time": pending.execute_at,
            "decision_index": pending.decision_index,
            "action": response.action,
            "from_symbol": response.from_symbol,
            "to_symbol": response.to_symbol,
            "status": "SKIPPED" if response.action == Action.HOLD else "PENDING",
            "reason": response.reasoning_summary,
        }
        if response.action == Action.HOLD:
            result.orders.append(order)
            return
        try:
            new_fills: list[Fill]
            if response.action == Action.BUY_FROM_USDT:
                assert response.to_symbol is not None
                new_fills = [
                    portfolio.buy(
                        symbol=response.to_symbol,
                        market_price=prices[response.to_symbol],
                        allocation_percent=response.allocation_percent,
                        simulated_time=pending.execute_at,
                        costs=self.config.costs,
                        marks=prices,
                    )
                ]
            elif response.action == Action.SELL_TO_USDT:
                assert response.from_symbol is not None
                new_fills = [
                    portfolio.sell(
                        symbol=response.from_symbol,
                        market_price=prices[response.from_symbol],
                        simulated_time=pending.execute_at,
                        costs=self.config.costs,
                    )
                ]
            else:
                assert response.from_symbol is not None and response.to_symbol is not None
                round_trip_cost = Decimal("2") * (
                    self.config.costs.fee_rate
                    + self.config.costs.spread_rate / Decimal("2")
                    + self.config.costs.slippage_rate
                )
                required_edge = round_trip_cost + self.config.rotation_edge_margin
                if (
                    response.expected_edge_after_costs is None
                    or response.expected_edge_after_costs <= required_edge
                ):
                    raise ExecutionRejected("rotation edge does not clear costs and margin")
                rotation = portfolio.rotate(
                    from_symbol=response.from_symbol,
                    to_symbol=response.to_symbol,
                    prices=prices,
                    allocation_percent=response.allocation_percent,
                    simulated_time=pending.execute_at,
                    costs=self.config.costs,
                )
                new_fills = rotation.fills
                result.failures.extend(rotation.failures)
            result.fills.extend(new_fills)
            order["status"] = (
                "PARTIAL"
                if response.action == Action.ROTATE_ASSET and len(new_fills) == 1
                else "FILLED"
            )
        except (ExecutionRejected, KeyError) as error:
            order["status"] = "REJECTED"
            order["reason"] = str(error)
            result.failures.append(str(error))
        result.orders.append(order)


def _max_drawdown_duration(points: list[dict[str, Any]]) -> int:
    longest = 0
    current = 0
    for point in points:
        if Decimal(str(point["drawdown"])) > 0:
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    return longest
