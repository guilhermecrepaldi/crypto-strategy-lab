# M025 research journal — order-size capacity curve

Append-only journal for `M024_ORDER_SIZE_CAPACITY_CURVE_V1`.

## 2026-09-09 — OWNER authority and design review

- M024 remains immutable. OWNER authorized one controlled eleven-scenario capacity
  curve on the same Jan1 three-hour tape, changing only full order quantity.
- Frozen Q values: 10, 50, 100, 250, 500, 750, 1000, 1500, 2000, 3000 and 5000 USDC.
- Capital scales from the actual 75 BUY reservations plus 75 USDC-funded SELL entries.
  The physical market tape, public queue and trade quantities do not scale.
- Growth profit remains measured but cannot add cells. No reserve, forced liquidation,
  endogenous impact, historical queue-rank claim, live access or successor is allowed.
- GPT-6 Astra rejected a thin quantity-only wrapper because M024 also contained fixed
  one-USDC assumptions in shadow diagnostics and its independent auditor. The accepted
  design requires scenario-bound checkpoints, a quantity-aware auditor, accurate locked
  partial classification and orthogonal evidence before declaring a capacity knee.
- Algebraic review proved that scaling efficiency and roundtrip-per-capital are equivalent
  to cycle retention under proportional Q/capital. They remain descriptive, not separate
  confirmation. Zero baselines are undefined.
- Implementation and source-bound final review are in progress. No scenario has started.

## 2026-09-09 — exact physical-unit audit repair

- Astra's first implementation review blocked the pre-run because a compact supplemental
  checker did not fully reconstruct M024 latency, public barriers or ownership.
- A second version reused the complete M024 reconstruction through division by Q. Astra
  reproduced an exactness failure for Q750/Q1500/Q3000: finite `Decimal` division created
  recurring decimals and rejected otherwise conserved physical ledgers.
- The normalization path was removed. M025 now owns a source-bound parameterization of the
  complete independent reconstruction and audits cash, inventory, lots, public/own FIFO,
  trade budgets, cycles and shadow timing directly in physical USDC at each Q.
- Tests now include all eleven Q values and one-USDC fill fragments inside Q500, Q750,
  Q1500 and Q3000 cycles. The joint M024/M025 suite passes 140 tests. Queue-zero metrics
  also separate reached-and-filled orders from zero-reached orders censored without a fill.
- This is pre-run evidence only. No historical event has been traversed and no scenario
  has started; the final source-bound Astra verdict remains pending.

## 2026-09-09 — pre-run gate passed

- GPT-6 Astra issued `PASS_CONDITIONAL_PRE_RUN` for the exact 30-file source closure
  after three review rounds. The source-bound report records all LF SHA-256 values.
- The focused M024/M025 suite passed 140 tests; Ruff and the full repository suite also
  passed. `TEST_SUITE_PASS != STRATEGY_PASS` remains explicit.
- M025 was registered as `CREATED` with model hash
  `a6fffeb379521679db725a30e361345af6356798e60d7ec32c0855f12e36112f`.
- No historical scenario had started at this journal checkpoint. The next gate is a
  clean pre-run commit on `origin/main`, followed by exactly one eleven-scenario run.
