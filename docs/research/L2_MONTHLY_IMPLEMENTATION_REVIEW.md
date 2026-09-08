# Independent observed-L2 implementation review

Status: CHANGES_REQUIRED_BEFORE_ECONOMICS. Review performed before any economic
monthly replay. Scope: observed_l2_execution.py, its synthetic fixtures, frozen
B10ReserveReplay/HighUptimeExecution consumers, and monthly protocol. This is not
an economic verdict or a review of a completed runner.

## Blocking finding: observed replenishment is suppressed by perpetual debt

ObservedL2Execution.observed_book currently computes available quantity as
max(0, observed absolute quantity - total historical IOC consumption at price).
The debt never changes when the external quantity decreases or disappears.
Synthetic reproduction: consume40 at0.99 from observed40, observe deletion of0.99,
then observe40 newly displayed at0.99. Actual adapter availability remains0,
with debt40. Likewise40 ->20 ->30 after consumption suppresses the observed new10.

The protocol admits new budget from observed positive quantity changes. Preserve
debt for unchanged depth and repeated snapshots, but reconcile debt/remaining
budget against actual per-price decreases and increases. No generic snapshot reset
is authorized. Add delete/re-add and down/up-below-old-high fixtures before execution.
This is conservative distortion, not fabricated liquidity, but it changes the
preregistered execution envelope and can materially suppress recovery.

## Integration conditions

The adapter's inherited WORKING_ORDER_HOURS includes any outstanding order,
including pending/release. It cannot substitute for protocol MOTOR_UPTIME or
capital-weighted ordinary active uptime. The runner must integrate these separately,
retain the inherited metric under its existing name, and include startup idle.

The prefix tape implements every direct tape access currently reached by the M015
selector/recovery path. It does not implement SerialTape.last_price_before, used by
other audit/temporal consumers; do not pass it to those consumers without an
equally bounded implementation. This is not a currently demonstrated M015 crash.

ObservedL2Replay.finish advances timers strictly before the exclusive day cutoff
and integrates to cutoff without forced settlement. Lifecycle callbacks cover book
IOC settlements and ordinary trade settlements. Incoming trades remain hidden from
strategy arrays until settlement callbacks finish; cycle-entry visibility is bounded
by paired cycle exits. Native/capture clocks remain distinct and preactivation or
newer-book print ambiguity suppresses execution while retaining prefix availability.
These examined paths match the stated contract; they do not certify runner inputs.

## Evidence and remaining review

21 observed-adapter synthetic tests pass. An additional read-only synthetic
delete/re-add reproduction confirms the blocking finding above. No real replay was
executed by this review. The final runner, historical rules mapping, daily metric
aggregation and complete source/validation binding require review before economics.

## Follow-up: first IOC correction independently checked

The adapter now restores40 after deletion/re-addition and10 after fully consumed
40 ->20 ->30. Both outcomes were reproduced independently. The consumption audit
correctly records available_before40 and available_after0: the inherited loop
decrements its bid quantity after the overridden fill callback returns. All31
observed-adapter and M014 synthetic fixtures pass at this follow-up.

A remaining conservative-allocation defect was demonstrated using an actual partial
BUY/cancel/release lifecycle: consume30 from displayed40, leaving available10;
then external quantity declines40 ->20. The first correction leaves available10
and reduces debt30 ->10, implicitly assigning the entire decline to already
hypothetically consumed volume. This is unproved cancellation/flow attribution.
The reviewed conservative recurrence is A'=max(0,min(D',A+D'-D)), where A is prior
available quantity and D/D' are prior/new external displayed quantities. It yields
0 in this fixture and admits only subsequent observed positive changes. Root
confirmed this interpretation and assigned the adapter owner its correction/test.
Status remains CHANGES_REQUIRED pending that delta and final runner review.

Performance note: the canonical iterator already supports include_book=False,
retaining ordered changes and complete reconstructed snapshot changes without
copying/sorting full books per message. Any adapter acceleration should reuse that
authority and validate only changed levels after a validated initial snapshot;
preserve exact full-depth access for queue activation and IOC. Benchmark before
changing production execution paths. No native validation source was changed by
this review while the published validation campaign was active.

## Follow-up: conservative recurrence verified

