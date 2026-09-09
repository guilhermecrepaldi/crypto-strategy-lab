# OWNER directive — M024 triangular pre-aged queue

AUTHORITATIVE_OWNER_REQUEST_DATE=2026-09-09
MODEL_ID=M024
PARENT_MODEL_ID=M023
M023_IMMUTABLE=true

## Objective and scope

M023 established that strict serial mechanics removed the self-cross/post-only storm
and kept order uptime near 99.9%, but a single physical order remained blocked by FIFO
and price recovery: four complete positive cycles in three hours. M024 tests whether
future capital already resting behind an older own order at the same price creates a
useful FIFO pipeline. It does not bypass public queue.

The only authorized economic replay is the same historical prefix:

- `USDCUSDT`, source day `2025-01-01`;
- `[2025-01-01T00:00:00Z, 2025-01-01T03:00:00Z)`;
- identical validated L2, canonical trades, queue policy, latency, strict compatible
  trade-through, no cancellation credit and native causal ordering used by M023;
- one run, no parameter sweep, rerun, M025, extension, account, Testnet or live access.

This is a normalized mechanics test. Every order is exactly one USDC and is below the
current Binance minimum notional. Only the minimum-notional gate is virtualized.

## Initial triangle and physical cap

Use 50 logical price levels per side, one historical tick (`0.0001`) apart. Level 01
is closest to the causal hot-line region and level 50 farthest. At initialization:

- levels 01–25 have two distinct one-USDC orders at the same price;
- levels 26–50 have one one-USDC order;
- each side therefore has 75 free-entry orders; target total is 150;
- `HARD_SIMULATED_OPEN_ORDER_CAP=200`, counting `PENDING + ACTIVE + CANCEL_PENDING`.

The 50 levels are logical radar addresses. If later depth growth requires it, physical
active levels must shrink so that two sides, queue depth and owned-return headroom stay
within 200. Parked levels reserve no capital and do not age in an exchange queue.

The hot line uses only the current causal bid/ask/mid rule already audited. Orders stay
near it, but an aged free order is not cancelled merely to appear central. It may be
cancelled only when sufficiently distant, needed to make physical room for an owned
return, invalid/post-only, or needed for missing-side coverage. Cancellation changes
priority only after causal `CANCEL_ACK`.

## Same-price queue semantics

A column is an individual physical order, not another price and not a consolidated
quantity. For every `SIDE + PRICE`, maintain a `PRICE_QUEUE_GROUP` containing public
queue and an own-order FIFO ordered by activation time, then order ID. The economic
ordering must be reconstructable as:

`PUBLIC_QUEUE_AHEAD -> OWN C1 -> OWN C2 -> later own orders`.

Public queue must not be independently copied into C1 and C2. A compatible trade first
depletes the public quantity according to the frozen conservative model, then C1, then
C2, using the trade quantity globally once. C2 retains submitted time, activation time,
age and ownership when C1 fills. A C1 residual remains before C2. A new recycled C3 is
younger and enters behind C2. A C1 cancellation benefits C2 only after the ACK.

When same-price orders activate at genuinely different times, the implementation must
not transfer old priority to the newcomer. Public liquidity conservatively placed ahead
of the new order after the older order activated must remain an explicit FIFO barrier or
cohort segment. Initial columns may share an activation cohort only when they actually
become active on the same causal book boundary; deterministic own order is then by
submission time and order ID. This clarification preserves the OWNER requirement while
preventing fabricated pre-aging.

## Lots, returns and capital ownership

Every fill creates or consumes a separate auditable lot with entry order, column, price
level, quantity, time and cost basis. Lots cannot merge to hide results. Every submitted
order is exactly `1USDC`; only the `minNotional` gate is virtualized. A sub-step partial
lot stranded by a causal cancel ACK remains locked without a fractional return or cycle.
Negative exits are prohibited and breakeven is not a positive cycle.

An owned return is an adaptive passive economic frontier, not a fixed one-tick address:

- BUY-first: choose a causal `LIMIT_MAKER` SELL at or above cost basis plus the minimum
  profitable tick/costs; a higher passive price is allowed if the market is already up;
- SELL-first: choose a causal passive BUY at or below proceeds/quantity less the
  minimum profitable tick/costs; a lower price is allowed if the market is already down.

Owned returns outrank free entries. Resolve a conflict by requesting cancellation of
the free order, waiting for ACK, then submitting the owned return with normal latency and
queue. There are no self-fills or internal fills and cost basis never moves.

Each column needs independently owned capital. Initial BUY reservations need their own
USDT and initial SELL entries need their own USDC. Calculate and record exact
`INITIAL_USDT`, `INITIAL_USDC` and marked equity from the frozen initial geometry. No
external capital injection is allowed.

## Recycle and profit-funded growth

Principal released by a completed cycle is recycled into a suitable hot-line queue as a
new young order at the back. It maintains the pipeline but is not profit-funded growth.
All strictly positive realized round-trip profit enters `GROWTH_POOL_USDT_EQ`; principal,
inventory and growth remain separate.

Only available realized growth can fund a new queue cell. Reserved capital, another lot,
or unrealized PnL cannot. Growth fills missing column 2 in levels 26, 27, 28, ... nearest
the hot line until every physically active level is depth 2 (`RECTANGLE_DEPTH_2`). It then
starts column 3 in the hottest active region. Architectural target depth is 8, but the
replay must report only what realized profit can finance and may never exceed the 200
order cap.

