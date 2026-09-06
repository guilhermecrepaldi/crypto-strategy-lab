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
- M006 was promoted and later superseded by M007. Its result was not final validation or
  executable edge:
  its 100,820,881,986.6700296 USDT marked result still assumes zero fees, unlimited capacity,
  counterfactual zero latency and price-path fills without queue or book evidence.
- Flat-only reselection cannot repair an existing open lot. M006 was holding inventory for 89.11%
  of elapsed time, so `LONG_HOLD` remains the dominant observed bottleneck and does not authorize
  a time stop.
- M007 confirmed that reducing only the flat decision interval from one hour to one minute can
  recover additional activity: idle fell 27.00 hours, cycles increased 10.42%, and mathematical
  marked equity rose 8.9330x versus M006 on the same frozen scenario.
- M007 is the current DEVELOPMENT champion. It did not improve continuous productivity: 193 days
  still had zero cycles, March and April had none, and daily p50 remained zero.
- M007 increased reselections from 191 to 234 and reversals within 24 hours from 65 to 100. This
  supports testing the already preregistered M008 anti-thrashing package, but the current replay
  cannot quantify queue-priority or latency cost.
- M007 exact maximum drawdown was materially unchanged at 0.26851667%. Its best-day and top-five
  concentration improved, while best-month concentration worsened slightly; the warning remains.
- M008 proved that the preregistered anti-thrashing package can reduce reselections and reversals,
  but it retained only 74.66% of M007 cycles and 3.22% of its mathematical equity. Reduced flat
  idle merely became more holding, while zero-cycle days and concentration worsened.
- M008 is rejected and M007 remains the DEVELOPMENT champion. This rejection applies to the
  four-control package; it does not identify which individual threshold caused the loss.
- M009 isolated M008's 10% score advantage. It retained 95.00% of M007 cycles and cut reversals
  from 100 to 22, but retained only 23.21% of M007 mathematical equity and made 119 reselections
  against a frozen maximum of 117.
- M009 is rejected and M007 remains champion. The result shows that reducing reversals alone did
  not preserve the development result; it does not establish the executable cost or value of a
  switch because queue, latency and cancellation effects remain unmodeled.
- A 76.79% equity reduction from a 5.00% cycle reduction demonstrates path-sensitive compounding.
  Exact decomposition attributes 98.01% of the log-equity difference to the old `0.0001` tick
  regime, chiefly in January and February; it is not an accounting or rounding discrepancy.
- M007 and M009 each had thirteen completed holds of at least 24 hours; eleven were shared entry
  and exit events, and their terminal censored entry was also shared. These are dependent paths,
  not 26 independent long-hold observations.
- Neither selection age, last-HIGH age nor raw lookback score presently distinguishes long holds
  robustly. The 111.28-day hold began 0.000331 second after a HIGH touch and after 43,132 lookback
  cycles; the old-tick long holds all followed substantial activity.

## Likely

- A preregistered relative activity signal `24 * C_1h / C_24h < 1` may reveal contraction without
  mixing the two tick grids, but it must be calculated for every M007 entry before it can motivate
  a new model.

## Refuted

- The M005 hypothesis that one static causally selected band would remain productively useful
  throughout the frozen 2026 DEVELOPMENT interval.
- The M008 hypothesis that its combined idle, confirmation, advantage and cooldown controls could
  preserve at least 90% of M007 cycles and 99% of M007 equity while reducing switches.
- The M009 joint hypothesis that isolated 10% relative-score hysteresis could preserve at least
  99% of M007 equity while meeting both anti-thrashing limits.

## Unknown

- Whether a persistent, causal and economically positive USDCUSDT microcycle phenomenon exists.
- Whether 2,000 completed cycles per day is physically attainable on enough valid days.
- How much Oracle activity a causal selector can capture.
- Historical maker-fee applicability, executable capacity, queue position, partial fills,
  latency degradation and adverse selection.
- Whether a frozen DEVELOPMENT champion generalizes prospectively.
