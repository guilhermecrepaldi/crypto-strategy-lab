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

## Likely

- Flat-only causal reselection is a justified next ablation because it can avoid future entries
  at an inactive frozen level. It cannot free inventory already waiting for HIGH, so it may not
  solve the dominant long-hold bottleneck.

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
