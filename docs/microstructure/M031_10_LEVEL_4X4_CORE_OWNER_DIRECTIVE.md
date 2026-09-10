# M031 — OWNER authority binding

OWNER authorized M031 as the sole capital-neutral geometry successor to M030.
M030 remains the economic manager and immutable published parent evidence. M031
changes only the grid from 15 to 10 levels per side: ranks 1–3 are CORE with
4 columns of 4 slot-units, ranks 4–8 are MID with 2 columns of 2, and ranks
9–10 are FAR with 1 column of 1. This is exactly 70 operational slot-units per
side plus the unchanged 8-unit mobility reserve per asset side: 156 total and
no capital injection. Initial physical free-entry orders are 48.

The M030 priority and safety policy is frozen: RETURN > current CORE > MID > FAR
> old zero-fill; capital is reusable only after cancel ACK; filled/partial
positions and cost basis are protected; direct final-target hotline jumps,
FIFO, once-only public liquidity, no self-fill and no negative realized exits
remain mandatory. An aged smaller MID order promoted into CORE is not resized or
cancelled cosmetically; younger missing columns are added, and recycled orders
adopt current CORE size.

The physically revalidated candidate pool, before selection, was exactly
2025-02-01, 2025-03-01, 2025-04-01, 2025-06-01 and 2025-08-01. One OS CSPRNG
64-bit draw produced seed `14895920518136483619`; deterministic sampling without
replacement selected 2025-02-01, 2025-08-01 and 2025-06-01. There is no redraw.
Each date is independent and both arms process 00:00–13:00 UTC continuously;
only 12:00–13:00 is scored. CONTROL is unchanged M030 geometry/manager. TREATMENT
is M031 geometry with the identical manager and tape.

The six arms run locally and deterministically, with parallelism only across
independent arms/dates and never within event chronology. CPU is preferred;
GPU cannot replace matching/FIFO. Source-bound independent review and publication
must precede the sole economic campaign. If a selected source date fails after
selection, stop without replacement. No sweep, new date, M032, live, Testnet or
account action is authorized.

## Pre-run capital-identity blocker

The required physical-bank gate does not close under all frozen constraints. At
the same hotline `H`, both geometries reserve 70 whole USDC on BUY, but M030's
rank-weight is 360 ticks while M031's is 235. Therefore M031's BUY reservations
cost `125 × 0.0001 = 0.0125 USDT` more, independently of H. At the synthetic
book used by the frozen tests (`ask=1.0020`, `bid=1.0019`), M030 requires
78.1040 USDT + 78 USDC including mobility; M031 requires 78.1165 USDT + 78 USDC.

No implementation can simultaneously preserve the exact M030 bank, all 48 M031
orders, whole-USDC sizing, the same prices and 8 USDT mobility. M031 is therefore
`BLOCKED_PRE_RUN_CAPITAL_IDENTITY` and must not be registered or replayed until
OWNER explicitly chooses which constraint may change. A common 78.1165-USDT bank
is a valid matched-control design but adds 0.0125 USDT versus M030; keeping the
M030 bank means initial M031 capacity cannot be fully funded.
