# LEGACY — FDUSDUSDC historical data audit

Status: `LEGACY_EVIDENCE` / `ARCHIVED_EXPERIMENT`. The files are preserved, but no further
FDUSDUSDC download, scan, backtest, model, control or comparison is authorized in the active
campaign.

- Source: official Binance public daily `aggTrades` archives
- Requested coverage: `2024-11-22` to `2026-09-05` inclusive
- Observed coverage: `2024-11-22 08:00:00+00:00` to `2026-09-05 23:59:24.074865+00:00`
- Archives: `653`
- Records: `43616373`
- Compressed bytes: `668320947`
- Dataset hash: `39e8f83ee3928788f004a77b8b79a22fd2fcc8bce96f6b262ef50c4e2b1792c8`
- Missing dates: `0`
- Within-archive ID gaps: `0`
- Duplicate IDs: `0`
- Cross-archive gaps: `0`
- Cross-archive overlaps: `0`
- Days with non-zero boundary silence: `653`
- Integrity: **VALID**

Boundary silence is reported rather than silently filled. It can reflect ordinary periods without trades; IDs and timestamps are the continuity authority. Every local ZIP is checksum-verified against Binance before ingestion and is re-verifiable offline.

This dataset contains public trades only. It does not contain our queue position and cannot prove hypothetical order fills.
