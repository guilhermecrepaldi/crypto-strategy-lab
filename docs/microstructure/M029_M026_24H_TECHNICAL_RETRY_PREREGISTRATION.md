# M029 — corrected M026 full-day retry preregistration

Status: `FROZEN_BEFORE_RUN`

M029 repeats the authorized24-hour temporal replication because M028 stopped at its
03:00 fail-closed gate without executing the extension. It is not a strategy change.

## Frozen execution

- period: 2025-01-01T00:00:00Z–2025-01-02T00:00:00Z exclusive;
- one continuous engine, no reset at03:00;
- exact M026 15-level HOT/MID/FAR 3/2/1 geometry;
- 60 initial physical orders,140 operating slot-units and8 mobility slot-units per
  asset side;
- identical FIFO, latency, historical tick/quantity, capital ownership, liquidity
  consumption, positive passive returns and compounding;
- no negative exit, capital injection or cutoff liquidation;
- normalized below minNotional and not live-executable.

## Sole technical correction

At the M026 prefix gate, both the live checkpoint and published JSON checkpoint are
converted through the same deterministic JSON representation (`sort_keys=true`,
`default=str`). Only the configured live `end_us` is then normalized from24h to03h.

The ledger remains byte-for-byte strict. Trade IDs/count and the frozen M026 metrics
remain exact. Canonical state inequality still invalidates the run before any
extension event is delivered.

## Reporting

`TOTAL_GAIN_PCT = 100 × (FINAL_TOTAL_MARKED / INITIAL_TOTAL_MARKED − 1)`.

`POST_3H_GAIN_PCT = 100 × (FINAL_TOTAL_MARKED / M026_3H_TOTAL_MARKED − 1)`.

Report physical and slot-equivalent cycles separately and normalize both by24hours.
Do not add realized PnL twice to marked equity. The proportional304/480 cycle values
remain descriptive rulers, not promises or promotion gates.

## Gates

Register, test, obtain source-bound GPT-6 Astra PASS, commit/push the exact source and
confirm clean `HEAD==origin/main` before the only run. After completion, independently
reconcile ledger, terminal state, capital, metrics and returns, then publish. Any
technical failure is preserved and closes M029. No rerun, M030, another day or live
action is authorized.
