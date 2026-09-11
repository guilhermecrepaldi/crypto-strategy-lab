# M034 research journal

## 2026-09-11 - owner forward diagnostic completed

The one-shot `M034_OWNER_DIAGNOSTIC_FORWARD_3H_200USD` process is no longer active and
its preserved result reports `status=COMPLETE`. Its exact economic window was
`2026-09-11T13:08:39.103903Z`–`16:08:39.103903Z` (`10,800,000,000 us`). The claim SHA
`cbd9e513...b14bd` remains consumed. No runner was restarted or rerun.

The result is the preregistered fail-closed outcome: 149,240 Binance-only eligibility
decisions, zero eligible candidates, zero slots, orders, cycles, fees, PnL, inventory
or capital lock. Final realized and marked equity are both `200.0000`; capital was
`BLOCKED_DATA` for 100% of the window, never ordinary idle. All decisions retained the
five mandatory blockers: unproven fee plus unknown execution cost, adverse selection,
completion probability and expected lock.

The raw capture has 343,717 sequential records, 343,715 included and two excluded at
cutoff. Headline counts include warm-up: 306,938 trades and 36,777 depth events. The
economic window contains 291,004 trades and 34,258 depth events. Seven initial books,
42 rule observations, 21 evidence-hash changes and zero native book gaps were verified.
`DATA_GAP=62,594` is a decision-evidence/staleness classification, not a native gap.

Manifest files, claim, published source review, fee evidence, config and threshold
hashes, checkpoints and all rejection counters reconcile. Current focused validation
passes 152 M032/M033/M034 tests. Independent GPT-6 Astra post-run review returned
`PASS_FOR_DIAGNOSTIC_ARTIFACT_PUBLICATION`, no P1/P2, without executing the runner.

This confirms public transport and fail-closed admission only. It does not validate
cycle execution, profitability, absence of opportunity, live readiness or strategy.
The USD label uses the diagnostic 1 USDT = 1 USD convention. The source enforces the
900-second warm-up, but its exact elapsed duration cannot be recomputed solely from the
persisted artifacts because the starting monotonic timestamp is absent.
`STRATEGY_PASS=false`; no successor run is authorized.

## 2026-09-11 - owner forward diagnostic preregistration

OWNER authorized identity `M034_OWNER_DIAGNOSTIC_FORWARD_3H_200USD`: exactly 200 USDT,
a 900-second non-economic warm-up and one 10,800-second Binance public forward-paper
window, with no real/Testnet/account order path. Kraken remains retired. This identity
is separate from the still-blocked historical OOS replay.

Canonical source and public transport were implemented and published through
`caf369c538e8b50109092104316667e5f0365cbb`, but independent GPT-6 Astra review blocked
it before collection because snapshots were not reconstructible, trade events could
mask stale depth, timestamp jumps could manufacture three hours, C1/C2 duplicated the
public queue, and provenance/run-once guards were incomplete. Corrected source
`533d7f07271da8bcbb039ee7acbe50b5feeffd85` was also blocked before collection on a
cutoff millisecond edge, overclaiming the generic fee table as proven, and terminal
queue-cohort reuse. Both blocks are preserved; neither SHA ran.

Final source `be78f31d03006a93e0af9165ee744b9b38cb5913` fixes those findings and passed the
third source-bound GPT-6 Astra review for the narrow option-B scope. Focused local
validation passed 180 tests before final review; Astra independently passed 177 plus
Ruff, format and strict mypy. Full snapshots, independent depth freshness, dual-clock
cutoff, shared queue cohorts, transitive source binding, semantic artifact checks and
an atomic canonical run claim are present.

The current Binance regular-user 0.100% public table is reference evidence only.
Binance documents exact current symbol/account commissions through signed USER_DATA;
that access was not authorized. Fee status is therefore `UNPROVEN`. Completion, lock,
adverse selection and execution costs remain `UNKNOWN`. Every dependent candidate is
blocked with zero slots, and capital is `BLOCKED_DATA`, never relabeled as ordinary
idle. Threshold values are separate `OWNER_DIAGNOSTIC_ASSUMPTION` constants, not
official M034 calibration or OOS evidence.

