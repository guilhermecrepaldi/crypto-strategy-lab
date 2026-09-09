# M021 research journal — dense 200-slot ping-pong mechanics probe

Append-only journal for `DENSE_200_SLOT_PING_PONG_MECHANICS_PROBE_V1`.

## 2026-09-08 — OWNER authority and pre-registration draft

- M020 remains preserved and rejected. M021 is a new mechanical hypothesis.
- Only 2025-01-01 00:00–05:00 UTC is authorized, using the same validated M020
  L2, canonical trades, queue, latency, and audit assumptions.
- First causal bridged book: bid 1.00190000, ask 1.00200000, midpoint
  1.00195000 at capture/exchange microsecond 1735689609412998. Deterministic
  half-up tick quantization freezes anchor 1.0020.
- Proposed grid: 100 BUY entries 1.0019–0.9920 and 100 SELL entries
  1.0021–1.0120; fixed one-tick returns, no recenter.
- Exact normalized capital: 99.6950 USDT plus 100 USDC, initially marked
  199.88500000 USDT-equivalent. This cannot be compared directly with M020's
  capital-100 return.
- The one-USDC unit is below Binance minimum notional and is not live
  executable. Only the minimum-notional gate is bypassed.
- GPT-6 Astra pre-implementation verdict is
  `PROCEED_TO_IMPLEMENTATION_CONDITIONAL`. It identified the anchor-return
  conflict: entries never use the anchor, but B001/S001 one-tick returns may;
  self-cross must block/defer without shifting or internally filling.
- No economic replay has started. Implementation, tests, final independent
  source-bound review, registry creation, and preregistration publication remain
  required.

## 2026-09-08 — implementation, review and registry milestone

- The dense kernel reuses M020 execution authority while keeping M021 geometry and
  capital explicit. It reports fill events, active time, partials, queue blocks and
  open economic positions for all200 slots and20 buckets.
- Two pre-run reporting defects were found and corrected: unknown book coverage no
  longer counts as capital shortage, and a canceled order uses the canonical
  `CANCELED` status for active-time termination. The registry grid field was also
  corrected before registration and covered by a frozen-design test.
- Focused validation passed62 tests; the complete repository suite passed with two
  expected skips. Ruff and diff checks passed.
- Independent GPT-6 Astra review status is `PASS_CONDITIONAL_PRE_RUN`, bound to20
  exact source hashes. This validates machinery only, not economic success.
- M021 was append-only registered as `CREATED`, model hash
  `2276cbcf7e3419f6c08d7242bfef2fe19e1a6be8f49ea4c9be333af53394f9f9`.
- The pre-run source publication and clean `HEAD == origin/main` check remain before
  the single authorized five-hour replay. No economic replay has started; Day2 and
  an automatic successor remain closed.

## 2026-09-08 — single five-hour result and autopsy

- Published execution source: `f430a07a416dc31e0b06a7198cd8f51fdd0b5a89`.
- Physical run hash:
  `7508beca1ee232864027204c6e33a92191fe1725d42d2eccd82f7349815a05ae`.
- Result:19 complete positive cycles in5h, or3.8/hour. BUY-first produced4;
  SELL-first produced15. The informational `>0` mechanic gate was observed, but
  this is not high throughput or strategy approval.
- Top slots were S002=6, S001=4, S003=3, B001=2, S004=2, B002=1 and B003=1.
  Buckets S001-S010 produced15 cycles(78.95%); B001-B010 produced4(21.05%).
- Initial balances:99.6950USDT+100USDC, marked199.88500000. Final balances:
  103.70680000USDT+96USDC, marked199.90840000. Realized PnL was0.00510000;
  unrealized PnL0.01830000. These are sanity checks under frozen zero-fee and
  normalized assumptions, not a controlled return comparison with M020.
- Physical audit `PASS_M021_LEDGER_EXECUTION_LIQUIDITY`:42 fills,19 cycles,
  39,742 trade deliveries, ownership/queue/causality/global-liquidity reconciled,
  zero negative exits.
- Autopsy: market path1.0017–1.0027 covered only10 ticks. Ten of200 slots filled;
  seven completed cycles. S005-S007 sold but their buyback exits conflicted with
  lower resting SELL entries. The repeated self-cross count is manager rechecks,
  not183,152 independent opportunities.
- A post-run bug was isolated to secondary `ACTIVE_TIME_US`: status
  `REJECTED_POST_ONLY` had been extended to cutoff. Kernel/test were corrected and
  the report rederived from the immutable checkpoint. Cycles, fills, prices,
  balances, PnL, queue, audit and physical files did not change; no replay occurred.
- Registry final status: `INCONCLUSIVE`. M021 proves only that the normalized
  mechanic can complete cycles under this simulator. One-USDC orders remain below
  Binance minimum notional. Execution gate is closed; no Day2 or M022 is authorized.

### Post-run factual correction

The preceding active-time bullet overstates the observed issue. Exact comparison
of the physical and rederived200 slot rows found zero `ACTIVE_TIME_US` differences.
All182 `REJECTED_POST_ONLY` orders had `activation_evaluated_us=None`, so the old
code already excluded them before checking the status literal. The code change is
defensive hardening for a latent case, not a correction to any M021 value. This
correction preserves the inaccurate note above as journal history and supersedes it.

Independent GPT-6 Astra post-run review then returned
`PASS_FACTUAL_POST_RUN`. It confirmed the physical hashes, all economic totals,
the 200/200 active-time equality, append-only correction evaluation, final
`INCONCLUSIVE` status and closed gate. It did not execute another replay.
