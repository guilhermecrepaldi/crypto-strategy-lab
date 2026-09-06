# USDCUSDT execution-evidence inventory

Status: `BLOCKED_MISSING_HISTORICAL_L2`

This is a local, read-only inventory for the active `USDCUSDT_EXHAUSTIVE` campaign. It did not
download data, open a market stream, access an account or Testnet, send orders, or replay a
strategy. The machine-readable authority is
`reports/usdcusdt/execution-evidence-inventory.json`.

## Evidence present

The active official Binance `trades` manifest covers 613 UTC days from `2025-01-01` through
`2026-09-05`: 275,345,480 records and 3,555,555,183 compressed archive bytes. Its dataset hash is
`8cb436b68d6953573d8e7e5dc89eaf53e344e46bde18ce749b440abdd757dd91`. The bounded range is
`VALID`, with no missing dates, ID gaps/overlaps, timestamp gaps/overlaps or invalidity reasons.
The manifest's `all_available=false` records bounded-range mode; it is not an integrity failure.

Each 2025--2026 row contains trade ID, price, base quantity, quote quantity, microsecond
timestamp, `buyer_is_maker` and best-match status. This supports exact ordering, traded quantity
and aggressor-side inference. It does not identify resting orders or queue position.

Historical tick evidence is partial but explicit: the campaign combines observed causal trade
grids with Binance's official completion bound for the move from `0.0001` to `0.00001` by
`2026-04-14T05:00:00Z`. A separate public snapshot captured on `2026-09-06` records current
`stepSize=1` and `minNotional=5`; current filters are not proof of past filters.

## Evidence absent

There are zero local USDCUSDT L2 snapshot, delta, depth or order-book files and zero L2
manifests. Consequently there is no historical book sequence, continuity proof, recovery
snapshot, cancellation stream, queue-ahead estimate or latency evidence. Historical step size
and minimum-notional rules are also absent. The current depth snapshot is neither historical nor
sequenced.

The repository already contains a deterministic execution engine with snapshot/delta validation,
gap invalidation, queue consumption, partial fills, latency, cancellation, fees and exact
single-lot accounting. Those capabilities are fixture-tested only; there is no real L2 importer
or real historical execution artifact. Trade volume cannot be substituted for book or queue
evidence, and no fill may be invented.

## Gate decision

`M007` remains frozen as the DEVELOPMENT price-path champion, `M010` remains unauthorized, and
the executable gate is not ready. The missing minimum evidence is:

- timestamped, sequenced L2 snapshots and deltas for an identified offline interval;
- explicit gap detection and recovery-snapshot provenance;
- historical quantity-step and minimum-notional rules;
- a preregistered fee scenario and declared latency/queue bounds.

Acquiring new historical L2 data—or starting any public live shadow capture—requires an explicit
OWNER decision. A future gate must be a separate execution scenario for frozen M007 and must not
rewrite the existing price-path artifacts.
