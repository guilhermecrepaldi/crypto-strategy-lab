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

## M006 autopsy — hourly flat-state reselection

Identity and scope:

```text
MODEL=M006
PARENT=M005
MODEL_HASH=dc63c807b874044fd9849459d7da0aabd9b99465b8a4fdd3a450160e96311980
SCENARIO=PRICE_PATH_HISTORICAL_TICK_ZERO_FEE_V2
RUN_HASH=3a020356445b362837da892715313d1d879a28823a2ea7b2646cd4ed8fbea2ff
START=2026-01-01T00:00:00Z
END_EXCLUSIVE=2026-09-05T23:59:59.783644Z
STATUS=EVALUATED
```

The canonical replay reused the verified tape
`505fd6c31b010eac4e8da2d7e290137bb455d475b95409ac306d1ded7be55b6c` and completed alone.
The earlier interrupted run remains separate and inconclusive. M006 made 312,163 completed
cycles and compounded 100 USDT to marked mathematical equity 100,820,881,986.6700296 USDT in
the same zero-fee, unlimited-capacity price-path scenario as M005. It made 191 flat-state
reselections, 65 of which reversed within 24 hours, and 5,295 further checks were blocked while
inventory was open.

The change recovered meaningful activity after the M005 collapse: 116,194 cycles (37.22%)
completed after February, versus 63 for M005. Complete-month cycle counts were 169,099 in
January, 26,870 in February, zero in March and April, 841 in May, 49,858 in June, 46,669 in July
and 18,826 in August. The best day was `2026-01-31` with 43,922 cycles, the best ISO week was
week 05 with 106,684, and January was the best month by cycles. The most productive UTC hours
were 20, 11, 17, 18 and 14. The most frequently completed level was
`1.00120 -> 1.00130` with 93,661 cycles; every selected distance remained one exchange tick at
selection time.

Temporal concentration improved but did not disappear. Of 248 observed days, 193 had zero
cycles and 28 reached 2,000. Complete-day p10 and p50 were zero and p90 was 2,660. The best day
provided 24.98% of positive daily MTM contributions, the top five 49.52%, and the best month
30.90%; the frozen concentration warning therefore remains active. The temporal-stability score
rose from 18.2146 to 19.6153. Hourly classification found 399 HOT, 3,680 COLD, 1,872 FAILURE and
one UNKNOWN hour. HOT hours had a median 18,944 events and 316 cycles per hour; the COLD and
FAILURE medians had zero cycles despite substantial observed trade flow.

The dominant bottleneck remains capital lock. Flat idle fell by 205.96 hours to 648.32 hours,
but open-position time rose by the same amount to 5,303.68 hours (89.11% of elapsed time). The
longest completed hold was 111.28 days and the terminal open position was censored after 19.37
days. There were 34 cycles crossing day boundaries and 14 crossing week boundaries. These are
throughput and risk observations, not time-stop authorization.

Python recomputed exact event-level maximum drawdown from all 109,053,867 replay events using
integer fixed-point cash and inventory reconciliation. M006 drawdown was 0.26851667%, from
31,611,268,969.729246 to 31,526,387,442.9489046 at
`2026-04-14T14:41:11.931810Z`, versus 0.30778732% for M005. Daily endpoint drawdown is not used
because it hides intraday paths. Against M005, M006 increased final marked equity by
80,076,181,373.8768630 USDT (4.8601x), added 120,466 cycles, reduced zero-cycle days by one and
increased days with at least 2,000 cycles by ten. Verified complete-month MTM deltas were
nonnegative in seven of eight months; April was the only negative month. The frozen
monthly-return comparison is a different normalized measure: M006 met it in six of eight
complete months. It must not be conflated with the seven-of-eight count for absolute MTM
contribution deltas; both pass the preregistered minimum of half the complete months.

Scientific decision:

```text
HYPOTHESIS_RESULT=PARTIAL
DECISION=PROMOTE_DEVELOPMENT
CURRENT_CHAMPION=M006
EXECUTABLE_EDGE=NOT_DEMONSTRATED
CURRENT_BOTTLENECK=LONG_HOLD
```

Hourly flat-only reselection improved access to migrated activity, idle, cycles, concentration
and exact drawdown. It did not materially improve the zero-day median or release an open lot,
and the enormous mathematical capital remains unsupported by queue, depth, partial-fill,
latency, fee or capacity evidence. Promotion therefore means DEVELOPMENT champion only.

## M007 preregistration

