# M030 — OWNER authority binding

Received 2026-09-10. The OWNER authorizes one new management-policy experiment,
`HOTLINE_FIRST_DYNAMIC_321_REALLOCATION_V1`, with M026 as parent and M029 as the
immutable full-day baseline. M026 and M029 remain unchanged.

The frozen M026 geometry, 3/2/1 columns and slot weights, tick/quantity rules,
positive-only owned returns, FIFO, latency, data, initial capital and eight mobility
slot-units per asset side remain unchanged. M030 changes only management:

1. economic obligations/owned returns have first priority;
2. current HOT precedes current MID, current FAR and old zero-fill free entries;
3. zero-fill ENTRY reservations are reclaimable by causal cancel, in order outside
   grid, FAR, MID, then demoted former-HOT; within class, farthest then youngest;
4. any filled or partially filled order is protected;
5. reservation is reusable only after CANCEL_ACK;
6. a multi-tick move from one causal book goes directly to its final hotline and
   performs one physical reconciliation, while recording all crossed ticks.

The full 2025-01-01 UTC tape runs continuously without reset, skipped events or
cutoff liquidation. The primary score covers exactly three randomly selected hours.
The single OS-CSPRNG draw produced seed `13525809254189156280` and hours 06, 12 and
13 UTC, i.e. [06,07), [12,13), [13,14). The score mask is reporting-only. M029 is
not rerun; its preserved ledger supplies matched baseline statistics.

The run is normalized below Binance minimum notional, uses the frozen conditional
zero-fee profile, has no endogenous impact and is not live-executable. Register,
test, source-review with GPT-6 Astra, commit and push before the sole replay. Stop
without reroll if any selected data window is invalid. No rerun, new seed, M031,
another day, account, Testnet or live action is authorized.
