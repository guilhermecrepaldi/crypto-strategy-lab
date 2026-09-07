# Dynamic recovery strategy — complete-strategy preregistration

Status: SCIENTIFIC_PREREGISTRATION; runtime NOT_IMPLEMENTED; no replay authorized by this file.
Scientific author/reviewer: GPT-6 Astra, high reasoning, 2026-09-07.
Authority: latest OWNER `MODEL LINEAGE + RECOVERY STRATEGY + QUALITY FIRST` override.
The previous reserve protocols remain historical evidence; their grids, caps, promotion gates
and identity conventions do not authorize this experiment.

## Identity, scope, and observed problem

`MODEL_ID=M011`, subject to the registry preflight performed at publication; `PARENT_MODEL=M007`.
`strategy=DYNAMIC_CAUSAL_RECOVERY`; `IMPLEMENTATION_STATUS=NOT_IMPLEMENTED`.
An existing runner that does not explicitly implement this strategy must reject it with
`UNSUPPORTED_STRATEGY`, never load M007 defaults or ignore the new fields. The future complete
configuration hash includes this protocol's published SHA256 and all financial/causal fields.
M007 is `HISTORICAL_BASELINE` / `SCIENTIFIC_ANCESTOR`, and its frozen SHADOW contract is unchanged.
M010 contributes no selection or release logic. M011 means this entire strategy, including the
ledger, funding, cap, clock semantics, peg gate, loss tiers, and confidence rule. Its selector
ancestry alone does not make it M007. Every sensitivity strategy and the passive control require
a distinct next-free Mn before execution; scenario labels never substitute for model identities.

Scope: `USDCUSDT_EXHAUSTIVE`, `USDCUSDT`, CPU, one operating bank, one lot, one LOW/HIGH, serial
cycles, `COMPOUNDING`, DEVELOPMENT only. Start is `2026-01-01T00:00:00Z`; the frozen physical
`end_exclusive=2026-09-05T23:59:59.783644+00:00`, copied from the canonical physical identity.
Do not add another microsecond. Dataset hash is
`8cb436b68d6953573d8e7e5dc89eaf53e344e46bde18ce749b440abdd757dd91`;
tape hash is `505fd6c31b010eac4e8da2d7e290137bb455d475b95409ac306d1ded7be55b6c`.
Reuse the exact canonical dataset manifest, tick metadata, event order and bootstrap evidence;
include their resolved identities in the implementation/run manifest. Do not extend data.
No VALIDATION, LOCKED_TEST, new market data, account connection, orders, Testnet or Live.

Physical M007 autopsy reports 344,704 cycles, 248 UTC calendar days, 55 active days and 193 zero
days. Its top 10 long holds explain 187 zero days (96.891192%) and 4,453.580662 hours of lock
beyond 24 hours (97.424873%). Total such lock is 4,571.297364 hours. This observation motivates
earlier causal intervention, but does not establish that an alternative range would keep cycling.
These numbers are historical M007 evidence, not M011 or the new fair-control results.

Hypothesis: a causally stronger, recently persistent destination can repay a fully reserve-funded
local loss through additional serial cycles. Funding remains the OWNER's exact 2% rule. Confidence
requirements rise with the loss; release count has no independent penalty. A price-path result
cannot establish executable economics or capacity.

## Frozen center and bounded strategy region

Only the center is registered now. The seven research configurations below are fully specified
before their results; the additional passive control gives eight planned full-interval runs.
Proposed neighbors are not execution authorizations or occupied IDs. On approval, allocate a
distinct next-free Mn, record parent M011 for a one-axis neighbor, and preserve its full hash.
The passive control's parent is M007. A changed configuration after observing results requires
another preregistration and another Mn, never editing an existing row.

