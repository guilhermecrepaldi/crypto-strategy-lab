# M016 — protected two-hour deadline, first reserve-rotation experiment

AUTHORITY=RESERVE_ROTATION_OWNER_DIRECTIVE.md
STATUS=PREREGISTERED_NOT_EXECUTED
PARENT=M015; CONTROL=M015_PRICE_PRIORITY_SYNTHETIC_CONSECUTIVE_12D
DATA=the same twelve source dates/order and causal capture clock, no extension.
INITIAL_OPERATING=100; INITIAL_RESERVE=10; TOTAL=110; FUNDING=0.10.

## Observation and question

M015 PRICE_PRIORITY completed12 synthetic days with16 positive ordinary cycles,
equity109.8843,reserve9.76568,5 releases and132.0009854975h maximum hold.
All five releases settled about3.5–3.7 seconds after a release signal. H1 is an
hourly eligibility evaluation, not a timeout. Loss-cap, original/destination
opportunity gates can prevent a signal. Daily marks during the longest hold
exceeded10bps although reserve above the2.5 floor remained available. Individual
hourly veto reasons were not persisted; that historical uncertainty is preserved.

Question: does an explicit protected deadline improve continuity when opportunity
vetoes no longer prevent an emergency exit, without changing funding or the book?
This experiment is not optimization of funding, and not proof of a universal2h exit.

## Frozen M016 contract

Same M007 selection, serial inventory, compounding, PRICE_PRIORITY envelope,
latency, fees, tick/filter assumptions, liquidity budgets, source-day seams and
causal prefix as control. No queue-cap hypothesis, cancellation credit or new venue.
Same normal B10 economic predicate before emergency preparation.

Deadline is first BUY fill+7,200,000,000us, including incomplete buys, retries and
cancel latency. Preparation begins deadline−cancel_latency−2*order_latency−2us,
accounting for the existing cancel-response and later submission/activation clocks.
Emergency latches a protected exit without requiring a different profitable
destination or future recovery opportunities. Keep the bound range until settlement;
resume causal selection using existing hooks. No fill occurs simply because a timer
fires. Depth must remain observed, available and uniquely consumed.

The total executed loss for the serial lot is protected by BOTH10bps of restored
operating bank AND the available reserve above2.5. This explicit executable cap is
stricter than M015's theoretical pre-signal10bps condition; it is part of the new
deadline contract, not a claim of byte-identical release execution.

For this first diagnostic, financial cap/floor are fail-closed and take precedence
over a deadline fill. Inventory remaining strictly after deadline is a violation,
not a valid bounded hold. No grace period, future reset, forced closure or early stop.
Persist preparation, veto reasons, unblock transitions and violations. Late fills
retain actual times. The contract intentionally exposes possible incompatibility
between loss budget and deadline, rather than silently spending more reserve.

Debt/funding state-machine changes are DEFERRED in M016 to isolate the contract.
Funding remains10%, reserve10. FIFO debt/repayment is postprocessed on actual
settlements. NORMAL/RECOVERY/PROTECTION trading gates require a later identity.

## Gates, endpoints and interpretation

Before execution: registered spec bound to this document and canonical policyhash;
tests of timer/cancel/partial/seam/liquidity/floor/cap/default M015; independent
source-bound review; normal GitHub publication; exact12-day evidence preflight.
One model/writer; full288h, no economic early stop; old artifacts never overwritten.

Primary: actual holds>2h, max hold (including censored), daily positive cycles,
total marked equity, operational bank and reserve trajectory. Secondary: debt
recovery counts/times including censored losses, loss budget vetoes, fees/slippage,
buy/position waiting, release costs and full fill audit. Report500/1000/2000 gates.
All fills reconciled by existing audit; test pass != strategy pass.

PASS of software does not authorize scientific promotion. A viable configuration
requires positive total net economics, operational growth, no persistent reserve
erosion and disclosed deadline risks; frequency alone cannot qualify it.

## Limited sequential campaign; not a sweep

At most three successor configurations may be defined in this research tranche,
including M016. Every later one needs its own autopsy, exact preregistration,
identity, implementation tests and published review before execution.

After M016: if protected budget demonstrably prevents deadlines, first document
the loss needed at the deadline before choosing ONE alternative budget. Do not
immediately vary funding, reserve and cap together. If total positive-cycle profits
cannot finance losses even at100% on that path, allocation alone cannot repair it;
do not call a larger reserve an economic solution. Any funding comparison must
execute its own sizing/compounding. Initial reserve redistribution only when
reserve availability is a demonstrated blocker, holding total110 fixed.

If the next step requires an explicit OWNER risk tradeoff beyond these bounds,
report the conflict and ask for that choice; no hidden budget escalation.
No claim of optimal percent or out-of-sample success is allowed.
