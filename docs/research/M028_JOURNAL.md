# M028 research journal

Append-only journal for the M026 full-day temporal replication.

## 2026-09-10 — OWNER authorization

- OWNER selected the unchanged M026 strategy and authorized extending its test to
  one full day, requesting before/after equity and percentage gain.
- Duration is part of M026's immutable identity; M028 is therefore a temporal
  replication with M026 as parent, not a retroactive edit or optimization.
- Fixed period: 2025-01-01T00:00:00Z through 2025-01-02T00:00:00Z exclusive.
- The engine initializes once at midnight and does not reset at 03:00.
- Exact M026 prefix equivalence is a hard technical gate before later events.
- Primary return is marked equity change including the mobility capital. Realized
  cycle PnL is reported separately and is not added twice.
- Result remains normalized, below minNotional and not live-executable.
- No other day, rerun, M029, account, Testnet or live execution is authorized.

## 2026-09-10 — physical preflight and registration

- All 144 validated ten-minute native L2 slices for January 1 were rehashed and
  accepted by the published evidence validator.
- The bounded canonical day contains 254,205 trades, IDs 206597089–206851293.
- Frozen latency and cancel latency remain 1,179,525 microseconds; maker/taker
  fees remain the M026 conditional zero-fee research assumption.
- M028 was registered with model hash
  `76305edc1bab271d5358ad6954195ff01ad77319a4a9f5dc7bc4b1c9d46be301`.
- Fifty-five focused M026/M028/registry tests passed and Ruff accepted the delta.
- No historical event has been replayed. Independent source-bound Astra review,
  publication and clean-HEAD gates remain pending.
- First GPT-6 Astra source-bound review: `BLOCK`. It found one exact historical
  test-only hash transition that the strict M026 source gate did not distinguish,
  and it demonstrated that the result auditor accepted tampered before/after aliases.
  It also requested a real-kernel boundary-continuation fixture. No replay started.
- Corrections now permit only the exact published-to-current hash pair for
  `tests/test_run_dynamic_hotline_321.py`; all economic sources and physical M026
  artifacts remain strict. The auditor independently reconciles both equity aliases,
  the 03h reference, incremental gain, percentages, auxiliary rulers and the terminal
  24h interval. Negative tamper tests and a real M026-kernel 3h boundary/continuation
  test were added. Sixty-four focused tests and Ruff now pass. Re-review is pending.
- Final GPT-6 Astra source-bound review: `PASS_CONDITIONAL_PRE_RUN`. It confirmed
  the exact test-only hash exception, strict economic/physical bindings, 24h result
  reconciliation and real-kernel no-reset fixture. The review binds all 35 source
  files. Publication and clean-HEAD checks remain before the single run.

## 2026-09-10 — only authorized run invalidated at the prefix gate

- Pre-run source was committed and pushed as `915cc44`; `HEAD==origin/main`, the
  source-bound Astra review and all preflight gates passed before execution.
- The run reached the exact 03:00 boundary, then failed closed with
  `M028_M026_PREFIX_ECONOMIC_STATE_MISMATCH` before any later event was delivered.
- `EVENTS_AFTER_03H_PROCESSED=0`; the 21-hour extension was not consumed and no
  24-hour result exists.
- The preserved M028 ledger is byte-for-byte identical to the published M026 ledger:
  43,372 rows and SHA-256
  `7d3fc1e67a41395c353009e829d1288562f8f25eb4554c3f2cf4db9743fd4bb8`.
  Fills, cycles and ledgered economics through03:00 therefore matched.
- Strongest reproduced diagnosis is a type-sensitive checkpoint comparison: the
  live object retained `Decimal` values and integer dictionary keys while published
  JSON restored strings. The failed process did not persist the rejected checkpoint,
  so the artifacts cannot prove this was the only non-ledger state difference. It
  remains a technical failure, not a strategy/economic result.
- M028 is `INVALIDATED_TECHNICAL`. Its one-run gate is consumed; no rerun, resume,
  M029 or post-03:00 replay is authorized. A corrected retry requires a new OWNER
  authorization and identity.
- The immutable reached reference remains M026: marked equity156.2522→156.2972,
  gain0.0450 or0.0287995945%,30 physical and90 slot-equivalent cycles in3h.
- Failure finalization registered only preserved artifacts and performed no market
  event replay.
- Final GPT-6 Astra post-failure review: `PASS` for technical closure, with the
  limitation above. It independently confirmed43,372 ledger rows,29,538 trades,
  78 fills,30 cycles, the identical ledger hash and no economic event at/after03:00.
