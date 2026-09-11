# M034 - Binance economic eligibility and productivity

Status: `SOURCE_IMPLEMENTATION_PENDING_SOURCE_BOUND_REVIEW`.

M034 is an incremental admission and allocation layer over the reviewed M032/M033
libraries. It is not a parallel strategy, a replay result or evidence of economic
profitability. The only economic execution venue in this phase is Binance. Kraken
remains implemented, tested and available for future L3 research, but it receives
zero M034 economic slots.

## Phase 0 - verified starting state

Initial repository state on 2026-09-10:

- `HEAD=aafb57ef4203ad2d0c46edacf0df503ec306795e`
- branch `main`, equal to `origin/main`, clean before this implementation;
- no active replay/trainer process;
- M032 reusable architecture review: PASS, replay blocked;
- M033 reusable architecture review: PASS at source `a44831e9...`, replay blocked;
- M032/M033 have no integrated economic multi-book replay runner.

The supplied strategy PDF is historical context at `f903b038...`; it predates the
final M033 corrections and PASS review. This is a documentation-version difference,
not a material conflict with the official M034 prompt.

| Existing component | File | Responsibility/current state | M034 impact |
|---|---|---|---|
| `StablecoinUniverse` | `adaptive_multi_stable_manager.py` | Asset-level M032 safety eligibility | Preserved; M034 adds book-level Binance evidence without replacing it |
| `SlotLedger` | `multi_stable_ledger.py` | Exact free/reserved/owned capital, fill and cancel-ACK lifecycle | Preserved; adds audited risk-reduction settlement that is not a positive cycle |
| `CausalQueueEstimator` | `multi_stable_queue.py` | One PUBLIC/C1/C2 queue and prefix flow | Preserved; completion/lock estimators consume resolved causal history, not a second queue |
| `PairProductivityScorer` | `multi_stable_routing.py` | Legacy M032 score | Preserved; gains a typed M034 path with the new formula |
| `AdaptiveColumnAllocator` | `adaptive_multi_stable_manager.py` | Priority then capital-constrained allocation | Preserved; gains an eligible-only entry point where zero selections are valid |
| route engine | `multi_stable_routing.py`, `multi_venue_models.py` | 2-4 asset route construction/scoring/lifecycle; venue-local routes | Preserved; M034 values only pre-gated candidates |
| capital order manager | `adaptive_multi_stable_manager.py` | Geometry, hotline, safety and ACK-gated reclaim | Preserved; M034 reallocation compares currency values and switching cost first |
| venue adapters | `venue_adapters.py` | Binance L2 and Kraken L2/L3 normalization | Unchanged; economic venue policy is not placed in adapters |
| fee models | `multi_stable_models.py`, `multi_venue_models.py` | Temporal symbol/venue fee values | `VenueFeeProfile` gains evidence/acquisition/source identity; registry is the lookup authority |
| replay engine | none for M032/M033 | No integrated economic runner exists | Not improvised in M034; replay remains blocked |
| reporting/metrics | `reporting.py`, ledgers and published status JSON | Older campaign reports plus turnover/ledger metrics | Decision ledger adds eligibility/rejection and capital-state evidence; runner KPIs remain blocked |
| multi-venue portfolio | `multi_venue_ledger.py` | Independent physical ledgers per venue | Preserved; Binance policy never borrows Kraken capital |
| M033 queue models | `multi_venue_queue.py` | Venue-keyed L2 and Kraken L3 FIFO | Preserved and regression-tested |

## Scope and non-scope

In scope: Binance-only economic admission; temporal fee evidence; threshold
provenance; market/data safety; causal adverse-selection, completion and lock
interfaces; productivity valuation; FIFO-aware reallocation; preregistered negative
inventory reduction; explainable decisions; explicit idle capital; multi-pair Binance
eligibility.

Out of scope: new venues, C3/C4, geometry changes, leverage, perpetuals, funding,
cross-exchange routes, AMMs, yield/treasury, account access, Testnet, live orders,
economic replay, parameter sweeps and claims of profitability.

## Canonical decision flow

```text
causal venue+book snapshot
  -> data / venue / rule / fee / market-safety evidence
  -> EconomicEligibilityGate
  -> eligible candidates only
  -> PairProductivityScorer.score_eligible
  -> AdaptiveColumnAllocator.choose_eligible
  -> ReallocationDecisionEngine when existing FIFO must be canceled
  -> existing SlotLedger reserve/cancel/fill lifecycle
  -> EligibilityDecisionLedger + capital-state record
```

