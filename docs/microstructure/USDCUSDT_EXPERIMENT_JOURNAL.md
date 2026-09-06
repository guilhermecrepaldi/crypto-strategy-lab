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
- Active data scope: official USDCUSDT trades from `2025-01-01` through the 2026 physical cutoff;
  the financial replay still starts at `2026-01-01`, with prior data used only causally
- Period class: `DEVELOPMENT`
- FDUSDUSDC operational comparison: disabled
- Existing `VALIDATION` and `LOCKED_TEST`: closed and not consulted
- Real trading, Testnet, credentials, deployment: prohibited

The owner limited active simulation and regime work to 2025-2026. Older downloaded archives are
preserved as data evidence but receive no further campaign computation. The standardized financial
model ladder uses the fixed reference interval above. If the dataset cutoff changes, a new campaign
snapshot is required and relevant models must be replayed; results with different cutoffs are never
compared silently.

### Reference scenario

`PRICE_PATH_HISTORICAL_TICK_ZERO_FEE_V2` is a counterfactual price-path benchmark:

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
- `distance=1` means one causally supported exchange grid step at the level-selection instant;
- LOW and HIGH remain absolute after selection, including across a later tick-size change.

`capacity_capped_final_capital` remains null until queue/capacity evidence exists. Price touches
are not described as fills.

### Identity and reproducibility

- `MODEL_HASH`: decision logic, distance semantics, fixing moment and all decision-changing
  parameters.
- `SCENARIO_HASH`: execution environment, accounting assumptions and the hashed historical
  filter-catalog policy.
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

Result: `SUPERSEDED` before execution due to an unverified constant historical tick assumption.

## M002 — preregistered

Parent: M001.

Problem: a level frozen for the full replay may become stale as the center of activity moves.

Hypothesis: hourly causal reselection with the same 24-hour lookback improves throughput without
changing tick distance.

Change: `PERIODIC_RESELECT`, one-hour decision interval. A change applies only while flat. If a
cycle is open, it remains at its original HIGH; after the sell, the candidate is recalculated from
the then-current causal prefix.

Result: `SUPERSEDED` before execution with M001; no replay or economic result exists.

## M003 — preregistered

Parent: M002.

Problem: hourly decisions may react too slowly to rapidly migrating activity.

Hypothesis: one-minute `ALWAYS_BEST` causal decisions raise throughput, at the cost of more
reselections.

Change: one-minute decision interval, same 24-hour lookback, distance and tie-break rules. A
change still applies only while flat.

Result: `SUPERSEDED` before execution with M001; no replay or economic result exists.

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

Result: `SUPERSEDED` before execution with M001; no replay or economic result exists.

## Technical correction and active identities M005-M008

The first full-replay attempt stopped before any model entered `RUNNING`: the tape contained
`0.99949` at `2026-04-14T04:59:57.245631Z`, which cannot be represented on the assumed constant
`0.0001` grid. Binance's official 2026-04-07 announcement establishes the historical filter
change for USDCUSDT: previous tick `0.0001`, updated tick `0.00001`, effective by
`2026-04-14T05:00:00Z`. It also states that existing orders retain their original tick.

Source: <https://www.binance.com/en/support/announcement/detail/1f1ee792db2d445eb967aa09f6c05138>

This was a technical incompatibility found before returns, not a response to model performance.
M001-M004 and their hashes remain immutable and are marked `SUPERSEDED` with reason
`UNVERIFIED_HISTORICAL_TICK_ASSUMPTION`. M005-M008 reproduce their respective decision rules with
the corrected, hashed semantics:

```text
DISTANCE_SEMANTICS=ONE_EXCHANGE_TICK_AT_LEVEL_SELECTION
DISTANCE_TICKS=1
TICK_SOURCE=BINANCE_ANNOUNCEMENT_PLUS_CAUSAL_TRADE_PREFIX
TICK_EVIDENCE_CLASS=OBSERVED_ACCEPTED_GRID
HIGH=LOW+CAUSALLY_SUPPORTED_TICK_AT_SELECTION
```

M005 is the corrected static reference. M006, M007 and M008 form its internal hourly,
always-best and idle-triggered lineage. A tick change never moves an already selected HIGH,
forces a close or creates an extra reselection. M005 may therefore remain at an absolute
`0.0001` distance after the exchange moves to `0.00001`; it is still one tick at selection.

