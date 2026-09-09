# M024 — triangular pre-aged same-price FIFO

STATUS=PREREGISTERED_PRE_RUN
MODEL=M024_TRIANGULAR_PRE_AGED_QUEUE_V1
PERIOD=2025-01-01T00:00:00Z/2025-01-01T03:00:00Z_EXCLUSIVE
ORDER_MODE=NORMALIZED_1_USDC_NON_EXECUTABLE_PRE_AGED_FIFO

> Every one-USDC order is below Binance minimum notional. This is a historical
> L2 mechanics test, not a live-executable replay.

## Observation, hypothesis and causal question

M023 completed four positive cycles in three hours with one physical order and no
rejection storm. Its order was active about99.9% of the time, yet waited behind
observed public FIFO and subsequent profitable price recovery. M024 asks whether a
second independently funded order already resting behind the first at the same price
reduces its later wait without bypassing public queue.

The tested mechanism is not merely more simultaneous capital. It is the measurable
preservation of the second column's own time priority after column1 fills. Therefore
the main result is reported with both absolute throughput and capital-normalized
efficiency. A 30-cycle result passes the engineering target of10/hour but neither
proves the pre-aging cause nor approaches the long-term83.33/hour target by itself.

## Frozen geometry and capital

At the first causal bridged book, bid is1.0019 and ask is1.0020. Fifty BUY prices are
`ask0 - rank*0.0001`; fifty SELL prices are `bid0 + rank*0.0001`. Ranks01–25 receive
two distinct columns and ranks26–50 one. This creates75 physical BUY and75 physical
SELL free entries.

The BUY reservations total74.9900USDT. The SELL entries reserve75USDC with initial
basis1.0019, marked to bid for75.1425USDT. Initial marked equity is150.1325USDT.
No capital is added after initialization. Initial endowment sales are not cycles;
SELL-first cycles require the same one-USDC principal to be bought back for a strictly
positive complete round-trip result.

## Shared FIFO representation

`PRICE_QUEUE_GROUP=(side, price)` is an ordered sequence, not an independent queue
counter on every order. Orders activated on the same causal book boundary form one
cohort: displayed public queue, then own orders ordered by submitted time and order ID.
For genuinely later activation, append a conservative public barrier of
`max(0, displayed_public - represented_public_remaining)` before the new own cohort.
This represents uncertainty conservatively and is not an L3 reconstruction.

A compatible print traverses the segments once. It depletes public barriers before
own orders, then C1 residual before C2 and C2 before a recycled C3. Quantity consumed
by any segment is unavailable to every other group/order in the physical scenario.
No public cancellation credit is granted. C1 cancellation removes it only after ACK.

Only funded, submitted and successfully activated orders age. A parked logical level,
rejected order or pending future replacement has no exchange priority.

## Rolling management, returns and partials

An aged free entry remains while passive and inside the current50-level side window.
If coverage must roll, evict the farthest free entry, breaking ties by youngest age,
and wait for ACK. Owned returns have priority over free entries and over growth. Return
conflicts use `cancel FREE -> ACK -> submit owned return`, with normal latency and a
new FIFO position. Return priority is oldest lot entry time then lot ID.

A SELL replacement or recycled SELL is never moved below its owned USDC cost basis
plus one tick. If the current50-level window is wholly below that boundary, the cell
remains economically protected outside the active region rather than realizing loss.
A missing replacement is explicit when the correct asset or principal is unavailable.

BUY-first return SELL is the lowest causal passive tick at or above exact basis plus
one profitable tick and modeled costs. SELL-first return BUY is the highest causal
passive tick at or below sale proceeds per unit minus one profitable tick and costs.
Market movement may improve either price. Negative and breakeven exits cannot produce
a positive cycle.

A partial own order remains at its exact FIFO position; its residual cannot be evicted
or crossed by C2. A post-only/coverage failure at activation rejects and releases it
without queue age. No self-fill, internal transfer, forced fill or cutoff liquidation
exists.

Every physical order remains exactly `1USDC`; only `minNotional` is virtualized. If a
rolling cancel was already in flight and an ENTRY receives a sub-step partial fill before
its ACK, the residual reservation is released once but the partial lot is locked. No
fractional RETURN is submitted, no aggregation is invented and no cycle is counted. A
partial BUY remains owned inventory; proceeds from a partial SELL remain unavailable to
new orders as an unresolved return obligation. This conservative V1 outcome is reported
as `PARTIAL_LOT_SUBSTEP_LOCKED`.

