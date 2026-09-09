# OWNER DIRECTIVE — M021 dense 200-slot ping-pong mechanics probe

Received: 2026-09-08  
Repository: `crypto-strategy-lab`  
Authority: OWNER request preserved from the task attachment.

## Scope and purpose

M021 is a new hypothesis. M020 remains immutable and `REJECTED`. This is not a
profitability, P80, or out-of-sample test. It is a normalized mechanical
throughput probe asking whether a dense grid around the market can physically
execute ping-pong cycles under historical L2.

The only authorized economic interval is
`2025-01-01T00:00:00Z/2025-01-01T05:00:00Z` exclusive. Reuse exactly the
validated M020 L2, canonical trades, and physical-audit assumptions. Do not
authorize Day2 or create M022 automatically.

## Causal frozen grid

Do not use P80/P90/P95/P99 to position the grid. Wait for the first valid,
bridged L2, obtain `FIRST_VALID_BID`, `FIRST_VALID_ASK`, calculate midpoint,
quantize it to the historical tick, and freeze `GRID_ANCHOR`. Do not move the
grid or use future data.

Create exactly 100 BUY entry slots and 100 SELL entry slots:

- `B001..B100`: entry at `anchor - n × 0.0001`;
- `S001..S100`: entry at `anchor + n × 0.0001`;
- no duplicated entry price and no entry at the anchor;
- total intended coverage is approximately `anchor ± 0.0100`.

Register all exact generated prices before the replay. `ROLLING_RECENTER=OFF`.

## Normalized execution and capital

Each slot uses exactly 1 USDC. This is below Binance minimum notional and must
be labeled `NORMALIZED_1_USDC_NON_EXECUTABLE_MECHANICS_PROBE`. Ignore only the
minimum-notional gate. Preserve L2, queue, direction, latency, post-only, price
priority, partial fills, global liquidity sharing, self-cross, and causality.
Never call M021 live-executable.

Set initial USDT to the exact amount required to fund all 100 BUY entries and
initial USDC to exactly 100. Initial marked equity is calculated at the first
valid bid and will be approximately 200 USDT-equivalent. Do not inject capital
during the run. Reserve is zero and release is disabled.

All 200 logical slots may be open. Record maximum simultaneous open orders.
Two hundred is also the current per-symbol ceiling noted for a future Binance
implementation and leaves no operational headroom; do not reduce it in this
diagnostic.

## Slot state machines

Each slot has persistent identity.

- BUY-first: BUY at fixed entry, then SELL one historical tick higher, complete
  only after the corresponding quantity finishes the round trip, and rearm the
  original BUY.
- SELL-first: SELL owned USDC at fixed entry, then BUY it back one historical
  tick lower, complete only after the corresponding quantity finishes the round
  trip, and rearm the original SELL.

Partial fills never count as cycles. One full economic round trip counts once.
No realized-loss exit is allowed. With frozen zero fee, still require a
strictly positive one-tick price difference. Breakeven is not a positive cycle.
If post-only prevents the one-tick return order, wait or record the blocker;
never widen or move the price automatically.

Clarification recorded before implementation: the prohibition on an anchor
level applies to the 200 initial entry prices. The explicitly prescribed B001
and S001 one-tick return prices may equal the anchor. Such opposing returns are
subject to deterministic self-cross prevention and may be deferred; they must
never be shifted or internally filled.

## Physical execution

All slots share one global trade quantity budget. Priority is better price,
then actual activation time, then order ID. Reuse M020's displayed depth at
activation, no cancellation credit, strict compatible trade-through, and native
causality. `PRICE_TOUCH != FILL`.

## Required reporting

For every slot record ID, initial side, fixed entry price, fill-event count,
complete cycles, active time, queue blocks, and open position at cutoff.

Aggregate into twenty fixed buckets of ten:
`BUY_001_010` through `BUY_091_100` and `SELL_001_010` through
`SELL_091_100`. Record fills, cycles, and share of total cycles. Save data for
later visualization but do not generate a graph now.

The first OWNER result must report model, five-hour period, total complete
cycles, cycles/hour, BUY-first and SELL-first cycles, total/BUY/SELL fills, top
ten slots, and top five buckets. Financial fields are sanity checks only:
initial/final USDT and USDC, initial/final marked equity, realized PnL, and
unrealized PnL.

If cycles are zero, diagnose without parameter changes: price outside grid,
post-only, queue, absence of compatible trades, partial-fill stall, capital,
self-cross, or implementation bug. Show counts. Do not create a successor.

`TOTAL_COMPLETE_CYCLES > 0` means only that the normalized physical mechanism
was observed under these assumptions. It does not prove profitability or live
executability.

## Publication and safety

Before the one allowed replay: create M021, preregister, test, obtain independent
review, commit, and push the exact configuration. Run exactly once, then publish
the result separately and update CURRENT_STATE, M021 journal, registry, and
result JSON. M020 and all previous evidence remain unchanged. No account,
Testnet, live trading, Day2, parameter sweep, or automatic successor is
authorized.
