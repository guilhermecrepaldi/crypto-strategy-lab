# Recovery reserve — preregistration

Status: PREREGISTERED_BEFORE_SCENARIO_RESULTS. Scientific review: GPT-6 Astra.
Scope: USDCUSDT_EXHAUSTIVE, HISTORICAL DEVELOPMENT ONLY, parent M007.
The owner's RECOVERY_RESERVE authorization supersedes the earlier no-sweep restriction
for this hypothesis only. Preserve M010 and the unexecuted HOLD_RISK hypothesis as
separate evidence. Registry preflight determines the available model identity; Phase A
uses SCENARIO_IDs and does not reserve a MODEL_ID for every parameter combination.

## Hypothesis and authorities

A segregated maintenance reserve may pay small realized release deficits and preserve
the pre-purchase operating capacity sufficiently to increase total economic equity.
The bottleneck is M007 LONG_HOLD_CAPITAL_LOCK. M007 remains the scientific parent and
operational champion. No change to the frozen shadow selector or operator is authorized.
No account, Testnet, Live, order or executable-fill claim belongs to this study.

Reuse the canonical serial replay, candidate timelines, tick catalog, M007 ranking,
ordinary selection and cycle accounting. Optional historical accounting/scheduling hooks
must default to absent and preserve canonical M007 output exactly. Do not duplicate the
serial engine. The release decision receives only causal state and prefix statistics;
the engine may index the next HIGH to execute events chronologically, but neither its
time nor existence is an input to release eligibility. Normal M007 decisions preserve
their existing event-order semantics; recovery decisions enforce timestamp < T and do
not silently redefine the parent's same-timestamp convention.

## Capital and exact ledger

`initial_capital=100`, `currency=USDT`, `capital_mode=COMPOUNDING` remain canonical.
Separately record `initial_recovery_reserve=5`, `total_initial_equity=105`.
The fair reference is an unchanged M007 replay plus 5 USDT idle reserve; also show the
canonical 100 USDT M007 result. Verify the physical M007 figures rather than replacing
computed metrics with the owner's reference 344704 cycles / 89.561188% time open.

Use Decimal/fixed point. With residual operating cash C, inventory quantity Q, total
inventory acquisition cost K (including modeled BUY fee), and modeled net sale N:

```
PRE_RELEASE_OPERATING_BANK = C + K
REALIZED_RELEASE_DEFICIT = K - N
C_after_sale = C + N
transfer = REALIZED_RELEASE_DEFICIT
C_restored = C_after_sale + transfer = C + K
R_after = R_before - transfer
equity = operating_cash + inventory_mark + reserve
```

Thus the restoration target is the bank before this position's BUY, including prior
retained profits; it is not the mark immediately before release, nor a fixed 100.
Cash never receives more than the exact positive deficit. Require full coverage or KEEP.
Reserve is never included in affordable quantity, a BUY, exposure, principal or second lot.
An ordinary completed cycle with positive net realized profit P contributes `P * skim`
to reserve immediately after settlement and before any subsequent BUY. Nonpositive P
contributes zero. No fraction of principal is skimmed. Ordinary cycle count excludes
loss releases. Track gross cycle profit, skim and release loss separately; reserve
transfers and skims are internal movements and cannot manufacture total profit.

## Frozen search space

Exhaust all 27 combinations, no adaptive refinement after results:

| Parameter | Values |
| --- | --- |
| Reserve skim rate | 0%, 1%, 5% |
| Lock age threshold | 1 hour, 6 hours, 24 hours |
| Maximum release loss | 2 bps, 5 bps, 10 bps |

Three levels per axis permit immediate-neighbor checks, retain the owner's 1% idea,
and limit evaluation cost and selection freedom. The initial study deliberately limits
losses to 10 bps. It makes no safety assertion for the omitted 50–100 bps regime.
Any later expansion requires a new preregistration and cannot replace this study.
Use stable IDs encoding all three values. Same settings and input hashes must reproduce
the same economic result regardless of scenario iteration order.

First release review is entry timestamp + configured lock age; subsequent reviews are
every 60 minutes while that position remains open. This cadence is fixed, not searched.
Ordinary HIGH settlement occurring strictly before a scheduled review takes precedence.
At review T, use only completed prefix observations with timestamp strictly before T:

1. The position is still open and meets lock age.
2. The last observed trade price before T exists; no fabricated historical bid/ask.
3. Net theoretical proceeds imply a strictly positive deficit.
4. `10000 * deficit / PRE_RELEASE_OPERATING_BANK <= maximum_loss_bps`.
5. Available reserve covers the entire deficit.
6. Run the canonical M007 selector with its normal ranking, lookback, tick validity and
   support on the strict prefix. Its winning candidate has positive score and differs
   from the trapped (LOW,HIGH). Do not exclude the trapped candidate to force another winner.

If any condition fails, KEEP. After a release, rerun the selector on the same prefix,
record the new LOW/HIGH, remain flat and wait for a subsequent normal LOW event. There
is no instantaneous arbitrary-price rebuy. Record every rejection reason for diagnostics.

Release price is the last trade strictly before T, with the replay's explicit scenario
fee assumptions applied to net proceeds. Label the result
THEORETICAL_RELEASE_PRICE_PATH / THEORETICAL_RELEASE_LOSS.
`EXECUTABLE_RELEASE_LOSS=UNKNOWN`: the tape does not establish spread, queue, latency,
slippage, liquidity or fills. Mark PEG_RISK_WARNING if observed price departs from 1
USDT by at least 50 bps, or any release loss reaches 50 bps; reporting only, no news.

## Metrics frozen before evaluation

