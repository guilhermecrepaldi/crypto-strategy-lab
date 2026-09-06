# LEGACY — stablecoin two-level cycling specification

Status: `LEGACY_EVIDENCE` / `ARCHIVED_EXPERIMENT`. `S0_FROZEN_LEVELS-v1` is preserved as the
first falsification slice and is not the active USDCUSDT campaign specification.

## Invariants

- Spot only, `FDUSD/USDC`, no leverage, grid, DCA, martingale, ML, real orders or credentials.
- Exactly one lot. Buy passively at `0.9988`; only after the buy is completely filled,
  sell the acquired FDUSD passively at `0.9989`.
- A touch or trade at a price is not our fill. Queue volume must be consumed before our order.
- The next buy may start only after the prior sell is completely filled and accounted.
- `COMPOUNDING_LOT` reinvests available USDC after each closed cycle.
  `FIXED_LOT` keeps its configured budget. Both round quantity down to `stepSize` and retain dust.
- No time-based stop, forced taker exit or repricing exists in the base strategy. Open inventory
  crosses reporting boundaries and remains open at the end of the dataset.
- Long holding time is measured as throughput and regime risk; it is not an automatic failure.
- Levels remain frozen for an identified operating window. Any reselection uses only information
  available before the next window and creates a new run identity.

## Risk states

`TEMPORARY_LOCK` leaves the sell at the frozen high level. `STRUCTURAL_DEPEG` requires explicit,
recorded evidence and enters `RISK_HALT`: the current cycle may finish at its existing target, but
no new cycle starts. The simulator never forces liquidation on this event.

## Capacity

Compounding cannot be extrapolated beyond observed execution capacity. Later L2/shadow gates must
estimate `MAX_EFFECTIVE_LOT` by quantity, queue ahead, partial fills, capital utilization and net
cycle throughput. Trade volume alone is not a capacity estimate.

## Current evidence boundary

The fixture validates mechanics only and reports `EDGE=NOT_EVALUATED`. Historical Spot archives
contain trades/aggTrades/klines, but not the sequenced L2 history needed to identify our queue.
Accordingly, a trade-only replay is an observed-price upper bound, never `REALISTIC_QUEUE` evidence.