| Planned order | Scenario role | Identity at this milestone | Minimum age | Confidence tier thresholds | Loss tier upper bounds, fraction of operating bank | Other change |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | PASSIVE_MATCHED_CONTROL | separate Mn required; UNREGISTERED | 1 hour, unused | .60 / .72 / .84 / .93, unused | .0025 / .01 / .02 / .03, unused | Release disabled; all other shared rules identical |
| 2 | CENTER_FULL | M011 | 1 hour | .60 / .72 / .84 / .93 | .0025 / .01 / .02 / .03 | None |
| 3 | CONFIDENCE_LOWER | separate Mn required; UNREGISTERED | 1 hour | .57 / .69 / .81 / .90 | .0025 / .01 / .02 / .03 | Thresholds minus .03 |
| 4 | CONFIDENCE_HIGHER | separate Mn required; UNREGISTERED | 1 hour | .63 / .75 / .87 / .96 | .0025 / .01 / .02 / .03 | Thresholds plus .03 |
| 5 | LOSS_LOWER | separate Mn required; UNREGISTERED | 1 hour | .60 / .72 / .84 / .93 | .00225 / .009 / .018 / .027 | Every loss bound times .9 |
| 6 | LOSS_HIGHER | separate Mn required; UNREGISTERED | 1 hour | .60 / .72 / .84 / .93 | .00275 / .011 / .022 / .033 | Every loss bound times 1.1 |
| 7 | AGE_LOWER | separate Mn required; UNREGISTERED | .75 hour | .60 / .72 / .84 / .93 | .0025 / .01 / .02 / .03 | Minimum age only |
| 8 | AGE_HIGHER | separate Mn required; UNREGISTERED | 1.25 hours | .60 / .72 / .84 / .93 | .0025 / .01 / .02 / .03 | Minimum age only |

`SCENARIO_COUNT=8_PLANNED = 1_CONTROL + 7_DISTINCT_RESEARCH_STRATEGIES`.
`REGISTER_NOW=1_CENTER`; `EXECUTE_NOW=0`. There is no Cartesian sweep or adaptive extension.
These thresholds are explicit scientific design assumptions, not empirically calibrated
probabilities, known optima, or a promise that any qualifying release exists in this dataset.

First future replay: PASSIVE_MATCHED_CONTROL, followed immediately by CENTER_FULL after the
control audit. This first pair answers whether reserve use buys cycles and reduces lock against
an identical funding/clock baseline. Neighbors follow only after center audit and the required
registration/authorization; their ordering is fixed above. Historical M007 remains visible as
a separate reference and never substitutes for the matched control.

## Operating bank, reserve, cap, and economic truth

All monetary quantities are USDT unless stated otherwise. Prices are USDT/USDC; inventory is
USDC; time is UTC and hours are elapsed seconds divided by 3600. A fraction .02 means 2%, or
200 bps; 1 bp is .0001. No implicit percent/bps conversions are allowed.

Initial operating bank O=100, reserve R=5, total equity E=105. O is **cost-basis operating
capital**: free operating cash plus the acquisition cost (including modeled buy fee) of the one
open lot. It is not mark-to-market equity. While a lot is held without a transaction, O remains
constant and marked operating equity changes with price. The hard cap is R <= .10*O at every
observable committed ledger state, including during holds. Price movement cannot change that
cost-basis denominator. Always report marked operating equity separately to prevent the cap
and restored bank from concealing an economic loss.

Quantities use the existing causal lot-step ROUND_DOWN rule; preserve residual operating cash.
Ledger arithmetic uses an isolated Decimal context with precision 128, never binary float or
the M007 ranking context. M007-like selector arithmetic retains its fixed Decimal28 context;
new confidence, rate, peg-risk and economic-gate arithmetic uses explicit Decimal128 with
ROUND_HALF_EVEN, except the downward cap bound specified below. Do not let ambient contexts
leak across these boundaries. Preserve exact inputs and deterministic decimal rounding residuals.
Initial invariants fail closed; do not silently change a supplied initial bank/reserve.
Implementation must prove monetary conservation at its declared precision and raise on
nonfinite arithmetic, overflow, invalid quantity, or an unreconciled residual. No new arbitrary
cash quantization is introduced by this protocol.

Cap allocation uses a downward-rounded Decimal128 bound for `(.10*B-R)/1.10`, including
negative bounds; the unallocated residual remains in O. Check the resulting inequality and
conservation using the exact integer-scaled representations of the stored Decimals, not a
second rounded approximate comparison. Any financial value that cannot be represented within
the declared ledger precision without an accounted residual fails closed as
`LEDGER_PRECISION_EXCEEDED`; increase neither precision nor tolerance silently during a run.