## Queue hypothesis and counterfactual

Record queue wait by column (mean, median, P95), queue ahead at activation for C1/C2 and
queue ahead for C2 when C1 fills. For each case where C1 fills and C2 remains resting,
estimate `PRE_AGING_BENEFIT_SECONDS` by comparing actual C2 time-to-fill with a diagnostic
new order created causally after C1 fill. This is `DIAGNOSTIC_COUNTERFACTUAL_ONLY`: it
cannot alter execution and cannot use future information when initializing the
counterfactual. Record cases and mean/median/P95 seconds plus mean/median queue advantage
when supported. Censored/unfilled cases remain explicit and are not silently dropped.

## Metrics and decision boundary

Primary metrics are complete strictly positive cycles and cycles/hour. Engineering gate
is 30 cycles in three hours (`10/hour`). The long-term 2,000/day target is about
83.33/hour and is not met by 10/hour.

Also report BUY-first/SELL-first cycles, fills, productive price levels/columns, waits by
column, initial/max open orders, capital utilization, cycles/hour per 100 USDT-equivalent,
capital per complete cycle, active capital time-weighted, realized/unrealized PnL, marked
equity, growth pool, cells funded, column-2 coverage, maximum depth and rectangle flags.
M024 uses more capital than M023, so raw PnL is not a financial comparison; the main
comparison is throughput mechanics, with capital efficiency disclosed.

Required OWNER scoreboard fields are:

`MODEL, PERIOD, TOTAL_CYCLES, CYCLES_PER_HOUR, TARGET_10_PER_HOUR_PASS,
BUY_FIRST_CYCLES, SELL_FIRST_CYCLES, TOTAL_FILLS, COLUMN_1_CYCLES,
COLUMN_2_CYCLES, COLUMN_1_MEDIAN_QUEUE_WAIT, COLUMN_2_MEDIAN_QUEUE_WAIT,
COLUMN_1_P95_QUEUE_WAIT, COLUMN_2_P95_QUEUE_WAIT, PRE_AGING_CASES,
PRE_AGING_BENEFIT_OBSERVED, PRE_AGING_BENEFIT_MEDIAN_SECONDS,
INITIAL_OPEN_ORDERS, MAX_OPEN_ORDERS, PRODUCTIVE_PRICE_LEVELS,
PRODUCTIVE_COLUMNS, GROWTH_POOL_FINAL, NEW_QUEUE_CELLS_FUNDED_BY_PROFIT,
COLUMN_2_COVERAGE_INITIAL, COLUMN_2_COVERAGE_FINAL, MAX_QUEUE_DEPTH_REACHED,
RECTANGLE_DEPTH_2_REACHED, INITIAL_USDT, INITIAL_USDC, INITIAL_MARKED_EQUITY,
FINAL_USDT, FINAL_USDC, FINAL_MARKED_EQUITY, REALIZED_PNL, UNREALIZED_PNL,
AUDIT, MAIN_LIMITER`.

Follow this with a column table (`COLUMN | ORDERS | FILLS | CYCLES | MEDIAN_WAIT |
P95_WAIT`) and counts of depth-1, depth-2 and depth-3-plus active levels.

## Required invariants and tests

Before the run, tests and source-bound independent review must establish:

- one shared public queue plus correctly segmented/cohorted own FIFO per side/price;
- public queue, trade quantity, capital and order identity are never duplicated;
- C2 never jumps C1, retains age after C1 fill/cancel ACK and stays behind C1 residual;
- volume 1 cannot fill two one-USDC orders; volume 2 can only when public queue is zero;
- owned-return conflict follows cancel request -> ACK -> submit return;
- no negative/breakeven positive cycle, internal self-fill or future data;
- pending + active + cancel-pending never exceeds 200;
- growth below one cell does not expand; sufficient realized growth funds exactly one
  cell and is debited exactly; unrealized growth never funds it;
- all physically active levels at depth 2 set the rectangle flag;
- checkpoint/resume preserves result, ledger, own FIFO, capital and growth pool;
- activation time priority beats lane/ID, and later recycled capital stays behind aged C2.

Synthetic queue sequence: public=10, C1=1, C2=1; compatible volume 5 leaves public=5;
next volume 5 reaches public zero without retroactive fill; the next eligible unit fills
C1 and leaves original C2 first among own orders.

Independent review must be Astra when available (otherwise GPT-5.6 Sol/high), identify
the actual reviewer and bind exact source hashes. `TEST_SUITE_PASS != STRATEGY_PASS`.

## Publication and final questions

Preregister, commit and push before replay. Confirm clean published `main`, execute once,
then independently audit and publish result/autopsy/journal/registry/CURRENT_STATE. Preserve
M023 and earlier evidence. Do not tune after observing the result.

The final answer must state whether the triangle increased physical throughput, whether
column 2 gained measurable FIFO pre-aging advantage, whether realized profit began the
triangle-to-rectangle conversion, and whether the limiter remained public FIFO, became
price recovery, or became capital/return management. Never label the normalized result
live-executable or promote the strategy merely because it produced cycles.
