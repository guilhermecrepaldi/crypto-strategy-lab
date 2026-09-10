# M028 — M026 full-day temporal replication preregistration

Status: `FROZEN_BEFORE_RUN`

M028 is not a new trading strategy. It applies the exact M026 kernel and frozen
economics from 2025-01-01 00:00 UTC through 2025-01-02 00:00 UTC exclusive. M026's
published three-hour result remains immutable.

## Causal execution

The engine starts once at 00:00, receives all 144 validated ten-minute L2 slices
and all canonical trades for January 1 in native order, and is never reset at
03:00. Decisions use only the prefix available at each event. No liquidation is
performed at cutoff.

All M026 parameters remain unchanged: 15 levels per side; HOT/MID/FAR 3/2/1
columns and slot weights; 60 initial orders; 140 operating slot-units; 8 mobility
slot-units per asset side; one historical tick; whole-USDC quantization; conservative
L2 FIFO; frozen latency; global trade-quantity consumption; positive passive returns;
realized-cycle-only growth; no external capital and no negative exit.

## Prefix equivalence gate

Before consuming the first event at or after 03:00, the engine observes the exact
03:00 boundary. Its audit ledger must equal M026's published ledger byte-for-byte.
Its complete economic checkpoint must equal M026's checkpoint after normalizing only
the configured `end_us` from 24h back to M026's 3h value. The prefix must also match
fills, cycles, slot-cycles, balances, realized/unrealized PnL, orders and hotline
epochs. Any mismatch invalidates the run before the extension is consumed.

## Reporting

Primary marked return:

`TOTAL_GAIN_PCT = 100 × (FINAL_TOTAL_MARKED / INITIAL_TOTAL_MARKED − 1)`.

Also report the 21-hour incremental comparison against M026 at 03:00:

`POST_3H_GAIN_PCT = 100 × (FINAL_TOTAL_MARKED / M026_3H_TOTAL_MARKED − 1)`.

Do not add `REALIZED_CYCLE_PNL` again to equity. Report it separately with realized
disposal PnL and unrealized PnL. Compare total cycles and cycles/hour so the longer
horizon is not misrepresented as a strategy improvement. The proportional 304
physical and 480 slot-cycle values are auxiliary rulers only.

## Gates

Registration, tests, GPT-6 Astra source-bound review, publication and clean
`HEAD==origin/main` precede the only run. The full-day data and all 144 slices must
pass physical validation. Result, audit, autopsy, registry and journal are published
afterward. No rerun, another day, M029 or live action is authorized.