Primary price-path cost scenario is the existing zero-maker-fee scenario, f_buy=f_sell=0.
This explicitly models no fees; it makes no claim that observed or future executions are free.
Keep all fee terms in the equations and record fees=0 in the manifest. Executable fees, spread,
queue, liquidity, slippage, partial fills, latency and market impact remain UNKNOWN. No fee
sensitivity or different execution scenario is silently added to these eight configurations.

For an ordinary completed cycle let P be its realized net profit after both modeled fees.
Calculate raw mandatory contribution s=.02*max(P,0), every time P>0. With pre-settlement O,R,
set B=O+P. The exact simultaneous cap solution is:

```text
u = min(s, (.10*B - R)/1.10)
O_after = B - u
R_after = R + u
RESERVE_CONTRIBUTION_RAW = s
RESERVE_CONTRIBUTION_APPLIED = max(u, 0)
RESERVE_CAP_OVERFLOW = s - u
```

Normally u is nonnegative. If a nonpositive ordinary cycle reduces B enough to violate the cap,
u may be negative: `-u` is a reserve-to-operating cap rebalance, explicitly recorded separately
from profit funding and release coverage. It is never called cycle profit. With B>=0 and R>=0,
this rule leaves both balances nonnegative and ensures the post-transfer cap exactly. If B<0,
halt with an accounting violation. Do not clip u to zero and leave an over-cap reserve. Apply
the same rule to the passive control. Transfers never create equity.

The denominator must include overflow returned to the operating bank. For example O=100,
R=10, P=1 gives s=.02 and u=.02 (cap not binding); O=100,R=10,P=100 gives u=2. If already at cap,
2% funding is below cap growth, so positive profits move away from the cap. A cap-overflow
unit fixture must therefore also exercise an intentionally over-cap intermediate settlement
state or a legitimate negative settlement, without claiming that the normal initial path
necessarily reaches it.

Before a release let q be inventory, K its acquisition cost, c free operating cash, and
p the last trade price strictly before review T. Define:

```text
O_pre = c + K
net_sale = q*p*(1-f_sell)
D = K - net_sale
loss_fraction = D/O_pre
reserve_spend_fraction = D/R_pre
marked_operating_equity = c + q*p
total_equity = marked_operating_equity + R_pre
```

Release is eligible only for D>0 and R_pre>=D, plus all gates below. Execute the modeled sale
and the exact coverage as **one atomic ledger transaction**: operating cash becomes
c+net_sale+D=O_pre; inventory becomes zero; R_after=R_pre-D. There is no intermediate cap
rebalance between the sale and its coverage. This restores pre-release cost-basis bank,
not its marked equity, not 100, and not the parent's capital. Log LOCAL_RELEASE_LOSS=D.
With zero modeled fees, the loss is already reflected in the preceding market mark: the sale
and internal coverage do not charge D to total equity a second time. From acquisition to sale,
the realized loss reduces equity by D; mark-to-realized reclassification is not another loss.

R_after may be below .05*O; classify RESERVE_REBUILDING. For .05*O <= R < .10*O classify
RESERVE_HEALTHY; equality to cap is RESERVE_CAPPED. R cannot buy, add size, fund another lot,
or replenish from principal. A release has no positive cycle contribution and is not counted
as a completed profitable LOW-to-HIGH cycle. Terminal inventory stays open and is marked to
the final physical price; no forced close at cutoff.

## The 5% target is not sustainably funded by 2% alone

Without releases or binding cap, after cumulative positive realized cycle profit G:

```text
O = 100 + .98*G
R = 5 + .02*G
R/O -> .02/.98 = .020408163265306122... as G -> infinity
R - .05*O = -.029*G
```

Thus every positive profit from an initially exact 5% reserve moves below the 5% target,
even if no reserve is spent. With cumulative release losses D_total, the latter gap becomes
`-.029*G - D_total` in the no-other-loss/no-cap case. A stationary 5% share without releases
would require at least `.05/1.05 = 4.7619047619%` profit funding, which is **not authorized**.
At 2%, absolute reserve rebuilding is possible; maintaining the moving 5% band during unlimited
compounding is not. Additional release spending requires still more funding for a stationary
5% share. Report this incompatibility; do not change the OWNER's 2% rate, inject cash, or claim
the reserve normally stays between 5 and 10%.

