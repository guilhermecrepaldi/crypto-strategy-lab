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