Use the full physical DEVELOPMENT interval from 2026-01-01 to the canonical cutoff,
with no economic early stop. Time measures include positions still open at cutoff;
future returns beyond cutoff remain unknown/right-censored.

For comparable primary lock metrics, fix a common 24-hour ruler for every scenario and
baseline. `LOCK_HOURS = sum(max(0, hold_duration - 24h))` over nonoverlapping inventory
episodes, including the final censored episode. `OPERATING_UPTIME = 1 - LOCK_HOURS /
full_interval_hours`; this counts flat eligible time and the first 24 hours of each
inventory episode as operating time. Report inventory-open fraction separately; it is
not the complement of uptime. Also report threshold-specific lock/uptime under explicit
secondary names, never use a scenario's own threshold to rank primary uptime.

`LOCK_HOURS_AVOIDED = baseline_LOCK_HOURS - scenario_LOCK_HOURS` is signed and may be
negative. Report hours >24h using the same excess-duration definition, plus time open,
max hold, cycles, zero-cycle UTC days, equity drawdown and operating-bank drawdown.

`RESERVE_DOLLARS_CONSUMED = sum(exact release deficits)`; replenishment does not net this
denominator down. `ADDITIONAL_PROFIT_ATTRIBUTABLE_TO_RELEASED_CAPITAL` is an explicitly
labeled retrospective policy-comparison proxy: scenario gross net-of-fees normal-cycle
profit minus baseline normal-cycle profit. It is not identified per-release causality:
skimming, compounding and later selection also differ. `RECOVERY_RESERVE_EFFICIENCY`
divides that proxy by consumed reserve. `ADDITIONAL_CYCLES_PER_RESERVE_DOLLAR` divides
scenario-minus-baseline normal cycles by consumed reserve. Both are null, not infinity
or zero, when denominator is zero. Also report net total-equity improvement divided by
consumption so release costs cannot be hidden by the gross productivity proxy.

Track each release's prior reserve as a replenishment target. First later time balance
again reaches that target gives time_to_replenish and cycles_to_replenish. Targets may
overlap; later releases do not reset earlier clocks. Unreached targets are right-censored.
Report total skim, minimum/final reserve, exact-zero reserve transitions as depletion
events, percent time empty, longest empty interval and full-coverage denials. Near-empty
and insufficient-for-a-release are distinct from zero; show both without renaming them.

Per release preserve entry time/age, original LOW/HIGH, price, loss/bps, all cash and
reserve before/after values, restoration target, new range/score, and later cycle counts.
Original HIGH's eventual return, subsequent cycles and per-release hypothetical avoided
waiting are RETROSPECTIVE_DIAGNOSTIC_ONLY. If HIGH never returns by cutoff, give censor
time and a lower-bound wait. Do not sum overlapping counterfactual per-release waits
into the primary aggregate LOCK_HOURS_AVOIDED metric.

Store timestamped operating cash, inventory mark, operating marked equity, reserve and
total equity; distinguish marked operating equity from the pre-BUY restoration target.
Dashboard traces show operating marked equity, reserve and total equity, with capital
lock start (fixed 24h ruler), recovery release, exact transfer, new range and replenishment
markers. Endpoints and every event reconcile; no unexplained balancing adjustments.

## Robust region, selection and promotion gates

Freeze these gates before Phase A and apply identically to any later full replay:

- Total final equity exceeds fair M007 + idle reserve by at least 0.01 USDT.
- Primary operating uptime improves and primary lock hours strictly decline.
- Normal completed cycles are at least 95% of baseline cycles.
- Minimum reserve is at least 1 USDT; depletion events equal zero.
- Maximum total-equity percentage drawdown is no more than baseline + 1 percentage point.
- Accounting, strict-prefix recovery decisions, deterministic replay and input provenance pass.

A robust eligible point and every existing immediate axis neighbor must pass all economic
and risk gates (change exactly one parameter one step). At least one qualifying neighbor
on each of the three axes is necessary. Record isolated wins as OVERFIT_WARNING.
Describe every connected robust region, including failing boundaries. If multiple
centers qualify, select by highest minimum equity improvement across its neighbor set,
then highest minimum uptime improvement, then lower loss cap, longer lock and lower skim.
These tie breaks are fixed before results and do not replace Astra's evidence review.

No robust region means no exact candidate registration and no successor full replay.
Complete valid evidence with no qualifying region gives REJECT; technical invalidity,
missing baseline reconciliation or incomplete evidence gives INCONCLUSIVE.
A qualifying region permits the exact config/lineage/spec to be committed and pushed
before the model full replay. Identical DEVELOPMENT full replay is verification, not
independent validation. PROMOTE means historical research champion only after all gates;
it never authorizes changing M007 shadow or operational settings.

## Evidence and milestones

Before scenario execution: preflight, implementation, mandatory invariant tests, protocol,
commit, normal push and HEAD == origin/main. Record published SHA and physical input hashes.
After Phase A: reports/usdcusdt/recovery-reserve-scenarios.csv and .json, release/time-series
artifacts, docs/microstructure/RECOVERY_RESERVE_STUDY.md and Astra review, commit and push.
Before any selected model replay: recheck registry ID, MODEL_SPEC, exact config and lineage,
commit and push. Afterwards reconcile replay, autopsy, decision and lightweight evidence,
commit and push. Raw tapes and large artifacts remain outside versioned reports.

Mandatory tests cover reserve segregation/no added exposure, exact deficit/no overfunding,
insufficient reserve KEEP, nonpositive deficit no transfer, positive-profit-only skim/no
principal skim, different valid positive-score candidate, strict-prefix recovery causality,
reserve and total-equity conservation, deterministic restart/repetition, initial operating
100 and reserve 5. Canonical M007 equivalence with hooks absent is also mandatory.
