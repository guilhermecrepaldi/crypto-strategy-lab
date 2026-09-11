# M034 pre-replay protocol

Status: `FROZEN_EX_ANTE_CRITERIA`; `READY_FOR_REPLAY=false`.

Registered on 2026-09-10 before inspecting market-performance content for M034,
choosing a pair, date or final window, or running any economic replay. Scientific
review: `PASS_FOR_EX_ANTE_REGISTRATION`, GPT-6 Astra, reviewed source HEAD
`420c99e825eea9c28a370b8f3f815bad923c60ce`.

This protocol governs preparation of the first Binance-only M034 economic replay.
It does not authorize that replay. `ECONOMIC_REPLAY_RUNS=0` and
`STRATEGY_PASS=false` remain invariants.

## 1. Order of operations

1. Reconcile the published engineering gates without changing economics.
2. Freeze this protocol.
3. Inventory candidate Binance Spot books and physical files without reading their
   profitability or M034 strategy outcome.
4. Build temporal fee, rule, safety and dataset evidence for every candidate unit.
5. Assign immutable `CALIBRATION` and `VALIDATION_OOS` roles and freeze their hashes.
6. Calibrate only from eligible calibration evidence; do not run M034 economics to
   manufacture labels.
7. Freeze thresholds, costs, latency, capital, runner, audit and replay protocol.
8. Build the immutable eligible window pool and only then select one final window by
   a preregistered fixed rule or one CSPRNG draw.
9. Register a complete experiment manifest and obtain source-bound review when code
   relevant to the runner or economics changed.

No later step may retroactively change an earlier artifact under the same experiment
identity.

## 2. Unit of eligibility and candidate universe

The atomic unit is `BookKey(BINANCE, native_symbol) + [start_us,end_us) + exact
fee/rule context`. Every physical book used by a canonical `VenueRoute` must qualify
independently. Kraken is not inventoried for M034 economics and contributes no
candidate, obligation, capital, slot, decision or KPI.

The candidate universe is formed without performance data from Binance Spot pairs
whose two assets are admitted by the existing stablecoin authority, subject to its
four-asset ceiling. Availability comes from an exchange/source catalog and physical
file inventory, not from spread, cycles, edge, PnL or realized regime. Geometry remains
seven ranks and C1+C2.

Each unit carries these separate states:

- `AVAILABLE`: a discoverable Binance Spot book/date exists;
- `DATA_ELIGIBLE`: physical L2 and individual trades pass all data gates;
- `FEE_ELIGIBLE`: historical fee evidence covers the whole economic interval and
  exact context;
- `RULES_ELIGIBLE`: historical symbol rules cover the whole interval;
- `SAFETY_ELIGIBLE`: temporal safety authority exists so the future runner can make
  causal decisions;
- `ECONOMIC_CANDIDATE`: every preceding state is true.

`AVAILABLE != ELIGIBLE`. If legitimate candidates exceed inherited asset/geometry
limits, no reduction rule is currently authorized; selection remains blocked as
`OWNER_VALUE_REQUIRED` rather than using observed market performance.

## 3. Date and physical-data eligibility

A date is a UTC civil-day candidate only when the exact interval and required warm-up
can be represented as `[start,end)` and all required books have:

- immutable source identity, provenance, byte size and SHA-256 for raw and normalized
  files, plus an explicit derivation link between them;
- a usable initial L2 snapshot and sequence-validatable L2 deltas, or an already
  validated alternative continuity authority explicitly named in the manifest;
- individual trades with exchange identity/timestamp, side or maker flag, price and
  quantity, and a deterministic duplicate identity;
- deterministic causal ordering by exchange time, capture/availability time, native
  sequence and source order;
- complete coverage of the economic interval and preregistered warm-up;
- audit counts for gaps, resets, duplicates, out-of-order events, crossed/invalid
  books and trade/book inconsistencies.

OHLC is not L2. Aggregate trades do not prove public queue consumption. A synthetically
generated stream cannot be labeled historical.

Any unresolved continuity gap makes the entire atomic interval ineligible. No numeric
gap tolerance is authorized. A discovered gap cannot be removed by clipping to a
profitable subinterval. If a future run encounters a previously hidden gap, the
affected scope is technically invalidated, the physical state is preserved and no
new fill inference is allowed after the gap.

