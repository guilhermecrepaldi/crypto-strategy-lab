# M032 — adaptive multi-stable capital manager — OWNER directive

Status: `OWNER_AUTHORIZED_ARCHITECTURE`; economic replay remains gate-bound.
Starting authority: `9e0f1e897789295b8478f339e2969723748f0955`.

M032 is a new system-integration and economic-architecture hypothesis. M030's
published evidence is immutable. M031 remains
`BLOCKED_PRE_RUN_CAPITAL_IDENTITY`; M032 does not repair or reinterpret it.

## Objective and invariants

With at most USD 200 equivalent of physical initial capital, allocate each
marginal slot to the explainably best available use considering net return,
completion probability, queue position, capital lock, residual inventory and
stablecoin safety. Primary KPIs are realized PnL per capital-hour,
slot-equivalent cycles per hour and P95 capital-lock time. Physical cycles remain
separate.

Strict causality, public and own FIFO, once-only trade quantity and queue,
ACK-only capital release, immutable cost basis, physical asset conversion,
protected partial/filled obligations, no self-fill and no deliberate negative
exit are hard requirements. No live, Testnet, account, forced cutoff liquidation,
parameter sweep, candle-as-L2 substitution or invented fee/fill is permitted.

## Geometry and economic entities

Each book has at most seven ranks per side: HOT 1–3, MID 4–5, FAR 6–7. Each rank
may fund zero, C1, or C1+C2. C1 is persistent and values accrued FIFO position;
C2 is opportunistic and more reclaimable while zero-fill. A new order is always
younger and cannot inherit price, age or public queue from another order.

Each slot has a persistent identity, epoch, asset ownership, state, reservation,
book/side/price/column/rank, queue evidence, route/cycle links, cost basis,
turnover clock and realized/marked result. Global reconciliation must answer
where the entire bankroll is without double counting free, reserved or owned
assets.

## Universe, routes and evidence gates

At most four eligible stablecoins may be selected before performance inspection.
Safety determines eligibility; book productivity determines capital allocation.
Cycles may contain two, three or four distinct stablecoins and close only after
every leg has a physical fill returning to the origin asset. Marked profit never
becomes realized profit or expansion capital.

Historical symbol rules, temporal fee profiles, physical L2 and canonical trades
must exist for every selected book over a common eligible date pool. Current
exchange information is descriptive only. If the common physical multi-book pool
is empty, implementation and tests may be published but replay must stop with a
data blocker.

## Required delivery gate

Audit M030/M031 reuse, implement separate reusable components, run deterministic
tests, complete a source-bound independent review, freeze a model hash and publish
the preregistration before replay. The registry entry is withheld until all replay
gates close. A failed gate must be published, not bypassed.
