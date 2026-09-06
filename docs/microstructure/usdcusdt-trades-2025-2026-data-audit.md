# USDCUSDT historical data audit

- Source: official Binance public daily `trades` archives
- Requested coverage: `2025-01-01` to `2026-09-05` inclusive
- Observed coverage: `2025-01-01 00:00:00.006766+00:00` to `2026-09-05 23:59:59.783643+00:00`
- Archives: `613`
- Records: `275345480`
- Compressed bytes: `3555555183`
- Dataset hash: `8cb436b68d6953573d8e7e5dc89eaf53e344e46bde18ce749b440abdd757dd91`
- Missing dates: `0`
- Missing date ranges: `0`
- No-trade ranges proven by contiguous trade IDs: `0`
- Unresolved missing date ranges: `0`
- Within-archive ID gaps: `0`
- Duplicate IDs: `0`
- Cross-archive gaps: `0`
- Cross-archive overlaps: `0`
- Days with non-zero boundary silence: `613`
- Integrity: **VALID**
- Invalidity reasons: `none`

Boundary silence is reported rather than silently filled. It can reflect ordinary periods without trades; IDs and timestamps are the continuity authority. Every local ZIP is checksum-verified against Binance before ingestion and is re-verifiable offline.

This dataset contains public trades only. It does not contain our queue position and cannot prove hypothetical order fills.