```text
PARENT_MODEL=M006
OBSERVATION=648.32 flat idle hours remain and hourly decisions may react late to level migration
ROOT_CAUSE_HYPOTHESIS=the one-hour flat decision interval misses useful intrahour recurrence
PROPOSED_CHANGE=reduce only the flat ALWAYS_BEST decision interval from 60 minutes to 1 minute
EXPECTED_EFFECT=reduce residual flat idle and increase completed cycles
RISKS_OF_CHANGE=more reselections, short-horizon reversals and unmodeled cancel/queue-priority cost
```

M007 is authorized as the next single-variable DEVELOPMENT ablation on the same dataset,
scenario and cutoff. It is not expected to solve `LONG_HOLD`, because selection remains frozen
while a lot is open. M008 remains unexecuted and unauthorized until the M007 autopsy determines
whether its preregistered anti-thrashing mechanism attacks an observed problem.

## M007 autopsy — one-minute flat-state reselection

Identity and scope:

```text
MODEL=M007
PARENT=M006
MODEL_HASH=2cb6c755cad4b805eb6b79e7b7e04fd271e660f285a8c1d6aca4c643dded934f
SCENARIO=PRICE_PATH_HISTORICAL_TICK_ZERO_FEE_V2
RUN_HASH=f622acb767d0dbaa39edfb7c90e6ef349dfaf6d694ee17dcde29f22a3d740d21
START=2026-01-01T00:00:00Z
END_EXCLUSIVE=2026-09-05T23:59:59.783644Z
STATUS=EVALUATED
```

The replay completed alone against the same verified tape, profile, scenario and cutoff as M006.
M007 completed 344,704 cycles and compounded 100 USDT to marked mathematical equity
900,637,402,983.4181046 USDT. Against M006 this is 32,541 more cycles (10.42%),
799,816,520,996.7480750 USDT more marked equity and an equity ratio of 8.9330. These numbers
remain zero-fee, unlimited-capacity price-path evidence rather than executable capital.

The single intended effect occurred. Flat idle fell by 27.00 hours to 621.32 hours, while holding
rose by the same amount to 5,330.68 hours. Average daily cycles increased from 1,258.72 to
1,389.94 and days reaching 2,000 cycles rose from 28 to 30. The change did not reduce the 193
zero-cycle days or lift the complete-day p50 above zero. March and April still produced no
completed cycles. Of the total, 127,989 cycles completed after February.

January completed 182,453 cycles, February 34,262, May 1,885, June 53,855, July 50,538 and
August 21,711. The best cycle-count day was `2026-01-31` with 44,788; the best week was ISO week
05 with 115,130; January was the best month with 182,453. The best MTM day, week and month were
`2026-02-05`, ISO week 06 and July. The worst complete MTM day, week and month were
`2026-09-03`, ISO week 15 and April. The top UTC hours by cycles were 11, 20, 14, 17 and 18.
The most frequent completed level remained `1.00120 -> 1.00130`, now with 98,838 cycles; the
largest mathematical level profit remained `1.00180 -> 1.00190`. Every selection still used one
exchange tick at selection time.

M007 recorded 234 reselections and 100 reversals within 24 hours, increases of 43 and 35 over
M006. The reversal share rose from 34.0% to 42.7%. Its 319,944 blocked checks mostly reflect the
one-minute decision clock observing the required no-reselection-while-open invariant; they are
not switches. There were no cooldown violations. The observed switching cost is behaviorally
real, but its queue-priority, latency and fee consequences are absent from this scenario.

Concentration improved on daily measures: best-day share fell from 24.98% to 23.69%, top-five
share from 49.52% to 47.29%, and top-ten share from 66.73% to 64.57%. Best-month share increased
slightly from 30.90% to 31.94%, so the concentration warning remains. Temporal stability rose
only from 19.6153 to 19.7221. Hourly classification found 435 HOT, 3,638 COLD, 1,878 FAILURE and
one UNKNOWN hour; HOT median productivity was 350 cycles per hour, while COLD and FAILURE
medians remained zero.

Complete-month absolute MTM deltas and normalized capital-hour returns were nonnegative in seven
of eight months; April was negative. Exact event-level fixed-point reconstruction found M007
maximum drawdown of 0.26851667% on the same April 14 path as M006. The sub-picounit numerical
difference between them is economically indistinguishable, so drawdown is classified as
materially unchanged. Cash, inventory and terminal marked equity reconciled exactly.

The dominant bottleneck remains `LONG_HOLD`. M007 held inventory for 89.56% of elapsed time; the
longest completed hold remained 111.28 days and the terminal lot remained open for 19.37 days.
Thirty-five completed cycles crossed days and fourteen crossed weeks. A faster flat decision
clock cannot release an open lot, and none of these observations authorizes a time stop.