Frozen configuration hash is
`6f7bbf6e44ad84742fb8e9f45bd33beeb889866418b31a25700f30720d8302bf`; threshold hash is
`0f13694af14cc324b938b4e26d6b7339ba095dcb6eebb4c2fb904d203b1bcf47`. The one-shot
claim is absent and no collection has begun. Config, review, fee evidence and protocol
must be published before claim creation/start. `STRATEGY_PASS=false`.

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

The fourth independent GPT-6 Astra review passed on published source
`4054dfd3d02d2075516e9272a4c03046e5e0e277`. It ran 141 focused tests and independent
combination probes covering retired Kraken injection, spent/received/external fees,
partial fills, duplicate settlement, temporal fee/mark evidence, threshold bounds,
censoring and calibration/OOS separation. No P1/P2 remained in the reviewed M034
library scope. `M034_SOURCE_ARCHITECTURE_PASS=true`; `READY_FOR_REPLAY=false` and
`STRATEGY_PASS=false`. No replay, dataset/window draw, model registration, account,
Testnet or live action occurred.

## 2026-09-10 - pre-replay hardening and evidence inventory

Starting from clean `HEAD=origin/main=989c1d4b9ecc31136e599ce094f540e32e1642e0`,
GitHub Actions was confirmed to fail exclusively at `uv run ruff format --check .`
before mypy/pytest. Ruff formatted 64 already-versioned Python files in isolated commit
`420c99e825eea9c28a370b8f3f815bad923c60ce`; `ruff check`, format check and
`git diff --check` passed. Full-package mypy then reproduced the known baseline of 117
errors in 13 legacy files. The exact `uv run pytest` console-script invocation on
Windows failed collection because the repository root was absent from `sys.path`; the
same suite remains to be rerun through the documented module invocation. These are
recorded separately from M034 introduced failures.

Before inspecting market-content eligibility, the ex-ante pre-replay protocol was
published at `f6fd64039843184458ef8470f2b605d2214d92c9`. GPT-6 Astra returned
`PASS_FOR_EX_ANTE_REGISTRATION`, required performance-blind date/pair selection,
semantic calibration/OOS identity, conservative censoring, and prohibited excluding
OOS dates by their later realized safety regime.

The subsequent physical inventory found the seven canonical M032 candidate books. Only
USDCUSDT has local L2+individual-trade units: 12 of 21 first-of-month days pass the
native-sequence, normalized-binding, trade-binding and coverage gates. All 12 were
already exposed to M016-M030 work and are registered as `CALIBRATION`; the independent
OOS pool is empty. No unit has a complete, date-bounded historical fee profile and
complete historical symbol-rule set. Current fee/rule material remains forward-only.
Thus the frozen candidate universe contains zero economic candidates.

Operational estimator labels, censoring method, execution-cost evidence and latency
authority are absent and remain unknown. All canonical threshold values, capital,
currency and SLOT_BASE require objective evidence or explicit OWNER preregistration;
no threshold hash was generated. The replay protocol and draft experiment manifest
make all nulls explicit. No master hash or model identity was registered; no window was
selected; official draw count remains zero. An integrated runner is still absent and is
not fabricated while its economic authorities are undefined.

Independent GPT-6 Astra review then bound the format-only source commit `420c99e` and
returned `IMPLEMENTATION_REVIEW=PASS`: all 64 changed Python ASTs are equivalent to
`4054dfd`, formatting the prior content reproduces the published files exactly, 141
focused tests passed, Ruff check/format, strict mypy on seven modules and diff check
passed. This closes the source-review gate only; it does not close any economic gate.

Final local reproduction passed the exact 141-test focused selection and the root-aware
full suite with 1,172 passed and 2 skipped. The bare Windows `uv run pytest` command's
earlier 25 collection errors are therefore classified as console-script `sys.path`
environment failure, not test failures. GitHub Actions now passes Ruff and reaches the
global mypy step, where it fails on the existing cross-platform baseline: 128 errors in
16 legacy files on Linux versus 117 errors in 13 files locally. Strict mypy remains green
for all seven M034-affected source modules; CI is truthfully non-green.

