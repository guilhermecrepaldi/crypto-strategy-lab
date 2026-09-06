# LEGACY — FDUSD/USDC daily level scanner

Status: `LEGACY_EVIDENCE` / `ARCHIVED_EXPERIMENT`. This result is preserved only to explain the
research lineage. It is not part of the active campaign and must not be resumed or compared with
USDCUSDT.

Run `380fa8afcddb6a69235e1a905dcb00adadbb3e87b6546bfbfe8cf989ff036974` used dataset `39e8f83ee3928788f004a77b8b79a22fd2fcc8bce96f6b262ef50c4e2b1792c8` over `2026-01-01` to `2026-08-01`.

## ORACLE daily constant-band reference

- Minimum: `54`
- Maximum: `4312`
- Mean: `422.4292452830189`
- Median: `141.5`
- Zero days: `0`
- Classification: **WEAK**

## Frozen causal selector

- Lookback: `30 minutes`
- Operating window: `360 minutes`
- Distances: `[1]`
- Score: `FREQUENCY_MARGIN`
- Classification: **FAIL**

ORACLE sees its complete day and is only a fixed-band retrospective reference. The causal selector uses `[decision-lookback, decision)` and preserves an open position and its original target across reselection boundaries. The comparison ratio is not clamped and can exceed one because the causal policy adapts intraday.

`EXECUTION=INCONCLUSIVE`: aggTrades prove observed price paths, not queue position or fills. No real capital, account, Testnet, order or credential was used.