Scientific decision:

```text
HYPOTHESIS_RESULT=YES
DECISION=PROMOTE_DEVELOPMENT
CURRENT_CHAMPION=M007
EXECUTABLE_EDGE=NOT_DEMONSTRATED
CURRENT_BOTTLENECK=LONG_HOLD
```

## M008 authorization — preregistered anti-thrashing package

```text
MODEL=M008
PARENT_MODEL=M007
MODEL_HASH=0c1fa31a6983ab295cfb043be5ef32425cc866d73a880166abeb0fb8d0a8a31d
OBSERVATION=M007 improved throughput but increased reselections and 24-hour reversals
ROOT_CAUSE_HYPOTHESIS=some minute-level candidate changes are transient and add avoidable churn
PROPOSED_CHANGE=30 flat-idle minutes, five confirmations, 10% advantage and 60-minute cooldown
EXPECTED_EFFECT=preserve M007 productivity while materially reducing changes and reversals
RISKS_OF_CHANGE=late response to real migration, higher idle and lost cycles
```

The thresholds were registered before observing M007 and are frozen as one policy package. Their
individual effects cannot be attributed from this single ablation. The 30-minute clock measures
only flat idle, never time waiting for HIGH. Promotion gates compare directly with M007: retain
at least 90% of its cycles and 99% of its equity, make at most 117 reselections and 50 reversals
within 24 hours, and record no cooldown violation. M008 alone is authorized for the next replay;
no later model is authorized before its autopsy.

## M008 autopsy — rejected anti-thrashing package

Identity and scope:

```text
MODEL=M008
PARENT=M007
MODEL_HASH=0c1fa31a6983ab295cfb043be5ef32425cc866d73a880166abeb0fb8d0a8a31d
SCENARIO=PRICE_PATH_HISTORICAL_TICK_ZERO_FEE_V2
RUN_HASH=3ede578b075b09ae6cb6ab148162327f69a43fe0c3cd2fd54df1dba3fef4952d
START=2026-01-01T00:00:00Z
END_EXCLUSIVE=2026-09-05T23:59:59.783644Z
STATUS=REJECTED
```

The complete replay used the same verified tape, profile, scenario and cutoff. M008 completed
257,368 cycles and ended with marked mathematical equity 29,005,626,823.2905544 USDT. Relative
to champion M007, it retained only 74.66% of cycles and 3.22% of equity, failing the frozen 90%
and 99% preservation gates. It added nine zero-cycle days, removed nine days with at least 2,000
cycles, and lowered temporal stability from 19.7221 to 17.9706.

The package did satisfy its switching limits: reselections fell from 234 to 64, reversals within
24 hours from 100 to 7, and cooldown violations remained zero. This operational benefit was too
expensive. Flat idle fell by 218.28 hours, but all of that time moved into holding; holding rose
to 5,548.96 hours. The fall in idle is therefore not a throughput improvement. The longest
completed hold remained 111.28 days, the terminal lot remained open for 19.37 days, and
`LONG_HOLD` remained the dominant bottleneck.

M008 averaged 1,037.77 cycles per observed day. January produced 163,142 cycles, February
25,065, May only four, June 32,835, July 13,826 and August 22,496; March and April remained at
zero. Only 69,161 cycles completed after February. The best cycle-count day was `2026-01-29`
with 40,656, the best week was ISO week 05 with 96,114, and January was the best month. The best
MTM day, week and month were `2026-02-05`, ISO week 06 and February; the worst were
`2026-02-06`, ISO week 15 and April. The top UTC hours were 11, 20, 9, 10 and 8. The most
frequent level remained `1.00120 -> 1.00130`, with 109,420 completed cycles.

Absolute MTM deltas against M007 were negative in seven of eight complete months; April was the
only positive delta because its loss was smaller. Normalized capital-hour returns were lower in
six of eight complete months, with April and August higher. These are separate measures. Profit
concentration worsened: best-day share rose from 23.69% to 45.48%, top-five from 47.29% to
63.65%, top-ten from 64.57% to 78.14%, and best-month from 31.94% to 45.91%. Exact event-level
maximum drawdown remained materially unchanged at 0.26851667%; accounting reconciled exactly.

Scientific decision:

```text
HYPOTHESIS_RESULT=NO
DECISION=REJECT
CURRENT_CHAMPION=M007
EXECUTABLE_EDGE=NOT_DEMONSTRATED
CURRENT_BOTTLENECK=LONG_HOLD
```

The experiment rejects only the complete M008 package. It cannot attribute the loss separately
to the 30-minute idle threshold, five confirmations, 10% advantage or 60-minute cooldown.