## 4. Temporal fee, rule and safety evidence

Historical replay accepts only `PROVEN_HISTORICAL` fee and rule records whose effective
intervals cover every relevant decision timestamp and whose venue, native symbol,
maker/taker intent, fee asset semantics, tier/account context and rule fields match the
candidate. Missing, ambiguous, overlapping or incomplete evidence fails closed.
`PROVEN_FORWARD` and `ACCOUNT_SPECIFIC` records may document current capabilities but
cannot validate a historical interval. Collection time is not effective time.

Rules must cover symbol status and every relevant price, lot-size, quantity and
notional filter. Fee evidence must cover maker/taker rates, promotions and debit asset
semantics. Both are re-resolved at each future decision, including every route leg.

Safety evidence must be temporal and causal. PEG, FLOW, DEPTH and SPREAD are evaluated
inside a future replay as decision-time gates. They are not used now to exclude a date
because its later realized regime looks poor. Missing safety evidence maps to
`BLOCKED_SAFETY`; missing data, fee or rule evidence maps to `BLOCKED_DATA`.

## 5. Calibration and independent OOS

Data roles are assigned before any estimator or threshold uses the content. Identity
is based on underlying venue/book/interval/content, not merely filename or normalized
hash. Recompression, renaming or re-normalization does not create independence.

Any tape, observation or derived artifact that influenced an M034 hypothesis, formula,
bound, estimator, threshold, regime rule, pair choice or window choice is
`CALIBRATION`. Historical tapes already observed by M030/M032/M033 do not recover OOS
status under a new hash. `VALIDATION_OOS` requires evidence that its content was not
used in model development and that it has no underlying interval overlap.

Calibration must precede validation chronologically. Before opening OOS, the final
artifacts must freeze warm-up, maximum label horizon, temporal separation and any
minimum sample-size method. On first validation, estimator parameters remain frozen;
only explicitly preregistered causal rolling features may evolve.

For a decision at `t`: `training_cutoff <= t`, `feature_cutoff <= t`, and every label's
`available_at <= t`. The same dataset identity cannot have both roles.

Calibration may use appropriate, already audited physical outcomes or non-economic
market statistics. It does not authorize an M034 strategy/ledger replay, PnL, fill or
cycle generation. If operational labels require a prohibited replay, record
`CALIBRATION_LABELS_UNAVAILABLE` and keep readiness false.

## 6. Estimator and censoring policy

Completion means full physical completion of the entire route within a frozen horizon;
partials are not completion. Cancellations, rejections, risk reductions and unfinished
outcomes are distinct states. Marginal leg probabilities are not multiplied under an
unproven independence assumption.

Administrative cutoff censoring is neither a fill nor an exact duration. Censored
observations remain in the completion denominator. Expected lock remains `UNKNOWN` if
the eligible prefix contains censoring and no separately justified survival method or
conservative bound has been frozen. Censored duration is never replaced by cutoff time.

Adverse-selection calibration must freeze side sign, reference price, horizon, unit,
population and label availability. Only labels whose horizon and delivery completed
inside the causal calibration prefix are usable.

Every estimator artifact must identify inputs, units, horizons, method, software
version, role-registry hash, training/feature cutoffs and SHA-256. Unknown remains
unknown.

## 7. Latency and execution-cost policy

Market-data delivery, submit, activation/ACK, cancel request, cancel ACK and requote
latencies are separate quantities. Exchange capture timestamps do not prove client or
order latencies. Zero is not an authorized default.

Each quantity must use historical evidence, a justified conservative bound, or remain
`UNKNOWN`. Execution cost may include only explicitly modeled tick loss, requote,
crossing, taker contingency, impact, slippage and latency cost. Its artifact must name
the population, horizon, unit, exclusions and evidence. Execution, adverse selection,
residual, carry, tail and risk buffer must not charge the same loss twice.

If a required cost is unknown, the candidate is rejected unless the complete
`CONSERVATIVE_BOUND` policy and both canonical unknown-cost bounds are preregistered.

## 8. Window, cutoff and terminal state

The economic interval is `[start,end)`. Events at or after `end` cannot reach the
economic state machine. Warm-up is causal and read-only: it creates no order, capital,
fill, PnL or pre-window result.