`AVAILABLE != ELIGIBLE`. An empty ranking is valid and produces
`IDLE_NO_ELIGIBLE_OPPORTUNITY` with `SLOTS_AUTHORIZED=0`.

## Venue policy

`ECONOMIC_EXECUTION_VENUES={BINANCE}` is represented by one validated
`EconomicExecutionPolicy`. Any Kraken economic candidate is rejected before ranking
with `VENUE_DISABLED_FOR_ECONOMIC_EXECUTION`; it cannot receive slots or enter M034
economic KPIs. Kraken code, adapters, tests, documents and future research capability
remain intact.

## Temporal fee evidence

`VenuePairFeeRegistry` wraps the M033 `VenueFeeProfile` authority. Each proven record
contains venue+native symbol, maker/taker rates, fee-asset semantics, effective range,
source, source reference, acquisition time, tier/account context, evidence status and
record identity.

Evidence states are `PROVEN_HISTORICAL`, `PROVEN_FORWARD`, `ACCOUNT_SPECIFIC` and
`UNPROVEN`. Historical lookup accepts only a `PROVEN_HISTORICAL` record whose effective
interval covers the decision timestamp. Forward lookup accepts `PROVEN_FORWARD` or a
matching `ACCOUNT_SPECIFIC` record acquired no later than the decision. Missing,
incomplete, ambiguous or inapplicable evidence produces `FEE_UNPROVEN`; it never
becomes zero.

Binance's official Spot documentation exposes current account commission through a
signed, account-specific endpoint and current symbol filters such as `PRICE_FILTER`,
`LOT_SIZE`, `MIN_NOTIONAL` and `NOTIONAL`. These sources support the forward schema;
they do not prove historical rates or historical filters.

## Threshold provenance and configuration hashes

Every instantiated M034 policy must supply all of these thresholds:

| Name | Unit | Function |
|---|---|---|
| `MIN_COMPLETION_PROBABILITY` | ratio | Minimum joint completion probability |
| `MAX_EXPECTED_LOCK_TIME` | seconds | Maximum expected capital lock |
| `RISK_BUFFER` | bps | Explicit economic uncertainty buffer |
| `MAX_INVENTORY_EXPOSURE` | USD | Per-candidate exposure ceiling |
| `PEG_DEVIATION_THRESHOLD` | ratio | Maximum causal peg deviation |
| `MIN_NET_EDGE` | bps | Minimum edge after known costs |
| `TAIL_RISK_BOUND` | USD | Maximum candidate tail-risk charge |
| `MAX_SPREAD` | bps | Maximum acceptable observed spread |
| `MIN_DEPTH` | USD | Minimum causal book depth |
| `MIN_COMPATIBLE_FLOW` | asset/second | Minimum compatible taker flow |

If conservative unknown-cost bounds are selected, both
`UNKNOWN_EXECUTION_COST_BOUND` and `UNKNOWN_ADVERSE_SELECTION_BOUND` in bps are also
mandatory. Each threshold records value, unit, source type, source reference,
derivation, calibration dataset hash when applicable, effective timestamp, frozen
timestamp and the canonical threshold-set SHA-256.

Allowed source types are `OWNER_PREREGISTERED`, `EXTERNAL_ECONOMIC_RULE`,
`TRAINING_DATA_ESTIMATE`, `SAFETY_BOUND` and `PROTOCOL_CONSTANT`. Training estimates
require a dataset hash. One dataset hash cannot be registered as both calibration and
independent OOS validation.

No operational M034 threshold values are authorized or frozen in this source delivery.
Therefore there is no production `configuration_hash`, and economic replay is blocked.
The deterministic tests use explicitly labeled synthetic boundary fixtures only; those
numbers are not economic parameters and cannot be promoted to a replay config.

## Eligibility formula and units

For one candidate, all cost terms below are basis points over `CapitalRequired`:

```text
ExpectedNetEdgeBps = ExpectedGrossEdgeBps
                   - KnownFeesBps
                   - ExpectedExecutionCostBps
                   - AdverseSelectionCostBps
                   - RiskBufferBps
```

The base gate is strict:

```text
ExpectedNetEdgeBps >= MIN_NET_EDGE
```

This implements the prompt's strict gross-edge inequality when `MIN_NET_EDGE > 0`.
Eligibility also requires valid data, enabled venue, acceptable market state, proven
fees, `P_complete >= MIN_COMPLETION_PROBABILITY`, expected lock within its maximum,
inventory exposure within its maximum and tail-risk charge within its bound.

