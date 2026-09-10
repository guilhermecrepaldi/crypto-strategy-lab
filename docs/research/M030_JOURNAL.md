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
