# M035 random 3h V2 — economic result

Status: complete development diagnostic; not OOS, not live, and not a strategy pass.

Window: 2026-02-01 01:00–04:00 UTC, selected and frozen before economic inspection.
Each scenario started independently with one 200 USDT bank. The parallel arm shared that one bank
between USDCUSDT and FDUSDUSDT; it did not duplicate capital.

| Fee/leg | Single cycles | Parallel cycles | Single PnL | Parallel PnL | Single utilization | Parallel utilization |
|---:|---:|---:|---:|---:|---:|---:|
| 0 bp | 0 | 0 | 0 | 0 | 50.004% | 99.525% |
| 1 bp | 0 | 0 | 0 | 0 | 40.001% | 79.616% |
| 2 bps | 0 | 0 | 0 | 0 | 29.999% | 59.709% |
| 5 bps | 0 | 0 | 0 | 0 | 0% | 0% |
| 10 bps | 0 | 0 | 0 | 0 | 0% | 0% |

All final marked equities were 200 USDT and all returns were 0%. There were zero fills, negative
cycles, risk exits, fees, dust or non-USDT residual inventory. Capital conservation and unique
ownership passed. Pair A and Pair B each completed zero cycles.

The parallel engine reserved almost twice as much capital at F0, but did not turn that capital into
a fill or cycle. The admitted buy levels were not reached while executable. F5/F10 admitted no
orders because the preregistered expected-net-edge gate rejected them. Therefore the parallel cycle
and capital-productivity acceptance conditions failed. Zero-loss is true only vacuously, and fee
break-even cannot be estimated from a zero-fill observation.

The uncompressed result is 185,838,056 bytes and remains immutable locally with SHA-256
`b241cf85c8ea8c6afb68fc37f7aa37371c49274466dff08635afe0342e57ddd0`. Git publishes the exact
result inside `M035_RANDOM_3H_V2_RESULT_FULL.zip`; the archive SHA-256 is
`7787fe34bf485781e32cb1a294be86aa841d4cbf988a4214b7837707ece13a93`.

Independent GPT-6 Astra audit passed 227 checks over 960,503 preserved records. See
`reports/m035/M035_RANDOM_3H_V2_RESULT_AUDIT.json` for hashes, reconciliation and interpretation
limits.