Unknown execution/adverse-selection cost rejects the candidate unless a complete,
pre-registered conservative-bound policy is supplied. `UNKNOWN != ZERO`.

## Productivity formula and units

The gate first converts the net edge to conditional complete PnL in the decision
currency:

```text
ConditionalCompleteNet = CapitalRequired * ExpectedNetEdgeBps / 10,000

ExpectedCycleValue = P(Complete) * ConditionalCompleteNet
                   - (1 - P(Complete)) * ConditionalResidualCost

CapitalHours = CapitalRequired * ExpectedLockSeconds / 3,600

Productivity = (ExpectedCycleValue
                - TailRiskCost
                - InventoryCarryCost) / CapitalHours
```

The numerator uses one decision currency; the result is `1/hour`. Safety is a gate,
not a multiplier. Completion probability is applied once. FIFO value is not in this
formula. Tail, carry, residual and risk-buffer populations/horizons must be disjoint or
their overlap explicitly removed before a replay config can pass review.

## FIFO and reallocation

`FIFOValueEstimator` produces opportunity value in currency. Reallocation uses the
same currency, capital basis and horizon for current and new positions:

```text
Value(New) - Value(Current)
  > LostFIFOValue + CancelCost + ReentryCost
```

Only then may the existing manager request a cancel. The existing ledger remains the
authority: `CANCEL_REQUEST != CAPITAL_FREE`; only `CANCEL_ACK` releases the real
remaining reservation. Queue age, slot epoch, cost basis and reservation identity do
not change retrospectively.

## Inventory reduction and negative exits

A negative exit is never allowed merely to clean inventory or improve a report. The
decision engine requires a time-bounded, hashed, preregistered rule and the strict
currency inequality:

```text
ExpectedHoldLoss + OpportunityCostOfLock + TailRiskIncrease
  > RealizedLossOfExit
```

The resulting authorization binds authorization ID, slot, slot epoch, quantity,
decision/expiry timestamps, rule ID/hash and all inequality terms. `SlotLedger` checks
that binding again at settlement. A loss is recorded in realized PnL,
`NEGATIVE_EXIT_COUNT` and `NEGATIVE_EXIT_COST`; it never increments positive cycles or
the completed-slot turnover numerator. Legacy M032 `close_slot` remains fail-closed.

## Causal estimators

`CausalAdverseSelectionEstimator` uses side-adjusted adverse movement labels only after
their horizon has ended and the label is observable. It returns a non-negative P95 cost
from the resolved training prefix. `CompletionProbabilityEstimator` and
`ExpectedLockTimeEstimator` use resolved outcomes, including censored/non-complete
observations, available by the frozen training cutoff.

Every estimate records estimator version, training cutoff and feature cutoff. Both
cutoffs must be no later than decision time. Existing queue-clear heuristics are not
relabeled as calibrated route-completion probabilities, and leg probabilities are not
multiplied under an unproven independence assumption.

## Safety, data and pair universe

The market gate uses causal PEG, FLOW, DEPTH and SPREAD inputs. A gap rejects. A missing
signal yields `UNKNOWN_MARKET_STATE`; it does not become normal. `DataState` is recorded
separately as `VALID`, `INVALID` or `UNKNOWN`.

`BinancePairUniverse` is book-based and does not hardcode USDCUSDT. A book can be
available while still ineligible. Eligibility requires data, temporal rules, temporal
fees, tick/step/min-notional compliance, safety, liquidity and provenance; the final
fee/rule checks occur again at decision time.

## Decision ledger and reason codes

Every candidate decision stores timestamp, physical book, side/rank/column/route,
intent, gross/fee/execution/adverse/risk/net bps, completion/lock values, carry/tail
costs, fee status, market regime, safety, data state, eligibility, authorized slots,
productivity, policy/threshold hashes and at least one reason code.

Reason codes include:

