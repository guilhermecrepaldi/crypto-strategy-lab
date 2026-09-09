# M025 — order-size capacity curve preregistration

## Status and boundary

`MODEL_ID=M025`; parent `M024`; strategy `M024_ORDER_SIZE_CAPACITY_CURVE_V1`.
This is an OWNER-authorized controlled capacity sweep, not a live-executable claim.
The single campaign uses only `2025-01-01T00:00:00Z` inclusive through
`2025-01-01T03:00:00Z` exclusive. M024 and its physical evidence remain immutable.

The eleven independent scenarios run once, held in ascending-Q order:
`Q={10,50,100,250,500,750,1000,1500,2000,3000,5000} USDC`.
Only Q changes. Book, trades, order-manager rules, latency, cancellation semantics,
post-only gates, fee assumption, queue policy, 50+50 levels, depth triangle,
150 initial orders, 200-order cap, causal cutoff and no-liquidation rule are frozen.
Each scenario owns an independent engine, capital ledger, public-queue estimate and
trade-consumption ledger. No state or consumed quantity crosses scenarios.

## Capital and execution semantics

Capital is derived from the 150 real initial reservations at the first causal book.
Expected at the frozen first bid/ask: `INITIAL_USDT=74.9900×Q`,
`INITIAL_USDC=75×Q`, `INITIAL_MARKED_EQUITY=150.1325×Q`.
No capital is injected later. Market trades and displayed book quantities are never
scaled with Q. Endogenous market impact is absent and historical queue rank is not
known; this is a conservative L2-model capacity curve.

Every submitted ENTRY or RETURN has exactly Q. An entry may fill in fragments, but
one cycle exists only after the entire Q entry and the entire Q profitable return
fill. A fragment is never a cycle or Q separate cycles. If a cancel race leaves a
partially filled entry, the unfilled reservation is released once and the acquired
partial lot stays visibly locked (`PARTIAL_ENTRY_CANCELED_LOCKED`); M025 does not add
fractional-return or aggregation policy. This deliberately conservative case cannot
count as a cycle or finance another full-Q cell.

`NEGATIVE_EXIT_ALLOWED=false`; breakeven is not positive. Principal recycles exactly
as in M024. Realized completed-cycle profit accumulates in `GROWTH_POOL`, but structural
expansion is disabled: no new queue cell, column or depth can be funded at any Q.

## Metrics frozen before observation

Per Q: full cycles and cycles/hour; completed roundtrip USDC (`Q × cycles`); total
two-way filled USDC and USDT notional; buy-first/sell-first and column cycles;
entry/return order counts and completions; fill fragments; partial and full-fill rates;
residual partials; first-fill, first-to-full, full-fill, public-queue-zero-to-first and
public-queue-zero-to-full timing distributions (mean/median/P95/max); queue consumption,
public and own quantities ahead; open inventory/cost and capital locked; final balances,
marked equity, completed-cycle/disposal/unrealized PnL and accounting residual; capital
utilization and all required per-hour/per-1000-capital normalizations.

`PARTIAL_FILL_RATE = orders with 0 < filled < Q at cutoff / all submitted orders`.
`FULL_FILL_RATE = fully filled orders / all submitted orders`. Fill-fragment rate is
reported separately. Public-queue-zero timing is reconstructed by cohort: for each
order, only public segments existing at its activation are relevant; later cohorts are
behind it. Own-size execution time begins when those relevant public barriers reach
zero. Zero/public and own-ahead statistics remain model estimates, not observed L3 rank.

`CAPITAL_LOCKED_IN_PARTIALS` is filled entry basis plus the still-required quantity of
partially filled returns at their order price. `CAPITAL_LOCKED_IN_OPEN_LOTS` uses the
owned USDC layer cost reconstructed by the M024 accounting authority. `REALIZED_PNL`
and its per-hour form mean completed-cycle PnL, matching M024; realized disposal PnL
and its per-hour form remain separate.

The audit reconstructs full-Q cycle identity, order quantities, per-trade global
volume budgets, own FIFO precedence, reservation ownership, lots, no negative exit,
no growth cells, checkpoint scenario binding and capital identity independently of
the kernel counters.

The independent audit reconstructs every scenario directly in physical USDC units.
It is a source-bound parameterization of the complete M024 reconstruction: public
queue, own FIFO, trade budget, fills, lots, cash, inventory, cycles and the shadow
pre-aging counterfactual are checked using exact `Decimal` values at Q. No division
by Q, normalized tape, rounding, epsilon or tolerance is permitted.

## Capacity and knee rules

For adjacent sizes, compute cycle retention, cycles/hour drop, incremental completed
notional and partial/censoring/timing deltas. If the previous scenario has zero cycles,
ratios are `UNDEFINED`, never zero or infinity. `SCALING_EFFICIENCY` and normalized
roundtrip throughput reduce algebraically to cycle retention because capital and Q
scale together; they are descriptive aliases, not independent evidence.

`FIRST_SIZE_WITH_GE20_CYCLE_RATE_DROP` is the first Q whose cycles/hour is at least
20% below the immediately smaller Q. A `CAPACITY_KNEE` is declared only when that drop
is corroborated by at least one orthogonal physical signal, frozen here as: at least
one additional residual partial order at cutoff; an order full-fill-rate decline of at
least 10 percentage points; or a median submission-to-full-fill duration increase of
at least 20%. Otherwise the result is `NOT_OBSERVED_UP_TO_5000` or
`CYCLE_DROP_WITHOUT_ORTHOGONAL_CONFIRMATION`. Ranking ties select lower Q.

Q500 receives an explicit scoreboard and comparisons to Q250/Q750/Q1000, plus the
required Q1000→Q1500 comparison. The post-curve future diagnostic covers exactly the
three requested bases without execution: B250={750,500,250}, B500={1500,1000,500},
B1000={3000,2000,1000}; each reports whether all three sizes lie below an observed
knee. It cannot alter M025.

## Fail-closed run discipline

The exact source, registration, tests and source-bound GPT-6 Astra review must be
committed and pushed before the first market event. Existing output blocks execution.
The campaign reads the native tape once and broadcasts each event in ascending Q to
eleven strictly independent engines; this is eleven independent scenario state machines,
not shared execution or shared liquidity. A technical error after any market event
preserves every reached prefix and
stops the campaign. No scenario is rerun. No M026, day2, tuning, account, Testnet or
live action is authorized.

`TEST_SUITE_PASS != STRATEGY_PASS`.
