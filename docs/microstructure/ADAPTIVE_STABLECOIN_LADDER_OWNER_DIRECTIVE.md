# OWNER — adaptive stablecoin inventory ladder

RECEIVED_DATE=2026-09-08
STATUS=ACTIVE_AUTHORITY
SYMBOL=USDCUSDT
SCOPE=HISTORICAL_L2_ONLY; NO_ACCOUNT; NO_TESTNET; NO_LIVE

This authority creates a new strategy identity. B10, M014, M015, M018 and all
published results remain immutable evidence. The prior three-range proposal is
superseded before implementation or execution.

## Objective and gates

Build a spot-only inventory ladder with exactly six logical BUY slots and six
logical SELL slots. It must recycle actual free capital, retain the cost basis of
every filled lot, allow old underwater inventory to wait while free capital keeps
working, and never realize a net loss. An ordinary positive cycle requires actual
entry fill(s), actual exit fill(s), complete economic settlement and strictly
positive net PnL after all modeled costs. Orders, cancellations, partial legs,
endowment sales, releases and breakeven do not count.

The first economic run is only the validated L2 source day 2025-01-01 UTC. It is
DEVELOPMENT. Target is at least1000 complete net-positive cycles in24h without
degrading total marked equity. No day2 input may be opened unless the first day
passes, the exact model is frozen and independently audited, and the OWNER gate
is updated. The2000 target belongs to a later identity after three unchanged days
each pass1000. Failure on day1 requires an autopsy, not parameter sweep.

## Absolute invariants

- REALIZED_LOSS_ALLOWED=false. An exit needs net proceeds greater than its
  assigned cost basis to count; negative exits are forbidden. Breakeven is not a
  positive cycle.
- Every USDT and USDC unit has exactly one owner state. No order, slot or lot may
  reuse funds reserved elsewhere. No unbacked spot SELL or BUY.
- Every observed trade/depth budget is shared across all twelve slots and may be
  consumed once. Self-competition, latency, queue and cancel-pending state apply.
- Every BUY fill creates traceable inventory. Partial lots persist. No lot may
  disappear or be sold twice. Recentring a free quote never moves inventory cost.
- Quotes backed only by free capital may be canceled and repositioned. Inventory
  exits may move only to another strictly profitable price for their bound lots.
- No fill from a touch, timer, chart or target. No forced liquidation at cutoff.
  Open inventory is marked and censored with unrealized PnL visible.
- Slots remain exactly BUY_SLOT_1..6 and SELL_SLOT_1..6. A blocked slot does not
  authorize slot7. Slots may be empty when capital, inventory, filters or causal
  book evidence are insufficient.
- Historical symbol rules and costs must be bound to their stated evidence.
  Current rules are not silently relabeled as historical facts.

## V1 isolation

The preregistered V1 isolates parallel quotes, ladder management and inventory
recycling. It uses observed L2, one simple causal center, one simple spacing rule,
small safe valid notional, an inventory cap and restrained quote refresh. It has
no ML, OBI, OFI, external or triangular fair value, reserve, release, stop-loss,
active treasury, DCA or future-data selection. Those are later hypotheses.

Internal artifacts must preserve slots, orders, cancel state, lots, cost basis,
balances, band memory, liquidity consumption and cycle IDs across checkpoint and
resume. Software tests do not imply strategy success.

## OWNER-facing result

Return first: day, model, positive cycles, final USDT, final USDC, marked USDC
value, total marked equity, realized net PnL, unrealized PnL and1000/2000 status.
Then report open lots, maximum hold, reposition count and the dominant bottleneck.
No chart unless requested.
