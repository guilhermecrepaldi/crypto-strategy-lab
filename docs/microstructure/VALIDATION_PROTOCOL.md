# Validation protocol

## Gates

1. **Identity:** freeze strategy, operating window, levels, size mode, exchange filters, fees,
   queue model and four latency components before evaluation.
2. **Data:** verify official checksum, UTC timestamps, IDs, duplicates, gaps and event ordering.
   Any L2 gap invalidates the book until a new snapshot reconstructs it.
3. **Exact mechanics:** synthetic fixtures must prove no fill on touch, no fill before arrival,
   queue consumption, partial fills, cancel-in-flight, post-only rejection, single-lot accounting,
   Decimal precision, deterministic replay and `RISK_HALT` without forced liquidation.
4. **Economic possibility:** calculate maker→maker, maker→taker, taker→maker and taker→taker
   independently. A negative perfect-fill cycle is `NO-GO` for that fee scenario.
5. **TRAIN exploration:** record every candidate pair/window/level combination. Selection uses only
   events available before the operating window. Price paths are not fills.
6. **Continuous replay:** carry open orders and inventory across days, weeks and months. Report
   closed cycles by calendar period, zero-cycle periods, censored inventory and mark-to-market.
7. **Capacity:** test increasing lot sizes; do not extrapolate compounding past
   `MAX_EFFECTIVE_LOT`.
8. **Out-of-sample:** freeze the selection and thresholds, then open the future gate once. No
   optimization after observing it.
9. **Shadow:** only after the replay engine and L2 reconstruction pass. Public/read-only market
   data, hypothetical orders only, no keys or order endpoint.

## Classification

`VALIDATED` requires positive net compounded return under realistic queue/cost assumptions,
causal out-of-sample persistence, acceptable structural risk and compatible shadow behavior.
Long inventory age alone never fails the gate. Missing queue or future evidence is
`INCONCLUSIVE`, not an optimistic fill. Any fee scenario with negative perfect-fill economics is
`NOT VALIDATED` for that scenario.

`VALIDATION`, `LOCKED_TEST`, Testnet and live/shadow remain unopened in the current gate.