`R_final>=5%*O_final` is therefore not a promotion gate. Reserve depletion, funding/outflow,
coverage and economic benefit remain explicit. Full reserve coverage can legitimately block
further releases and produce long holds. Do not automatically stop an otherwise valid run.

## Strict causality and event order

All selection and release feature snapshots at clock time T use only trade timestamps <T,
including every member of an equal-timestamp group. For windows use [T-w,T). This strict
timestamp boundary is part of the new strategy and matched control; it does not silently
rewrite the historical event-prefix M007 replay or the separate SHADOW temporal-choice gate.
Inside an admitted prefix, preserve canonical event IDs and their order, including different
IDs at the same timestamp. Do not deduplicate distinct trades.

1. Apply ordinary touch settlements with timestamps <T before the scheduled review at T.
2. At T, take one immutable strict-prefix snapshot. If a position is eligible for age, evaluate
   the release once before processing any market event whose timestamp equals T.
3. If no release occurs, process market events at T in canonical event order. The currently
   selected LOW/HIGH may settle on an exact price touch under the existing theoretical rules.
   Such a touch is an event observation, not inclusion of T in selection/confidence features.
4. After any ordinary exit, reselection uses the strict timestamp snapshot at that exit time.
   A later event ID is required for the next ordinary entry, as in the serial ancestor. After
   a release at T, require a market timestamp strictly greater than T for the new LOW entry;
   never buy at the release price as part of the coverage transaction.
5. A normal HIGH at exactly scheduled T does not preempt the strict-prefix review. A HIGH
   strictly before T already closed the lot. Freeze this boundary in fixtures.

Review first at entry timestamp + the scenario minimum age, then every 15 minutes from that
anchor while the same position remains open. Skipped or failed reviews do not change the
anchor; a new position creates a new anchor. Review scheduling is independent of future
timestamps and market activity. No extra release-count cooldown or hindsight suppression.

After release, set the causal winner as candidate, stay FLAT and use the shared canonical
60-second FLAT reselection schedule (anchored to replay start), plus immediate post-exit
selection. If another eligible winner appears before a LOW, the normal FLAT selector may
replace the destination. Do not force the released destination to persist. Preserve an open
position's absolute LOW/HIGH across tick transitions. The shared peg gate below blocks new
entries when active, without automatic liquidation.

Theoretical release price uses the last known trade at review time, not a later executable
fill. If that observation is more than 60 seconds old, skip release as STALE_PREFIX_PRICE;
do not interpolate or substitute a future price. This is a stated price-path assumption.

## Prefix features and units

Reuse `_selection_grid`, `CandidateTimeline.contained_cycles`, `_score` and `_select` from
the serial replay authority. The M007-like candidate score is `C24*(HIGH/LOW-1)`, dimensionless;
its winner maximizes `(score, C24, -LOW, -distance)` over the causal one-exchange-tick grid.
Do not exclude the original to manufacture a different winner. Require winner score >0.
The original absolute range is evaluated even if it is no longer eligible in the current grid.

For each original o and destination d and w in {1,4,24} hours:

- C_r,w is contained complete serial LOW-to-HIGH cycles, starting FLAT at the left edge;
  no cycle is borrowed from before that edge. Count exact touches, no overlaps.
- L_r,w and H_r,w count exact LOW and HIGH trade-event visits respectively, including repeated
  events at the same level. This deliberately measures visits, not independent fills.
- closure_r,w=C_r,w/max(1,L_r,w). This visit-based fraction is an observable diagnostic,
  not an empirical fill probability. It lies in [0,1].
- high_support_r,w=min(1,H_r,w/max(1,L_r,w)). Weighted closure and high support below use
  weights (.5,.3,.2) for (1h,4h,24h). Record every raw count as well as the aggregates.
- last_r is the latest complete cycle exit in the 24h contained-cycle prefix; if none, its
  age is +infinity. Destination requires a real recent completion. Original infinity is
  treated as maximal staleness, not fabricated as a known historical completion.
