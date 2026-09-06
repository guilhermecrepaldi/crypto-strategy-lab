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

## Likely

- None yet.

## Refuted

- None yet.

## Unknown

- Whether a persistent, causal and economically positive USDCUSDT microcycle phenomenon exists.
- Whether 2,000 completed cycles per day is physically attainable on enough valid days.
- How much Oracle activity a causal selector can capture.
- Historical maker-fee applicability, executable capacity, queue position, partial fills,
  latency degradation and adverse selection.
- Whether a frozen DEVELOPMENT champion generalizes prospectively.