The announcement says the adjustment completes **by** 05:00 UTC; it does not prove an exact
rollout start. The replay therefore discovers the first fine-grid evidence from the chronological
trade prefix at runtime. A selection whose prefix excludes that first fine event still uses the
old-grid assumption; only a later selection may use the observed accepted fine grid. The pre-event
`0.0001` period, including 2025, is explicitly
`OLD_GRID_ASSUMPTION_COMPATIBLE_WITH_OBSERVED_TRADES`, not an official point-in-time filter
snapshot. At 05:00 the catalog uses `OFFICIAL_COMPLETION_BOUND`.

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

## Frozen full-replay and temporal-productivity protocol

Every executed `Mxxx` must replay continuously from `2026-01-01T00:00:00Z` to the last physical
timestamp in the frozen validated snapshot. The portfolio is never reset at calendar boundaries,
an open position is never liquidated merely because time elapsed, and poor economics, idleness or
inferiority never stop a replay. Only a proven technical invalidity can stop it, with preserved
evidence and status `INVALIDATED_TECHNICAL`.

Temporal analysis is strictly post-replay. It cannot alter selection or execution. UTC horizons
are 1h, 4h, 12h, 1d, 3d, 7d, 14d and 30d. Rolling windows advance by one hour for visualization;
baselines, rankings and streaks use non-overlapping blocks anchored at campaign start. Incomplete
tails are explicit and are not annualized. Invalid data is `UNKNOWN`, never zero.

For `W=[a,b)`, frozen accounting is:

- `MTM_DELTA = equity(b) - equity(a)`;
- `REALIZED_NET = sum(net PnL of cycles closed in W)`;
- `CAPITAL_HOURS = integral(equity(t), a, b)`, including idle and locked capital;
- `NET_PROFIT_PER_HOUR = REALIZED_NET / elapsed_hours`;
- `NET_PRODUCTIVITY = REALIZED_NET / CAPITAL_HOURS`;
- `CAPITAL_HOUR_RETURN = MTM_DELTA / CAPITAL_HOURS`.

Equity marks inventory with the last valid observed trade. This remains a price-path mark, not an
executable mid or fill. Nonpositive capital-hours produce `UNKNOWN`.

For each model and horizon, the baseline is the median `NET_PRODUCTIVITY` of at least four valid
complete independent blocks. Dispersion is the median absolute deviation and the band is
`max(MAD, 1e-12 h^-1)`. With `EPS_PROFIT=0.00000001 USDT`, classification order is:

1. `FAILURE` when MTM delta or realized net is below `-EPS_PROFIT`;
2. `HOT` when realized net is positive and productivity exceeds baseline plus band;
3. `COLD` when no cycle closed or productivity is below baseline minus band;
4. `NORMAL` otherwise.

`FAILURE` here describes a negative period; it is not a software failure and never authorizes a
stop. Top/bottom 10 and HOT/COLD streaks use independent blocks and deterministic UTC tie-breaks.
Rolling overlaps cannot be presented as independent evidence.

Profit concentration uses additive MTM deltas over UTC days, ISO weeks and civil months. Full and
complete-period denominators remain separate. The frozen warning thresholds are best day >20%,
top five days >50%, top ten days >75% (minimum 30 days), best week >35% (minimum eight weeks), or
best month >50% (minimum six months) of positive MTM contributions. This warning is diagnostic,
not a promotion veto.

Per-horizon temporal stability is
`100 * profitable_block_fraction * (1 - failure_fraction) * (1 - relative_variability)`, where
relative variability is `MAD / (median_absolute_productivity + MAD + 1e-12)`. The aggregate needs
all eight eligible horizons and is forced to zero when the full replay MTM is not positive. It is
not a probability, significance test, fill claim or optimization target.

A frozen cross-model cohort requires at least three distinct models with the same dataset,
scenario and cutoff. A block is `CONSENSUS_FAILURE`, `CONSENSUS_HOT`, `CONSENSUS_COLD` or
`CONSENSUS_NORMAL` at a two-thirds threshold, otherwise `MIXED`. This is observed cohort
productivity, not proof of an exogenous market regime or independent evidence.

Trade archives support traded prices, counts, gross volume, intensity, visits, order and
price-path results. They do not establish bid/ask spread, true mid, book depth, queue ahead,
partial fills, executable capacity, operational latency or adverse selection. Unsupported fields
remain `UNKNOWN`; traded volume is never relabeled as available liquidity.

The registry and evaluation artifacts retain daily, weekly, monthly, hour-of-day, day-of-week,
window, regime, replay and decision evidence. The offline dashboard shows model×time and
model×month matrices including return, cycles, idle time and days with at least 2,000 cycles.
Retrospective HOT/COLD observations can motivate only a separately preregistered `M+1`; they may
not become a hidden filter in an already executed model.

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