The first partial ENTRY fill creates a traceable lot immediately. Initial SELL cells
carry the first bid as their owned-USDC basis; subsequent recycled SELL cells carry the
actual reacquisition basis. Disposal PnL, completed-cycle PnL and growth-eligible PnL
are separate, while remaining USDC layers are marked independently to the final bid.

## Recycle versus realized-profit expansion

When a cycle finishes, its principal returns as a new young free entry at the back of
an eligible hot-line group. This is recycling, not expansion. Strictly positive profit
from the completed cycle is credited once to `GROWTH_POOL_USDT_EQ`.

Growth candidates are missing cells in ascending level rank, BUY before SELL at a tie.
A cell opens only when the available realized pool covers its complete capital and the
required asset is actually unreserved. USDT cannot become USDC by accounting entry;
a SELL growth cell remains blocked without real acquired USDC. No candidate is funded
by unrealized PnL, reserved principal or another lot. Consequently zero profit-funded
cells in this three-hour prefix is an expected possible result, not a failure of code.
Conversely, an OWN BUY reservation may spend only `free cash - growth pool - unresolved
SELL-return obligations`; the matching full SELL-first RETURN may use its own obligation.
Principal recycling cannot silently reserve profit or cash belonging to an unresolved lot.

All physically active free-entry levels on both sides form the rectangle denominator.
Depth2 is reached only when every such level has two genuinely funded active cells.
After depth2, growth may begin depth3 at the nearest hot region, subject to the physical
cap. Depth8 is only a long-term architectural marker.

The nonterminal count `PENDING + ACTIVE + CANCEL_PENDING` never exceeds200. To reserve
owned-return headroom, farthest then youngest zero-fill free entries are cancelled as
needed. Parked cells reserve no asset and accumulate no age.

## Counterfactual diagnostic

When C1 fills fully and C2 remains resting, create one shadow case for that C2. It
models a fresh same-price order submitted only after C1 fill with normal latency and
the public queue causally visible then. The C1 fill print cannot fill the shadow. Future
compatible prints may update the shadow in an isolated ledger that neither removes
physical liquidity nor changes balances/orders.

The shadow substitutes for C2 in its counterfactual branch; it therefore does not count
the physical C2 itself as an own predecessor. Other genuinely preceding own orders remain
ahead. Native trade time must be strictly later than submission, logical activation and
the activation book's native upper bound.

Report actual and shadow wait, signed benefit and censoring. Unfilled shadow or C2 cases
remain in denominators explicitly; no future values initialize the branch. This is
`DIAGNOSTIC_COUNTERFACTUAL_ONLY`, not alternative execution evidence.

## Data, execution and immutability

Only the validated L2 slices and canonical trades for `[00:00,03:00)` on2025-01-01 may
reach the state machine. M023's frozen profile, native ordering, latency, queue policy,
strict compatible direction/trade-through, global volume ledger and zero conditional
fee assumption remain unchanged. A trade cannot be reused between physical orders.

M023 and all earlier evidence stay immutable. This configuration runs once after the
exact code/spec/tests and source-bound Astra review are published on clean synchronized
`main`. No rerun, sweep, day2, M025 or live action is authorized.

## Audit, metrics and verdict

The physical audit reconstructs capital, reservations, lots, cost basis, return
ownership, public/own FIFO segments, activation/cancel order, single-use trade volume,
cycles, growth and the cap from the event ledger. Checkpoint/resume must equal continuous
execution.

Primary fields follow the OWNER scoreboard, including cycles/hour, direction and column
counts, queue-wait distributions, pre-aging cases/benefit, open-order cap, productive
levels/columns, growth coverage/depth, initial/final assets/equity and realized/unrealized
PnL. Wait statistics include only completed physical orders and report their denominator;
open/censored cases are separate. Pre-aging does not become `YES` unless at least one
paired actual/counterfactual observation closes with positive measurable benefit.
The kernel leaves `MAIN_LIMITER` undetermined; the independent post-run autopsy must
classify it from the physical queue, return, price and capital evidence.

`TEST_SUITE_PASS != STRATEGY_PASS`. The final scientific conclusion must separately
answer throughput increase, column2 FIFO advantage, profit-funded rectangle progress
and the observed limiter. No outcome promotes a strategy automatically.
