# M032 research journal

## 2026-09-10 — architecture and evidence gate

Starting `HEAD=origin/main=9e0f1e897789295b8478f339e2969723748f0955`; worktree was clean and M032 was free
in the 218-event append-only registry. M030 evidence and the blocked M031 capital
identity were read and preserved.

Implemented separate typed components for persistent slots, global multiasset
reservations, public→C1→C2 FIFO, causal queue estimates, turnover, explainable
marginal scoring, 2–4 asset route lifecycle, seven-rank per-book geometry, safety
guards and physical evidence inventory. No economic event was processed.

The local evidence audit found valid L2 only for USDCUSDT. FDUSDUSDC has trades
but no L2; every other candidate book lacks locally validated L2. Historical fees
and symbol filters for a common multi-book period are also unresolved. Therefore
the common eligible date pool is empty and no stablecoin universe, slot base,
bankroll, window or fee profile was selected.

Decision: preserve implementation, tests and provenance; publish
`DATA_BLOCKER=MULTI_BOOK_L2_INTERSECTION_EMPTY`; withhold the registry entry and
stop before replay. `TEST_SUITE_PASS != STRATEGY_PASS`.

Draft `MODEL_HASH=fb35f67e414cce9cb03b0e83824304f9b4286617b679785663e941fca6e11215`.
It identifies the blocked model specification only; it is not a registry identity
or an executed strategy result.

Initial validation: 38 M032 tests and 85 inherited FIFO/hotline-manager regression
tests passed (123 total). Ruff and strict mypy passed for the new source. The historical
test harness requires the repository root on `PYTHONPATH` for tests importing
`scripts`; this environment detail did not alter source or results.

The first source-bound GPT-6 Astra review on published source `a80fbd75...` returned
`BLOCK`. Reproduced findings were non-atomic fill validation, cancel/fill race and
causal ACK defects, same-price replacement inheriting an empty queue epoch, route
fills detached from ledger ownership, and manager safeguards not enforced at the
configuration/allocation boundary.

Corrections validate before mutation, enforce lifecycle time/state, preserve owned
fills during cancel races while releasing only residual on ACK, segment later public
cohorts, reset an empty queue epoch, bind every route fragment to a unique ledger
fill/reservation, close cycles through the ledger, protect obligations in allocation,
and validate safety/hotline/rank/cell uniqueness. The data audit now hashes physical
L2 and trade files. Post-correction validation passed 45 M032 tests plus 85 inherited
regressions (130 total), Ruff and strict mypy. A second source-bound review is required.

The second review on published source `4376d932...` again returned `BLOCK`: a
never-activated cancel-pending reservation could fill, third-asset fees were not
attributed to cycle PnL, and the final loss gate ran after ledger mutation. The
next correction requires prior activation regardless of cancel state, values
external fees in the origin asset using frozen ledger marks, and rejects a
negative projected final return before physical fill mutation. Validation after
that correction passed 49 M032 tests plus 85 inherited regressions (134 total),
Ruff and strict mypy. A third source-bound review is required.

The third review on `1be66f139...` confirmed those corrections but found one final
input-fee mismatch: 4.9 units traded plus a 0.1-unit fee consumed a 5-unit physical
reservation while route progress consumed only 4.9. The correction now treats a
fee in the input asset as part of the leg's consumed capital, does not deduct it a
second time from PnL, and reserves separate origin-value attribution for fees paid
in a third asset. Post-correction validation passed 50 M032 tests plus 85 inherited
regressions (135 total), Ruff and strict mypy. A fourth source-bound review is required.

The fourth review on `8d96ddd...` confirmed input-fee correctness but found that
same-timestamp activations used lexical order ID as the FIFO tie-break. This could
place later C2/public cohort ahead of earlier C1. The queue now assigns a monotonic
causal activation ordinal and orders by timestamp then ordinal. Post-correction
validation passed 51 M032 tests plus 85 inherited regressions (136 total), Ruff and
strict mypy. A fifth source-bound review is required.

The fifth source-bound GPT-6 Astra review on published source `25273367...`
returned `IMPLEMENTATION_REVIEW=PASS` for the reusable library/architecture
scope. It reproduced the inverted lexical-ID/same-timestamp fixture and confirmed
C1 remains ahead of the later public cohort and C2. No new P1 was found in the
delimited review. `READY_FOR_REPLAY=false` remains unchanged: no multi-book L2
intersection, temporal fee/rule profiles, selected universe, SLOT_BASE, bankroll
or windows exist. Future runner integration requires a new source-bound review.