- persistence_d is the number of disjoint completed hours [T-kh,T-(k-1)h), k=1..4, containing
  at least one complete window-contained cycle, divided by 4. Range is {0,.25,.5,.75,1}.

Define conservative destination rate r_d=min(C_d,1, C_d,4/4, C_d,24/24), cycles/hour, and
conservative-for-release original rate r_o=max(C_o,1, C_o,4/4, C_o,24/24), cycles/hour.
The max original rate deliberately preserves evidence that the original was productive in
the prior day; these are fixed estimates, not forecasts fitted after observing a recovery.

Let g_d be theoretical positive net profit of one destination cycle sized by the restored
O_pre using the same lot step, dust and two fee terms. Compute g_o analogously at the original
range, using max(0,g_o) below. Require a legal nonzero destination quantity and g_d>0.

```text
RECOVERY_COST_IN_CYCLES = D/g_d                      [cycles, real-valued]
RECOVERY_COST_WHOLE_CYCLES = ceil(D/g_d)              [integer cycles]
FUNDING_RECOVERY_CYCLES = ceil(D/(.02*g_d))           [integer cycles]
G24 = 24 hours * max(0, r_d*g_d - r_o*max(0,g_o))     [USDT]
```

FUNDING_RECOVERY_CYCLES ignores subsequent size changes and cap overflow, and therefore is a
fixed-current-bank explanatory estimate, not a promised funding time. G24 is a causal
constant-rate productivity hypothesis over a frozen 24h horizon, not future realized gain.
Require G24>0. Never feed future completion times, remaining horizon or realized post-release
cycles back into these features.

## Exact confidence formula and monotonic loss tiers

`clip(x)=min(1,max(0,x))`. Times below are elapsed hours; fractions are dimensionless. Define:

```text
co = .5*closure_o,1 + .3*closure_o,4 + .2*closure_o,24
ho = .5*high_support_o,1 + .3*high_support_o,4 + .2*high_support_o,24
A = .4*clip(1-r_o/r_d) + .2*(1-co) + .2*(1-ho) + .2*clip(age(last_o)/4)

relative_score = clip((S_d-S_o)/S_d)
B = .25*clip(1-r_o/r_d) + .25*relative_score
    + .25*clip(1-age(last_d)/1) + .25*persistence_d

AGE = clip(position_age/4)
deviation = max(0, (original_LOW-p)/original_LOW)
PRICE = 1-clip(deviation/.10)
ECON = .7*clip(G24/(4*D)) + .1*(1-D/R_pre) + .2*clip((R_pre/O_pre)/.05)

CAUSAL_RELEASE_CONFIDENCE = .25*A + .30*B + .10*AGE + .10*PRICE + .25*ECON
```

S_o=C_o,24*(original_HIGH/original_LOW-1); S_d is the causal winner score. r_d and S_d must be
positive before division. All components lie in [0,1]. Raw current deviation, absolute peg
distance, reserve before/after, reserve fractions, loss and both recovery-cycle costs are
logged even when a gate fails. Confidence is an ordinal, interpretable score, **not a
calibrated probability**. Increasing D with all market evidence fixed cannot increase ECON;
larger adverse price displacement cannot increase PRICE. Thresholds and hard evidence
requirements below never decrease as the loss tier rises.

Normalization deliberately assigns the largest economic weight to prospective incremental
productivity; reserve spending itself contributes only .025 of total confidence. With all
other evidence at its maximum, zero fees/full deployment, R/O=.05 and loss=.03, this score
can reach `1-.10*(.03/.10)-.25*.10*(.03/.05)=.955`, above the center's .93 requirement.
At loss=.025 that upper bound is .9625, above the stricter neighbor's .96. Thus >2% tiers
are not made algebraically impossible by the confidence normalization itself. These are
feasibility bounds, not observations; actual prefix evidence and peg gates can still prevent
every such release. As reserve/operating tends toward 2.0408% without releases, the .75
reserve-spend gate alone limits an individual covered loss to about 1.5306% of operating:
larger tiers may be reachable only while sufficient initial reserve headroom remains.

