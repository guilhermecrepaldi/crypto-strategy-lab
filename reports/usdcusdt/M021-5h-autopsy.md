# M021 five-hour result and autopsy

STATUS=COMPLETE
MODEL_STATUS=INCONCLUSIVE
PERIOD=2025-01-01T00:00:00Z/2025-01-01T05:00:00Z_EXCLUSIVE
ORDER_MODE=NORMALIZED_1_USDC_NON_EXECUTABLE_MECHANICS_PROBE

This is below Binance minimum notional and is not a live-executable result.

## Owner result

```text
MODEL=M021
PERIOD=5H
TOTAL_COMPLETE_CYCLES=19
CYCLES_PER_HOUR=3.8
BUY_FIRST_CYCLES=4
SELL_FIRST_CYCLES=15
```

## Concentration

| Rank | Slot | Cycles |
|---:|:---|---:|
| 1 | S002 | 6 |
| 2 | S001 | 4 |
| 3 | S003 | 3 |
| 4 | B001 | 2 |
| 5 | S004 | 2 |
| 6 | B002 | 1 |
| 7 | B003 | 1 |

Only two ten-slot buckets produced cycles:

| Bucket | Cycles | Share |
|:---|---:|---:|
| S001-S010 | 15 | 78.95% |
| B001-B010 | 4 | 21.05% |

The full200-slot and20-bucket tables are preserved in `M021-5h-result.json`.

## Balance sanity check

```text
INITIAL_USDT=99.6950
INITIAL_USDC=100
INITIAL_MARKED_EQUITY=199.88500000
USDT_FINAL=103.70680000
USDC_FINAL=96
TOTAL_MARKED_EQUITY=199.90840000
REALIZED_NET_PNL=0.00510000
UNREALIZED_PNL=0.01830000
```

## What limited rotation

The market traded from1.0017 to1.0027, only a10-tick span. Ten of200 slots
filled and seven completed cycles;190 slots never filled. The upper S005-S007
entries sold once, but their fixed one-tick buybacks conflicted with lower
resting SELL entries. The required self-cross/post-only protections therefore
blocked those returns. Raw self-cross counts are repeated manager evaluations,
not independent market opportunities.

The physical audit reconciled42 fills,19 cycles and39,742 delivered canonical
trades with no negative exits, capital creation, future data or duplicated
liquidity. Status is `PASS_M021_LEDGER_EXECUTION_LIQUIDITY`.

A post-run review found a fragile exact-status predicate in the secondary active-
time reporter and hardened it. It was not an observed M021 value defect: all182
post-only rejections had no activation timestamp and were already excluded before
the status check. Physical and rederived `ACTIVE_TIME_US` matched for all200 slots.
No cycle, fill, price, balance, PnL, queue, active-time value or economic decision
changed, and the replay was not repeated.

Conclusion: the ping-pong mechanism was observed, but3.8cycles/hour is low and
does not demonstrate the intended high-throughput architecture, profitability,
or live viability. Day2 and an automatic successor remain unauthorized.
