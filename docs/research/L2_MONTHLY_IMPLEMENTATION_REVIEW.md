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
