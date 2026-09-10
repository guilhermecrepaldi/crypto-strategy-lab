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

Validation: 38 M032 tests and 85 inherited FIFO/hotline-manager regression tests
passed (123 total). Ruff and strict mypy passed for the new source. The historical
test harness requires the repository root on `PYTHONPATH` for tests importing
`scripts`; this environment detail did not alter source or results.
