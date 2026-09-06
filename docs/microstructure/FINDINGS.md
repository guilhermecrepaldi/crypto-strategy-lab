# LEGACY findings — initial FDUSDUSDC falsification gate

Status: `LEGACY_EVIDENCE` / `ARCHIVED_EXPERIMENT`; no new FDUSDUSDC work is authorized.

Classification: **INCONCLUSIVE** — recurrence is real in the inspected archives; executable edge
has not been demonstrated.

## Real historical sample

| UTC day | aggTrades | low→high paths | high→low paths | low→high→low cycles | low→high p50 | p95 | max |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2026-09-04 | 14,965 | 101 | 101 | 100 | 26.00 s | 435.33 s | 6,406.45 s |
| 2026-09-05 | 4,590 | 48 | 49 | 48 | 68.28 s | 736.91 s | 2,979.50 s |

Both official archives passed SHA-256 and contain no duplicate or missing aggregate-trade IDs.
The implemented state machine reproduces the stated 48 price paths on 05/09. These 149 paths are
discovery observations, not fills; the levels were selected with knowledge of 05/09. They cannot
be called prospectively validated.

For these exact levels, even the observed-price ceiling is below 2,000 cycles on each inspected
day. That refutes the 2,000/day example for these days, not the long-run strategy. Two days cannot
estimate sustainable weekly/monthly throughput, and daily report boundaries must not reset an
open cycle.

## Mechanics and costs

The full-capital compounding fixture buys 1,001.20 FDUSD from 1,000 USDC, sells the same single lot,
and ends with 1,000.100120 USDC under optimistic queue and zero maker fee. It proves deterministic
Decimal accounting only (`EDGE=NOT_EVALUATED`).

The gross spread is 1.001201 bps. With symmetric fees, break-even is about 0.500576 bps per leg,
before latency or other error. Per 100 FDUSD:

- maker→maker with zero maker fee: `+0.0100 USDC`;
- maker→maker with 1 bp each leg: `-0.009977 USDC`;
- any tested path containing a 10 bp taker leg: negative.

Thus the 1 bp-per-leg and taker-exit scenarios are economically refuted for strict one-tick
capture even with perfect fills. Waiting longer cannot turn a negative per-cycle margin positive.

## Evidence still missing

The official Spot bulk archive documents trades, aggTrades and klines, not historical sequenced
L2 for this pair. Without queue-ahead evidence, `REALISTIC_QUEUE`, partial-fill probability,
`MAX_EFFECTIVE_LOT`, net compounded return and completed executable cycles/week/month remain
unknown. The next available prospective archive after the 05/09 level freeze is also not yet a
completed historical day at this gate.
