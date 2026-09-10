# M027 — Micro-Hot Reallocation preregistration

Status: `FROZEN_BEFORE_RUN`
Parent evidence: M026 (`INCONCLUSIVE`, immutable)
Purpose: frequency-only controlled A/B; normalized and not live-executable.

## Physical evidence gate

The only eligible tape is USDCUSDT 2026-05-01 00:00–03:00 UTC. Before either
economic scenario, the runner verifies the published monthly L2 validation,
all 18 ten-minute raw slice hashes, canonical daily trade archive, exact trade
binding and a streaming L2 price-grid GCD. Every delivered L2/trade price must be
representable at five decimal places; the observed common increment must be
`0.00001` and at least one fine-grid price must exist. Local Binance authority
records that the tick migration completed before this day. Failure stops both
scenarios; another day cannot be substituted.

## Frozen A/B

Scenario order is `CONTROL` once, then `TREATMENT` once. Each gets an independent
engine and independent historical liquidity budget, but byte-identical slice and
canonical-trade identities. Only the treatment geometry differs:

| Element | CONTROL | TREATMENT |
|---|---:|---:|
| MICRO ±0.00005 | absent | 2 columns × 1 slot |
| HOT rank 1–5 | 3 × 3 | 3 × 3 |
| MID rank 6–10 | 2 × 2 | 2 × 2 |
| FAR rank 11–13 | 1 × 1 | 1 × 1 |
| FAR rank 14–15 | 1 × 1 | absent |
| orders initially | 60 | 60 |
| operational slots | 140 | 140 |
| mobility slots | 16 | 16 |

Coarse spacing remains `0.0001`; MICRO offset is the legal `0.00005`. Initial
slot base is 1 USDT-equivalent with whole-USDC historical-step quantization.
This remains below Binance minimum notional and only that gate is virtualized.

## Invariants

- no external capital, negative exit, future data, forced fill or cutoff liquidation;
- public/own FIFO and each native trade quantity are consumed once per scenario;
- cancel request precedes ACK and capital reuse;
- old order absolute price, size, ownership and genuine FIFO age survive hotline motion;
- two MICRO columns only, one slot each; HOT and mobility geometry unchanged;
- old zero-fill MICRO target is drained via cancel/ACK; filled inventory is not canceled;
- open orders ≤200; marked-equity and reservation identities reconcile exactly;
- capital match error is `abs(T-C)/C×100` and must be ≤`0.01%`.

## Frozen measurements

Physical and slot cycles; cycles/hour; MICRO C1/C2 cycles; MICRO created/full/
partial/open orders; activation-to-fill median/P95; MICRO public-FIFO, own-FIFO
and price-recovery entity time; causal micro-only compatible trade touches;
micro cycles whose entry used such a touch; HOT rank-1 control/treatment cycles;
near-hot net gain; control FAR14/FAR15 cycles/fills/order-hours; and per-distance
physical cycles, slot cycles, fills, order-hours and median full-fill wait for
MICRO, rank1–5, MID, FAR11–15.

`MICRO_UNIQUE_PRICE_TOUCHES` counts compatible native trades reaching MICRO but
not the contemporaneous coarse rank1 boundary. The cycle diagnostic links those
trade IDs only to actual MICRO entry fills; it does not alter execution.

`NET_NEAR_HOT_CYCLE_GAIN = (treatment MICRO + treatment rank1) - control rank1`.

Favorable gate: treatment physical cycles > control. Strong ruler: treatment
cycles/hour ≥1.20× control. Results are preserved regardless of either gate.

## Required flow

Tests and independent GPT-6 Astra source-bound review must pass. The complete
source/config/review is committed and pushed; `HEAD==origin/main` and clean;
then exactly one run per scenario. Results, ledger hashes, terminal state,
audits, autopsy, journal, registry and CURRENT_STATE are published afterward.
No M028 or follow-on execution is authorized.
