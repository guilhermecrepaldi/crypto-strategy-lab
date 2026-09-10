# M026 — dynamic hotline 3/2/1 preregistration

`MODEL_ID=M026`; parent M024; M025 is evidence only. One run is authorized on
the exact M024 tape, 2025-01-01T00:00:00Z–03:00:00Z exclusive.

## Frozen geometry and capital

The first causal ask anchors the hotline. Fifteen absolute prices exist on each
side. Ranks 1–5 are HOT (3 columns × 3 slot units), 6–10 MID (2 × 2), and 11–15
FAR (1 × 1): 60 physical entries and 140 operating slot units. A real buffer of
8 slot units in USDT plus 8 slot units in USDC is endowed at initialization.
The physical initial bank is derived after the first book from exact reserved
quantities and prices; 156 is a slot-unit description, not an exact USDT claim.

Target order notional is `slot_count × slot_base_at_epoch`. Historical quantity
step is 1 USDC. Quantity is `max(1, ROUND_HALF_UP(target/price))`; target, actual
and quantization error are logged. Only min-notional is virtualized.
The normalized balance ledger uses a `0.00000001` USDC/USDT quantum. A future
slot base is rounded down to that quantum before it becomes an epoch authority;
this is conservative and prevents sub-quantum compounding from creating usable
capital. Returns still preserve the entry's actual filled quantity exactly.

## Frozen causal manager

Midpoint greater than hotline + 0.5 tick advances one tick; midpoint lower than
hotline − 0.5 retreats one. Equality holds. Multi-tick changes are processed one
step at the same causal timestamp. Each step is a new epoch. No fills occur
between synthetic substeps.

Order identity is `(side, absolute line price, column, lifecycle)`. Old orders
never move, resize or reset FIFO. A newly required column is submitted behind
aged orders if real capital exists. A demoted excess column drains and is not
recycled after its positive return. Outside-grid free orders are canceled only
through causal cancel acknowledgment; owned returns always win conflicts.

The initial slot base is 1 USDT-equivalent. Realized completed-cycle profit can
raise the candidate base only at a later hotline epoch and only after both
mobility reserves meet their candidate targets. Unrealized profit, locked
capital and asset conversion cannot fund growth.

## Outcome and gates

A physical cycle is one fully completed positive entry/return lot. Its
slot-equivalent weight is the entry's frozen slot count. The primary results are
physical cycles, physical cycles/hour, slot-equivalent cycles and slot cycles/hour.
Pass requires independently: at least 38 physical cycles and at least 60 slot
cycles in three hours. PnL, inventory and all reserve movements are reconciled.

The run is normalized and not live executable. Public queue is an L2 estimate,
true L3 position and endogenous impact are unknown, and zero fees are a frozen
profile assumption rather than an account fact. No rerun, sweep, M027, extension
or live action is authorized.
