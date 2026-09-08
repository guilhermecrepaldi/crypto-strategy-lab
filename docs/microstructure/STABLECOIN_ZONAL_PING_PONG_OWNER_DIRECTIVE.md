# OWNER DIRECTIVE — STABLECOIN ZONAL PING-PONG — 5H THROUGHPUT DISCOVERY

Status: ACTIVE OWNER AUTHORITY  
Date: 2026-09-08  
Scope: USDCUSDT historical L2, DEVELOPMENT only

This is a new hypothesis, not a silent continuation of M019. Preserve M019,
including its D1 result of 10 cycles and its `INVENTORY_LOCK` autopsy. Do not
modify B10 or M014–M019 retroactively. Register the new hypothesis under M020 if
that registry identity remains free.

## 1. Authorized question and exact window

Measure how many complete `BUY→SELL` and properly owned `SELL→BUY` round trips
can close in five hours with immutable fixed price zones, a rolling operational
window and fast per-band recycling.

- `SOURCE_DAY=2025-01-01`
- `START=2025-01-01T00:00:00Z`
- `END_EXCLUSIVE=2025-01-01T05:00:00Z`
- use validated historical L2 and matching canonical trades;
- no economic decision may read or depend on an event at or after 05:00 UTC;
- no second day is authorized.

Primary OWNER result:

```text
MODEL=
PERIOD=5H
TOTAL_CYCLES=
CYCLES_PER_HOUR=

TOP_5_BANDS:
1. BAND=... CYCLES=...
...
```

Then report all bands as `BAND_LABEL | PRICE_LOW | PRICE_HIGH | CYCLES |
SHARE_OF_TOTAL`. Do not generate a graph. Preserve machine-readable data for a
possible later graph.

## 2. Normalized order mode

- `NORMALIZED_NOTIONAL_PER_ORDER=1 USDT`
- `ORDER_NOTIONAL_MODE=NORMALIZED_1_USDT_NON_EXECUTABLE`
- `NON_EXECUTABLE_NORMALIZED_THROUGHPUT_DIAGNOSTIC=true`

One-USDT orders are below the real USDCUSDT Spot minimum notional. Disable only
the minimum-notional acceptance gate required for this structural comparison.
Do not claim that Binance would accept these orders. Preserve price/tick and
quantity rules unless the preregistration explicitly records why an additional
virtual normalization is required; preserve L2, queue, latency, post-only
semantics, trade direction, liquidity consumption, price priority and
future-data protection.

The report must state at its top:

> THIS 1-USDT ORDER RESULT IS A NORMALIZED STRUCTURAL THROUGHPUT TEST. IT IS
> BELOW BINANCE MINIMUM NOTIONAL AND IS NOT A LIVE-EXECUTABLE RESULT.

A later replay with `EXECUTABLE_SAFE_MIN_NOTIONAL` is a possible new step, not
authorized by this directive.

## 3. Economics and cycle definition

This round measures throughput, not profit optimization. Do not research
funding, reserve, compounding percentage, optimal order size or annualized
return. `RESERVE=0` and `RELEASE=DISABLED`.

- a counted cycle requires a fully filled entry and fully filled exit linked by
  ownership;
- `NEGATIVE_EXIT_ALLOWED=false`;
- an exit must not be below the economic basis of its entry after applicable
  costs;
- breakeven may be recorded separately but is not a positive cycle;
- an initial endowment leg alone is not a cycle;
- do not force liquidation at the five-hour cutoff;
- open inventory stays open and marked.

If the implementation supports `SELL→BUY`, the SELL must be backed by explicitly
reserved, pre-existing USDC and the later BUY must close that same economic
sequence without double-counting the endowment or cash proceeds. Freeze this
definition before the replay.

## 4. Descriptive 2025 occupancy and immutable band map

Before the replay, calculate `PRICE_OCCUPANCY_2025` and the narrowest contiguous
price interval containing at least each requested fraction of observed time:

```text
ANNUAL_LOW=
ANNUAL_HIGH=
P80_RANGE_LOW=
P80_RANGE_HIGH=
P80_WIDTH=
P90_RANGE_LOW=
P90_RANGE_HIGH=
P95_RANGE_LOW=
P95_RANGE_HIGH=
P99_RANGE_LOW=
P99_RANGE_HIGH=
```

For avoidance of doubt, the OWNER explicitly permits the full canonical
calendar-2025 historical trade universe for this **descriptive geometry
research**. The exact weighting method, missing-time treatment and deterministic
tie breaks must be preregistered and reported. This creates deliberate
development lookback/lookahead relative to D1 and therefore:

- `DEVELOPMENT_RANGE_SELECTION_USES_HISTORICAL_OCCUPANCY=true`;
- D1 is not out-of-sample and must never be described as such;
- only the resulting frozen geometry may enter the five-hour replay;
- no event at/after 05:00 may be used by the economic state machine.

Within P80, construct contiguous immutable price-band addresses. The real count
depends on `P80_WIDTH / TICK_SIZE`: use the maximum physically distinct count
when fewer than 40 useful levels exist; otherwise freeze at most 40 potential
BUY regions and at most 40 potential SELL regions in V1. Never create duplicate
prices. Record:

```text
PRICE_BAND_ADDRESS_IMMUTABLE=true
AVAILABLE_DISTINCT_PRICE_LEVELS=
BUY_BAND_COUNT=
SELL_BAND_COUNT=
TOTAL_BANDS=
```

Bands do not follow mid. The map is fixed; free quote allocation over it may
move. A finite map may fail to provide four valid levels at an edge. In that
case record `WINDOW_UNDERSUPPORTED`; do not invent, move or extend bands.

