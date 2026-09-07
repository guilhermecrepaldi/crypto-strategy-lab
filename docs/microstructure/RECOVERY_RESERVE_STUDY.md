# Recovery Reserve study

> CURRENT_STATUS=SUPERSEDED_BY_OWNER_STRATEGY_UPDATE (OWNER override, 2026-09-07).
> All V2 identities and completed artifacts remain historical evidence. Do not resume the
> old grid. See `CURRENT_STRATEGY.md` and `reports/usdcusdt/OWNER-strategy-transition-evidence.json`
> for observed completion counts, process state and preservation hashes. This owner retirement
> is not an economic FAIL and does not retroactively invalidate individually audited results.
> Older status entries below describe their respective attempts only.

Status: V2_PREREGISTERED; FIRST_ATTEMPT_INVALIDATED_TECHNICAL. No M011 registered or promoted.

The canonical protocol is `RECOVERY_RESERVE_PROTOCOL.md`. The previous v1 grid completed 10/27
scenarios at commit `515eddeb`; it is preserved as superseded partial evidence and must not resume.
V2 uses a fresh hashed identity, fixed 2% skim and 18 scenarios.

After milestone 1 is committed and published with `HEAD == origin/main`, run:

```powershell
uv run python scripts/study_recovery_reserve.py
```

The command verifies published source and physical M007 provenance, shares immutable candidate
timelines, uses an OS-owned single-instance lock and atomic checkpoints, and writes only after all
18 scenarios finish:

- `reports/usdcusdt/M011-recovery-reserve-scenarios.csv`
- `reports/usdcusdt/M011-recovery-reserve-scenarios.json`

Artifacts live under `artifacts/usdcusdt/recovery-reserve/<v2-identity>/`. They are unregistered
Phase A scenarios, not M011 and not operational evidence. Do not delete checkpoints to bypass an
identity mismatch. No private exchange API is used.

## Technical attempt ledger

The first v2 attempt at published commit `d024746e` used artifact identity
`47851d4b7522d4e3cb600a7220e72105b49b0fef52509e34f40d4fef4cec1c2b`. It completed two
checkpoints and failed closed while independently auditing `RRV2_H1_B5_F0`. At event
`7249832558710554624`, default Decimal precision reconstructed a spurious `0.0000020` buy fee in
the release closure even though the configured acquisition fee was zero. The deficit itself had
been computed under Decimal128, so the serialized closure did not exactly reconcile.

This is `INVALIDATED_TECHNICAL`, not an economic result. The entire attempt is excluded from
candidate comparison: its two completed checkpoints remain physically preserved as superseded
attempt evidence, and no checkpoint is reused after the correction. The replacement scan starts
all 18 scenarios under a new source-bound identity. See the machine-readable correction report
and `M011_RECOVERY_RESERVE_DECIMAL_CLOSURE_CORRECTION.md`.

The replacement attempt at `10e5b20` / identity `88a08fad8436e7f6519342713457db12ede727bb01809bab3d38ca51e79ab65c`
also completed two checkpoints before failing the final audit of `RRV2_H1_B5_F0`. This time the
closure fee was exact, while its independently serialized `reserve_after` was rounded outside
Decimal128. It is a second `INVALIDATED_TECHNICAL` attempt, excluded wholesale and preserved.
The next identity must again run every scenario from zero.

The third attempt at `8831f6a` / identity `6dd59fd69597bae4f1f9b391e24ee8f56812487ca1bd3d69bbae3069a55f84c6`
reconciled all 99 release transfers in `RRV2_H1_B5_F0`, then failed its final ledger gate because
the derived buy fee of the still-open final position was calculated under Decimal28. The
checkpoint cash and reserve were exact; the result field was not. This attempt is also preserved,
excluded wholesale as `INVALIDATED_TECHNICAL`, and never resumed after the source correction.

The fourth attempt at `2c1fef9` / identity `c7ee9d04d56e586c06b06d34d114ff9989ff6fb9849b516ba8f33ebc9aa3aeb5`
was stopped during its second scenario after a read-only mechanical audit found that monetary
post-processing gates and ranking still used Decimal28. No final grid or scientific selection was
produced. Its first completed checkpoint and partial second checkpoint are preserved and excluded
as `INVALIDATED_TECHNICAL_PRE_OUTPUT`; the next identity restarts the entire grid.