| Center loss interval D/O | Minimum confidence | Destination minimum C1/C4/C24 | Minimum persistence | Latest destination completion | Required G24/D | Maximum D/R | Maximum peg-risk score |
| --- | ---: | --- | ---: | --- | ---: | ---: | ---: |
| (0,.0025] = up to .25% | .60 | 3 / 12 / 24 | .75 | <=15 minutes | >=2 | <=.75 | <1 |
| (.0025,.01] = up to 1% | .72 | 6 / 24 / 48 | .75 | <=15 minutes | >=2.5 | <=.75 | <1 |
| (.01,.02] = up to 2% | .84 | 12 / 48 / 96 | 1 | <=10 minutes | >=3 | <=.75 | <=.75 |
| (.02,.03] = up to 3% | .93 | 24 / 96 / 192 | 1 | <=5 minutes | >=4 | <=.75 | <=.5 |

The first matching upper bound selects the tier; equality belongs to the lower-cost tier.
Above the largest scenario bound: LOSS_OUTSIDE_PREREGISTERED_REGION, no release. Confidence
and loss neighbor changes affect only their declared table columns; the support/margin/peg
columns remain attached to tier ordinal. The high-loss risk override is independent of
ordinal: every loss strictly above 2% must satisfy at least tier-4 confidence, support,
persistence, recency, economic margin and peg gates. This prevents the LOSS_HIGHER neighbor's
2.2% tier-3 boundary from weakening the rule for actual >2% losses. Use the larger applicable
confidence threshold in that neighbor. Log PEG_RISK_HIGH for every evaluated loss >2%.

Additional release gates, all conjunctive: position open; scenario age met; original C1=0;
winner differs from original; r_d>r_o; full reserve coverage; fresh prior price; positive
causal destination profit; confidence and all tier supports passed; no metadata, integrity,
ledger, causal-prefix or peg halt. Neither elapsed age nor observed loss alone causes a sale.
The .75 reserve-spend limit is a fixed liquidity-risk invariant, not a preference for fewer
releases. It preserves some ability to fund a subsequent event and is not a 5% reserve floor.

## Price-only peg-risk gate

Use only the canonical trade-price prefix; volume, book, news and liquidity are unavailable
and are never invented. Require a complete 4h prefix, positive prices, and a fresh last price.
Let p4 be the last observed price strictly before T-4h (no more than 60 seconds old at that
boundary); if unavailable, skip the gate-dependent action as INSUFFICIENT_PEG_PREFIX.

```text
d1 = max over trade events in [T-1h,T) of abs(price/1 USDT_per_USDC - 1)
drift4 = abs(p/p4 - 1)
span1 = max_price_1h/min_price_1h - 1
PEG_RISK_SCORE = max(d1/.02, drift4/.01, span1/.02)
```

If score>=1, block releases and new entries; keep an existing position, allow its normal
HIGH settlement, and continue later causal reviews. FLAT selection may still be computed but
cannot open inventory until the gate clears. The same entry gate applies to the passive
control. Risk acceptance is deliberately asymmetric: this study does not add an emergency
liquidation mechanism. A structural peg event can therefore remain locked indefinitely.

The gate can make a >2% release impossible for this observed tape, even though its loss tier
exists. This is a legitimate reachable-support result: report evaluations, rejections and
reachable loss range; label an unused tier UNTESTED_IN_OBSERVED_SUPPORT. Do not relax peg
thresholds, extrapolate tail safety, or fabricate volume evidence to force a large release.

## Scoreboard and denominator conventions

Use the full physical interval H elapsed hours and every intersecting UTC calendar day N,
including partial first/last days consistently for all runs. Historical reference N=248 must
be physically rechecked against the unchanged manifest. A day is active if at least one
ordinary completed LOW-to-HIGH cycle exits that day. Releases are not cycles. Zero days=N-active.

- TOTAL_CYCLES, CYCLE_MULTIPLIER_VS_M007=C/344704, CYCLES_GAINED_VS_M007=C-344704; also report
  equivalent comparisons to the matched control. Daily mean=C/N; daily median includes zeros.
