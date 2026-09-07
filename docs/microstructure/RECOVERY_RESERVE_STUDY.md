# Recovery Reserve study

Status: IMPLEMENTED_PENDING_PHYSICAL_SCENARIO_EXECUTION. No M011 registered or promoted.
Scientific parent and frozen operator remain M007. Scope is historical DEVELOPMENT only.

The [frozen protocol](RECOVERY_RESERVE_PROTOCOL.md) defines all 27 scenarios and selection gates.
Operating initial capital is 100 USDT, reserve initial balance 5 USDT. Fair comparison uses
M007 plus 5 USDT idle cash. Theoretical zero-fee price-path results are not executable returns.

Run from the canonical repository, only after committing and publishing tested code:

```powershell
uv run python scripts/study_recovery_reserve.py
```

The command verifies published HEAD, physical M007 artifacts, corrected event provenance,
scenario and tape hashes; shares immutable canonical candidate timelines among serial scenarios.
It creates an OS-owned single-instance lock and atomic checkpoints every five wall-clock minutes.
Restart the same command/code to restore an interrupted scenario or reuse hashed completed runs.
Never delete a checkpoint to hide an identity/hash error. No private exchange API is involved.

Artifacts: `artifacts/usdcusdt/recovery-reserve/<identity>/`; outputs include independent exact
ledger audits, replay, reserve state and completion hashes. Large data remain ignored by Git.
Summary CSV/JSON are written only after the complete grid. Phase A outputs are explicitly
unregistered research scenarios, not canonical M007 results or automatically approved M011.

Checks include a real-selector release fixture and deterministic recovery during LONG and after
release, plus unchanged canonical replay when no reserve movement occurs. Financial tests use
Decimal. Autopsy data are copied, never injected back into causal runtime records.

Known unrelated work: untracked `public_market.py` belongs to unfinished Prompt 2 and remains
unchanged. Its existing lint/type issues are excluded only in scoped CLI validation, not hidden
by repository configuration. Prompt 2's previously reported temporal-semantics choice remains
unresolved; this study does not alter the frozen operator.

No economic conclusion is available before the full grid and Astra review.
