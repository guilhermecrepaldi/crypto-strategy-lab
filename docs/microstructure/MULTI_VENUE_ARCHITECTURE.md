# M033 multi-venue architecture

```text
M032 ECONOMIC POLICY
        |
GLOBAL REPORTING SUPERVISOR (no remote funding)
        |
  +-----+------+
  |            |
BINANCE      KRAKEN
VenueLedger  VenueLedger
  |            |
L2 adapter   Kraken adapter
L2 queue     L2 queue / L3 queue
```

`BookKey(Venue, native_symbol)` is the physical identity boundary. Rules, fees,
market state, event IDs, order IDs, queues, reservations and balances never use
symbol alone. A future adapter can add OKX without changing the economic policy.

`MultiVenuePortfolio` owns one `SlotLedger` per venue. It may sum marked equity,
but routing and reservation call only the selected venue ledger. A route validates
that every leg uses the same venue. Cross-venue transfer mechanics do not exist.

`L2QueueModel` namespaces the reviewed M032 conservative queue implementation by
book. `L3QueueModel` keeps observable public orders and simulated own C1/C2 in one
price-time sequence. Same-timestamp ambiguity puts public orders ahead of our
order. Increasing quantity or changing price loses priority; decreasing quantity
retains it. These rules follow Kraken's documented atomic-amend table.

Kraken's native L3 feed exposes `add`, `modify` and `delete`. A `modify` is a
visible quantity reduction; a `delete` alone does not prove whether full fill or
cancel caused removal. M033 does not invent that cause. Correlation with trade
evidence is required before an execution label can be asserted.

Raw capture is written before normalization. Gaps, reconnects, duplicate and
out-of-order events fail closed. Kraken L3 requires an authenticated token, so
the transport remains blocked under the no-credentials authority; the recorder,
parser and deterministic fixtures are implemented without connecting an account.