## Evolutionary-development gate

Every new model after the already registered first block must be justified by the preceding
artifacts. The loop is `EXECUTE -> AUTOPSY -> HYPOTHESIS -> PREREGISTER -> FULL REPLAY ->
COMPARE`. A challenger normally branches from the current DEVELOPMENT champion; a rejected
challenger does not become the automatic parent. One interpretable change should attack one
observed bottleneck unless a deliberate architectural change is separately documented.

The complete `2026-01-01` through physical-cutoff interval is DEVELOPMENT data. Reusing it to
design successors creates declared development bias and does not permit any model decision at
time `T` to use information after `T`. `VALIDATION` and `LOCKED_TEST` remain unopened. A model
autopsy is mandatory before the next model is scientifically authorized, and every ten completed
models require a temporary research-direction review.

## M005 autopsy — corrected static baseline

Identity and scope:

```text
MODEL=M005
MODEL_HASH=c5e2d7a1fc0ea6279fc71f05f5551508ea6ac4a71d391f5854dfe7e6eccc4c62
SCENARIO=PRICE_PATH_HISTORICAL_TICK_ZERO_FEE_V2
RUN_HASH=16487d8f1c68966198cfbe7026c45cc246da67431e06b805e41f63c9e0c8c751
START=2026-01-01T00:00:00Z
END_EXCLUSIVE=2026-09-05T23:59:59.783644Z
STATUS=EVALUATED
```

The full replay completed without an economic early stop. It selected absolute levels
`1.00090 -> 1.00100`, made no reselections and reported 191,697 completed cycles. The zero-fee,
unlimited-capacity price path compounded 100 USDT to marked equity
20,744,700,612.7931666 USDT. This number reconciles exactly as initial capital plus realized
profit 20,766,901,116.5514930 minus unrealized loss 22,200,603.7583264. It is mathematical
price-path evidence, not executable capital: fills, queue, book depth, latency and capacity are
unknown.

Productivity was not temporally stable. Average daily cycles were 772.97 but the median was zero;
194 of 248 days had zero cycles and only 18 days reached 2,000. January and February contained
99.9671% of all cycles, while only 63 cycles completed after February. The best day was
`2026-01-23` with 28,779 cycles. Profit concentration triggered the frozen warning: the best day
accounted for 59.2%, the top five days for 89.6%, and the best month for 92.96% of positive MTM
contributions.

Completed-hold p50 was 0.368 seconds, but that statistic hides the capital-lock tail. The longest
completed hold ran from `2026-02-10T08:10:53.227612Z` to
`2026-05-23T20:58:01.999673Z` (102.53 days). The terminal cycle remained open from
`2026-08-17T15:04:02.390957Z` for 19.37 days at the cutoff. The position was open for about
85.65% of elapsed time. These holds remain open until HIGH and do not justify a time stop.

Scientific decision:

```text
HYPOTHESIS_RESULT=NO
DECISION=RETAIN_AS_BASELINE
CURRENT_CHAMPION=NONE_CONFIRMED
EXECUTABLE_EDGE=NOT_DEMONSTRATED
CURRENT_BOTTLENECK=LONG_HOLD_THEN_STATIC_LEVEL_SELECTION
```

The supported conclusion is that the frozen band lost useful access after the concentrated
January-February period. The artifacts alone do not establish whether this was caused by a
general activity migration, reduced flow or another market condition; that distinction remains
diagnostic work, not a hidden trading filter.

## M006 authorization and interrupted attempt

M006 remains authorized as the next causal ablation after this autopsy. It changes only flat-state
selection: the same one-tick distance and 24-hour causal lookback are reconsidered hourly. The
expected effect is to avoid new entries at a level that has lost recent activity. Its principal
risk is reselection churn, and it cannot release an already open position or move HIGH.

The first M006 invocation began automatically four seconds after M005 was persisted by the old
multi-model command. The OWNER's new autopsy gate arrived before it completed, so the process was
interrupted gracefully. The partial run has no evaluation and is preserved as
`INCONCLUSIVE / OWNER_PROTOCOL_CHANGE`; it is not scientific evidence. M006 must be rerun alone,
with the same dataset, scenario and cutoff, after the reusable market tape is ready. M007 remains
unauthorized until the M006 autopsy.

M007 and M008 were already registered before the evolutionary-development gate. Their immutable
records are preserved, but `CREATED` means reserved identity rather than scientific authorization.
After the M006 autopsy, each configuration must either receive an explicit evidence-linked
authorization or remain unexecuted; registration order alone cannot determine the next model.
