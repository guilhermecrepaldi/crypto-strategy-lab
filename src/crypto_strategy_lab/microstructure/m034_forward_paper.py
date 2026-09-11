"""Binance-only forward paper diagnostic for M034.

The module has no trading transport. It consumes the existing public-market
authority, applies the canonical M034 gate and preserves every raw observation.
Unknown estimators and costs remain blocking inputs rather than zeroes.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import time
from collections import Counter, deque
from collections.abc import Callable, Mapping
from contextlib import AbstractContextManager
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal
from enum import StrEnum
from pathlib import Path
from typing import Any, Protocol

from crypto_strategy_lab.microstructure.adaptive_multi_stable_manager import priority_class
from crypto_strategy_lab.microstructure.economic_eligibility import (
    BPS,
    BinancePairEvidence,
    BinancePairUniverse,
    CapitalState,
    CapitalStateRecord,
    CausalAssetMarkRegistry,
    DataState,
    DecisionIntent,
    DecisionReasonCode,
    EconomicCandidate,
    EconomicEligibilityGate,
    EconomicExecutionPolicy,
    EligibilityDecision,
    EligibilityDecisionLedger,
    EvaluationMode,
    FeeLeg,
    M034EconomicAllocationEngine,
    M034Policy,
    MarketRegimeSnapshot,
    RuleEvidenceStatus,
    ThresholdDefinition,
    ThresholdRegistry,
    ThresholdSourceType,
    UnknownCostPolicy,
    VenuePairFeeRegistry,
    VenuePairRuleRegistry,
    VenueSymbolRuleRecord,
)
from crypto_strategy_lab.microstructure.multi_stable_ledger import SlotLedger
from crypto_strategy_lab.microstructure.multi_stable_models import ZERO, CausalAssetMark, D
from crypto_strategy_lab.microstructure.multi_venue_models import (
    BookKey,
    FeeEvidenceStatus,
    Venue,
    VenueFeeProfile,
    VenueRoute,
    VenueRouteLeg,
    VenueSymbolRule,
)
from crypto_strategy_lab.microstructure.public_calibration import BookGap, LocalDepth
from crypto_strategy_lab.microstructure.public_market import PublicMarketClient

IDENTITY = "M034_OWNER_DIAGNOSTIC_FORWARD_3H_200USD"
CANONICAL_SYMBOLS = (
    "USDCUSDT",
    "FDUSDUSDT",
    "FDUSDUSDC",
    "USD1USDT",
    "USD1USDC",
    "TUSDUSDT",
    "USDPUSDT",
)
ACCOUNT_CONTEXT = "PUBLIC_REGULAR_USER_NO_BNB_STANDARD_SCHEDULE"


class ForwardDiagnosticError(RuntimeError):
    """Fail-closed diagnostic error."""


class PaperOrderState(StrEnum):
    PENDING_ACTIVATION = "PENDING_ACTIVATION"
    LIVE = "LIVE"
    PARTIAL = "PARTIAL"
    CANCEL_PENDING = "CANCEL_PENDING"
    FILLED = "FILLED"
    CANCELED = "CANCELED"


@dataclass
class PaperMakerOrder:
    order_id: str
    symbol: str
    side: str
    price: D
    quantity: D
    placed_at_us: int
    activation_due_us: int
    queue_ahead: D
    remaining: D
    state: PaperOrderState = PaperOrderState.PENDING_ACTIVATION
    activated_at_us: int | None = None
    cancel_requested_at_us: int | None = None
    cancel_ack_due_us: int | None = None


@dataclass
class PaperQueueCohort:
    symbol: str
    side: str
    price: D
    public_queue_ahead: D
    order_ids: list[str]


class PaperQueueModel:
    """Conservative exact-price FIFO model using only later public trades."""

    def __init__(self) -> None:
        self.orders: dict[str, PaperMakerOrder] = {}
        self.cohorts: dict[tuple[str, str, D], PaperQueueCohort] = {}
        self.consumed_trade_ids: set[tuple[str, int]] = set()

    def place(
        self,
        *,
        order_id: str,
        symbol: str,
        side: str,
        price: D,
        quantity: D,
        now_us: int,
        activation_latency_us: int,
        best_bid: D,
        best_ask: D,
        public_quantity_at_price: D,
    ) -> PaperMakerOrder:
        if order_id in self.orders:
            raise ForwardDiagnosticError("M034_FORWARD_DUPLICATE_PAPER_ORDER")
        if side not in {"BUY", "SELL"} or price <= ZERO or quantity <= ZERO:
            raise ForwardDiagnosticError("M034_FORWARD_INVALID_PAPER_ORDER")
        if activation_latency_us <= 0 or public_quantity_at_price < ZERO:
            raise ForwardDiagnosticError("M034_FORWARD_INVALID_LATENCY_OR_QUEUE")
        if (side == "BUY" and price >= best_ask) or (side == "SELL" and price <= best_bid):
            raise ForwardDiagnosticError("M034_FORWARD_POST_ONLY_WOULD_TAKE")
        order = PaperMakerOrder(
            order_id=order_id,
            symbol=symbol,
            side=side,
            price=price,
            quantity=quantity,
            placed_at_us=now_us,
            activation_due_us=now_us + activation_latency_us,
            queue_ahead=public_quantity_at_price,
            remaining=quantity,
        )
        self.orders[order_id] = order
        cohort_key = (symbol, side, price)
        cohort = self.cohorts.get(cohort_key)
        if cohort is None:
            cohort = PaperQueueCohort(
                symbol=symbol,
                side=side,
                price=price,
                public_queue_ahead=public_quantity_at_price,
                order_ids=[],
            )
            self.cohorts[cohort_key] = cohort
        cohort.order_ids.append(order_id)
        return order

    @staticmethod
    def activate(order: PaperMakerOrder, *, now_us: int, best_bid: D, best_ask: D) -> None:
        if order.state != PaperOrderState.PENDING_ACTIVATION or now_us < order.activation_due_us:
            raise ForwardDiagnosticError("M034_FORWARD_INVALID_ACTIVATION")
        if (order.side == "BUY" and order.price >= best_ask) or (
            order.side == "SELL" and order.price <= best_bid
        ):
            raise ForwardDiagnosticError("M034_FORWARD_POST_ONLY_INVALID_AT_ACTIVATION")
        order.state = PaperOrderState.LIVE
        order.activated_at_us = now_us

    @staticmethod
    def request_cancel(order: PaperMakerOrder, *, now_us: int, cancel_ack_latency_us: int) -> None:
        if order.state not in {PaperOrderState.LIVE, PaperOrderState.PARTIAL}:
            raise ForwardDiagnosticError("M034_FORWARD_INVALID_CANCEL_REQUEST")
        if cancel_ack_latency_us <= 0:
            raise ForwardDiagnosticError("M034_FORWARD_INVALID_CANCEL_LATENCY")
        order.state = PaperOrderState.CANCEL_PENDING
        order.cancel_requested_at_us = now_us
        order.cancel_ack_due_us = now_us + cancel_ack_latency_us

    @staticmethod
    def acknowledge_cancel(order: PaperMakerOrder, *, now_us: int) -> None:
        if (
            order.state != PaperOrderState.CANCEL_PENDING
            or order.cancel_ack_due_us is None
            or now_us < order.cancel_ack_due_us
        ):
            raise ForwardDiagnosticError("M034_FORWARD_CANCEL_ACK_NOT_DUE")
        order.state = PaperOrderState.CANCELED

    def consume_trade(
        self,
        *,
        symbol: str,
        trade_id: int,
        price: D,
        quantity: D,
        buyer_is_maker: bool,
        trade_time_us: int,
    ) -> dict[str, D]:
        trade_key = (symbol, trade_id)
        if trade_key in self.consumed_trade_ids:
            raise ForwardDiagnosticError("M034_FORWARD_DUPLICATE_PUBLIC_TRADE")
        if price <= ZERO or quantity <= ZERO or trade_time_us <= 0:
            raise ForwardDiagnosticError("M034_FORWARD_INVALID_PUBLIC_TRADE")
        self.consumed_trade_ids.add(trade_key)
        left = quantity
        fills: dict[str, D] = {}
        side = "BUY" if buyer_is_maker else "SELL"
        cohort = self.cohorts.get((symbol, side, price))
        if cohort is None:
            return fills
        eligible_orders: list[PaperMakerOrder] = []
        for order_id in cohort.order_ids:
            order = self.orders[order_id]
            activated_at_us = order.activated_at_us
            if (
                order.state
                in {
                    PaperOrderState.LIVE,
                    PaperOrderState.PARTIAL,
                    PaperOrderState.CANCEL_PENDING,
                }
                and activated_at_us is not None
                and trade_time_us >= activated_at_us
            ):
                eligible_orders.append(order)
        if not eligible_orders:
            return fills
        ahead = min(cohort.public_queue_ahead, left)
        cohort.public_queue_ahead -= ahead
        left -= ahead
        for order_id in cohort.order_ids:
            self.orders[order_id].queue_ahead = cohort.public_queue_ahead
        if left <= ZERO:
            return fills
        for order in sorted(eligible_orders, key=lambda row: (row.placed_at_us, row.order_id)):
            own_fill = min(order.remaining, left)
            if own_fill > ZERO:
                order.remaining -= own_fill
                left -= own_fill
                fills[order.order_id] = own_fill
                order.state = (
                    PaperOrderState.FILLED
                    if order.remaining == ZERO
                    else (
                        PaperOrderState.CANCEL_PENDING
                        if order.cancel_requested_at_us is not None
                        else PaperOrderState.PARTIAL
                    )
                )
            if left <= ZERO:
                break
        return fills


@dataclass(frozen=True)
class DiagnosticConfig:
    identity: str
    source_sha: str
    source_review_status: str
    source_review_artifact: str
    source_review_sha256: str
    run_claim_artifact: str
    duration_seconds: int
    warmup_seconds: int
    initial_equity_usdt: D
    slot_base_usdt: D
    decision_interval_seconds: int
    activation_latency_us: int
    cancel_ack_latency_us: int
    max_book_age_us: int
    flow_window_seconds: int
    depth_band_bps: D
    max_stream_silence_seconds: int
    rule_refresh_seconds: int
    max_market_clock_lead_us: int
    max_market_clock_lag_us: int
    fee_maker_rate: D
    fee_taker_rate: D
    fee_evidence_status: str
    fee_source_reference: str
    fee_evidence_artifact: str
    fee_evidence_sha256: str
    fee_applicable_symbols: tuple[str, ...]
    fee_observed_at_us: int
    thresholds: tuple[ThresholdDefinition, ...]

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> DiagnosticConfig:
        threshold_rows = payload.get("thresholds")
        if not isinstance(threshold_rows, list):
            raise ForwardDiagnosticError("M034_FORWARD_THRESHOLDS_REQUIRED")
        definitions = tuple(
            ThresholdDefinition(
                name=str(row["name"]),
                value=D(str(row["value"])),
                unit=str(row["unit"]),
                source_type=ThresholdSourceType(str(row["source_type"])),
                source_reference=str(row["source_reference"]),
                derivation_method=str(row["derivation_method"]),
                calibration_dataset_hash=(
                    None
                    if row.get("calibration_dataset_hash") is None
                    else str(row["calibration_dataset_hash"])
                ),
                effective_from_us=int(row["effective_from_us"]),
                frozen_at_us=int(row["frozen_at_us"]),
            )
            for row in threshold_rows
        )
        config = cls(
            identity=str(payload["identity"]),
            source_sha=str(payload["source_sha"]),
            source_review_status=str(payload["source_review_status"]),
            source_review_artifact=str(payload["source_review_artifact"]),
            source_review_sha256=str(payload["source_review_sha256"]),
            run_claim_artifact=str(payload["run_claim_artifact"]),
            duration_seconds=int(payload["duration_seconds"]),
            warmup_seconds=int(payload["warmup_seconds"]),
            initial_equity_usdt=D(str(payload["initial_equity_usdt"])),
            slot_base_usdt=D(str(payload["slot_base_usdt"])),
            decision_interval_seconds=int(payload["decision_interval_seconds"]),
            activation_latency_us=int(payload["activation_latency_us"]),
            cancel_ack_latency_us=int(payload["cancel_ack_latency_us"]),
            max_book_age_us=int(payload["max_book_age_us"]),
            flow_window_seconds=int(payload["flow_window_seconds"]),
            depth_band_bps=D(str(payload["depth_band_bps"])),
            max_stream_silence_seconds=int(payload["max_stream_silence_seconds"]),
            rule_refresh_seconds=int(payload["rule_refresh_seconds"]),
            max_market_clock_lead_us=int(payload["max_market_clock_lead_us"]),
            max_market_clock_lag_us=int(payload["max_market_clock_lag_us"]),
            fee_maker_rate=D(str(payload["fee_maker_rate"])),
            fee_taker_rate=D(str(payload["fee_taker_rate"])),
            fee_evidence_status=str(payload["fee_evidence_status"]),
            fee_source_reference=str(payload["fee_source_reference"]),
            fee_evidence_artifact=str(payload["fee_evidence_artifact"]),
            fee_evidence_sha256=str(payload["fee_evidence_sha256"]),
            fee_applicable_symbols=tuple(str(row) for row in payload["fee_applicable_symbols"]),
            fee_observed_at_us=int(payload["fee_observed_at_us"]),
            thresholds=definitions,
        )
        config.validate()
        return config

    def validate(self) -> None:
        if self.identity != IDENTITY:
            raise ForwardDiagnosticError("M034_FORWARD_IDENTITY_MISMATCH")
        if (
            len(self.source_sha) != 40
            or self.source_review_status != "PASS_GPT_6_ASTRA"
            or not self.source_review_artifact
            or len(self.source_review_sha256) != 64
            or self.run_claim_artifact
            != "data/m034/M034_OWNER_DIAGNOSTIC_FORWARD_3H_200USD.claim.json"
        ):
            raise ForwardDiagnosticError("M034_FORWARD_SOURCE_REVIEW_REQUIRED")
        if self.duration_seconds != 10_800 or self.warmup_seconds != 900:
            raise ForwardDiagnosticError("M034_FORWARD_FIXED_WINDOW_REQUIRED")
        if self.initial_equity_usdt != D("200") or self.slot_base_usdt <= ZERO:
            raise ForwardDiagnosticError("M034_FORWARD_BANKROLL_MISMATCH")
        if any(
            value <= 0
            for value in (
                self.decision_interval_seconds,
                self.activation_latency_us,
                self.cancel_ack_latency_us,
                self.max_book_age_us,
                self.flow_window_seconds,
                self.max_stream_silence_seconds,
                self.rule_refresh_seconds,
                self.max_market_clock_lead_us,
                self.max_market_clock_lag_us,
                self.fee_observed_at_us,
            )
        ):
            raise ForwardDiagnosticError("M034_FORWARD_INVALID_TIMING")
        if self.depth_band_bps <= ZERO:
            raise ForwardDiagnosticError("M034_FORWARD_INVALID_DEPTH_BAND")
        if self.fee_evidence_status != FeeEvidenceStatus.PROVEN_FORWARD.value:
            raise ForwardDiagnosticError("M034_FORWARD_FEE_UNPROVEN")
        if (
            not self.fee_source_reference
            or not self.fee_evidence_artifact
            or len(self.fee_evidence_sha256) != 64
            or self.fee_applicable_symbols != CANONICAL_SYMBOLS
            or min(self.fee_maker_rate, self.fee_taker_rate) < ZERO
        ):
            raise ForwardDiagnosticError("M034_FORWARD_INVALID_FEE_EVIDENCE")
        ThresholdRegistry(list(self.thresholds))

    @property
    def threshold_registry(self) -> ThresholdRegistry:
        return ThresholdRegistry(list(self.thresholds))

    @property
    def threshold_config_hash(self) -> str:
        return self.threshold_registry.config_hash

    @property
    def configuration_hash(self) -> str:
        payload = {
            "identity": self.identity,
            "source_sha": self.source_sha,
            "source_review_status": self.source_review_status,
            "source_review_artifact": self.source_review_artifact,
            "source_review_sha256": self.source_review_sha256,
            "run_claim_artifact": self.run_claim_artifact,
            "duration_seconds": self.duration_seconds,
            "warmup_seconds": self.warmup_seconds,
            "initial_equity_usdt": str(self.initial_equity_usdt),
            "slot_base_usdt": str(self.slot_base_usdt),
            "decision_interval_seconds": self.decision_interval_seconds,
            "activation_latency_us": self.activation_latency_us,
            "cancel_ack_latency_us": self.cancel_ack_latency_us,
            "max_book_age_us": self.max_book_age_us,
            "flow_window_seconds": self.flow_window_seconds,
            "depth_band_bps": str(self.depth_band_bps),
            "max_stream_silence_seconds": self.max_stream_silence_seconds,
            "rule_refresh_seconds": self.rule_refresh_seconds,
            "max_market_clock_lead_us": self.max_market_clock_lead_us,
            "max_market_clock_lag_us": self.max_market_clock_lag_us,
            "fee_maker_rate": str(self.fee_maker_rate),
            "fee_taker_rate": str(self.fee_taker_rate),
            "fee_evidence_status": self.fee_evidence_status,
            "fee_source_reference": self.fee_source_reference,
            "fee_evidence_artifact": self.fee_evidence_artifact,
            "fee_evidence_sha256": self.fee_evidence_sha256,
            "fee_applicable_symbols": list(self.fee_applicable_symbols),
            "fee_observed_at_us": self.fee_observed_at_us,
            "threshold_config_hash": self.threshold_config_hash,
            "unknown_cost_policy": UnknownCostPolicy.REJECT.value,
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()


@dataclass
class SymbolState:
    symbol: str
    base_asset: str
    quote_asset: str
    rule: VenueSymbolRule
    book: LocalDepth
    acquired_at_us: int
    rule_evidence_hash: str
    last_depth_event_us: int | None = None
    last_depth_received_us: int | None = None
    last_depth_received_monotonic_ns: int | None = None
    last_trade_event_us: int | None = None
    last_trade_received_us: int | None = None
    last_trade_id: int | None = None
    trades: deque[tuple[int, D]] | None = None
    gaps: int = 0

    def __post_init__(self) -> None:
        if self.trades is None:
            self.trades = deque()

    def flow_per_second(self, *, now_us: int, window_seconds: int) -> D:
        assert self.trades is not None
        cutoff = now_us - window_seconds * 1_000_000
        while self.trades and self.trades[0][0] < cutoff:
            self.trades.popleft()
        return sum((quantity for _, quantity in self.trades), ZERO) / D(window_seconds)


class StreamConnection(Protocol):
    def recv(self, timeout: float | None = None) -> str | bytes: ...


class PublicStreamFactory(Protocol):
    def __call__(self, symbols: tuple[str, ...]) -> AbstractContextManager[StreamConnection]: ...


class PublicClient(Protocol):
    last_response: dict[str, Any] | None

    def exchange_info(self, symbol: str) -> dict[str, Any]: ...

    def depth_snapshot(self, symbol: str, *, limit: int = 5000) -> dict[str, Any]: ...


def _event_time_us(data: Mapping[str, Any]) -> int:
    event_type = data.get("e")
    raw = data.get("T") if event_type == "trade" else data.get("E")
    if type(raw) is not int or raw <= 0:
        raise ForwardDiagnosticError("M034_FORWARD_EXCHANGE_TIMESTAMP_REQUIRED")
    normalized = raw * 1000 if raw < 10**15 else raw
    if not 10**14 <= normalized < 10**17:
        raise ForwardDiagnosticError("M034_FORWARD_INVALID_EXCHANGE_TIMESTAMP")
    return normalized


def _decimal(value: Any, name: str) -> D:
    try:
        result = D(str(value))
    except Exception as exc:
        raise ForwardDiagnosticError(f"M034_FORWARD_INVALID_{name}") from exc
    if not result.is_finite():
        raise ForwardDiagnosticError(f"M034_FORWARD_INVALID_{name}")
    return result


def parse_forward_rule(
    payload: Mapping[str, Any], *, symbol: str, acquired_at_us: int
) -> tuple[VenueSymbolRule, dict[str, Any]]:
    symbols = payload.get("symbols")
    if not isinstance(symbols, list) or len(symbols) != 1 or symbols[0].get("symbol") != symbol:
        raise ForwardDiagnosticError("M034_FORWARD_INVALID_EXCHANGE_INFO")
    row = symbols[0]
    if row.get("status") != "TRADING":
        raise ForwardDiagnosticError("M034_FORWARD_SYMBOL_NOT_TRADING")
    filters = {item["filterType"]: item for item in row.get("filters", [])}
    required = {"PRICE_FILTER", "LOT_SIZE"}
    if not required.issubset(filters) or not ({"NOTIONAL", "MIN_NOTIONAL"} & set(filters)):
        raise ForwardDiagnosticError("M034_FORWARD_REQUIRED_FILTER_MISSING")
    notional = filters.get("NOTIONAL") or filters["MIN_NOTIONAL"]
    price_filter = filters["PRICE_FILTER"]
    lot_filter = filters["LOT_SIZE"]
    rule = VenueSymbolRule(
        book=BookKey(Venue.BINANCE, symbol),
        base_asset=str(row["baseAsset"]),
        quote_asset=str(row["quoteAsset"]),
        tick_size=_decimal(price_filter["tickSize"], "TICK_SIZE"),
        quantity_step=_decimal(lot_filter["stepSize"], "STEP_SIZE"),
        minimum_quantity=_decimal(lot_filter["minQty"], "MIN_QTY"),
        minimum_notional=_decimal(notional["minNotional"], "MIN_NOTIONAL"),
        price_precision=int(row["quoteAssetPrecision"]),
        effective_start_us=acquired_at_us,
        effective_end_us=None,
        provenance="BINANCE_EXCHANGE_INFO_FORWARD_OBSERVATION",
    )
    return rule, {"symbol": symbol, "status": row["status"], "filters": row["filters"]}


def _quantize_price(value: D, tick: D) -> D:
    return (value / tick).to_integral_value(rounding=ROUND_HALF_UP) * tick


def _floor_step(value: D, step: D) -> D:
    return (value / step).to_integral_value(rounding=ROUND_DOWN) * step


def _serialize_decision(decision: EligibilityDecision) -> dict[str, Any]:
    result = asdict(decision)
    for key, value in list(result.items()):
        if isinstance(value, Decimal):
            result[key] = str(value)
        elif isinstance(value, StrEnum):
            result[key] = value.value
    result["venue"] = decision.venue.value
    result["pair"] = decision.pair.canonical_id
    result["intent"] = decision.intent.value
    result["safety_state"] = decision.safety_state.value
    result["data_state"] = decision.data_state.value
    result["fee_evidence_status"] = decision.fee_evidence_status.value
    result["decision_reason_codes"] = [row.value for row in decision.decision_reason_codes]
    return result


class ForwardPaperDiagnosticRunner:
    """Run one immutable 15-minute warm-up plus 3-hour economic window."""

    def __init__(
        self,
        *,
        config: DiagnosticConfig,
        public_client: PublicClient,
        stream_factory: PublicStreamFactory,
        wall_time_us: Callable[[], int] | None = None,
        monotonic_ns: Callable[[], int] | None = None,
        claim_artifact: Path | None = None,
    ) -> None:
        self.config = config
        self.public_client = public_client
        self.stream_factory = stream_factory
        self.wall_time_us = wall_time_us or (lambda: time.time_ns() // 1000)
        self.monotonic_ns = monotonic_ns or time.monotonic_ns
        self.claim_artifact = claim_artifact
        self.ledger = SlotLedger({"USDT": config.initial_equity_usdt}, marks_usd={"USDT": D("1")})
        self.decision_ledger = EligibilityDecisionLedger()
        self.paper_queue = PaperQueueModel()
        self.states: dict[str, SymbolState] = {}
        self.pair_status: dict[str, dict[str, Any]] = {}
        self.rejections: Counter[str] = Counter()
        self.event_counts: Counter[str] = Counter()
        self.capital_state_durations_us: Counter[str] = Counter()
        self.last_capital_state = CapitalState.BLOCKED_DATA
        self.last_capital_state_at_us: int | None = None

    def _capture_rules(self) -> list[dict[str, Any]]:
        records = []
        for symbol in CANONICAL_SYMBOLS:
            requested_at_us = self.wall_time_us()
            payload: Mapping[str, Any] | None = None
            try:
                payload = self.public_client.exchange_info(symbol)
                acquired_at_us = self.wall_time_us()
                rule, evidence = parse_forward_rule(
                    payload, symbol=symbol, acquired_at_us=acquired_at_us
                )
            except (ForwardDiagnosticError, OSError, TimeoutError, ValueError) as exc:
                acquired_at_us = self.wall_time_us()
                reason = f"{type(exc).__name__}:{exc}"
                self.pair_status[symbol] = {
                    "state": "INELIGIBLE_RULE_EVIDENCE",
                    "reason": reason,
                }
                records.append(
                    {
                        "symbol": symbol,
                        "requested_at_us": requested_at_us,
                        "acquired_at_us": acquired_at_us,
                        "evidence_status": RuleEvidenceStatus.UNPROVEN.value,
                        "reason": reason,
                        "payload": payload,
                    }
                )
                continue
            evidence_hash = hashlib.sha256(
                json.dumps(evidence, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()
            self.states[symbol] = SymbolState(
                symbol=symbol,
                base_asset=rule.base_asset,
                quote_asset=rule.quote_asset,
                rule=rule,
                book=LocalDepth(expected_symbol=symbol),
                acquired_at_us=acquired_at_us,
                rule_evidence_hash=evidence_hash,
            )
            self.pair_status[symbol] = {
                "state": (
                    "ELIGIBILITY_EVALUATED"
                    if rule.quote_asset == "USDT"
                    else "OBSERVED_NOT_FUNDED_FROM_INITIAL_USDT"
                ),
                "reason": None,
            }
            records.append(
                {
                    "acquired_at_us": acquired_at_us,
                    "requested_at_us": requested_at_us,
                    "source_reference": (
                        "https://data-api.binance.vision/api/v3/exchangeInfo?symbol=" + symbol
                    ),
                    "evidence_status": RuleEvidenceStatus.PROVEN_FORWARD.value,
                    "observation_sha256": evidence_hash,
                    **evidence,
                }
            )
        return records

    def _snapshot_books(self) -> list[dict[str, Any]]:
        snapshots = []
        for symbol, state in self.states.items():
            try:
                payload = self.public_client.depth_snapshot(symbol, limit=5000)
            except (OSError, TimeoutError, ValueError) as exc:
                reason = f"{type(exc).__name__}:{exc}"
                state.book.valid = False
                self.pair_status[symbol] = {
                    "state": "INELIGIBLE_DEPTH_SNAPSHOT",
                    "reason": reason,
                }
                snapshots.append(
                    {
                        "symbol": symbol,
                        "acquired_at_us": self.wall_time_us(),
                        "snapshot": None,
                        "reason": reason,
                    }
                )
                continue
            state.book.snapshot(payload)
            request = self.public_client.last_response or {}
            response_body = request.get("body")
            snapshots.append(
                {
                    "symbol": symbol,
                    "lastUpdateId": payload["lastUpdateId"],
                    "acquired_at_us": self.wall_time_us(),
                    "source_reference": (
                        "https://data-api.binance.vision/api/v3/depth?symbol="
                        + symbol
                        + "&limit=5000"
                    ),
                    "request_evidence": {
                        "url": request.get("url"),
                        "sent_us": request.get("sent_us"),
                        "received_us": request.get("received_us"),
                        "rtt_us": request.get("rtt_us"),
                        "status": request.get("status"),
                        "body_sha256": (
                            hashlib.sha256(response_body.encode()).hexdigest()
                            if isinstance(response_body, str)
                            else None
                        ),
                    },
                    "snapshot": payload,
                }
            )
        return snapshots

    def _refresh_rules(self) -> list[dict[str, Any]]:
        observations: list[dict[str, Any]] = []
        for symbol, state in self.states.items():
            requested_at_us = self.wall_time_us()
            try:
                payload = self.public_client.exchange_info(symbol)
                acquired_at_us = self.wall_time_us()
                rule, evidence = parse_forward_rule(
                    payload, symbol=symbol, acquired_at_us=acquired_at_us
                )
            except (ForwardDiagnosticError, OSError, TimeoutError, ValueError) as exc:
                acquired_at_us = self.wall_time_us()
                reason = f"{type(exc).__name__}:{exc}"
                state.book.valid = False
                self.pair_status[symbol] = {
                    "state": "INELIGIBLE_RULE_REFRESH",
                    "reason": reason,
                }
                observations.append(
                    {
                        "symbol": symbol,
                        "requested_at_us": requested_at_us,
                        "acquired_at_us": acquired_at_us,
                        "evidence_status": RuleEvidenceStatus.UNPROVEN.value,
                        "reason": reason,
                    }
                )
                continue
            evidence_hash = hashlib.sha256(
                json.dumps(evidence, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()
            changed = evidence_hash != state.rule_evidence_hash
            if changed:
                state.rule = rule
                state.acquired_at_us = acquired_at_us
                state.rule_evidence_hash = evidence_hash
                self.event_counts["rule_change"] += 1
            observations.append(
                {
                    "symbol": symbol,
                    "requested_at_us": requested_at_us,
                    "acquired_at_us": acquired_at_us,
                    "changed_since_previous_observation": changed,
                    "observation_sha256": evidence_hash,
                    "source_reference": (
                        "https://data-api.binance.vision/api/v3/exchangeInfo?symbol=" + symbol
                    ),
                    "evidence_status": RuleEvidenceStatus.PROVEN_FORWARD.value,
                    **evidence,
                }
            )
        return observations

    def _gate(self, *, now_us: int) -> EconomicEligibilityGate:
        policy = M034Policy(
            policy_id="M034_OWNER_DIAGNOSTIC_FORWARD_3H_THRESHOLDS",
            provenance="OWNER_DIAGNOSTIC_ASSUMPTION_DIAGNOSTIC_ONLY",
            thresholds=self.config.threshold_registry,
            unknown_cost_policy=UnknownCostPolicy.REJECT,
        )
        execution_policy = EconomicExecutionPolicy(
            economic_venues=frozenset({Venue.BINANCE}),
            policy_id="M034_BINANCE_ONLY_FORWARD_PAPER",
            policy_hash=hashlib.sha256(b"M034_BINANCE_ONLY_FORWARD_PAPER").hexdigest(),
            provenance="OWNER_FORWARD_DIAGNOSTIC_2026_09_11",
        )
        fees = VenuePairFeeRegistry()
        rules = VenuePairRuleRegistry()
        pair_evidence: list[BinancePairEvidence] = []
        for state in self.states.values():
            book = state.rule.book
            fees.add(
                VenueFeeProfile(
                    book=book,
                    maker_rate=self.config.fee_maker_rate,
                    taker_rate=self.config.fee_taker_rate,
                    fee_asset_semantics="RECEIVED_ASSET",
                    effective_start_us=self.config.fee_observed_at_us,
                    effective_end_us=None,
                    provenance="BINANCE_PUBLIC_STANDARD_FORWARD_DIAGNOSTIC",
                    account_tier_assumption=ACCOUNT_CONTEXT,
                    acquired_at_us=self.config.fee_observed_at_us,
                    evidence_status=FeeEvidenceStatus.PROVEN_FORWARD,
                    record_id=f"forward-standard-fee:{state.symbol}",
                    source_reference=self.config.fee_source_reference,
                )
            )
            rules.add(
                VenueSymbolRuleRecord(
                    rule=state.rule,
                    evidence_status=RuleEvidenceStatus.PROVEN_FORWARD,
                    acquired_at_us=state.acquired_at_us,
                    record_id=f"forward-rule:{state.symbol}:{state.acquired_at_us}",
                    source_reference=(
                        "https://data-api.binance.vision/api/v3/exchangeInfo?symbol=" + state.symbol
                    ),
                )
            )
            fresh = (
                state.book.valid
                and state.last_depth_event_us is not None
                and now_us - state.last_depth_event_us <= self.config.max_book_age_us
            )
            pair_evidence.append(
                BinancePairEvidence(
                    book=book,
                    available=True,
                    data_proven=fresh,
                    rules_proven=True,
                    safety_acceptable=True,
                    liquidity_acceptable=fresh,
                    temporal_provenance="FORWARD_BOOK_AND_MARKET_SAFETY_AT_DECISION",
                    effective_start_us=state.acquired_at_us,
                    effective_end_us=None,
                )
            )
        marks = CausalAssetMarkRegistry()
        marks.add(
            CausalAssetMark(
                base_asset="USDT",
                quote_asset="USD",
                rate=D("1"),
                observed_at_us=now_us,
                effective_until_us=now_us,
                record_id=f"diagnostic-usdt-numerary:{now_us}",
                source_reference="OWNER_DIAGNOSTIC_USDT_USD_EQUIVALENT_CONVENTION",
                provenance="ACCOUNTING_NUMERARY_NOT_FIAT_MARK",
            )
        )
        return EconomicEligibilityGate(
            execution_policy=execution_policy,
            policy=policy,
            fee_registry=fees,
            rule_registry=rules,
            pair_universe=BinancePairUniverse(pair_evidence),
            mark_registry=marks,
        )

    def _candidates(self, *, now_us: int) -> list[EconomicCandidate]:
        candidates: list[EconomicCandidate] = []
        for state in self.states.values():
            if state.quote_asset != "USDT":
                continue
            if not state.book.bids or not state.book.asks:
                continue
            bid, ask = max(state.book.bids), min(state.book.asks)
            midpoint = (bid + ask) / D(2)
            hotline = _quantize_price(midpoint, state.rule.tick_size)
            spread_bps = (ask - bid) / midpoint * BPS
            band = midpoint * self.config.depth_band_bps / BPS
            depth_usd = sum(
                (
                    price * quantity
                    for price, quantity in state.book.bids.items()
                    if price >= midpoint - band
                ),
                ZERO,
            ) + sum(
                (
                    price * quantity
                    for price, quantity in state.book.asks.items()
                    if price <= midpoint + band
                ),
                ZERO,
            )
            flow = state.flow_per_second(
                now_us=now_us, window_seconds=self.config.flow_window_seconds
            )
            fresh = (
                state.book.valid
                and state.last_depth_event_us is not None
                and now_us - state.last_depth_event_us <= self.config.max_book_age_us
            )
            market = MarketRegimeSnapshot(
                observed_at_us=state.last_depth_event_us or now_us,
                regime="FORWARD_OBSERVED",
                peg_deviation=midpoint - D(1),
                spread_bps=spread_bps,
                depth_usd=depth_usd,
                compatible_flow_per_second=flow,
                data_gap=not fresh,
            )
            for rank in range(1, 8):
                buy_price = hotline - state.rule.tick_size * rank
                sell_price = hotline + state.rule.tick_size * rank
                quantity = _floor_step(
                    self.config.slot_base_usdt / buy_price,
                    state.rule.quantity_step,
                )
                if quantity <= ZERO:
                    continue
                return_quantity = _floor_step(
                    quantity * (D(1) - self.config.fee_maker_rate),
                    state.rule.quantity_step,
                )
                gross_edge_bps = max((sell_price / buy_price - D(1)) * BPS, ZERO)
                route_id = f"{state.symbol}:BUY_RETURN:{rank}"
                book = state.rule.book
                route = VenueRoute(
                    route_id=route_id,
                    origin_asset="USDT",
                    legs=(
                        VenueRouteLeg(book, "USDT", state.base_asset, True),
                        VenueRouteLeg(book, state.base_asset, "USDT", True),
                    ),
                )
                for column in (1, 2):
                    candidates.append(
                        EconomicCandidate(
                            candidate_id=(f"{state.symbol}:{rank}:{column}:{now_us}"),
                            venue=Venue.BINANCE,
                            pair=book,
                            side="BUY",
                            rank=rank,
                            column=column,
                            route_id=route_id,
                            route=route,
                            inventory_state="FLAT_USDT",
                            intent=DecisionIntent.NEW_ENTRY,
                            priority_class=priority_class(
                                obligation=False,
                                rank=rank,
                                column=column,
                                old_zero_fill=False,
                            ),
                            decision_currency="USDT",
                            decision_time_us=now_us,
                            gross_edge_bps=gross_edge_bps,
                            execution_cost_bps=None,
                            adverse_selection_bps=None,
                            completion_probability=None,
                            expected_lock_seconds=None,
                            p95_lock_seconds=None,
                            capital_required=buy_price * quantity,
                            residual_cost_if_incomplete=ZERO,
                            tail_risk_cost=ZERO,
                            inventory_carry_cost=ZERO,
                            fee_legs=(
                                FeeLeg(
                                    book,
                                    True,
                                    "USDT",
                                    state.base_asset,
                                    "BUY",
                                    buy_price,
                                    quantity,
                                ),
                                FeeLeg(
                                    book,
                                    True,
                                    state.base_asset,
                                    "USDT",
                                    "SELL",
                                    sell_price,
                                    return_quantity,
                                ),
                            ),
                            market=market,
                            data_state=DataState.VALID if fresh else DataState.INVALID,
                            account_context=ACCOUNT_CONTEXT,
                        )
                    )
        return candidates

    def evaluate(self, *, now_us: int) -> tuple[EligibilityDecision, ...]:
        candidates = self._candidates(now_us=now_us)
        if not candidates:
            self.decision_ledger.append_capital_state(
                CapitalStateRecord(
                    timestamp_us=now_us,
                    state=CapitalState.BLOCKED_DATA,
                    capital=self.ledger.free["USDT"],
                    currency="USDT",
                    reason_code=DecisionReasonCode.DATA_INSUFFICIENT,
                )
            )
            self.rejections[DecisionReasonCode.DATA_INSUFFICIENT.value] += 1
        engine = M034EconomicAllocationEngine(
            gate=self._gate(now_us=now_us), decision_ledger=self.decision_ledger
        )
        if candidates:
            result = engine.evaluate_and_allocate(
                candidates,
                mode=EvaluationMode.FORWARD,
                available_capital=self.ledger.free["USDT"],
                available_capital_currency="USDT",
                now_us=now_us,
            )
            decisions = result.decisions
            selected_candidate_ids = result.selected_candidate_ids
        else:
            decisions = ()
            selected_candidate_ids = ()
        if selected_candidate_ids:
            raise ForwardDiagnosticError("M034_FORWARD_UNKNOWN_ESTIMATORS_MUST_BLOCK_ORDERS")
        for decision in decisions:
            for reason in decision.decision_reason_codes:
                if reason.value != "ELIGIBLE":
                    self.rejections[reason.value] += 1
        if self.decision_ledger.capital_states:
            state = self.decision_ledger.capital_states[-1].state
            if self.last_capital_state_at_us is not None:
                self.capital_state_durations_us[self.last_capital_state.value] += (
                    now_us - self.last_capital_state_at_us
                )
            self.last_capital_state = state
            self.last_capital_state_at_us = now_us
        return decisions

    def _apply_event(
        self,
        data: Mapping[str, Any],
        *,
        received_us: int,
        received_monotonic_ns: int,
    ) -> int:
        symbol = str(data.get("s", ""))
        state = self.states.get(symbol)
        if state is None:
            if symbol in CANONICAL_SYMBOLS:
                self.event_counts["ignored_ineligible_pair_event"] += 1
                return _event_time_us(data)
            raise ForwardDiagnosticError("M034_FORWARD_UNEXPECTED_SYMBOL")
        event_time_us = _event_time_us(data)
        event_type = data.get("e")
        if event_type == "depthUpdate":
            try:
                applied = state.book.apply(dict(data))
                if applied:
                    if (
                        state.last_depth_event_us is not None
                        and event_time_us < state.last_depth_event_us
                    ):
                        raise BookGap("DEPTH_TIMESTAMP_REGRESSION")
                    state.last_depth_event_us = event_time_us
                    state.last_depth_received_us = received_us
                    state.last_depth_received_monotonic_ns = received_monotonic_ns
            except BookGap:
                state.gaps += 1
                state.book.valid = False
            self.event_counts["depth"] += 1
        elif event_type == "trade":
            trade_id = data.get("t")
            if type(trade_id) is not int or trade_id < 0:
                raise ForwardDiagnosticError("M034_FORWARD_INVALID_TRADE_ID")
            if state.last_trade_id is not None and trade_id <= state.last_trade_id:
                self.event_counts["trade_duplicate_or_regression"] += 1
                return event_time_us
            quantity = _decimal(data.get("q"), "TRADE_QUANTITY")
            price = _decimal(data.get("p"), "TRADE_PRICE")
            if quantity <= ZERO or price <= ZERO or type(data.get("m")) is not bool:
                raise ForwardDiagnosticError("M034_FORWARD_INVALID_TRADE")
            state.last_trade_id = trade_id
            assert state.trades is not None
            state.trades.append((event_time_us, quantity))
            state.last_trade_event_us = event_time_us
            state.last_trade_received_us = received_us
            self.paper_queue.consume_trade(
                symbol=symbol,
                trade_id=trade_id,
                price=price,
                quantity=quantity,
                buyer_is_maker=bool(data["m"]),
                trade_time_us=event_time_us,
            )
            self.event_counts["trade"] += 1
        else:
            raise ForwardDiagnosticError("M034_FORWARD_UNEXPECTED_EVENT_TYPE")
        return event_time_us

    def run(self, output: Path) -> dict[str, Any]:
        if self.claim_artifact is None or not self.claim_artifact.is_file():
            raise ForwardDiagnosticError("M034_FORWARD_CANONICAL_RUN_CLAIM_REQUIRED")
        claim_sha256 = hashlib.sha256(self.claim_artifact.read_bytes()).hexdigest()
        output.mkdir(parents=True, exist_ok=False)
        configuration_path = output / "configuration.json"
        configuration_path.write_text(
            json.dumps(
                {
                    "identity": self.config.identity,
                    "source_sha": self.config.source_sha,
                    "source_review_artifact": self.config.source_review_artifact,
                    "source_review_sha256": self.config.source_review_sha256,
                    "run_claim_artifact": self.config.run_claim_artifact,
                    "run_claim_sha256": claim_sha256,
                    "threshold_config_hash": self.config.threshold_config_hash,
                    "configuration_hash": self.config.configuration_hash,
                    "duration_seconds": self.config.duration_seconds,
                    "warmup_seconds": self.config.warmup_seconds,
                    "unknown_cost_policy": UnknownCostPolicy.REJECT.value,
                    "estimator_policy": "UNKNOWN_BLOCKS",
                    "depth_band_bps": str(self.config.depth_band_bps),
                    "rule_refresh_seconds": self.config.rule_refresh_seconds,
                    "max_market_clock_lead_us": self.config.max_market_clock_lead_us,
                    "max_market_clock_lag_us": self.config.max_market_clock_lag_us,
                    "fee_evidence_artifact": self.config.fee_evidence_artifact,
                    "fee_evidence_sha256": self.config.fee_evidence_sha256,
                    "fee_applicable_symbols": list(self.config.fee_applicable_symbols),
                    "economic_venue": Venue.BINANCE.value,
                    "kraken": "RETIRED_DISABLED",
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        rules = self._capture_rules()
        rule_path = output / "exchange-rules.json"
        rule_path.write_text(json.dumps(rules, indent=2) + "\n", encoding="utf-8")
        warmup_started_mono = self.monotonic_ns()
        warmup_deadline_mono = warmup_started_mono + self.config.warmup_seconds * 1_000_000_000
        economic_start_us: int | None = None
        economic_start_mono_ns: int | None = None
        economic_end_us: int | None = None
        next_decision_us: int | None = None
        checkpoints: list[dict[str, Any]] = []
        next_checkpoint = 0
        next_rule_refresh_us: int | None = None
        ingest_sequence = 0
        status = "RUNNING"
        failure: str | None = None
        last_message_mono = warmup_started_mono
        market_watermark_us: int | None = None
        validated_market_watermark_us: int | None = None
        raw_path = output / "raw-market.jsonl.gz"
        decisions_path = output / "eligibility-decisions.jsonl.gz"
        try:
            with (
                self.stream_factory(CANONICAL_SYMBOLS) as stream,
                gzip.open(raw_path, "wt", encoding="utf-8") as raw_file,
                gzip.open(decisions_path, "wt", encoding="utf-8") as decision_file,
            ):
                snapshots = self._snapshot_books()
                snapshot_path = output / "depth-snapshots.json"
                snapshot_path.write_text(json.dumps(snapshots, indent=2) + "\n", encoding="utf-8")
                while True:
                    try:
                        message = stream.recv(timeout=1.0)
                    except TimeoutError:
                        if (
                            self.monotonic_ns() - last_message_mono
                            > self.config.max_stream_silence_seconds * 1_000_000_000
                        ):
                            raise ForwardDiagnosticError("M034_FORWARD_STREAM_SILENCE") from None
                        continue
                    received_us = self.wall_time_us()
                    received_mono = self.monotonic_ns()
                    last_message_mono = received_mono
                    payload = json.loads(message)
                    if not isinstance(payload, dict):
                        raise ForwardDiagnosticError("M034_FORWARD_INVALID_STREAM_PAYLOAD")
                    data = payload.get("data", payload)
                    if not isinstance(data, dict):
                        raise ForwardDiagnosticError("M034_FORWARD_INVALID_STREAM_DATA")
                    ingest_sequence += 1
                    event_time_us = _event_time_us(data)
                    market_watermark_us = max(market_watermark_us or event_time_us, event_time_us)
                    included = economic_end_us is None or market_watermark_us < economic_end_us
                    raw_file.write(
                        json.dumps(
                            {
                                "ingest_sequence": ingest_sequence,
                                "received_us": received_us,
                                "received_monotonic_ns": received_mono,
                                "included_before_cutoff": included,
                                "payload": data,
                            },
                            separators=(",", ":"),
                        )
                        + "\n"
                    )
                    if economic_start_us is not None and economic_start_mono_ns is not None:
                        market_elapsed_us = market_watermark_us - economic_start_us
                        monotonic_elapsed_us = (received_mono - economic_start_mono_ns) // 1000
                        if (
                            market_elapsed_us
                            > monotonic_elapsed_us + self.config.max_market_clock_lead_us
                        ):
                            raise ForwardDiagnosticError("M034_FORWARD_MARKET_CLOCK_JUMP")
                        if (
                            monotonic_elapsed_us
                            > market_elapsed_us + self.config.max_market_clock_lag_us
                        ):
                            raise ForwardDiagnosticError("M034_FORWARD_MARKET_CLOCK_STALLED")
                        validated_market_watermark_us = market_watermark_us
                        if economic_end_us is not None and market_watermark_us >= economic_end_us:
                            if monotonic_elapsed_us < self.config.duration_seconds * 1_000_000:
                                raise ForwardDiagnosticError("M034_FORWARD_THREE_HOURS_NOT_ELAPSED")
                            break
                    self._apply_event(
                        data,
                        received_us=received_us,
                        received_monotonic_ns=received_mono,
                    )
                    if economic_start_us is None and received_mono >= warmup_deadline_mono:
                        economic_start_us = market_watermark_us
                        economic_start_mono_ns = received_mono
                        validated_market_watermark_us = market_watermark_us
                        economic_end_us = (
                            economic_start_us + self.config.duration_seconds * 1_000_000
                        )
                        next_decision_us = economic_start_us
                        next_checkpoint = 0
                        next_rule_refresh_us = (
                            economic_start_us + self.config.rule_refresh_seconds * 1_000_000
                        )
                    if economic_start_us is None or next_decision_us is None:
                        continue
                    if (
                        next_rule_refresh_us is not None
                        and market_watermark_us >= next_rule_refresh_us
                    ):
                        rules.extend(self._refresh_rules())
                        next_rule_refresh_us = (
                            market_watermark_us + self.config.rule_refresh_seconds * 1_000_000
                        )
                    if market_watermark_us >= next_decision_us:
                        decisions = self.evaluate(now_us=market_watermark_us)
                        for decision in decisions:
                            decision_file.write(
                                json.dumps(_serialize_decision(decision), separators=(",", ":"))
                                + "\n"
                            )
                        next_decision_us = (
                            market_watermark_us + self.config.decision_interval_seconds * 1_000_000
                        )
                    while next_checkpoint <= 5 and market_watermark_us >= economic_start_us + (
                        next_checkpoint * 1_800_000_000
                    ):
                        checkpoint_time_us = economic_start_us + next_checkpoint * 1_800_000_000
                        checkpoints.append(
                            {
                                "offset_seconds": next_checkpoint * 1800,
                                "timestamp_us": checkpoint_time_us,
                                "realized_equity_usd": "200.00",
                                "marked_equity_usd": "200.00",
                                "free_capital_usdt": str(self.ledger.free["USDT"]),
                                "reserved_capital_usdt": "0",
                                "inventory_value_usd": "0",
                                "physical_cycles": 0,
                            }
                        )
                        next_checkpoint += 1
                assert economic_start_us is not None and economic_end_us is not None
                while next_checkpoint <= 5:
                    checkpoints.append(
                        {
                            "offset_seconds": next_checkpoint * 1800,
                            "timestamp_us": (economic_start_us + next_checkpoint * 1_800_000_000),
                            "realized_equity_usd": "200.00",
                            "marked_equity_usd": "200.00",
                            "free_capital_usdt": str(self.ledger.free["USDT"]),
                            "reserved_capital_usdt": "0",
                            "inventory_value_usd": "0",
                            "physical_cycles": 0,
                        }
                    )
                    next_checkpoint += 1
                checkpoints.append(
                    {
                        "offset_seconds": 10800,
                        "timestamp_us": economic_end_us,
                        "realized_equity_usd": "200.00",
                        "marked_equity_usd": "200.00",
                        "free_capital_usdt": str(self.ledger.free["USDT"]),
                        "reserved_capital_usdt": "0",
                        "inventory_value_usd": "0",
                        "physical_cycles": 0,
                    }
                )
                status = "COMPLETE"
        except Exception as exc:
            status = "INVALIDATED_TECHNICAL"
            failure = f"{type(exc).__name__}:{exc}"
        observed_end_us = (
            None
            if economic_start_us is None or validated_market_watermark_us is None
            else min(
                validated_market_watermark_us,
                economic_end_us or validated_market_watermark_us,
            )
        )
        if economic_start_us is not None and self.last_capital_state_at_us is not None:
            duration_end = observed_end_us or self.last_capital_state_at_us
            self.capital_state_durations_us[self.last_capital_state.value] += max(
                0, duration_end - self.last_capital_state_at_us
            )
        duration_us = (
            0
            if economic_start_us is None or observed_end_us is None
            else max(0, observed_end_us - economic_start_us)
        )
        blocked_data_us = self.capital_state_durations_us[CapitalState.BLOCKED_DATA.value]
        idle_us = self.capital_state_durations_us[CapitalState.IDLE_NO_ELIGIBLE_OPPORTUNITY.value]
        result: dict[str, Any] = {
            "schema": "m034-owner-diagnostic-forward-paper-v1",
            "identity": self.config.identity,
            "scientific_status": "OWNER_DIAGNOSTIC_FORWARD_PAPER",
            "status": status,
            "failure": failure,
            "source_sha": self.config.source_sha,
            "source_review_status": self.config.source_review_status,
            "threshold_config_hash": self.config.threshold_config_hash,
            "configuration_hash": self.config.configuration_hash,
            "RUN_CLAIM_ARTIFACT": self.config.run_claim_artifact,
            "RUN_CLAIM_SHA256": claim_sha256,
            "START_TIMESTAMP_US": economic_start_us,
            "END_TIMESTAMP_US": observed_end_us,
            "PLANNED_END_TIMESTAMP_US": economic_end_us,
            "INITIAL_BANK_USD": "200.00",
            "DURATION_HOURS": str((D(duration_us) / D(3_600_000_000)).quantize(D("0.001"))),
            "PHYSICAL_CYCLES": 0,
            "SLOT_EQUIVALENT_CYCLES": 0,
            "GROSS_REALIZED_PNL_USD": "0.0000",
            "FEES_PAID_USD": "0.0000",
            "NET_REALIZED_PNL_USD": "0.0000",
            "REALIZED_RETURN_PCT": "0.0000",
            "FINAL_REALIZED_EQUITY_USD": "200.0000",
            "UNREALIZED_PNL_USD": "0.0000",
            "FINAL_MARKED_EQUITY_USD": "200.0000",
            "MARKED_RETURN_PCT": "0.0000",
            "CAPITAL_UTILIZATION_PCT": "0.00",
            "IDLE_NO_OPPORTUNITY_PCT": str(
                (ZERO if not duration_us else D(idle_us) / D(duration_us) * D(100)).quantize(
                    D("0.01")
                )
            ),
            "BLOCKED_DATA_OR_ESTIMATOR_PCT": str(
                (
                    ZERO if not duration_us else D(blocked_data_us) / D(duration_us) * D(100)
                ).quantize(D("0.01"))
            ),
            "MEDIAN_SLOT_TURNOVER_SEC": None,
            "P90_SLOT_TURNOVER_SEC": None,
            "P95_SLOT_TURNOVER_SEC": None,
            "MAX_CAPITAL_LOCK_USD": "0.00",
            "FINAL_RESIDUAL_INVENTORY": {},
            "ELIGIBILITY_EVALUATIONS": len(self.decision_ledger.decisions),
            "ELIGIBLE_COUNT": sum(row.eligible for row in self.decision_ledger.decisions),
            "REJECTED_COUNT": sum(not row.eligible for row in self.decision_ledger.decisions),
            "REJECTION_REASONS": dict(sorted(self.rejections.items())),
            "CAPITAL_STATE_DURATIONS_US": dict(sorted(self.capital_state_durations_us.items())),
            "EVENT_COUNTS": dict(sorted(self.event_counts.items())),
            "BOOK_GAPS": {symbol: state.gaps for symbol, state in self.states.items()},
            "PAIR_STATUS": dict(sorted(self.pair_status.items())),
            "checkpoints": checkpoints,
            "cycles": [],
            "ECONOMIC_REPLAY_RUNS": 0,
            "REAL_ORDER_COUNT": 0,
            "TESTNET_ORDER_COUNT": 0,
            "STRATEGY_PASS": False,
        }
        result_path = output / "result.json"
        result_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        rule_path.write_text(json.dumps(rules, indent=2) + "\n", encoding="utf-8")
        files = []
        for path in sorted(output.iterdir()):
            if path.is_file() and path.name != "manifest.json":
                files.append(
                    {
                        "path": str(path),
                        "bytes": path.stat().st_size,
                        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                    }
                )
        manifest = {
            "identity": self.config.identity,
            "created_at": datetime.now(UTC).isoformat(),
            "status": status,
            "files": files,
            "real_order_endpoints_present": False,
            "run_claim_artifact": self.config.run_claim_artifact,
            "run_claim_sha256": claim_sha256,
        }
        (output / "manifest.json").write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )
        return result


def load_config(path: Path) -> DiagnosticConfig:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ForwardDiagnosticError("M034_FORWARD_CONFIG_MUST_BE_OBJECT")
    return DiagnosticConfig.from_mapping(payload)


def claim_identity(config: DiagnosticConfig, output_path: Path, *, root: Path) -> Path:
    marker = (root / config.run_claim_artifact).resolve()
    if root.resolve() not in marker.parents:
        raise ForwardDiagnosticError("M034_FORWARD_RUN_CLAIM_OUTSIDE_REPOSITORY")
    marker.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "identity": config.identity,
        "claimed_at": datetime.now(UTC).isoformat(),
        "source_sha": config.source_sha,
        "configuration_hash": config.configuration_hash,
        "output": str(output_path),
        "rule": "ONE_SHOT_PRESERVE_ON_SUCCESS_OR_FAILURE",
    }
    try:
        with marker.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(payload, stream, indent=2)
            stream.write("\n")
    except FileExistsError as exc:
        raise ForwardDiagnosticError("M034_FORWARD_IDENTITY_ALREADY_CLAIMED") from exc
    return marker


def default_public_client() -> PublicMarketClient:
    return PublicMarketClient()


__all__ = [
    "ACCOUNT_CONTEXT",
    "CANONICAL_SYMBOLS",
    "IDENTITY",
    "DiagnosticConfig",
    "ForwardDiagnosticError",
    "ForwardPaperDiagnosticRunner",
    "PaperMakerOrder",
    "PaperOrderState",
    "PaperQueueModel",
    "claim_identity",
    "load_config",
    "parse_forward_rule",
]
