# M026 — OWNER authority binding

This file binds the repository to the OWNER directive received on 2026-09-09,
`M026 DYNAMIC HOTLINE 3-2-1 SLOT GRID — FREQUENCY-FIRST PRE-AGED QUEUE WITH
MOBILE CAPITAL RESERVE`.

Attachment SHA256:
`d99c636b7722b57e735a385e6b2f50e37043a8fc5bd35dcfd5f8c364106079f4`.

The controlling terms are: new `M026`, parent `M024`, M025 as a supporting
capacity diagnostic; one historical L2 run from 2025-01-01 00:00Z through
03:00Z exclusive; 15 price levels per side; HOT ranks 1–5 use three columns of
three slot units, MID ranks 6–10 two columns of two units, FAR ranks 11–15 one
column of one unit. The initial grid has 60 physical orders and 140 operating
slot units. Eight slot units of real capital per asset side are a segregated
mobility buffer. Prices remain on the historical 0.0001 tick, quantities on the
historical whole-USDC step, and only the minimum-notional gate is virtualized.

The hotline moves causally in whole ticks using midpoint hysteresis. Existing
orders never move, resize, lose their FIFO age or change cost basis. Promotion
adds younger columns behind old orders; demotion is drain-only. Capital,
liquidity, public FIFO and own FIFO cannot be duplicated. Returns remain passive,
owned, positive-only and higher priority than free entries. No realized loss,
future data, artificial fill, external capital, reserve loss-release, cutoff
liquidation, account, Testnet or live access is allowed.

Physical cycles and slot-equivalent cycles are separate. The physical gate is
strictly better than M025's 37 cycles/3h, therefore at least 38; the slot gate is
at least 60 slot-equivalent cycles/3h. Source, tests, preregistration and an Astra
source review must be published before the one run. After it, publish the result,
autopsy, independent review, registry, journal and current state. No rerun,
automatic M027, day 2, sweep or tuning is authorized.