- COMPOUNDING_UPTIME is the fraction of elapsed replay time covered by the union of
  [ordinary_cycle_exit, ordinary_cycle_exit+1h), clipped to the replay interval. It measures
  observed recent cycling and cannot be inflated by merely staying FLAT or issuing releases.
- LOCK_HOURS is sum(max(0, inventory_episode_duration-24h)), including released positions and
  the terminal censored open position. OPERATING_UPTIME=1-LOCK_HOURS/H retains the historical
  convention; also report holding hours, FLAT hours, and excess holding beyond 1h/6h/24h.
- CYCLES_PER_CALENDAR_DAY=C/N. CAPITAL_HOURS is the integral of deployed acquisition cost
  divided by initial 100 USDT over elapsed hours (unit: 100-USDT-bank-hours).
  CYCLES_PER_CAPITAL_HOUR=C/CAPITAL_HOURS; also report cycles per inventory-held clock hour.
  This prevents silent interchange of time utilization and capital-weighted efficiency.
- Report closed-hold mean/median/p95/p99 and max hold including the terminal censored duration;
  label censoring and report closed-only quantiles separately. Quantiles use sorted durations
  with nearest-rank ceil(p*n), undefined for no closed episode.
- At every market-price change and ledger transaction, calculate total marked equity and
  drawdown=(running_equity_peak-current_equity)/running_equity_peak. Peak starts at 105.
  MAX_DRAWDOWN is the maximum fraction over this full path, never only day-end snapshots.
- Report operating bank at cost, operating marked equity, reserve, total equity, all modeled
  fees, reserve raw/applied funding, cap overflow, cap rebalances, cumulative release loss,
  minimum reserve/fraction, final reserve/fraction, rebuilding time and time at cap.
- Report release count, daily/30d/per-100k-cycle rates, mean interval (null for fewer than two),
  maximum release USDT and percent, mean release and every rejected-gate count by loss tier.
  Report exposure to each confidence/loss/peg tier, including zero reachable opportunities.

Let D_total be gross release loss, not net of funding. Post-replay efficiency measures are
`(C-C_control)/D_total`, `(LOCK_control-LOCK)/D_total`,
`(ZERO_control-ZERO)/D_total` and `(E_final-E_control_final)/D_total`, respectively named
CYCLES_PURCHASED_PER_RELEASE_DOLLAR, LOCK_HOURS_AVOIDED_PER_RELEASE_DOLLAR,
ZERO_DAYS_AVOIDED_PER_RELEASE_DOLLAR and TOTAL_EQUITY_GAIN_PER_RELEASE_DOLLAR.
Use null with a reason when D_total=0, never zero or infinity. These aggregate matched-policy
contrasts are RETROSPECTIVE_DIAGNOSTIC_ONLY, not a sum of overlapping hypothetical futures
per release. Negative efficiencies remain visible.

Reserve coverage ratio is applied positive-profit funding / D_total, null if D_total=0.
Report absolute inflow/outflow, per-day/30-day/per-100k-cycle rates and R_final-R_initial.
`ABSOLUTE_RESERVE_SELF_FUNDED` requires applied funding>=D_total; otherwise label
`SEED_RESERVE_DEPENDENT` even if equity improves. Falling below the moving 5% target is
RESERVE_REBUILDING, not automatically failure. It must not be described as sustainable 5%
funding. All monthly/concentration and post-release effects are descriptive after replay.

## Eligibility, robustness, throughput ranking, and stop rules

A scientifically valid full run requires a complete interval, invariant-preserving accounting,
R>=0, continuously valid cost-basis cap, strict-prefix decisions, deterministic restart and
complete source/config/data/checkpoint provenance. Technical failure is INVALIDATED_TECHNICAL
only for the demonstrated scope, preserving artifacts. A partial run is not eligible.

Center and each neighbor must separately satisfy these **economic eligibility** gates versus
the matched passive control:

1. cycles strictly greater, zero days strictly fewer, and both COMPOUNDING_UPTIME and
   OPERATING_UPTIME strictly greater; LOCK_HOURS strictly lower;