## 5. Rolling active window

Implement a `ROLLING_COVERAGE_MANAGER` that attempts, when fixed bands,
inventory and real capital permit, to maintain:

- `MIN_ACTIVE_BUYS_BELOW=4`
- `MIN_ACTIVE_SELLS_ABOVE=4`

When coverage thins, it may cancel only unfilled and economically free quotes,
release their reserved capital exactly once, and activate eligible fixed bands.
It may not teleport inventory, create capital, create a seventh logical need,
or silently extend the immutable price map. It must preserve useful queue
priority and realistic cancel/re-entry latency. Freeze the deterministic
selection/reposition policy before execution.

## 6. Per-band ping-pong and ownership

Each band owns at most one open economic sequence in V1:

```text
READY_FOR_BUY
BUY_WORKING
USDC_INVENTORY
SELL_WORKING
CYCLE_COMPLETE
DORMANT
```

The ordinary sequence is `BUY → fill → owned USDC → profitable SELL → fill →
cycle complete → capital returns → BUY again`. Do not allow repeated BUY
accumulation in the same band before its prior sequence resolves.

Filled inventory is not a movable quote. If price leaves it behind, the band may
become `DORMANT_WAITING_PROFITABLE_EXIT`; other bands may continue if they have
real free capital. Dormant inventory is not productive capital and cannot be
discarded or reassigned.

Adjacent bands or opposite-side quotes must never self-cross. Where a requested
four-by-four window cannot be represented without self-crossing, record the
constraint instead of fabricating active coverage.

## 7. Execution fidelity

All bands share the same tape and global consumption ledger.

- one observed quantity is consumable once;
- deterministic allocation is `PRICE_PRIORITY`, then `ACTIVE_TIME`, then
  `ORDER_ID`, with side-specific price ordering frozen before the run;
- use the best currently authorized observed-L2 queue model and strict
  trade-through where preregistered;
- touch is not fill;
- record `QUEUE_BLOCKED_FILLS`, `TRADE_THROUGH_FILLS` and `EXACT_LEVEL_FILLS`;
- preserve latency, post-only behavior, aggressor compatibility and price
  priority;
- never invent fills or liquidity.

## 8. Fixed normalized capital

Freeze `TOTAL_NORMALIZED_CAPITAL=100 USDT-equivalent` before the run. The initial
split must finance both BUY quotes and owned SELL inventory. The suggested V1
split is 50 USDT plus 50 USDT-equivalent of USDC at the first valid causal bid.
This endowment is not an executed trade and does not count as a cycle. Do not
create capital on demand. Track USDT, USDC, reserved balances, working orders,
lots and marked equity exactly.

## 9. Preregistered single configuration

Run one configuration only:

- P80 immutable map;
- at most 40 regions per side as physically distinct;
- rolling target 4 BUY below / 4 SELL above when feasible;
- normalized 1-USDT first-leg unit;
- one economic sequence per band;
- no reserve or release;
- no negative exit;
- no parameter sweep and no result-driven tuning.

M019 may be cited qualitatively only. Do not compare PnL directly because its
architecture, horizon and executable notional differ.

## 10. Required artifacts and metrics

For every band retain:

- fixed ID, price low/high;
- complete and positive cycles;
- share of total;
- time and percentage of the five hours with price inside;
- trades and volume inside;
- cancels and repositions;
- current inventory and state.

Also record:

```text
TOTAL_CYCLES_COMPLETE=
TOTAL_POSITIVE_CYCLES=
CYCLES_PER_HOUR=
USDT_FINAL=
USDC_FINAL=
TOTAL_MARKED_EQUITY=
ORDERS_CANCELED=
ORDERS_REPOSITIONED=
ACTIVE_BANDS=
DORMANT_BANDS=
TOP_BAND_SHARE=
TOP_3_SHARE=
TOP_5_SHARE=
PERCENT_BANDS_RESPONSIBLE_FOR_80_PERCENT_CYCLES=
MAIN_LIMITER=
```

Balance is a sanity check for capital creation/loss and inventory bugs, not the
optimization objective.

## 11. Mandatory tests and deterministic restart

Before the economic replay test at minimum:

- fixed band IDs never move;
- one economic sequence per band;
- free-quote cancel releases capital exactly once;
- inventory cannot move bands without an explicit ownership event;
- negative exit is rejected;
- a cycle requires full entry and exit;
- the same fill cannot count twice;
- the same liquidity cannot be reused;
- rolling coverage preserves four below/four above when bands,
  inventory and capital permit and reports insufficiency otherwise;
- no future-price use;
- checkpoint/resume equivalence;
- exact five-hour cutoff.

`TEST_SUITE_PASS != STRATEGY_PASS`.

## 12. Autopsy and publication gates

If throughput is low, classify the limiter without changing the strategy. Do not
perform a parameter sweep. Preserve and publish:

- new model identity/specification;
- this OWNER authority;
- journal and registry entry;
- preregistration and independent scientific review;
- source and tests;
- 2025 occupancy result and provenance;
- result JSON and audit/autopsy.

Preregistration must be committed and pushed before the replay. Result evidence
must be committed and pushed after the replay. Preserve M019 and all older
published evidence. No live, Testnet, account, API-key or second-day access is
authorized.

## Final OWNER question

In five hours, with fixed price bands, rolling coverage, individual per-band
ping-pong and normalized one-USDT orders, how many complete cycles were possible,
and in which bands were they concentrated?

Do not optimize the result, use future economic data, fabricate fills, duplicate
capital/liquidity, or call the one-USDT normalized order Binance-executable.
