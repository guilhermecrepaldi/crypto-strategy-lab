# M020 — zonal ping-pong 5h V1 preregistration

STATUS=PREREGISTERED_PRE_RUN  
OWNER_AUTHORITY=STABLECOIN_ZONAL_PING_PONG_OWNER_DIRECTIVE.md  
MODEL=STABLECOIN_ZONAL_PING_PONG_5H_V1  
PERIOD=2025-01-01T00:00:00Z/2025-01-01T05:00:00Z_EXCLUSIVE

> THIS 1-USDT ORDER RESULT IS A NORMALIZED STRUCTURAL THROUGHPUT TEST. IT IS
> BELOW BINANCE MINIMUM NOTIONAL AND IS NOT A LIVE-EXECUTABLE RESULT.

## Observation and falsifiable hypothesis

M019 closed only 10 positive cycles in its 24-hour D1 and accumulated inventory;
84 USDC remained after an 18.503-hour cycle plateau. M020 does not repair or
reinterpret M019. It tests the separate hypothesis that immutable price zones,
one unresolved economic sequence per zone and a rolling four-by-four quote
window can preserve independent recycling capacity. The primary measurement is
complete positive round trips in exactly five hours. No minimum result is
presumed.

## Deliberately retrospective DEVELOPMENT geometry

The OWNER authorized the full canonical 2025 trade history solely to select
geometry. `PRICE_OCCUPANCY_2025` treats the last canonical trade price as a step
function until the next canonical trade, weighted in microseconds. The first
6,766 microseconds of 2025 before the first print are UNKNOWN; the last observed
price persists only to the calendar-year end. Equal timestamps give zero dwell
to all but the last canonically ordered print.

For P80/P90/P95/P99, the algorithm minimizes interval width subject to reaching
the requested fraction of known duration. Ties prefer greater covered duration,
then the lower low. This processed 365 validated archives and 166,291,613 trades.

```text
ANNUAL_LOW=0.98500
ANNUAL_HIGH=1.00900
P80=0.99940..1.00030 (80.08038628823642483594012083%)
P90=0.99930..1.00050 (90.63967825518988023448169488%)
P95=0.99910..1.00070 (95.59490815443921703998401010%)
P99=0.99900..1.00130 (99.09240636881212650594182139%)
```

This is development lookback/lookahead relative to the five-hour replay. D1 is
not out-of-sample and no result may be generalized as prospective evidence.
Only the frozen map below reaches the economic engine; no annual event stream is
available to its decisions.

## Immutable map

The frozen transferred source-day tick is 0.0001. P80 aligns exactly to it and
contains 10 distinct endpoints, hence nine physical intervals—fewer than the
requested maximum of 40:

```text
Z001=[0.9994,0.9995]
Z002=[0.9995,0.9996]
Z003=[0.9996,0.9997]
Z004=[0.9997,0.9998]
Z005=[0.9998,0.9999]
Z006=[0.9999,1.0000]
Z007=[1.0000,1.0001]
Z008=[1.0001,1.0002]
Z009=[1.0002,1.0003]
```

`BUY_BAND_COUNT=9`, `SELL_BAND_COUNT=9`, and `TOTAL_BANDS=9` mean directional
capabilities of the same nine addresses, not 18 duplicated bands. A band may run
BUY-first or SELL-first, never both simultaneously, and may hold only one open
economic sequence. IDs and endpoints never move. Reporting assigns price at a
shared edge to the upper half-open interval; the last band includes its high.

## Capital and normalized quantity

At the first valid causal L2 bid, create a non-trade initial endowment:
`Q0=floor_to_historical_step(50/bid)` USDC and
`cash0=100-Q0*bid` USDT. Initial liquidatable marked equity is exactly 100.
Endowment is owned inventory but not an executed entry and cannot count alone as
a cycle.

Each first leg uses exactly 1 USDC, the preserved historical step/minimum
quantity and approximately one-USDT equivalent over the frozen map. Its notional
ranges from 0.9994 to 1.0003 USDT. This is intentionally not exactly 1 USDT on
every band. Only the exchange minimum-notional gate is bypassed; tick, step,
minimum quantity, L2, queue, latency, post-only, direction and shared liquidity
remain enforced. The second leg uses the same 1 USDC. This interpretation obeys
the OWNER's instruction not to disable other symbol filters.

Balances and reservations have exclusive ownership. No capital is created on
demand. Profit returns to the free pool, but sequence quantity remains fixed in
this throughput diagnostic; optimizing size or compounding policy is outside
scope. Reserve and release are zero/disabled.

The inventory ledger preserves exact fixed-price cost layers. Aggregate average
basis is descriptive only; total pool cost and per-lot remaining cost are the
authorities. Reservations, partial fills, cancellation and reentry move exact
cost between those authorities with a deterministic final residual. No Decimal
tolerance is used to conceal conservation drift.

