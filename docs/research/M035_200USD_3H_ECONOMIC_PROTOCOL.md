# M035 200 USDT / 3h economic protocol

Identity: `M035_200USD_3H_PARALLEL_DEVELOPMENT_BACKTEST_V1`  
Classification: `DEVELOPMENT_DIAGNOSTIC_BACKTEST_NOT_OOS_NOT_LIVE`  
OWNER authorization: explicit in the M035 economic-run directive received 2026-09-11.

## Frozen comparison

The causal baseline is the M035 engine with only `USDCUSDT`. The treatment is the same M035
engine with `USDCUSDT` and `FDUSDUSDT` on one merged causal timeline. Every scenario starts with
exactly one `200 USDT` global bank. The treatment never creates a per-pair bank.

The window is the OWNER's absolute preference, `2025-01-01T00:00:00Z` inclusive through
`2025-01-01T03:00:00Z` exclusive. It was accepted before any economic result was computed because
both pairs passed native snapshot/delta sequence validation and exact individual-trade binding.
The frozen window hash is
`327142fa6be8a51a70b8f845842e97a596b52b8ab744ab95f68ba72261d60b9b`.

## Data provenance

L2 comes from Tardis's Binance native `depth` and `depthSnapshot` replay. Native Tardis Binance
`trade` events are bound trade-for-trade to the official Binance Vision daily individual-trade
archive. This is deliberately disclosed as mixed-source verification; candles and aggregate trades
are not used. Pair A hash is
`22696126494561e7a23354570bf3f7aa60f9ff6389a6d36d304e5a7d54ccce52`; Pair B hash is
`fd2d83ebc8bf0301616a3679da302e20cd56c8cde1235758c8aedc6f8b07eb09`.

## Frozen execution

Exactly five independent single-pair scenarios run first, followed by five independent parallel
scenarios: maker fee per leg `0/1/2/5/10 bps`. Only the fee differs. Each scenario uses physical L2,
individual public trades, observed public queue ahead, FIFO, native-time activation boundaries,
1,179,525 microseconds activation/cancel-ACK latency, seven ranks, persistent C1 and opportunistic
C2. Ordinary returns with negative attributed PnL are prohibited. Dust remains owned, cost-based,
causally marked inventory.

The detailed immutable configuration is
`reports/m035/M035_200USD_3H_CONFIG.json`. Its canonical JSON SHA-256 is computed and recorded by
the one-shot runner before the first event. A claim file is created before event consumption; any
existing claim makes a later invocation fail closed. There is no rerun or post-result tuning.

M026/M029/M030 figures are historical context only and are explicitly not the causal baseline.