At cutoff, open inventory, reservations, orders, cost basis, FIFO/epoch and owned-return
obligations remain physical. There is no forced liquidation, reset, synthetic fill or
synthetic cancel ACK. Terminal marking uses the last admissible causal mark; missing
marks remain unknown and do not become a one-dollar parity.

The official duration, sortable unit and admissible calendar are currently
`OWNER_VALUE_REQUIRED`. They cannot be inferred from earlier campaigns. The final
selection must be one of:

- `FIXED_EX_ANTE`: a window demonstrably fixed before inspecting M034 performance; or
- `CSPRNG_ONE_DRAW`: after pair/date pool, fees, rules, dataset, thresholds, estimators,
  replay protocol and capital are frozen and hashed, preregister the deterministic draw
  algorithm, perform exactly one draw, publish seed provenance and output, and never
  reroll.

If the selected unit later proves invalid, preserve the selection and block. Do not
silently substitute another unit.

## 9. Capital and KPI denominator

Initial capital, physical composition, capital currency and `SLOT_BASE` are
`OWNER_VALUE_REQUIRED`, subject to the M034 ceiling of 200 USD-equivalent. Conversion
requires causal temporal marks and does not move assets physically.

Before any replay, `NET_REALIZED_PNL_PER_CAPITAL_HOUR` must use total campaign capital
for the whole registered window, including idle and blocked states. Productivity per
actually locked capital-hour is a separate diagnostic. No exclusion of
`BLOCKED_DATA`, `BLOCKED_SAFETY`, idle or residual inventory may improve the primary
denominator.

## 10. Decision table and unresolved gates

| Area | Frozen rule | Current state |
|---|---|---|
| Binance venue | Binance only; Kraken excluded before economics | `FROZEN` |
| Physical identity | `BookKey + [start,end) + context` | `FROZEN` |
| Data gaps | any unresolved continuity gap rejects atomic interval | `FROZEN` |
| Calibration/OOS | disjoint underlying content; calibration never OOS | `FROZEN` |
| Cutoff/residual | preserve physical state; no cosmetic liquidation | `FROZEN` |
| Unknowns | fail closed; never zero | `FROZEN` |
| Candidate pairs/dates | evidence-derived, performance-blind | `NOT_INVENTORIED` |
| Final duration/calendar | owner choice or prior objective authority | `OWNER_VALUE_REQUIRED` |
| Initial capital/SLOT_BASE | physical, <=200 USD-equivalent | `OWNER_VALUE_REQUIRED` |
| Estimator methods/artifacts | causal, role-bound, censored correctly | `NOT_CALIBRATED` |
| Latency/cost evidence | evidence/bound or unknown | `NOT_CALIBRATED` |
| Threshold values | canonical source names and provenance | `NOT_REGISTERED` |
| Final window | fixed ex ante or one frozen-pool CSPRNG draw | `NOT_SELECTED` |

## 11. Research-first disposition

- `ADOPT`: canonical `BookKey`, `VenueRoute`, ledgers, queues, temporal registries,
  cancel-ACK lifecycle, capital-state reasons and provenance contracts.
- `ADAPT`: existing data manifests/validators to Binance book+interval evidence;
  semantic role registry; prior CSPRNG mechanics only after a new M034 pool is frozen.
- `INSPIRE`: formal survival/censoring methods after an objective method and evidence
  are selected and preregistered.
- `BUILD`: missing binding among evidence manifests, configuration hashes, canonical
  runner, physical audit, reporting and readiness gate.
- `REJECT`: OHLC as L2; aggregate trades as public queue; current fee/rule projected
  backward; queue-clear heuristic relabeled calibrated completion; calibration on OOS;
  performance-based selection; unknown cost or latency set to zero; exploratory replay;
  reroll.

## 12. Readiness rule

`READY_FOR_REPLAY=false` until all engineering, evidence, role, estimator, threshold,
capital, runner, reporting, audit, protocol, selection and experiment-manifest gates in
the OWNER directive are complete, source-bound reviewed and published. A protocol hash
does not waive any unresolved field.

`ECONOMIC_REPLAY_RUNS=0`  
`STRATEGY_PASS=false`
