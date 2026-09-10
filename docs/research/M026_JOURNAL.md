# M026 research journal — dynamic hotline 3/2/1

## 2026-09-09 — OWNER authorization and preregistration

M026 is a new mechanics hypothesis based on immutable M024. It uses M025 only as
the 37-cycle physical reference. The implementation freezes a dynamic causal
hotline, 3/2/1 order sizing and column depth, real per-asset mobility capital,
old-order FIFO preservation, drain-only demotion and separate physical/slot-cycle
accounting. The whole-USDC quantization and the exact physical initial bank are
explicit so the 156 architectural slot units are not misrepresented as exactly
156 USDT. Execution remains normalized and non-live-executable.

Source review exposed Decimal drift in proportional cost and mobility-lock
allocation. Before any replay, the implementation was changed to preserve
homogeneous USDC cost layers, consume partial fills from those layers in FIFO,
derive remaining mobility ownership from the actual reservation, and record a
normalized eight-decimal balance quantum. Future slot-base growth rounds down at
that quantum. A deterministic 60-event fragmentation regression now completes
14 cycles with an exact zero PnL-identity residual. Returns are independently
audited against the original entry quantity rather than requantized at exit.

A source-bound `gpt-6-astra` review is now
`PASS_CONDITIONAL_PRE_RUN`: 31 focused M026 tests and 172 combined
M024/M025/M026 tests passed. The review remains conditional on publication,
registry and clean-HEAD preflight. TEST_SUITE_PASS != STRATEGY_PASS.

Status: preregistration ready for publication. No economic event processed yet.

## 2026-09-09 — only authorized replay completed

The preregistered source was published at
`9e0664faf79d172a2a8a7dc4e800504712983cfd`, then the exact three-hour prefix was
processed once. Campaign run hash is
`9ddb531b506225885a02290d04eb57eb172be33aba88562f1e654b83f526fb7c`.
No rerun occurred.

M026 completed 30 physical cycles (10/h) and 90 slot-equivalent cycles (30/h).
The physical gate of at least 38 failed; the slot ruler of at least 60 passed.
Every cycle came from HOT, whose three-slot weight explains the divergence. This
is not 90 independently completed roundtrips. M024 had 35 physical cycles and the
best M025 scenario had 37 on the same prefix, so M026's physical rate was lower.

Initial assets were 78.1040 USDT plus 78 USDC, marked at 156.2522. Final assets
were 128.2356 USDT plus 28 USDC, marked at 156.2972. Completed-cycle PnL was
+0.0108; realized disposal PnL was +0.0380 and open-inventory PnL +0.0070. Their
sum reconciles the +0.0450 marked-equity change without double counting.

The independent physical audit passed over 29,538 trades, 169 orders, 78 fills,
30 physical cycles and 90 slot cycles. It reconciled capital, segmented FIFO,
single-use trade quantity, immutable old-order state and the terminal checkpoint.
A source-bound Astra post-run review returned `PASS_FACTUAL_POST_RUN`; this is a
factual and accounting verdict, not strategy approval.

Public FIFO wait was the dominant descriptive entity-time state. It is not a
causal proof: mobility reserve exhaustion occurred 16 times and 605 promotion
attempts were underfunded. M026 is `INCONCLUSIVE`, normalized below minNotional,
and cannot establish live capacity. The gate is closed; no rerun, M027, day2 or
live action is authorized.
