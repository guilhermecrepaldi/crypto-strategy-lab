"""Exchange-native to canonical market-event adapters for M033."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

from crypto_strategy_lab.microstructure.multi_venue_models import (
    BookKey,
    CanonicalBookDelta,
    CanonicalTrade,
    D,
    L3EventType,
    L3OrderEvent,
    Venue,
    VenueLatencyProfile,
    VenueOrderSemantics,
    VenueSymbolRule,
)


def _time_us(value: str | int | float) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value * 1_000_000)
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return int(parsed.timestamp() * 1_000_000)


class ExchangeAdapter(ABC):
    venue: Venue

    @abstractmethod
    def order_semantics(self) -> VenueOrderSemantics:
        raise NotImplementedError

    @abstractmethod
    def conservative_latency_profile(self) -> VenueLatencyProfile:
        raise NotImplementedError

    @abstractmethod
    def normalize_l2_row(self, row: dict[str, Any]) -> CanonicalBookDelta:
        raise NotImplementedError

    @abstractmethod
    def normalize_trade_row(self, row: dict[str, Any]) -> CanonicalTrade:
        raise NotImplementedError


class BinanceL2Adapter(ExchangeAdapter):
    venue = Venue.BINANCE

    def order_semantics(self) -> VenueOrderSemantics:
        return VenueOrderSemantics(
            venue=self.venue,
            post_only_mechanism="LIMIT_MAKER",
            cancel_releases_on_ack_only=True,
            quantity_decrease_priority="HISTORICALLY_UNPROVEN",
            quantity_increase_priority="HISTORICALLY_UNPROVEN",
            price_change_priority="HISTORICALLY_UNPROVEN",
            chained_unacknowledged_actions="HISTORICALLY_UNPROVEN",
            provenance=("inherited M032 Binance L2 semantics",),
        )

    def conservative_latency_profile(self) -> VenueLatencyProfile:
        return VenueLatencyProfile(
            venue=self.venue,
            market_data_latency_us=None,
            order_submit_latency_us=None,
            order_ack_latency_us=None,
            cancel_latency_us=None,
            cancel_ack_latency_us=None,
            provenance="M033: no precise historical Binance latency evidence selected",
        )

    def normalize_l2_row(self, row: dict[str, Any]) -> CanonicalBookDelta:
        return CanonicalBookDelta(
            book=BookKey(self.venue, str(row["symbol"])),
            side=str(row["side"]).upper(),
            price=D(str(row["price"])),
            quantity=D(str(row["amount"])),
            exchange_time_us=int(row["timestamp"]),
            local_capture_time_us=int(row.get("local_timestamp", row["timestamp"])),
            update_id=str(row.get("update_id", row["timestamp"])),
        )

    def normalize_trade_row(self, row: dict[str, Any]) -> CanonicalTrade:
        side = row.get("side")
        return CanonicalTrade(
            book=BookKey(self.venue, str(row["symbol"])),
            trade_id=str(row.get("id", row.get("trade_id", row["timestamp"]))),
            price=D(str(row["price"])),
            quantity=D(str(row["amount"])),
            aggressor_side=str(side).upper() if side else None,
            exchange_time_us=int(row["timestamp"]),
            local_capture_time_us=int(row.get("local_timestamp", row["timestamp"])),
        )


class KrakenSpotAdapter(ExchangeAdapter):
    venue = Venue.KRAKEN

    def order_semantics(self) -> VenueOrderSemantics:
        return VenueOrderSemantics(
            venue=self.venue,
            post_only_mechanism="post_only order flag",
            cancel_releases_on_ack_only=True,
            quantity_decrease_priority="PRESERVED",
            quantity_increase_priority="LOST_BACK_OF_QUEUE",
            price_change_priority="LOST_BACK_OF_NEW_PRICE_QUEUE",
            chained_unacknowledged_actions="NON_DETERMINISTIC_DO_NOT_CHAIN",
            provenance=(
                "https://docs.kraken.com/exchange/guides/general/amends",
                "https://docs.kraken.com/exchange/api-reference/spot-websocket-v2/add_order",
            ),
        )

    def conservative_latency_profile(self) -> VenueLatencyProfile:
        return VenueLatencyProfile(
            venue=self.venue,
            market_data_latency_us=None,
            order_submit_latency_us=None,
            order_ack_latency_us=None,
            cancel_latency_us=None,
            cancel_ack_latency_us=None,
            provenance="M033: no precise historical Kraken latency evidence selected",
        )

    def normalize_l2_row(self, row: dict[str, Any]) -> CanonicalBookDelta:
        return CanonicalBookDelta(
            book=BookKey(self.venue, str(row["symbol"]).replace("-", "/")),
            side=str(row["side"]).upper(),
            price=D(str(row["price"])),
            quantity=D(str(row["amount"])),
            exchange_time_us=int(row["timestamp"]),
            local_capture_time_us=int(row.get("local_timestamp", row["timestamp"])),
            update_id=str(row.get("update_id", row["timestamp"])),
        )

    def normalize_trade_row(self, row: dict[str, Any]) -> CanonicalTrade:
        side = row.get("side")
        return CanonicalTrade(
            book=BookKey(self.venue, str(row["symbol"]).replace("-", "/")),
            trade_id=str(row.get("id", row.get("trade_id", row["timestamp"]))),
            price=D(str(row["price"])),
            quantity=D(str(row["amount"])),
            aggressor_side=str(side).upper() if side else None,
            exchange_time_us=int(row["timestamp"]),
            local_capture_time_us=int(row.get("local_timestamp", row["timestamp"])),
        )

    @staticmethod
    def normalize_l3_message(
        message: dict[str, Any], *, local_capture_time_us: int, sequence_start: int
    ) -> tuple[L3OrderEvent, ...]:
        if message.get("channel") != "level3" or message.get("type") not in {
            "snapshot",
            "update",
        }:
            raise ValueError("M033_NOT_KRAKEN_LEVEL3_MESSAGE")
        events: list[L3OrderEvent] = []
        sequence = sequence_start
        for payload in message.get("data", []):
            book = BookKey(Venue.KRAKEN, str(payload["symbol"]))
            exchange_time = _time_us(payload.get("timestamp", local_capture_time_us))
            for side_key, side in (("bids", "BUY"), ("asks", "SELL")):
                for raw in payload.get(side_key, []):
                    native_event = str(
                        raw.get("event", "add" if message["type"] == "snapshot" else "")
                    )
                    try:
                        event_type = L3EventType(native_event.upper())
                    except ValueError as exc:
                        raise ValueError("M033_UNKNOWN_KRAKEN_L3_EVENT") from exc
                    order_time = _time_us(raw["timestamp"])
                    order_id = str(raw["order_id"])
                    events.append(
                        L3OrderEvent(
                            book=book,
                            event_id=f"{book.canonical_id}:{sequence}:{order_id}:{event_type.value}",
                            event_type=event_type,
                            side=side,
                            price=D(str(raw["limit_price"])),
                            order_id=order_id,
                            remaining_quantity=D(str(raw["order_qty"])),
                            order_entry_time_us=order_time,
                            exchange_time_us=exchange_time,
                            local_capture_time_us=local_capture_time_us,
                            message_sequence=sequence,
                        )
                    )
                    sequence += 1
        return tuple(events)

    @staticmethod
    def rule_from_asset_pairs(payload: dict[str, Any], *, as_of_us: int) -> VenueSymbolRule:
        if payload.get("error"):
            raise ValueError("M033_KRAKEN_ASSET_PAIRS_ERROR")
        rows = payload.get("result", {})
        matching = [row for row in rows.values() if row.get("wsname") == "USDC/USDT"]
        if len(matching) != 1:
            raise ValueError("M033_KRAKEN_USDC_USDT_RULE_NOT_UNIQUE")
        row = matching[0]
        return VenueSymbolRule(
            book=BookKey(Venue.KRAKEN, row["wsname"]),
            base_asset="USDC",
            quote_asset="USDT",
            tick_size=D(str(row["tick_size"])),
            quantity_step=D(1).scaleb(-int(row["lot_decimals"])),
            minimum_quantity=D(str(row["ordermin"])),
            minimum_notional=D(str(row["costmin"])),
            price_precision=int(row["pair_decimals"]),
            effective_start_us=as_of_us,
            effective_end_us=None,
            provenance="Kraken public REST /0/public/AssetPairs current snapshot",
        )


__all__ = ["BinanceL2Adapter", "ExchangeAdapter", "KrakenSpotAdapter"]
