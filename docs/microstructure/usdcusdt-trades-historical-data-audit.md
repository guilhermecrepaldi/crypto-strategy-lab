# USDCUSDT historical data audit

- Source: official Binance public daily `trades` archives
- Requested coverage: `2018-12-15` to `2026-09-05` inclusive
- Observed coverage: `2018-12-15 03:12:19.234000+00:00` to `2026-09-05 23:59:59.783643+00:00`
- Archives: `2657`
- Records: `481942569`
- Compressed bytes: `5923788248`
- Dataset hash: `6be9db7a24a74b04b633efa8b8ef73f03367351673a63d62b20bdc0857e4cb17`
- Missing dates: `165`
- Missing date ranges: `1`
- No-trade ranges proven by contiguous trade IDs: `1`
- Unresolved missing date ranges: `0`
- Within-archive ID gaps: `0`
- Duplicate IDs: `0`
- Cross-archive gaps: `0`
- Cross-archive overlaps: `0`
- Days with non-zero boundary silence: `2657`
- Integrity: **VALID**
- Invalidity reasons: `none`

Boundary silence is reported rather than silently filled. It can reflect ordinary periods without trades; IDs and timestamps are the continuity authority. Every local ZIP is checksum-verified against Binance before ingestion and is re-verifiable offline.

This dataset contains public trades only. It does not contain our queue position and cannot prove hypothetical order fills.