`READY_FOR_REPLAY=false`; `ECONOMIC_REPLAY_RUNS=0`; `STRATEGY_PASS=false`.

## 2026-09-11 - zero-loss development backtest preregistration

The OWNER authorized the separate one-shot identity
`M034_ZERO_LOSS_DEV_BACKTEST_200USD_3H_V1`. It does not consume or modify the existing
forward identity. Binance-only source was published through `5761ce9`, `b6cff4f`,
`87210c5` and final `2a895e5`. Independent GPT-6 Astra reviews BLOCKed native-time
activation, aggregate exposure, risk-depth reuse/latency, partial cancel races,
failure-prefix evidence, input-provenance shadowing and stale-flow admission. Each was
reproduced and corrected. Final source-bound verdict is
`PASS_FOR_DEVELOPMENT_DIAGNOSTIC_BACKTEST` on `2a895e5`; 28 dedicated invariant tests
pass, along with the M032/M033/M034 regressions and the complete repository suite.

The frozen diagnostic uses the validated 2025-01-01 00:00–03:00 UTC calibration tape,
200 USDT per independent F0/F1/F2/F5/F10 scenario, 10-USDT cells, 20-USD aggregate
exposure, causal C1/C2 queues and the OWNER diagnostic assumptions. Configuration hash
is `d85a3bbe2017f77446cebfe67ee74eba7901372b9512554939bbdf667d4a185a` and threshold
hash is `c2b239f6c89efd64ac22f755cbd76be756cd4c764869e6b99da9a7b246bede76`.
No replay has run at this checkpoint; the claim is absent and the next authorized
action is the single five-scenario execution after publication of this preregistration.

## 2026-09-11 - zero-loss development backtest result

The canonical one-shot claim was created after preregistration commit `19df09d`. The
five frozen scenarios each consumed the complete 100,760-event tape (71,222 books and
29,538 individual trades). The strategy evaluation completed, but the reporter then
raised `M034_ZERO_LOSS_ACCOUNTING_AUDIT_FAILED` because exact numeric zeros serialized
with decimal scale were compared to the literal string `"0"`. The failure artifact,
claim and complete causal prefix were preserved. Prefix SHA-256 is
`1cd9447b39b40f9f1fa36753e3b021a2021ebb6e6b3ba8a3849be23bb41df178`.

GPT-6 Astra independently reconstructed all assets from fills, fees and cost debits,
matching ledger totals, physical buckets and terminal checkpoints exactly. Reporting
was recovered from the complete prefix without strategy decisions or fills being run
again: `RUN_STATUS=RECOVERED_FROM_COMPLETE_PREFIX`, `REPLAY_RERUNS=0`.

F0 closed 2 positive physical/slot-equivalent cycles, no zero/negative cycles and no
risk exit. Realized and marked equity ended at `200.007193700`, for `+0.007193700` or
`+0.00359685%`. Residual inventory and unrealized PnL were zero. Maximum marked capital
and inventory lock was `18.039600`; final `18.036903510 USDT` remained in unfilled
entry reservations. Time-weighted utilization was `9.009327%`, inventory lock
`5.627669%`, and idle capital `90.990673%`.

F1/F2/F5/F10 closed no cycles, used no capital and ended unchanged at 200. Each
recorded 997,108 `FEE_DUST_PREVENTS_FULL_RETURN` rejections: with received-asset fees,
whole-unit quantity step and no-residue closure, even 1 bp was structurally ineligible.
Thus pure economic break-even is not identified; the observed admission boundary lies
between 0 and 1 bp/leg and 0 bp is the highest tested fee that produced cycles.

Relative to M026's 30 physical cycles, F0 is `-28`/`-93.3333%`; all nonzero-fee
scenarios are `-30`/`-100%`. No cycle loss was hidden or cross-subsidized. The zero-loss
boolean held mechanically in every scenario, but the present formulation failed the
productivity objective. This is calibration-only development evidence;
`STRATEGY_PASS=false`, no live claim, no rerun and no successor experiment authorized.