## M009 preregistration — isolated relative-score hysteresis

```text
MODEL=M009
PARENT_MODEL=M007
MODEL_HASH=1bc2e893ff54a05d79e3035b1820a9cb62cae6d197d5b97e2ed1a20f9d5570ed
BASE_CONFIG=EXACT_COPY_OF_CANONICAL_M007_MODEL_SPEC
OBSERVATION=M007 recovered throughput but 42.7% of its reselections reversed within 24 hours
ROOT_CAUSE_HYPOTHESIS=some candidate changes have too little causal score advantage to persist
PROPOSED_CHANGE=require best_score > 1.10 * incumbent_score before a flat-state switch
EXPECTED_EFFECT=reduce reversals while preserving the one-minute response and M007 productivity
RISKS_OF_CHANGE=block useful migrations; causal recent score may describe activity that vanishes
```

The 10% threshold is inherited from the preregistered M008 component, not selected through a new
sweep. M009 changes only the switching comparison; it has no idle wait, repeated confirmation or
additional cooldown. At each M007 decision point, both candidates are evaluated on the same
causal prefix and lookback. The incumbent uses its current absolute endpoints. Equality keeps the
incumbent; when incumbent score is zero, the proposed score must be positive. Initialization,
eligibility, tie-breaking, open-position freezing and every economic rule remain those of M007.

The implementation must expose one immutable expanded configuration and exact model hash before
execution. Its direct gates against M007 are at least 90% of cycles, at least 99% of equity, at
most 117 reselections and at most 50 reversals, plus no cooldown violation. Promotion to champion
also requires at least 101% of M007 equity and all general frozen guardrails. M009 is authorized
only after its implementation and causal incumbent-score semantics pass review; no replay may
begin before that gate.

The implementation gate passed at code commit `5dc208f`: the expanded registry configuration
differs from M007 only in `strategy` and `switch_advantage`. The engine applies the same strict
causal comparison at minute boundaries and immediately after an exit, preserves M007 behavior
when no candidate exists, and never evaluates a switch while inventory is open. Unit tests cover
the strict threshold, zero-score incumbent, equality, missing candidate and causal boundaries;
real-timeline fixtures cover exact score comparison and an open absolute band across the
historical tick transition. Astra's semantic review reported no blocking finding. M009 is now
authorized for one full identified replay; no successor is authorized before its autopsy.

## M009 autopsy — rejected isolated score hysteresis

Identity and scope:

```text
MODEL=M009
PARENT=M007
MODEL_HASH=1bc2e893ff54a05d79e3035b1820a9cb62cae6d197d5b97e2ed1a20f9d5570ed
SCENARIO=PRICE_PATH_HISTORICAL_TICK_ZERO_FEE_V2
RUN_HASH=8829762ac9fb0e6b2f842054d5b3e966f535c35f5b6691ecfcc0de1050cabe3c
START=2026-01-01T00:00:00Z
END_EXCLUSIVE=2026-09-05T23:59:59.783644Z
STATUS=REJECTED
```

M009 completed 327,460 cycles and ended with marked mathematical equity
208,998,109,792.7031495 USDT. Against champion M007 it retained 94.9974% of cycles, passing the
90% gate, but only 23.2056% of equity, failing both the 99% retention and 101% promotion gates.
The 10% hysteresis reduced reselections from 234 to 119 and reversals within 24 hours from 100
to 22. Reversals passed their maximum of 50; reselections missed their frozen maximum of 117 by
two. Gate proximity does not authorize changing the threshold after observing the result.

Flat idle increased by 11.89 hours to 633.21 hours and holding fell by the same amount to
5,318.79 hours. M009 kept the 193 zero-cycle days and increased days with at least 2,000 cycles
from 30 to 31. Average daily cycles were 1,320.40 and 125,081 cycles completed after February.
March and April still completed none. The longest completed hold remained 111.28 days and the
terminal open lot remained censored after 19.37 days.

January completed 172,917 cycles, February 29,462, May 2,221, June 52,977, July 50,475 and
August 19,408. The best cycle-count day was `2026-01-31` with 45,310, the best week ISO week 05
with 108,297, and the best month January. Best MTM day, week and month were `2026-02-05`, ISO
week 06 and July; worst were `2026-09-03`, ISO week 15 and April. The leading UTC hours were 20,
11, 18, 17 and 12. The most frequent level was again `1.00120 -> 1.00130`, with 95,100 cycles.

