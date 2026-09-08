# M018 — causal passive BUY admission, one-day challenger

STATUS=PREPARED_NOT_REGISTERED_NOT_EXECUTED.
Scientific parent M015; technical ancestor M017; control M017 day1 prefix.
Authority: OWNER_GATED_REPLAY_WINDOW.md, maintained by the coordinator from the
latest OWNER directive. This document does not itself authorize an extension.

## Evidence used to choose this hypothesis

Only the closed first source day2025-01-01 of M017:12 positive ordinary cycles,
operating100.10692, reserve9.99208, total110.099;2546 rejected BUYs,4 canceled
BUYs,13 filled BUYs and1 still ACTIVE. Maximum hold2h+47.867ms. These values
were read from daily/01.json and decoded daily/01-engine-state.json under
artifacts/usdcusdt/l2-monthly-samples/M017/SYNTHETIC_CONSECUTIVE_12D/PRICE_PRIORITY.
No outcomes from days2+ were used to choose this rule or parameters. Those data
are already historically known and are not described as fresh holdout.

The support review already in reports/usdcusdt/B10-execution-research.html,
sections comparacao/adaptacao and sources6/7, distinguishes post-only placement,
cancel/replace latency and loss of priority. Classification: ADAPT passive
placement discipline; BUILD the small B10-specific admission cap; REJECT for this
case queue-credit changes, probabilistic cancellation, OBI/OFI/microprice bundles,
multiple lots and new matching engines. No external code is copied. This is a
testable adaptation, not a claim that the cited projects prove higher profits.

Canonical diagnosis: b10_reality.B10Replay._submit_next submits the selected LOW;
B10Execution._advance rejects a crossing ordinary BUY at activation. The frozen
selection can keep the same LOW despite post-only rejection. The new case addresses
price admissibility, not presumed absence of liquidity or a proven replay bug.

## Single delta and exact causal rule

When flat and about to submit a NEW BUY, use the currently available validated
book and source-day symbol rules. Let L be the original selected LOW, H the original
selected HIGH, A the observed best ask, and tick the current valid price increment.
Submit at P=min(L, floor_to_tick(A−tick)). Require P>0 and all existing price,
quantity/notional and known-level-coverage gates. If book/candidate/coverage is
unavailable, WAIT; never fabricate a level or a fill. If L is already passive,
its price is unchanged. Existing available-bank sizing now uses P normally.

This is placement-time passivity only. Feed/order latency can still produce a
legitimate post-only rejection at activation. Do not suppress that rejection or
assume a fill. Queue is seeded by the unchanged observed execution authority at
activation, not at submission. PRICE_PRIORITY and every trade/depth budget remain
unchanged; a new order never inherits the canceled order's priority.

Keep original candidate and HIGH H for selector state and ordinary SELL target.
Do not shift H downward to preserve a smaller spread, and do not rewrite the
registered range to pretend the original selector chose P. Record original L/H,
admitted P, ask, tick, capture/book identity and reason for every adjusted admission.
Admission price is separate execution state, not a second strategy selector.

An already active or pending order is NOT canceled/repriced merely because the
book changes. Existing candidate-change cancellation still applies. A zero-fill
terminal order may be followed by a newly evaluated placement using the new causal
book. Once a first BUY fill establishes a position, freeze that order's admitted
limit for all partial-entry continuations of the same lot; do not lower the price
again, create DCA, reset inventory, or spend additional lot budget. Clear the frozen
entry price only after canonical settlement; checkpoint it with the existing engine.

All other decisions and economic controls remain M017:100+10 initial, funding10%,
compounding, one serial lot, theoretical H1 cap10bps, protected actual cap20bps,
reserve floor2.5, fee-zero profile, capture clocks and observation-only fills.
Deadline policy hash remains M017's registered88b14751e15093cadc6abbaa9f3e1a70e875ff4e884b1cd911cf7146af494224.
M018 additionally binds entry_admission_policy_hash
3fbb1dd25550f017bafe811a6b6e2a92f33af1df94d9835f8e525aa56aec778a.
The actual runtime model_id must be M018, never a disguised M017 identity.

OWNER's “one hour maximum wait” remains unresolved between simulated holding and
delivery time. This case does not silently reinterpret it: preserve2h with actual
violations reported, and disclose this limitation. A clarified1h holding policy
would require revising the unexecuted preregistration before publication/run, not
changing an executing model.

## Falsifiable risks and gates

Lower P may reduce maker rejections yet make purchase fills slower, or increase
the distance to unchanged H and worsen holding. More trades can increase losses.
The41420 MISSED_BY_QUEUE events on day1 show another bottleneck; this case grants
no cancellation credit to remove it. No guaranteed improvement or1000-cycle
attainability is claimed.

First run scope: only2025-01-01, logical00:00 to next00:00,24h, cold start.
No later source-day data may be loaded for this first run. The spec's source_dates
and calendar_days=3 describe the maximum conditional stage universe, NOT the
current execution window. initial_stage_days=1 is the initial limit. This keeps
model identity fixed for a gated continuation without silently changing policy.
The three declared dates are2025-01-01,2025-02-01,2025-03-01; only the current
OWNER-approved prefix may enter any input verification/history builder.
No forced liquidation at cutoff. Primary target1000 complete NET-positive ordinary
cycles in that day; releases, partials and zero-profit cycles do not count. Report
cycles, operating bank, reserve and total equity to OWNER without new HTML/plots.
Audit also maker rejections, adjusted admissions, entry waiting, open/censored hold,
release losses and actual deadline violations. Compare the same day1 control.

Before execution: explicit current OWNER gate, M018 registered spec/hash, one
canonical runtime/runner, tests, independent source-bound review and publication.
Only the coordinator can initiate the run. A later day2 or day3 requires the
current gated protocol, audited1000 in every preceding day, same model and full
financial/selector/order/book/timer state. No reset or silent tuning. Pursuing2000
after three qualifying days is a later identity returning to day1, not this run.

Acceptance fixtures before source review: already-passive L unchanged; crossing
L clipped to ask−tick on coarse/fine grids; no known book/coverage means WAIT;
no fill at placement or on price touch; activation-time crossing still rejects;
book changes preserve ACTIVE queue/order; zero-fill retries recompute causally;
partial BUY continuation freezes admitted limit; SELL keeps original H; funding,
loss cap, deadline and legacy M015/M016/M017 behavior unchanged. Retain canonical
single-lot financial invariants and all-fill audit; tests are not strategy success.
