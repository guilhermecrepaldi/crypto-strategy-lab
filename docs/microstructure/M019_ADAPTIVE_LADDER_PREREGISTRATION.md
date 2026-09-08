# M019 — adaptive stablecoin ladder V1 preregistration

STATUS=PREPARED_NOT_REGISTERED_NOT_EXECUTED
OWNER_AUTHORITY=ADAPTIVE_STABLECOIN_LADDER_OWNER_DIRECTIVE.md
MODEL=ADAPTIVE_STABLECOIN_LADDER_V1
DAY=2025-01-01T00:00:00Z/2025-01-02T00:00:00Z

## Observation and hypothesis

M018's one serial lot completed9 positive cycles and spent substantial time
waiting for one entry or exit. A retrospective one-tick price-path diagnostic
found29182 HIGH completion events on the same day, but those are not executable
fills. The falsifiable hypothesis is that twelve small, capital-backed logical
quotes managed in parallel can convert more of the observed oscillation into
complete positive cycles without degrading marked equity. This does not assume
that1000 is physically attainable.

## Capital and bootstrap

Initial liquidatable marked equity is exactly100USDT at the first valid observed
L2 bid. Target50% is converted only as an explicit initial endowment convention:
`Q0=floor_to_step(50/best_bid)` USDC and `cash0=100-Q0*best_bid` USDT. Thus the
first mark equals100 exactly. This is not an executed BUY and has no ordinary
cycle-entry identity. Endowment sales may change realized PnL after start but do
not count as cycles. A future100%-USDT executable bootstrap is a different model.

No reserve, release or cross-slot loan exists. Proceeds and profits return to the
single real free pool only after settlement. Every amount is exactly one of FREE,
RESERVED_FOR_ORDER, IN_OPEN_ORDER, FILLED_INVENTORY, PENDING_SETTLEMENT or
AVAILABLE_AFTER_SETTLEMENT. Conservation is checked after every transition.

## Frozen V1 quote policy

At each causal validated L2 state, `mid=(best_bid+best_ask)/2`. With current
temporal rule tick `t`, BUY offset i=0..5 targets `floor(mid/t)*t-i*t`, strictly
below ask. SELL offset i targets `ceil(mid/t)*t+i*t`, strictly above bid and the
strictly positive break-even price of its bound FIFO lot. No microprice, OBI, OFI,
volatility adaptation, external fair value or retrospective range is used.

SAFE_MIN_NOTIONAL is `max(6USDT,1.20*rule.min_notional)`. Order quantity is the
smallest whole step whose price-notional reaches that threshold, subject to all
available balance and symbol filters. The transferred historical rule envelope
for this source day has tick0.0001, step1USDC and min-notional5USDT; its evidence
hash remains bound, but it is a conditional historical assumption, not proof of
the exact account rule. The rule yields six-USDC orders around par.

The first valid book divides the complete endowment quantity as evenly as the
step permits across six bands; any rounding remainder stays in band6. Subsequent
BUY fills create traceable lots in the BUY slot's band. A SELL selects FIFO lots
within that band only until their combined quantity reaches SAFE_MIN_NOTIONAL;
its price is at least the greatest strictly profitable break-even of those lots.
If the combined quantity is still too small, no SELL is sent. Partial exits
preserve exact remaining basis. Closed lots remain in the lineage with zero
remaining quantity. An endowment lot never produces an ordinary cycle ID.

Cycle identity is the source BUY order, not each partial print. One positive
cycle is recorded only after that BUY is terminal (FILLED or partially filled
then CANCELED), every lot created by its fills is fully sold, and their aggregate
net PnL is positive. Fragmenting the same entry into more prints cannot increase
the cycle count.

Free quotes are reconsidered every60seconds. Cancel/reposition only when their
new target differs by at least2 current ticks. Pending cancel retains its capital
and can still fill until effective acknowledgement. Inventory exits are not
canceled merely because mid moves; a replacement must remain strictly profitable.
No position timeout, forced exit or cutoff settlement exists. Holds beyond1/2/6/
24hours are metrics.

Projected marked USDC share includes current inventory and every active/pending
BUY as if filled at its order price and marked at the current bid. Projected
equity includes that execution-cost/mark difference. A candidate smaller than
SAFE_MIN_NOTIONAL is not submitted, even if it satisfies the exchange minimum.
New BUYs are blocked when the full counterfactual would exceed90% of projected
marked equity. Crossing the cap through price movement blocks new exposure but
never causes a loss sale.

The manager prevents self-cross against all own PENDING, ACTIVE and
CANCEL_PENDING orders. During construction a SELL is shifted at least one tick
above the highest own BUY; any remaining crossing is blocked at submission and
checked again at activation. No own quote is treated as observed market
liquidity.

## Shared execution

Use the existing capture-ordered observed L2 source, temporal rules and frozen
B_REALISTIC_CONSERVATIVE latency/cancel latency/zero-fee profile. PRICE_PRIORITY
is the only first-run envelope. It remains a counterfactual execution assumption.

At activation, LIMIT_MAKER crossing is rejected and reservations are returned.
An order outside the snapshot's causally known coverage is also rejected; a
missing level is zero queue only inside that coverage. Actual activation time is
the capture-arrival evaluation, and a native trade can participate only when its
exchange timestamp is strictly later than that activation time. A cancel-pending
order submitted before activation does not gain premature fill eligibility.
Otherwise queue ahead is same-side displayed quantity at that limit. Compatible
exact-price trades reduce ahead then fill. Strict trade-through may infer priority
only for orders active before that print. All open orders are processed by
(active_time,order_id); one global per-trade quantity budget covers queue depletion
and fills across all slots. Book touch alone never fills. Depth is likewise not
reused. Self-cross is prohibited. Shared order-rate limits apply.

## Required evidence and metrics

Every order, fill, reservation, cancellation, lot creation/allocation, settlement,
cycle, band, liquidity consumption and balance transition is audit logged. A
checkpoint preserves all twelve slots, open/cancel-pending orders, lots and basis,
balances, band memory, counters, consumption state and clock. Resume must equal a
continuous fixture.

Primary OWNER output: positive cycles, final USDT, final USDC, USDC marked value,
total marked equity, realized and unrealized PnL, and1000/2000 gates. Internal
metrics include endowment sales, open/dormant/underwater lots, per-slot submissions,
fills/cycles/PnL/inventory/cancels/reprices/fill time, queue consumption,
post-only rejects, fees and hold alerts. Compare descriptively with M018 and a
passive same-endowment mark;
M018's110 initial capital is not a capital-matched causal control.

If day1 completes below1000, do not retune. Classify the dominant bottleneck from
QUEUE, INSUFFICIENT_PRICE_OSCILLATION, SPREAD, ORDER_REPRICE, INVENTORY_LOCK,
CAPITAL_SHORTAGE, POST_ONLY_REJECTION, LATENCY, EXECUTION_MODEL or OTHER, then
preregister at most one justified successor. No day2 load or execution.

## Pre-execution gates

Before run: implementation tests for capital/fill/lot/cycle/cancel/shared-liquidity/
checkpoint/profile/rule and continued-suffix equivalence invariants; independent
GPT-6 Astra review bound to exact sources;
M019 CREATED registry identity; clean published origin/main; explicit OWNER gate
for M019 and one day. TEST_SUITE_PASS does not imply STRATEGY_PASS.
