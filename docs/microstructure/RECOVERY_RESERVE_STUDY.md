# Recovery Reserve study

Status: V2_PREREGISTERED_PENDING_PUBLISHED_MILESTONE_1. No M011 registered or promoted.

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