2. final total marked equity exceeds control by at least .01 USDT;
3. maximum total-equity drawdown <= control maximum drawdown + .01 (one percentage point);
4. applied positive-profit funding >= gross cumulative release loss, ensuring reserve use has
   been replenished in absolute dollars over this observed horizon; no demand for final 5%
   share, reserve minimum USDT floor, or fewer releases;
5. no validity/integrity violations and complete event-level plus daily/monthly evidence.

The absolute self-funding gate is a finite-horizon sustainability condition, not an excuse to
avoid using reserve. A candidate passing gates 1-3 and 5 but failing gate 4 is reported fully
as ECONOMIC_GAIN_SEED_RESERVE_DEPENDENT; it is not silently called an economic failure, yet
cannot receive the stronger sustainable-region recommendation under this preregistration.

TARGET95_VS_M007 is classified separately: zero_days<=9, since (193-9)/193 >=.95. Also report
zero-day reduction against the matched control. Ten days is not TARGET95. Target attainment
alone is never sufficient, and zero remains a desirable reported outcome.

A robust region requires all seven research strategies to satisfy the eligibility gates, plus
each neighbor's positive cycle gain over the control to be at least 50% of the center's cycle
gain and its log equity gain `ln(E/E_control)` to be at least 50% of the center's. Log gains
are retrospective comparison metrics only; calculate with reproducible high-precision code.
This guards against a lone winning point without demanding similar dollar balances after
geometric compounding. If the center passes but a neighbor fails, classify
PARAMETER_CLIFF / ROBUST_REGION_NOT_DEMONSTRATED; preserve the passing point as development
evidence, never automatically promote it or search another neighborhood.

Within the fixed eligible region report lexicographic throughput-first ordering:
greater total cycles; greater COMPOUNDING_UPTIME; fewer zero days; greater final total equity;
lower LOCK_HOURS; lower max drawdown. Ties at full recorded precision use the planned order,
not fewer releases, smaller reserve consumption or a newly invented tie-break. Report the
worst neighbor's cycle gain, uptime gain, zero-day reduction, log equity gain and drawdown
margin as the region's conservative evidence. The center remains M011; a better neighbor
keeps its own Mn and requires explicit scientific/OWNER acceptance. No SHADOW migration,
production promotion or prospective claim follows from DEVELOPMENT success.

Every started valid model covers the full interval. This protocol chooses **no economic
early-stop/dominance rule** because unlimited modeled compounding and future reserve recovery
provide no proven prefix upper bound on final superiority. Poor equity, low cycles, depleted
reserve, a long hold or an unfinished position do not authorize stopping. Once the center is
fully audited, a failed core economic gate can close this fixed hypothesis as REJECTED without
starting any neighbors; record unstarted neighbors NOT_RUN_CENTER_INELIGIBLE, never failed.
If center passes and neighbors are later authorized, run the fixed six without adaptive
pruning. Technical invalidity or a later explicit OWNER supersession can stop a started run;
preserve the last intact checkpoint and mark the exact reason, never recast it as a full loss.

## Before implementation and before any replay

Reuse and extend the canonical serial/reserve implementation by explicit configuration; no
parallel permanent replay engine. Historical configurations and their old artifacts remain
unchanged. The present document is a specification, not implemented capability.

Before a future implementation is declared ready, required fixtures cover: raw 2% skim and
simultaneous cap algebra, large-capital precision and no double charging of release loss;
full versus one-unit-insufficient reserve coverage; every inclusive tier boundary and actual
>2% override; confidence monotonicity in D with features fixed; strict timestamp groups and
same-time HIGH/review priority; stale price/p4; no-prefix or zero denominators; unchanged
winner ties; peg-blocked entry without forced sell; identical passive/common semantics;
release FLAT transition and next-LOW wait; terminal censoring; cumulative funding and
drawdown reconciliation; deterministic uninterrupted versus checkpoint-resumed traces.

No trade, long replay, research grid, new data acquisition, training or SHADOW run is started
by this milestone. Publish strategy identity, this preregistration and current-state authority,
then stop for the OWNER's next execution instruction. Before that future run, commit/push
validated implementation and exact resolved manifests; record its published GIT_COMMIT_SHA.
Do not label pending code or an unexecuted strategy as delivering cycles, reserve recovery,
economic improvement, or the 95% target.
