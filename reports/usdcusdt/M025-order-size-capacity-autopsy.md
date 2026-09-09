# M025 — order-size capacity curve autopsy

`CORRECTED_DERIVED_REPORT_NO_EVENT_REPLAY`

Physical run: `a2ada49ad8c237ad8b41b7da9096b15e67c5005e81c31fc7ed6e2672090adc22`
Published execution source: `7745600715bdc321a65296b67b0faba67cfe1b79`
Window per scenario: 2025-01-01 00:00–03:00 UTC
Physical audit: PASS in all 11 independent scenarios

## Owner result

M025 did **not** find an order-size capacity knee through Q=5,000 USDC under the
frozen historical tape and queue model. Q=500 completed 35 positive cycles in three
hours (11.67/h), exactly the Q10/Q50 rate and slightly above Q100/Q250/Q750/Q1500.
It closed 5,833.33 USDC of roundtrip quantity per hour. The order quantity was not the
observed throughput bottleneck in this tested range.

For Q=500, initial capital was 37,495.00 USDT plus 37,500 USDC, marked at
75,066.25 USDT-equivalent. It finished with 39,433.3051 USDT plus 35,569 USDC,
marked at 75,080.5569. Completed-cycle PnL was 3.35 USDT; realized disposal PnL was
5.45 and unrealized PnL 8.8569. Those PnL definitions are distinct and must not be
added together as independent profits: the marked-equity identity uses disposal PnL
plus unrealized PnL.

## Capacity curve

| Q USDC | Cycles | Cycles/h | Roundtrip USDC/h | Residual partial orders | Partial rate | Median full fill | P95 full fill | Initial equity | Final equity | Cycle PnL/h | Unrealized PnL |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 10 | 35 | 11.67 | 116.67 | 0 | 0.0000% | 387.60s | 10,187.42s | 1,501.3250 | 1,501.6160 | 0.0227 | 0.1830 |
| 50 | 35 | 11.67 | 583.33 | 0 | 0.0000% | 387.72s | 10,187.42s | 7,506.6250 | 7,508.0800 | 0.1133 | 0.9150 |
| 100 | 34 | 11.33 | 1,133.33 | 1 | 0.4065% | 402.06s | 10,187.42s | 15,013.2500 | 15,016.1069 | 0.2200 | 1.7769 |
| 250 | 34 | 11.33 | 2,833.33 | 1 | 0.4065% | 402.06s | 10,187.42s | 37,533.1250 | 37,540.2569 | 0.5500 | 4.4319 |
| 500 | 35 | 11.67 | 5,833.33 | 1 | 0.4032% | 402.06s | 10,187.42s | 75,066.2500 | 75,080.5569 | 1.1167 | 8.8569 |
| 750 | 34 | 11.33 | 8,500.00 | 1 | 0.4065% | 402.06s | 10,187.42s | 112,599.3750 | 112,620.7569 | 1.6500 | 13.2819 |
| 1,000 | 35 | 11.67 | 11,666.67 | 1 | 0.4032% | 402.06s | 10,187.42s | 150,132.5000 | 150,161.1069 | 2.2333 | 17.7069 |
| 1,500 | 34 | 11.33 | 17,000.00 | 2 | 0.8065% | 350.31s | 10,187.42s | 225,198.7500 | 225,241.7699 | 3.3000 | 26.5199 |
| 2,000 | 36 | 12.00 | 24,000.00 | 2 | 0.7937% | 350.31s | 10,187.42s | 300,265.0000 | 300,322.7699 | 4.5333 | 35.3699 |
| 3,000 | 36 | 12.00 | 36,000.00 | 2 | 0.7905% | 307.83s | 10,187.42s | 450,397.5000 | 450,485.0699 | 6.9000 | 53.0699 |
| 5,000 | 37 | 12.33 | 61,666.67 | 2 | 0.7843% | 307.83s | 10,187.42s | 750,662.5000 | 750,808.9699 | 11.6667 | 88.4699 |

The largest raw cycle count was Q5,000 with 37, only two more cycles than Q10/Q50/Q500.
Because initial capital scales linearly with Q, normalized capital efficiency mostly
tracks cycle retention. Larger absolute volume or PnL is not free efficiency.

## Q500 scoreboard

- Complete positive cycles: 35 (6 BUY-first, 29 SELL-first).
- Full entry / return orders: 39 / 35; 131 fill fragments.
- Residual partials: one order, 431 USDC residual; 69.1449 USDT locked in partials.
- Orders open at cutoff: 141.
- Public-zero observed: 62; 56 subsequently filled; 6 remained censored without fill.
- First fills without an observed prior public-zero: 19, principally strict
  trade-through cases. No public-zero time was invented for them.
- Median public-FIFO wait: 236.83s. Median entry-to-return completion: 3,980.76s
  (66.35 minutes). P95 order full-fill time: 10,187.42s (2.83 hours).
- Final balances: 39,433.3051 USDT and 35,569 USDC; marked equity 75,080.5569.

## Limiter and interpretation

`MAIN_LIMITER=UNDETERMINED_RETURN_PATH_COMPOSITE;
ORDER_SIZE_CAPACITY_KNEE_NOT_OBSERVED_THROUGH_Q5000`.

The cycle rate stayed near 11–12/h across a 500x size span, while the median complete
entry-to-return path remained roughly 58–74 minutes and 140–141 orders were still open
at cutoff in the larger scenarios. Public FIFO and the return path both matter, but the
available medians describe different selected cohorts and are not additive. The present
artifacts do not isolate price recovery, return FIFO, own FIFO or deferred cancel time
well enough to name one as primary. This test does not support raising Q as a route to
the OWNER target of 83.33 cycles/h: Q increases absolute processed quantity and required
capital, while cycle rate changes little. Per-lot phase attribution is the next justified
diagnostic, not an automatic new model or replay.

## Reporting correction

The first derived report attributed some public-queue zeroes after an order had already
received a strict trade-through fill or after its cancel ACK. That produced impossible
negative zero-to-fill durations. The original derived report is preserved separately.
The corrected report uses ledger ordinal, not timestamp alone: public zero is accepted
only while the order is still observed and before its first fill; same-timestamp events
after fill/ACK remain excluded. All eleven ledgers/checkpoints were reaudited without
replaying a historical event. Cycles, fills, balances, PnL, curve and run hash are
unchanged.

## Future-base diagnostic only

- B250: HOT 750 / MID 500 / FAR 250.
- B500: HOT 1,500 / MID 1,000 / FAR 500.
- B1000: HOT 3,000 / MID 2,000 / FAR 1,000.

No capacity knee was observed, so all-below-knee is not asserted (`null`). These mixed
bases were not executed and are not authorization for a successor.

## Limitations

This is one developmental three-hour historical prefix with exogenous tape, modeled
queue rank, zero conditional fee profile and no endogenous impact. It does not prove
live fill capacity, profitability or safe deployability. M025 is complete as a capacity
measurement but remains scientifically inconclusive for live trading. No Day2, M026,
mixed-base run or live action is authorized.
