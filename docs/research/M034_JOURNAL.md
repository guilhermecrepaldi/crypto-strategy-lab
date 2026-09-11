# M034 research journal

## 2026-09-10 - official source implementation

Starting `HEAD=origin/main=aafb57ef4203ad2d0c46edacf0df503ec306795e` on
`main`; the worktree was clean and no economic replay/trainer was active. The supplied
strategy PDF was confirmed as a historical summary at `f903b038...`, before the final
M033 correction/review commits. The repository itself contains reviewed M032/M033
libraries and no integrated M032/M033 economic runner, consistent with a source-only
M034 implementation and a blocked replay.

The Phase 0 component map is in
`docs/microstructure/M034_BINANCE_ECONOMIC_ELIGIBILITY_PRODUCTIVITY.md`. GPT-6 Astra
returned `PRE_IMPLEMENTATION_REVIEW=PASS_SOURCE_ONLY` at the starting HEAD and required
fee/threshold fail-closed behavior, a separate typed M034 scorer path, currency-consistent
FIFO switching decisions, causal estimators that do not relabel queue-clear heuristics,
and physically bound negative-exit authorization. `READY_FOR_REPLAY=false`.

Implementation adds one cohesive M034 eligibility/decision module and evolves existing
M032/M033 authorities rather than creating parallel ledgers, queues, scorers or venue
adapters. The operational threshold set, pair universe, dataset, window and model
registration remain empty; deterministic tests use synthetic boundary fixtures only.
No replay, CSPRNG draw, account access, Testnet/live action or registry mutation occurred.

Pre-review validation passed 25 M034 tests, 48 M032 regressions and 46 M033
regressions (119 focused tests). The complete repository suite passed with the
documented root `PYTHONPATH`: 1,153 passed, 2 skipped, 0 failed. Repository-wide Ruff
passed. Strict mypy passed for all seven changed M032/M033/M034 source modules. The
legacy full-package mypy invocation remains non-green with 117 pre-existing errors in
13 unrelated files; those campaigns were not modified to conceal an out-of-scope gate.
The first published source-bound GPT-6 Astra review of
`d009653afaf4dd361dcc4095090e97788b2015f4` returned
`IMPLEMENTATION_REVIEW=BLOCK`, `READY_FOR_REPLAY=false`. Reproduced blockers were:
owned-return priority/shortfall bypass; non-physical and retroactive negative-exit
settlement; negative conservative bounds; fee-tier ambiguity; disconnected pair/rule
evidence; temporally impossible completion labels and censored lock mismeasurement;
future-effective thresholds; mixed-currency allocation; and incorrect data/safety idle
classification.

The correction keeps replay blocked and adds adversarial regression tests for each
finding. It reserves owned-return capital before new-entry ranking, registers negative
exit authorization in the ledger before the exit path, binds physical fills and
residual closure, validates threshold effectiveness/bounds, fee tier, temporal pair and
rule evidence, coherent outcome horizons, one allocation currency with causal USD mark,
and state-specific blocked capital. Corrected-source review is still required.

Correction validation: 38 deterministic M034 tests, 51 M032 regressions and 46 M033
regressions passed (135 focused). The full repository collected 1,168 tests and exited
green with 1,166 passed and 2 skipped. Repository-wide Ruff passed, and strict mypy
passed on all seven affected source modules. Full-package mypy remains a pre-existing
non-green gate with 117 errors in 13 untouched legacy modules.

The second published review, bound to
`1dd2f3de2c11449bb5f65f9dfae2a076bfccb01b`, again returned BLOCK. It confirmed the ten
original fixes, then reproduced six further defects: external fee omission in negative
exit loss, censored-lock underestimation, order funding not bound to capital, secondary
route books outside rule/universe gates, unregistered USD marks, and Kraken diagnostics
inside Binance KPI aggregates.

The second correction adds canonical M033 route binding, per-leg rules/universe/fees,
physical first-leg funding checks, a causal mark registry, all-in external-fee loss,
fail-closed censored lock, and Binance-only KPI aggregation. Its 42 M034 tests plus 51
M032 and 46 M033 regressions pass (139 focused). A third published source-bound review
is required; no replay has run.

Second-correction full validation collected 1,172 tests and exited green with 1,170
passed and 2 skipped. Repository-wide Ruff, strict mypy on the seven affected modules,
JSON parsing and `git diff --check` passed.

The third published review, bound to
`e55bb7bb4c768d78fc82c3238ee8ac9120c8f070`, returned BLOCK on two remaining cases:
a Kraken owned-return diagnostic could still reserve Binance capital indirectly, and a
valid reduction whose fee was debited from the spent inventory asset was rejected.
During that review the OWNER clarified: "não vamos usar mais o Kraken". M034 therefore
retires Kraken before all economic evaluation, ranking, obligation, capital and KPI
paths while retaining only M033 historical code/evidence. The spent-asset proof now
counts `input_quantity + fee_quantity` when the fee asset is the input asset. Forty-four
M034 tests plus 51 M032 and 46 M033 regressions pass (141 focused). A fourth published
source-bound review is required; no replay has run.

Third-correction full validation collected 1,174 tests and exited green with 1,172
passed and 2 skipped. Repository-wide Ruff, strict mypy on the seven affected modules,
JSON parsing and `git diff --check` passed.
