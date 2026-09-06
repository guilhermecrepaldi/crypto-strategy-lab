# USDCUSDT learnings

This knowledge base records conclusions only when they are supported by reproducible artifacts.
Absence of evidence remains `UNKNOWN`; a price-path result is never relabeled as an executable
fill result.

## Confirmed

- The campaign identity is serial: one pair, one bank, one lot, one LOW and one HIGH.
- Time in an open position is not a stop-loss and does not authorize a forced close.
- Existing `VALIDATION` and `LOCKED_TEST` partitions are outside this DEVELOPMENT campaign.
- The optional CUDA Oracle matched CPU outputs on all four golden datasets, but its maximum
  frozen end-to-end speedup was 1.681x and failed the frozen 2x adoption gate. CPU remains the
  selected Oracle backend.
- M005 is the corrected active baseline, not a confirmed champion. Its complete zero-fee
  price-path replay produced 191,697 cycles, but 194 of 248 days had no completed cycle and
  January plus February contained 99.9671% of all cycles.
- A LOW/HIGH pair frozen for the whole replay did not preserve continuous productivity. The
  longest completed M005 hold lasted 102.53 days and the terminal open cycle was censored after
  19.37 days; neither event authorizes a time stop.
- M005's mathematical compounding result is not executable evidence: fill probability, queue,
  book depth, capacity and latency remain unknown, while its reference scenario has zero fees
  and no capacity cap.
- M006's hourly flat-only reselection partially confirmed the level-migration hypothesis. It
  completed 312,163 cycles, including 116,194 after February, reduced idle by 205.96 hours and
  improved exact maximum drawdown from 0.30778732% to 0.26851667% relative to M005.
- M006 improved temporal concentration, but 193 of 248 days still had zero cycles and complete-day
  p50 remained zero. Seven of eight complete months improved their MTM contribution over M005;
  April was the exception. The separate normalized monthly-return criterion passed in six of
  eight months; the two measures must not be conflated.
- M006 is the current DEVELOPMENT champion. This is not final validation or executable edge:
  its 100,820,881,986.6700296 USDT marked result still assumes zero fees, unlimited capacity,
  counterfactual zero latency and price-path fills without queue or book evidence.
- Flat-only reselection cannot repair an existing open lot. M006 was holding inventory for 89.11%
  of elapsed time, so `LONG_HOLD` remains the dominant observed bottleneck and does not authorize
  a time stop.

## Likely

- One-minute flat-only reselection is a justified M007 ablation for the remaining 648.32 idle
  hours. It may improve intrahour access, but it risks more switching and cannot fix `LONG_HOLD`.

## Refuted

- The M005 hypothesis that one static causally selected band would remain productively useful
  throughout the frozen 2026 DEVELOPMENT interval.

## Unknown

- Whether a persistent, causal and economically positive USDCUSDT microcycle phenomenon exists.
- Whether 2,000 completed cycles per day is physically attainable on enough valid days.
- How much Oracle activity a causal selector can capture.
- Historical maker-fee applicability, executable capacity, queue position, partial fills,
  latency degradation and adverse selection.
- Whether a frozen DEVELOPMENT champion generalizes prospectively.