Absolute MTM deltas against M007 were negative in seven of eight complete months; April alone
was positive. Normalized capital-hour returns improved in three of eight months: April, May and
July. Daily concentration improved marginally while best-month concentration rose from 31.94%
to 32.65%; temporal stability declined slightly from 19.7221 to 19.6698. Exact event-level
maximum drawdown remained materially unchanged at 0.26851667% on the same April 14 path, and the
fixed-point account reconciled exactly.

Scientific decision:

```text
HYPOTHESIS_RESULT=NO
MECHANISM_RESULT=PARTIAL
DECISION=REJECT
CURRENT_CHAMPION=M007
CURRENT_BOTTLENECK=LONG_HOLD
M010_AUTHORIZED=NO
EXECUTABLE_EDGE=NOT_DEMONSTRATED
```

The supported lesson is narrow: fewer reversals did not preserve M007's result. The 76.79%
equity loss despite only 5.00% fewer cycles indicates strong path and compounding dependence,
but totals cannot identify which skipped cycles caused it. Choosing another advantage threshold
now would be retrospective tuning.

Before another model, Python must decompose M007 and M009 using their existing artifacts. The
required diagnostic records exact `log(cash_after/cash_before)` contribution by cycle, month,
level and tick regime; keeps the terminal marked component separate; and reconciles rounding and
cash residue. It must list every completed hold of at least 24 hours plus the censored terminal
position, attach only pre-entry causal context (selection age, time since HIGH, canonical
lookback cycles and score, best alternative, tick regime), and compare these with all other
entries rather than selected anecdotes. This is exploratory DEVELOPMENT analysis. It cannot add
a timeout, move an open HIGH or authorize M010 until an interpretable causal signal is found.

## M007/M009 causal composition and long-hold diagnostic

The immutable diagnostic artifact
`63dce839c6983021bbc33603faf5c8aec22ede775dca3195a9f7d3779afce0e6` consumed the existing
M007/M009 replays and their shared READY tape. It evaluated all 344,704 M007 entries and all
327,460 M009 entries without rerunning either model. Exact cycle-log plus terminal-log
reconciliation errors were `4.3E-25` and `1.25E-24`, respectively. The terminal marked component
was practically identical; rounding residue did not explain the result gap.

The difference in `ln(marked_equity / 100)` was `1.4607775303182`. January accounted for 65.20%
and February for 32.81% of that difference. The old `0.0001` tick regime accounted for 98.01%,
where M009 completed 14,336 fewer cycles. The three largest positive M007-minus-M009 level
contributions were `1.00110 -> 1.00120` (48.25%), `1.00120 -> 1.00130` (25.56%) and
`1.00180 -> 1.00190` (16.41%). These are accounting decompositions of realized paths, not a
counterfactual valuation of isolated skipped cycles.

Each model had thirteen completed holds of at least 24 hours plus one terminal censored hold;
eleven completed holds and the terminal entry were shared events. The 111.28-day hold entered
only 0.000331 second after the previous HIGH touch and followed 43,132 completed lookback cycles.
All five long entries in the old tick regime followed 28,009--55,966 lookback cycles. Selection
age, last-HIGH age and raw score therefore do not justify an admission gate: raw score also mixes
a tenfold tick-edge change with activity. No timeout, forced close or M010 is authorized.

Scientific decision:

```text
SCIENTIFIC_REVIEW=COMPLETE
CURRENT_CHAMPION=M007
M009_STATUS=REJECTED
M010_AUTHORIZED=NO
NEXT_STEP=ONE_PREREGISTERED_CAUSAL_ACTIVITY_DIAGNOSTIC
PLATEAU_DEMONSTRATED=NO
EXECUTABLE_EDGE=NOT_DEMONSTRATED
```

## Preregistered causal activity-contraction diagnostic

Before any M010 design, Python will calculate exactly one fixed signal for every M007 entry:

```text
R(t) = 24 * C_1h(t) / C_24h(t)
C_wh(t) = completed cycles of the same absolute LOW/HIGH in [t-wh, t)
C_24h(t) = 0 => UNKNOWN
SIGNAL = CONTRACTING when R(t) < 1, otherwise NOT_CONTRACTING
```

The one-hour and 24-hour windows and threshold one are frozen before calculation; there is no
threshold search. Results must count completed long holds and all other entries by signal,
entry month and selection tick, publish capture rate, fraction of other entries signalled and
historical cycle-log sums, and list the signal for each of the thirteen M007 long holds. The
terminal position remains censored and separate. M009 is only a dependent verification, with
shared entry events explicitly counted rather than treated as independent evidence. Associated
historical log return is descriptive and is not PnL of a hypothetical filter. Only a signal that
discriminates beyond one isolated episode/regime may support a separately preregistered M010.
