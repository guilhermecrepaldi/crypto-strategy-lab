# M030 research journal

Append-only journal for hotline-first capital reallocation.

## 2026-09-10 — OWNER authorization and randomization

- OWNER authorized M030 as a new management policy with M026 parent and immutable
  M029 full-day baseline.
- Git gate passed at `4973be9cf5223f119d5be9fd623f01f8a31ced6f`, equal to
  `origin/main`, with a clean worktree.
- Before any hourly performance inspection, one OS-CSPRNG 64-bit seed was drawn:
  `13525809254189156280`.
- Its frozen sample without replacement from hours 03–23 is 06, 12 and 13 UTC.
- No random reroll, M029 replay, M031, another day or live action is authorized.

## 2026-09-10 — implementation in progress

- The canonical M026 engine was preserved. M030 subclasses it only for the isolated
  management policy, direct same-book hotline jump and required instrumentation.
- Current HOT has submission/funding priority; only zero-fill ENTRY reservations are
  reclaimable, and released assets remain unavailable until cancel ACK.
- Cycle recycling now returns principal to the central priority arbiter instead of
  recreating an obsolete source cell ahead of current HOT.
- Tests, independent source review, registration and published clean source remain
  mandatory before the single historical run.

## 2026-09-10 — registration

- M030 registered `CREATED` with model hash
  `9b7e9c8b6471243a65e0f298397e29790fa49ec4c5211c34b97d1bda6b16c7b5`.
- Ninety-two focused M026/M029/M030/registry tests pass at this checkpoint; the
  complete repository suite also passes with its two pre-existing skips.
- The first Astra review blocked execution. Corrections now bind management metrics
  back to ledger/terminal state, preserve ACK-gated request lifecycles (including
  pre-ACK rejection and partial fills), separate operational reclaim from restored
  mobility, enforce RETURN > HOT > MID/FAR admission, and propagate unexpected
  submission errors.
- The quantitative management gate was frozen before results in
  `M030_MANAGEMENT_GATE_ADDENDUM.md`: at least +5 percentage points of matched HOT
  coverage and at least 50% relative reduction of reclaimable stranded time.
- No historical M030 event has been replayed.

## 2026-09-10 — independent pre-run review passed

- GPT-6 Astra returned `PASS_CONDITIONAL_PRE_RUN` after the terminal true-capital-
  shortfall metric was independently reconstructed from physical balances,
  ownership, HOT deficits, reclaimable orders and mobility reserves.
- Sixty focused review tests passed; root's complete repository suite passed with
  the two pre-existing skips. Ruff and immutable-parent binding passed.
- The source-bound review is `reports/usdcusdt/M030-preflight-independent-review.md`.
- This is a software/scientific preflight pass, not a strategy pass. No historical
  M030 event had been replayed at this checkpoint.

## 2026-09-10 — sole physical run and reporting recovery

- The only authorized continuous 24-hour M030 engine run used published source
  `459d0237ae9005fd272a91e00de744c21da71435` and consumed all 254,205 canonical
  trades through the exact cutoff. No rerun occurred.
- The engine completed physically, then the first post-run audit stopped on
  `M030_AUDIT_RANDOM_STRANDED`. The immutable ledger, terminal, manifest and failure
  were preserved. Root cause: one raw engine counter combined literal zero-fill
  reclaimable/pending capital with broader free/mobility administrative capacity.
- Reporting-only recovery restored the terminal, invoked only `checkpoint()` and
  `metrics()`, independently reconstructed both definitions from the ledger and
  repeated the full physical audit. It delivered zero market events and changed no
  execution, fill, cycle, balance or PnL.
- The matched random hours were 06–07, 12–13 and 13–14 UTC. M029 closed 6 physical
  cycles; M030 closed 13: +7, or +116.6667%. HOT coverage rose from 67.4125% to
  94.2835% (+26.8711 percentage points).
- Literal reclaimable-stranded time fell from 100% to 59.2785%, a 40.7215%
  reduction. This missed the frozen 50% management threshold. Frequency and
  coverage gates passed; the combined management gate failed.
- Full-day diagnostic: 170 physical cycles, 509 slot cycles. Initial marked equity
  156.25220000 became 156.3188000000000000: +0.0666000000000000, or +0.0426234%.
  Final assets were 51.1088 USDT and 105 USDC. Realized cycle PnL was +0.0642;
  realized disposal PnL +0.0810014422; unrealized PnL -0.0144014422.
- Independent audit and GPT-6 Astra factual review passed. No filled-order forced
  cancel, negative realized exit, cost-basis rewrite or owned-return capital theft
  occurred. Verdict remains `INCONCLUSIVE`: normalized below minNotional,
  conditional zero-fee, no endogenous impact/live L3 rank, management gate miss and
  far below 1,000 cycles/day.
- Gate consumed. No rerun, M031, another day, account, Testnet or live action is
  authorized.
