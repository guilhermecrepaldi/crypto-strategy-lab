# M026 — three-hour autopsy

## OWNER scoreboard

MODEL=M026

PERIOD=3H

INITIAL_SLOT_BASE=1

FINAL_SLOT_BASE=1

PHYSICAL_CYCLES=30

PHYSICAL_CYCLES_PER_HOUR=10

SLOT_EQUIVALENT_CYCLES=90

SLOT_EQUIVALENT_CYCLES_PER_HOUR=30

PHYSICAL_GATE_GT_12_3333_PASS=false

SLOT_GATE_20_PER_HOUR_PASS=true

HOT_PHYSICAL_CYCLES=30

MID_PHYSICAL_CYCLES=0

FAR_PHYSICAL_CYCLES=0

HOT_SLOT_CYCLES=90

MID_SLOT_CYCLES=0

FAR_SLOT_CYCLES=0

COLUMN_1_CYCLES=11

COLUMN_2_CYCLES=10

COLUMN_3_CYCLES=9

HOTLINE_CHANGES=29

MOBILITY_RESERVE_USED=123.2230134346080000_USDT_EQ_CUMULATIVE_REUSE

MOBILITY_RESERVE_EXHAUSTION_EVENTS=16

UNDERFUNDED_PROMOTIONS=605

AGED_ORDERS_PRESERVED=1271

POST_ONLY_REJECTIONS=0

REALIZED_CYCLE_PNL=0.01080000_USDT

UNREALIZED_PNL=0.0070000000000000_USDT

INITIAL_TOTAL=156.25220000_USDT_EQ

FINAL_TOTAL=156.2972000000000000_USDT_EQ

AUDIT=PASS_M026_INDEPENDENT_LEDGER_AND_TERMINAL_AUDIT

MAIN_LIMITER=UNDETERMINED; DOMINANT_DESCRIPTIVE_ENTITY_TIME=PUBLIC_FIFO_WAIT

STATUS=COMPLETE_INCONCLUSIVE_NORMALIZED_MECHANICS

## What happened

The dynamic hotline concentrated every completed cycle in HOT: 30 physical
roundtrips and 90 slot-equivalent cycles. The slot-rate ruler passed, but physical
frequency fell short of the required 38 cycles and was lower than both comparable
references: M024 closed 35 (11.6667/h) and M025's best size closed 37 (12.3333/h).
M026 therefore did not improve physical throughput on this tape.

The marked balance increased by 0.0450 USDT-equivalent, from 156.2522 to 156.2972.
Final assets were 128.2356 USDT plus 28 USDC. Completed-cycle PnL was +0.0108;
realized disposal PnL was +0.0380 and open-inventory PnL was +0.0070. These labels
are not interchangeable. The double-entry identity residual is exactly zero.

The hotline moved 29 times, and 39 promotions were fully funded, but 605 promotion
attempts were underfunded (391 quote-capital and 214 base-asset blocks). The USDC
mobility reserve reached zero and 16 exhaustion events were recorded; final mobility
balances were 2.0056 USDT and 0 USDC against targets of 8.00055288 per side. The
reported 123.2230 USDT-equivalent `MOBILITY_RESERVE_USED` is cumulative reuse, not an
initial reserve, external injection or loss.

Public FIFO wait occupied 81.77% of the explicit entity-time denominator. Capital
funding blocks contributed 9.48%, mobility-reserve blocks 4.47%, and outside-grid
states 4.25%. This supports a descriptive diagnosis of combined FIFO and mobility
pressure, but entity-time overlap and censoring do not prove a single causal limiter.
Completed-order median activation-to-full-fill residence was about 20.63 minutes;
P95 was about 2.83 hours. This residence measure is completed-only and must not be
read as a decomposed causal queue wait.

## Comparison and target arithmetic

| Model | Physical cycles / 3h | Physical cycles/h | Relative to M026 |
|---|---:|---:|---:|
| M024 | 35 | 11.6667 | M026 was 14.29% lower |
| M025 best | 37 | 12.3333 | M026 was 18.92% lower |
| M026 | 30 | 10.0000 | baseline |

At an arithmetic constant rate only, 30 slot cycles/hour equals 720 slot cycles/day.
The 2,000/day target requires 83.3333/hour, or approximately 2.7778 times M026's
observed slot rate. This is not a daily, monthly or live forecast.

## Conclusion

The 3/2/1 weighting achieved the slot-count gate because each successful HOT
roundtrip represented three slots. It did not increase the number of independently
completed physical roundtrips. Mobility capital repeatedly became the secondary
constraint, slot-base growth never activated, and MID/FAR contributed no cycles.

M026 is `INCONCLUSIVE`, not promoted: it is a below-minNotional normalized mechanics
probe under an exogenous L2 tape, unknown true L3 rank and no endogenous impact. The
audit proves internal accounting and event fidelity, not live executability or
profitability. No rerun, M027, new day or parameter change is authorized.