The adapter owner replaced the recurrence with max(0,min(D',A+D'-D)). The same
partial30-of40 release followed by observed40 ->20 now yields available0 in an
independent synthetic reproduction. The earlier replenishment fixtures and31
adapter/M014 tests still pass. The IOC debt findings above are therefore resolved
for the reviewed full-book path. Final status is PENDING_RUNNER_AND_FAST_PATH_REVIEW:
the owner is adding an optimized changed-level path, which is not certified by
the full-book checks. No economic replay approval is implied.

Baseline measurement before acceleration:1000 synthetic full-book messages with
2000 preconstructed Decimal levels took4.332seconds (230.8messages/second), excluding
fixture level construction. This isolates adapter overhead, not end-to-end replay
performance; no historical economics were measured.

## Final delta review: OWNER consecutive12-day sequence

Current recommendation: PASS_CONDITIONAL_PRE_RUN for the source hashes below,
superseding the earlier unresolved-review statuses in this append-only record.
This authorizes no account access or deployment and is not an economic verdict.
Publication, exact approved input rehashing and the runner's normal preflight remain
required before execution. Root owns the separate machine-checked review gate.

The approved source order is exactly2025-01-01,2025-02-01,2025-03-01,2025-04-01,
2025-06-01,2025-08-01,2026-01-01,2026-02-01,2026-03-01,2026-04-01,2026-05-01,
2026-07-01. November remains excluded, regardless of its representation correction.
One100+10 initial treasury is created per envelope and carried through12 logical
days; this is an artificial consecutive stress sequence, not a real-calendar path.

Reviewed mapped source clocks/grid periods, exact selected-archive scope with no
calendar warmup, received-prefix views, both-envelope M015 identity flag, globally
unique capture ordinals, native source-time reconciliation by inverse offset, seam
invalidation, carried active queue and pending orders, persistent constrained IOC
budgets, daily boundary reporting and final all-fill ledger reconciliation. No
additional structural or scientific blocker was found in these reviewed paths.
Cold start happens once; trade tape history contains only the selected12 days.
Seam snapshots cannot replenish previously seen prices beyond retained availability.
Within-day quantity changes follow the corrected conservative recurrence.

Native millisecond book timestamps now expose an upper bound; fills ambiguous
within that interval are suppressed without invalidating the whole day. The
independent auditor checks the book upper bound, ineligible prints, cancellation,
activation, source ownership, quantity, fees and reconstructed treasury/terminal
ledger. Snapshot CAPTURE_BOUND is labeled separately from native exchange precision.

Review-triggered reporting fixes are present:12-day rates and full-stop hours use
actual duration; total return is cumulative/stress return; executable motor and
capital-weighted uptime exclude unavailable-book seam intervals. The inherited
working-order metric remains separate and is no longer double-counted. Daily
checkpoints preserve prior close capital as the next opening capital and remain
PENDING until complete-run audit. No forced terminal settlement is introduced.

Verification:94 synthetic tests passed across test_observed_l2_execution.py,
test_run_l2_monthly_samples.py, test_b10_reserve_weekly.py,
test_tardis_l2_book.py and test_tardis_l2_validation.py. No historical economic replay
was executed during this review. Passing fixtures support these bounded invariants;
runtime all-fill audit and final reconciliation remain separate required evidence.

### Differential data evidence versus published e1525f4

Reference source: e1525f4cd97082f66cd99377c22e9128080064f4, tardis_l2.py loaded directly
from its Git blob. Comparison examined every pre-existing event field, including
capture order, native IDs, trades, full executable levels, sequence flags and changes;
new precision metadata fields were excluded from the equality comparison explicitly.

2025-01-01 first10-minute slice:2364 TRADE +4074 BOOK events; zero differences in
pre-existing fields. Old/new CSV projection7412 rows, identical serialized-row hash
73843f2455305a5cfb4b69cf0f843de3f9fbd0ef4c396142ade5bdacf2e62121.
Normalized batch binding remained PASS,4074 batches, hash
be0b6ea5254f25598f26a242c25ef7404870211e61bfd55feaf00fee40284213.

2026-01-01 first10-minute slice:4561 TRADE +5372 BOOK events; zero differences in
pre-existing fields. Old/new CSV projection11570 rows, identical serialized-row hash
7097dcfff1a0220f49d7744754c6f9d58371bf054cd61a8382398ee8eb1df92e.
Normalized batch binding remained PASS,5372 batches, hash
08327a6de4e627333651b267394374cdf26e03435af6a5b7c8b71d372c2717b7.

