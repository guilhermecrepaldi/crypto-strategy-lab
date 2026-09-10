"""Independent physical venue ledgers and aggregate reporting for M033."""

from __future__ import annotations

from decimal import Decimal

from crypto_strategy_lab.microstructure.multi_stable_ledger import SlotLedger
from crypto_strategy_lab.microstructure.multi_venue_models import Venue, VenueRoute

D = Decimal


class MultiVenuePortfolio:
    """Own one M032-compatible ledger per venue; never lends across venues."""

    def __init__(self) -> None:
        self.ledgers: dict[Venue, SlotLedger] = {}

    def add_venue(
        self,
        venue: Venue,
        balances: dict[str, D | str],
        *,
        marks_usd: dict[str, D | str],
    ) -> SlotLedger:
        if venue in self.ledgers:
            raise ValueError("M033_DUPLICATE_VENUE_LEDGER")
        ledger = SlotLedger(balances, marks_usd=marks_usd)
        self.ledgers[venue] = ledger
        return ledger

    def ledger(self, venue: Venue) -> SlotLedger:
        try:
            return self.ledgers[venue]
        except KeyError as exc:
            raise ValueError("M033_VENUE_LEDGER_MISSING") from exc

    def reserve(
        self,
        venue: Venue,
        *,
        slot_id: str,
        reservation_id: str,
        asset: str,
        quantity: D,
        now_us: int,
    ) -> None:
        self.ledger(venue).reserve_free(
            slot_id,
            reservation_id,
            asset=asset,
            quantity=quantity,
            now_us=now_us,
        )

    def assert_route_fundable(self, route: VenueRoute, *, asset: str, quantity: D) -> None:
        ledger = self.ledger(route.venue)
        if ledger.free.get(asset, D(0)) < quantity:
            remote = sum(
                (
                    row.free.get(asset, D(0))
                    for key, row in self.ledgers.items()
                    if key != route.venue
                ),
                D(0),
            )
            if remote > D(0):
                raise ValueError("M033_REMOTE_VENUE_CAPITAL_UNAVAILABLE")
            raise ValueError("M033_LOCAL_VENUE_CAPITAL_INSUFFICIENT")

    def venue_equities(self) -> dict[Venue, D]:
        return {venue: ledger.marked_equity() for venue, ledger in self.ledgers.items()}

    def global_marked_equity(self) -> D:
        return sum(self.venue_equities().values(), D(0))

    def reconcile(self) -> None:
        for ledger in self.ledgers.values():
            ledger.reconcile()
        if self.global_marked_equity() != sum(self.venue_equities().values(), D(0)):
            raise ValueError("M033_GLOBAL_PORTFOLIO_RECONCILIATION_FAILED")


__all__ = ["MultiVenuePortfolio"]
