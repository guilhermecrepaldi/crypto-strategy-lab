# M035 — FDUSDUSDT 21-day data acquisition

Status: `21_OF_21_SOURCE_PAIRS_ACQUIRED_AND_OFFLINE_REVALIDATED`  
Economic replay: `NOT_STARTED`  
Three-hour window: `NOT_SELECTED`

## Result

| Evidence | Source | Files/days | Records | Compressed bytes | Validation |
|---|---|---:|---:|---:|---|
| L2 | Tardis archive of Binance Spot `incremental_book_L2` | 21 | 3,437,530 | 37,470,494 | gzip, schema, symbol, day scope, monotonic capture time, SHA-256 |
| Individual trades | Binance Vision official Spot `trades` | 21 | 2,704,621 | 34,561,612 | official adjacent checksum, ZIP member binding, symbol/day, positive finite values, IDs/timestamps, SHA-256 |

The source mode is deliberately `MIXED_EXPLICIT`: L2 is obtained from Tardis and the individual
trades are obtained directly from Binance Vision. The exact source URL and hash of every original
are recorded in `reports/m035/M035_FDUSDUSDT_21_DAY_DATA_REPORT.json`. No candle or `aggTrades` file
is used as a fill substitute.

## Frozen scope

The 21 dates are the first day of every month from 2025-01-01 through 2026-09-01 inclusive. They
were frozen before acquisition. No PnL was calculated or inspected and no three-hour interval was
chosen. The future three-hour interval must be randomly drawn and preregistered before replay.

## Remaining gate

The acquired Tardis L2 is detailed normalized depth, but it does not by itself prove the native
Binance `U/u` sequence. Before M035 economic execution, Pair A and Pair B must pass aligned coverage
validation; any native-detail supplement needed for the randomly selected interval must retain its
own explicit provenance. Therefore this result is data acquisition evidence, not OOS, strategy
profitability evidence or `STRATEGY_PASS`.
