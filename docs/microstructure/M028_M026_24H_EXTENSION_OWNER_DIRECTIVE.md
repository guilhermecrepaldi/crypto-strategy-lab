# M028 — OWNER authority binding: M026 full-day extension

Received on 2026-09-10:

> vamos ficar com M26 então, prolonge o teste para 1 dia e me fale o ganho em
> porcentagem, quanto antes e quanto depois

This authorizes exactly one historical L2 DEVELOPMENT replay of the unchanged
M026 strategy over the complete 2025-01-01 UTC day. M026 and M027 remain
immutable. Because duration is part of M026's registered identity, this temporal
replication is registered as M028 with M026 as its scientific parent.

The only experimental change is:

- start: 2025-01-01T00:00:00Z;
- end exclusive: 2025-01-02T00:00:00Z;
- duration: 24 hours rather than 3 hours.

M028 must preserve M026's engine, 15-level 3/2/1 geometry, 60 initial physical
orders, 140 operating slot-units, 8 mobility slot-units per asset side, historical
tick/quantity rules, FIFO and latency, capital ownership, liquidity consumption,
positive passive returns, compounding, no realized negative exit and no cutoff
liquidation. It must use the same validated January 1 L2 and canonical trades.

The 00:00–03:00 prefix must reproduce M026's ledger and economic state after
normalizing only the registered end timestamp. Failure closes the run as a
technical invalidation; it must not be hidden by continuing.

Primary OWNER output:

- initial marked equity (before);
- final marked equity (after 24h);
- absolute marked gain;
- total marked gain percentage;
- M026 equity at 03:00 and incremental 03:00–24:00 gain percentage;
- complete physical and slot-equivalent cycles.

Do not add M027 MICRO geometry, tune parameters, reset at 03:00, inject capital,
force liquidation, access an account/Testnet/live, run another day or create an
automatic successor. The normalized one-unit mechanics remain below Binance
minimum notional and are not a live-executable result.