Excluded2025-11-01 first10-minute slice:2687 TRADE +4644 BOOK events. Only existing
field difference is snapshot ordinal7 changes731 ->733, retaining the two proven
wire tombstones bid0.988=0 and ask1.022=0. Executable levels, IDs and timestamps are
unchanged. Old projection8547 rows/hash
43e3cc41f6d55d369f29cd126663224ff4a3f1dbfe27399e0d3580850c7766ff;
corrected projection8549 rows/hash
572b0e75605d3b028f5f07db0cb5fb14c87dbc221abdb4fe3ab0b25f1bd36e8b.
Corrected slice binding PASS,4644 batches/hash
7d9c4ba21604dab98405657708880acc2a43d6723b6fd8f06e267ac6c4ada1e1.
This was not a full November audit and does not expand approved execution scope.

The unchanged approved data audits retain their original validator identities.
They are not relabeled as having run against this enriched iterator. Runner rehashes
the pinned original CSV/native/canonical bytes,144 native slices and published old
validator Git blobs before reuse; current execution source provenance is separate.

### Reviewed LF-normalized SHA256

```
scripts/run_l2_monthly_samples.py 214821e53af9d676d21b734a554177885173c411efa8acfeba8dd5a9244ab34e
scripts/validate_tardis_l2_samples.py 6e6d2c799293da4fc6ef5debbf890236fbaa62f7420a047d71f11c532b037f99
scripts/run_high_uptime_recovery.py 4ce00d03fd86d1c4c09db523e6b1c6fd4b6f01edd72899585151a0b8aa2e8186
scripts/run_b10_reality.py 90f6852a773ca678570c2347a95e6caa348f11b30811066155e1b18b96a33ff7
src/crypto_strategy_lab/microstructure/observed_l2_execution.py 5132ecfedfa65a1f0c4925007c48506695cc7eb587158b698e8dbab9a065e701
src/crypto_strategy_lab/microstructure/tardis_l2.py 1899a0b0d968296b2b9d9a6bba8a1f1602e0b34162b4ca4b7ecfdbe665f9490d
src/crypto_strategy_lab/microstructure/high_uptime_recovery.py 2f47b0b1c0f89a73156330f506002a7e64ef75f70ddb1622876053f0251fb489
src/crypto_strategy_lab/microstructure/b10_reality.py 4345ef764299d5414c29a9411fe00e613e02dac542f147e29064cf48b31bd4cb
src/crypto_strategy_lab/microstructure/serial_replay.py 8515862b88842565cfb99295da651521a27eef28290f0e2b0ca742851b924ab0
src/crypto_strategy_lab/microstructure/recovery_reserve.py 0882b2d465ed0fc7c163e00046a5ac5b7127b57f586082d222ac05f9b57c9dd5
src/crypto_strategy_lab/microstructure/data.py b7b19926c7bbcfb91f377228447a2b750c05150de4f2c514b60b6b2d5be4b080
src/crypto_strategy_lab/microstructure/tape_cache.py 7640e20446eb02fb9296ba801605318c11993899e47cbdef38540b08a8d732fb
src/crypto_strategy_lab/microstructure/operator.py 07458aea39284982ed7fe1e08e5527de4ac7dc1acc7d87c2a0bcace1a44d628d
docs/microstructure/L2_MONTHLY_SAMPLE_PROTOCOL.md 59bef2a834afcc334a3e1bc88d6070c2edefda6105cb5fa6020ba35594dd5090
```

### Preparation coverage delta — independent review PASS_CONDITIONAL

GPT-6 Astra independently inspected the runner-only correction after preparation
stopped before economics: shared archive selection requires its lower bound at
or after the manifest's first actual trade (2025-01-01T00:00:00.006766Z).
The runner now clamps only selection/iteration to max(source midnight, that
manifest bound). Logical day origins, exact source offsets, midnight day ends,
full24h denominators, cold initialization and unavailable initial book interval
remain unchanged. No observed trade is removed and no earlier data is introduced.
This is a data-reader boundary correction, not a scientific/strategy change.

Independent verification:21 runner tests PASS, including parameterized0/6766us
first-print regression, exact logical timestamp and second-day boundary checks.
No economic artifacts existed before the fix. Prior hashes above remain evidence
of the earlier review; the following runner hash supersedes only its source line:

```
scripts/run_l2_monthly_samples.py 8933bf36141c5c050aa5fce3ee74c11c7238d110ecf9280119467df27952491a
```