`ELIGIBLE`, `EDGE_BELOW_MINIMUM`, `FEE_UNPROVEN`, `EXECUTION_COST_UNKNOWN`,
`ADVERSE_SELECTION_UNKNOWN`, `ADVERSE_SELECTION_TOO_HIGH`,
`COMPLETION_PROBABILITY_UNKNOWN`, `COMPLETION_PROBABILITY_TOO_LOW`,
`EXPECTED_LOCK_UNKNOWN`, `EXPECTED_LOCK_TOO_HIGH`, `PEG_RISK`, `ABNORMAL_SPREAD`,
`LIQUIDITY_COLLAPSE`, `COMPATIBLE_FLOW_COLLAPSE`, `DATA_GAP`,
`UNKNOWN_MARKET_STATE`, `VENUE_DISABLED_FOR_ECONOMIC_EXECUTION`,
`CAPITAL_UNAVAILABLE`, `OWNED_RETURN_PRIORITY`, `FIFO_SWITCHING_COST_TOO_HIGH`,
`PRODUCTIVITY_NON_POSITIVE`, `NO_ELIGIBLE_OPPORTUNITY`,
`CAPITAL_RESERVED_OWNED_RETURN`, `CAPITAL_LOCKED_INVENTORY`,
`CAPITAL_PENDING_CANCEL_ACK`, `MARKET_SAFETY_BLOCK`, `DATA_INSUFFICIENT`,
`TAIL_RISK_TOO_HIGH`, `INVENTORY_EXPOSURE_TOO_HIGH`,
`NEGATIVE_EXIT_NOT_ALLOWED_COSMETIC`, `NEGATIVE_EXIT_RISK_RULE_TRIGGERED`,
`INVENTORY_LOCK_EXCEEDED`, `PEG_RISK_ESCALATED` and
`OPPORTUNITY_COST_EXCEEDED`.

Capital-state records use `ACTIVE_NEW_ENTRY`, `ACTIVE_OWNED_RETURN`,
`LOCKED_INVENTORY`, `PENDING_CANCEL_ACK`, `IDLE_NO_ELIGIBLE_OPPORTUNITY`,
`BLOCKED_DATA` and `BLOCKED_SAFETY`. The no-candidate path records idle capital and
`NO_ELIGIBLE_OPPORTUNITY` explicitly.

## Invariants

1. Binance is the only M034 economic venue; Kraken remains dormant and intact.
2. No ineligible candidate reaches productivity ranking or reservation.
3. Zero authorized slots is valid and auditable.
4. `BookKey(venue, native_symbol)` remains the physical identity boundary.
5. Ledgers, queues, balances and obligations never cross venues.
6. C1/C2 and seven ranks remain the maximum geometry.
7. Owned return priority precedes new-entry productivity.
8. Fees/rules are temporal; current evidence is not projected backward.
9. Unknown economic data is never converted to zero.
10. Safety is a gate; probability is applied once; FIFO is a switching cost.
11. All valuation terms declare currency/bps/time units and use `Decimal`.
12. Fills and public liquidity are consumed once; estimators never create fills.
13. Cancel capital releases only on ACK; partial/filled obligations remain owned.
14. Negative inventory reduction requires a bound authorization and is never a cycle.
15. Calibration data cannot be relabeled independent validation.
16. Future events cannot change a past decision.
17. Tests/source pass never imply strategy, replay or live pass.

## KPIs and capital time

The future integrated runner must report `NET_REALIZED_PNL_PER_CAPITAL_HOUR` with a
pre-registered denominator, plus every KPI and capital state required by the OWNER
prompt. This source layer already exposes decision acceptance/rejection counts, reason
distribution, authorized slots, explicit idle events, slot turnover and negative-exit
count/cost. Physical cycles, slot-equivalent cycles, utilization, state durations,
edge/cost aggregates and inventory residual remain runner responsibilities and are not
fabricated without an integrated replay.

## Replay gates and current blockers

`READY_FOR_REPLAY=false`. No replay may begin until all of these are frozen, reviewed,
registered and published before the first event: M034 source-bound PASS; Binance pair
universe; historical L2+trades continuity and hashes; historical rules; historical fee
records for every leg/tier; latency/execution/adverse-selection policy; safety and all
threshold values; threshold/configuration hashes; calibration/OOS roles; endowment and
slot base; model identity; window/CSPRNG result; replay protocol; integrated runner and
physical audit/reporting path.

Current blockers are the absence of operational threshold/configuration values,
historical Binance fee evidence for a selected interval and pair universe, selected
dataset/window, calibrated causal completion/lock/adverse estimates, proven execution
cost/latency policy, registered model identity, integrated runner and replay protocol.

No account, key, Testnet, live order, replay, random window draw or registry mutation is
authorized by this source implementation.

`M034_SOURCE_ARCHITECTURE_PASS != M034_STRATEGY_PASS`.