## Per-band state machines and cycle identity

BUY-first:

`READY → BUY_WORKING at LOW → 1 USDC owned → SELL_WORKING at HIGH → complete`.

SELL-first:

`READY → reserve 1 pre-existing USDC → SELL_WORKING at HIGH → reserve its cash
proceeds → BUY_WORKING at LOW for the same 1 USDC → inventory restored → complete`.

SELL-first cannot short or use unowned base. The initial sale is not a complete
cycle. The reverse cycle's result is its net cash delta after restoring the same
base quantity, and is counted exactly once. Partial sale proceeds are segregated
in per-band reentry escrow as they arrive; they are unavailable to every other
order. The matching BUY consumes that escrow and only its positive remainder
returns to free cash after the entire base quantity is restored. BUY-first exits must have
net proceeds strictly greater than their entry basis. SELL-first round trips
must also have positive net cash delta. Breakeven and partial legs count zero.

Two profit views remain separate. Disposal PnL versus the original lot basis is
recognized once on the SELL for inventory accounting. `ROUNDTRIP_CYCLE_PROFIT`
is sale proceeds minus same-quantity rebuy cost and is the reverse-cycle measure.
It is not added again to disposal PnL. Cash, escrow, inventory cost and marked
equity reconcile both views without double counting.

Partial fills preserve identity and remaining quantity; they cannot be canceled
to fabricate smaller complete cycles. A band with filled inventory may remain
`DORMANT_WAITING_PROFITABLE_EXIT` while other bands work. That inventory and its
marked PnL remain visible and cannot migrate.

## Rolling four-by-four window

After each valid book and after a complete trade event has processed any fill or
acknowledged cancellation, retain useful free
entries and select, when bands/ownership/capital allow:

- four nearest eligible band LOWs strictly below causal mid for BUY-first;
- four nearest eligible band HIGHs strictly above causal mid for SELL-first.

Ties use ascending band ID. A band occupied by a sequence is not another entry.
Only a completely unfilled entry that left the selection may be canceled; its
capital remains reserved through cancel latency and is released once at ACK.
Owned exits remain at immutable endpoints outside the active window.
An order created by post-trade reconciliation receives normal latency and cannot
consume the print that caused its creation.

Coverage is an attempt, not a promise. Map edge, insufficient balance,
endowment basis, ownership, pending cancel, observed-book coverage, post-only or
self-cross can produce `WINDOW_UNDERSUPPORTED`. No band may be added, extended or
moved. Equal/crossing own opposite-side quotes are blocked.

## Execution and hard cutoff

Use the already authorized observed native-L2 ingestion and the transferred
`B_REALISTIC_CONSERVATIVE` PRICE_PRIORITY profile. Zero fee remains a conditional
historical profile fact, not an account claim. Queue ahead is causally displayed
same-side depth at activation, receives no cancellation credit, and strict
trade-through can infer priority only for an order active before the print.
Touch is not fill.

A trade has one global quantity budget across queue depletion and all bands.
BUY priority is higher price first; SELL priority is lower price first; ties are
actual activation time then order ID. Native exchange time must be strictly
after activation. Unknown book coverage rejects activation. Cancel latency and
post-only behavior remain active.

The L2 reader is limited to the first 30 ten-minute slices and canonical trades
strictly before 05:00. Neither exchange nor capture timestamp at/after 05:00 can
create an action or fill. Finish only marks balances/inventory at the last
available bid before cutoff; it never liquidates.

## Frozen result and autopsy rules

Primary metrics are total complete positive cycles, cycles/hour and cycles per
band. BUY→SELL and SELL→BUY are separate subtotals. All-band ranking sorts cycle
count descending and band ID ascending. Share denominator is total positive
cycles; if zero, shares are zero. Price occupancy inside a reporting band uses
half-open endpoints and remains secondary.

Balance is a conservation sanity check, not an objective. Report final USDT,
USDC and bid-marked total equity, open/dormant states, cancels/repositions,
window shortages, queue blocks, exact/trade-through fills and the dominant
limiter. Do not change the strategy after seeing the result.

Fail closed on unverified occupancy/provenance, invalid or duplicate geometry,
zero quantity, economic input at/after cutoff, unowned SELL, negative exit,
capital/lot/liquidity duplication, causal violation, audit divergence or
checkpoint/resume mismatch. Edge shortages and low throughput are valid results,
not technical invalidity.

## Pre-execution gates

Before the run: exact implementation and invariant tests; independent GPT-6
Astra review bound to the source hashes; M020 CREATED registry entry; clean
published `origin/main`; and explicit M020/5h-only machine gate. The prereg/source
commit must be public before execution. Tests passing do not make the strategy
pass. No day2, executable-minimum rerun, parameter sweep, account, Testnet or live
operation is authorized.
