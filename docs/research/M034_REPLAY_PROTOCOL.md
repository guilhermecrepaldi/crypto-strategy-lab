# M034 Binance-only replay protocol

Status: `REGISTERED_SKELETON_BLOCKED`; this document does not authorize replay.

## Frozen authorities

- Economic venue: Binance only; Kraken is retired before every economic path.
- Source commit containing the current source tree:
  `420c99e825eea9c28a370b8f3f815bad923c60ce`.
- Prior semantic source review: PASS at `4054dfd3d02d2075516e9272a4c03046e5e0e277`.
- Exact post-format source review: independent GPT-6 Astra `PASS` bound to
  `420c99e825eea9c28a370b8f3f815bad923c60ce`; the 64 Python-file delta from
  `4054dfd` is Ruff-format-only and AST-equivalent.
- Pair-universe hash:
  `b9637e30323b9da4885706b805ef7a482616eaab76224cb2b4e105eb1471d66d`.
- Fee-evidence hash:
  `ff25c6ff1b31c202f6b6779f1b0832053f0d9d3906df75a12bd1b6b003fa68da`.
- Exchange-rule evidence hash:
  `ed7b810c5541cdc208ff12f974884d3d3bdba6ad696d6c2124db475e855f73ef`.
- Physical dataset inventory hash:
  `31307132cd9227f6e85d0ac453396d3b679ca0bd9758b9183c77d6c77b81b6fa`.
- Calibration set hash:
  `694752eb0f83ce10315e7cfffdb86dea5601c60ea92373d5821dbfb508f814a0`.
- OOS pool hash: `null` because the independent pool is empty.

These evidence hashes identify the current blocked inventory. They do not make it a
replay dataset.

## Unresolved authorities

`THRESHOLD_CONFIG_HASH=null`
`COMPLETION_ESTIMATOR_HASH=null`
`LOCK_ESTIMATOR_HASH=null`
`ADVERSE_SELECTION_ESTIMATOR_HASH=null`
`EXECUTION_COST_MODEL_HASH=null`
`LATENCY_POLICY_HASH=null`
`INITIAL_CAPITAL=null`
`CAPITAL_CURRENCY=null`
`SLOT_BASE=null`
`WINDOW_SELECTION=null`

Every unresolved field is a hard gate; it is never substituted by zero, an old
campaign value or a test fixture.

## Future runner contract

The canonical runner must perform this single causal flow for each event:

1. read only the registered L2+trade dataset and preserve exchange/capture ordering;
2. reconstruct every physical book and stop at a sequence/data gap;
3. resolve the canonical `VenueRoute` and every physical leg;
4. resolve temporal rules, fees, safety marks, thresholds, estimators, latency and cost
   artifacts at the decision timestamp;
5. apply `EconomicEligibilityGate` before productivity or capital reservation;
6. score eligible candidates once, with safety as a gate and completion probability
   applied once;
7. use `AdaptiveColumnAllocator` under owned-return priority;
8. use `SlotLedger` as the only capital/reservation/fill authority;
9. preserve queue age, epoch and C1/C2; release only after cancel ACK;
10. persist every accept/reject/capital-state event in `EligibilityDecisionLedger`;
11. preserve inventory at cutoff and perform no cosmetic liquidation;
12. stop exactly at `[start,end)` and persist terminal physical state.

No integrated event-loop runner currently satisfies this contract. Source libraries and
synthetic integration tests are not relabeled a replay runner.

## Reporting schema

The future report must emit at least:

- `NET_REALIZED_PNL_PER_CAPITAL_HOUR`, with total registered campaign capital over the
  full window as denominator, including idle and blocked states;
- `GROSS_EDGE`, `NET_EDGE`, `FEE_TO_GROSS_EDGE_RATIO`,
  `ADVERSE_SELECTION_COST`, `EXECUTION_COST`;
- `PHYSICAL_CYCLES`, `SLOT_EQUIVALENT_CYCLES`;
- median/P90/P95 slot turnover;
- capital utilization, idle-capital time and no-eligible-opportunity time;
- inventory residual and carry cost;
- negative-exit count and cost;
- eligibility accept/reject rates and reason distribution;
- capital-state duration distribution.

All amounts declare currency, all bps declare notional base and all durations declare
unit. Physical cycles and loss exits remain disjoint.

## Physical audit protocol

An independent audit must reconcile, from immutable input and event ledgers:

- every fill to one causal public-liquidity consumption and one order reservation;
- maker/taker intent, fee rate, fee asset and fee conversion marks;
- quantity and cost-basis evolution for every inventory lot;
- free, reserved, owned-return, pending-cancel and locked-inventory capital at every
  transition;
- cancel request versus cancel ACK and fills received while cancel is pending;
- absence of self-fill and duplicate trade/fill consumption;
- positive-cycle counts excluding partials and negative exits;
- all negative exits to prior, unexpired ledger authorization and complete physical
  return to the origin asset;
- terminal inventory without forced liquidation or invented conversion;
- exact cutoff, source/config hashes and deterministic report reproduction.

Any mismatch produces `INVALIDATED_TECHNICAL` for the proved affected scope, preserves
the artifact and forbids a silent rerun.

## Failure semantics

- Missing data/rules/fees/config: fail closed before the first economic event.
- Gap during a future run: preserve checkpoint, block fill inference after the gap and
  mark affected scope technically invalid.
- No eligible opportunity: valid economic result with zero slots; do not call it data
  failure.
- Safety block: `BLOCKED_SAFETY`, not idle.
- Data/evidence block: `BLOCKED_DATA`, not idle.
- Technical failure after events: preserve prefix; no rerun under the same consumed gate.
- Economic loss: valid result only if physical audit passes; never technical failure.

## Randomization and window selection

No method is selected because duration/calendar and an economic-eligible OOS pool are
absent. `reports/usdcusdt/M034-window-selection.json` records zero official draws and
zero rerolls. A future CSPRNG draw is legal only after every upstream artifact and the
ordered pool are frozen and hashed. An invalid selected unit is preserved as invalid;
it is not replaced.

## Authorization gate

`RUNNER_STATUS=NOT_IMPLEMENTED`
`READY_FOR_REPLAY=false`
`ECONOMIC_REPLAY_RUNS=0`
`STRATEGY_PASS=false`
