# USDCUSDT experiment journal

This journal is updated when hypotheses are registered and when experiments finish. It is not a
retrospective winner log. Every result in this campaign is a **DEVELOPMENT replay**, not evidence
of production execution.

## Campaign preregistration

- Campaign ID: `USDCUSDT_EXHAUSTION_V1`
- Primary pair: `USDCUSDT`
- Initial reference capital: `100 USDT`
- Reference start: `2026-01-01T00:00:00Z`
- Reference end: last common physically validated event in the frozen dataset snapshot
- Period class: `DEVELOPMENT`
- FDUSDUSDC operational comparison: disabled
- Existing `VALIDATION` and `LOCKED_TEST`: closed and not consulted
- Real trading, Testnet, credentials, deployment: prohibited

The maximum official historical corpus is used for market description, regime research, causal
warm-up and integrity work. The standardized financial model ladder uses the fixed reference
interval above. If the dataset cutoff changes, a new campaign snapshot is required and relevant
models must be replayed; results with different cutoffs are never compared silently.

### Reference scenario

`PRICE_PATH_MATHEMATICAL_ZERO_FEE_V1` is a counterfactual price-path benchmark:

- serial one-pair, one-bank, one-lot, one-LOW, one-HIGH state machine;
- full compounding after each completed cycle;
- zero maker fee and no taker execution;
- exact observed-price equality;
- full hypothetical lot, zero counterfactual latency;
- queue and executable capacity are unknown;
- quantity is rounded down to the configured step and residual cash remains cash;
- no forced liquidation at the terminal boundary;
- terminal equity is cash plus open inventory marked at the last valid trade;
- realized, unrealized and open-cycle results are reported separately.

`capacity_capped_final_capital` remains null until queue/capacity evidence exists. Price touches
are not described as fills.

### Identity and reproducibility

- `MODEL_HASH`: decision logic and all decision-changing parameters.
- `SCENARIO_HASH`: execution environment and accounting assumptions.
- `RUN_HASH`: model, scenario, dataset, interval, code commit, technical revision and execution
  backend provenance. CPU and CUDA executions remain the same model and scenario, but cannot
  overwrite each other's run artifact.
- Model IDs represent strategy logic; fee, latency, queue and stress variants are scenario IDs.
- Once executed, a model ID and its artifact directory are immutable.

## M001 — preregistered

Problem: establish the simplest causal serial reference.

Hypothesis: a one-tick pair selected from the preceding 24 hours may retain positive price-path
throughput after it is frozen for the entire standardized replay.

Change: first model; `STATIC`, one tick, 24-hour lookback ending strictly before
`2026-01-01T00:00:00Z`, no reselection and no time stop.

Selection: among exact `LOW`, `HIGH=LOW+tick` pairs observed in the warm-up, maximize
`cycles * (HIGH / LOW - 1)`, then completed cycles, then lower LOW and lower HIGH. If no positive
candidate exists, remain in USDT.

Expected effect: provide an interpretable lower-complexity reference and expose level migration.

Result: pending validated USDCUSDT dataset.

## M002 — preregistered

Parent: M001.

Problem: a level frozen for the full replay may become stale as the center of activity moves.

Hypothesis: hourly causal reselection with the same 24-hour lookback improves throughput without
changing tick distance.

Change: `PERIODIC_RESELECT`, one-hour decision interval. A change applies only while flat. If a
cycle is open, it remains at its original HIGH; after the sell, the candidate is recalculated from
the then-current causal prefix.

Result: pending validated USDCUSDT dataset.

## M003 — preregistered

Parent: M002.

Problem: hourly decisions may react too slowly to rapidly migrating activity.

Hypothesis: one-minute `ALWAYS_BEST` causal decisions raise throughput, at the cost of more
reselections.

Change: one-minute decision interval, same 24-hour lookback, distance and tie-break rules. A
change still applies only while flat.

Result: pending validated USDCUSDT dataset.

## M004 — preregistered

Parent: M003.

Problem: continuous best-candidate chasing may create unnecessary thrashing.

Hypothesis: a stay-until-bad policy can preserve most M003 throughput with materially fewer
changes.

Change: `IDLE_TRIGGERED`, one-minute checks, 24-hour lookback, continuous-flat idle threshold of
30 minutes, five consecutive confirmations, 10% switch advantage and 60-minute cooldown. Waiting
for HIGH is never idle and never triggers a time stop. Partial inventory also blocks reselection.

Expected gate: at least 90% of M003 cycles, at least 99% of M003 ending equity, no more than 50%
of its reselections, no cooldown violation and at least 50% fewer `A -> B -> A` reversals in a
rolling 24-hour window when the comparator has such reversals.

Result: pending validated USDCUSDT dataset.

## Frozen first-block mechanics

- Scheduled selectors use only events with timestamp strictly less than the decision time.
- One market event causes at most one state transition; a buy and sell cannot share one event.
- Same-timestamp events may transition successively only according to their recorded sequence,
  under the explicitly counterfactual zero-latency scenario.
- Day, week and month reporting boundaries never reset the portfolio or an open position.
- Oracle daily diagnostics start flat each day and are not summed as a continuous portfolio.
- Initial Oracle distances are 1, 2, 3, 4, 5 and 10 ticks; 6 through 9 follow only after the
  first integrity-validated pass.
- Fee stress per leg: 0, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5 and 1 basis point.
- Exact symmetric break-even fee per leg is `(HIGH - LOW) / (HIGH + LOW)`.

## Promotion guardrail

A challenger can replace the current DEVELOPMENT champion only when all apply on the same frozen
snapshot and scenario:

1. integrity and causal-isolation checks pass;
2. ending equity is at least 101% of the current champion;
3. median daily cycles remain at least 90% of the champion;
4. zero-day and idle fractions worsen by no more than five percentage points each;
5. maximum drawdown worsens by no more than one percentage point;
6. at least half of complete months have a nonnegative monthly delta;
7. a model justified by anti-thrashing passes its own anti-thrashing gate.

These are administrative DEVELOPMENT promotion limits, not confirmation of an executable edge.

## Infrastructure decision — GPU Oracle gate

The optional RTX 5060/CuPy Oracle backend matched CPU semantic hashes on a tiny synthetic tape,
a 10,000-event historical sample, one complete 196,022-event day and a 426,197-event three-day
sample. The frozen report measured end-to-end speedups of 0.157x, 1.476x, 1.681x and 1.331x,
respectively, including
transfers, allocation, synchronization and exact event-index reconstruction.

Scientific review decision: `GPU_ORACLE_GATE=FAIL`; CPU remains the canonical and selected
Oracle backend. The preregistered 2x threshold was not changed after seeing results. Another GPU
workload is deferred until a concrete campaign hotspot is measured; this infrastructure result
does not create a model ID and says nothing about strategy edge.
