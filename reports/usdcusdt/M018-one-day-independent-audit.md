# M018 — independent completed first-day audit

STATUS=PASS_WITH_TRACE_CAVEAT
STRATEGY_PASS=false
DAILY_1000_CYCLE_GATE=NOT_MET
EXTENSION_ALLOWED=false
REVIEW_DATE=2026-09-08
REVIEWER_MODEL=gpt-6-astra
RUNTIME_STATUS=COMPLETE
SCOPE=2025-01-01T00:00:00Z_INCLUSIVE_TO_2025-01-02T00:00:00Z_EXCLUSIVE

## Closed evidence and provenance

Reviewed only the completed M018 OWNER_GATED_DAY1/PRICE_PRIORITY run and M017's
matching first-day prefix. The coordinator reported exit0; a separate process
inspection found no Python run_l2_monthly_samples writer before artifact reads.
Summary, terminal and all-fill-audit were present. No new economic replay,
runtime edit, registry mutation, later-day data analysis or HTML was performed.

Root: `artifacts/usdcusdt/l2-monthly-samples/M018/OWNER_GATED_DAY1/PRICE_PRIORITY`.
The manifest specifies only source2025-01-01, logical start1735689600000000 and
exclusive cutoff1735776000000000. Duration24h;254205 expected and processed
canonical trades. The final boundary seam does not introduce a second source
day's market data. Initial100USDT operating+10reserve, COMPOUNDING,
PRICE_PRIORITY, funding10%, actual cap20bps, floor2.5 and timer2h are unchanged.
No1h policy is implemented or validated by this run.

All14 runtime-source LF hashes matched `git show` of execution source
`65b7fe6aebb91d6c01ee6ef92d90b7c26f84a83c`; current working source was not treated
as proof of historical execution. Registry/spec/preregistration validation
passed with model hash `68e9b01e0f4646319364199fe17970c5c1ec9b22e46c6a498df131ac2f0f43e5`.
Published OWNER authority, preregistration and preflight review hashes match
the run manifest. Recomputing the manifest identity excluding run_hash yields
`219acf9d02fbf954fa4c85342583c047749a87244172a63310441aa2e8279b48`.

| Physical artifact | SHA256 |
| --- | --- |
| run-manifest.json | a0f020dd98b8189a9d61d8a9aa1e87220b49afe3b8ceecbfffb0f03b2997fa96 |
| execution-audit.jsonl | 4bc2f823be46436581869d390f98d78401f19ee6172d329d36825de3ae57a793 |
| all-fill-audit.json | dcf1d9a3a4a2875cb9541e80aa7a20bc67ce276af0013526aa26c6ddcec56eea |
| summary.json | 70c36a2c02980b6ec4d14052b07a18257e78b12f583ea740ab723f34518a2a48 |
| terminal-engine-state.json | 5e177230145cc782e72008a18216cbf437db4a42a9b71d86eb12270a19bde9c5 |
| daily/01.json | 9fcfd4f9e1d1ad25915ce049d804505a56d599a25e33a2013b45b58d43c737ff |

Terminal internal canonical hash recalculated and matched
`8669f4ad267f6d0853829e1fe4fd48a293909ca5b1895807ac2e6cbd19bbb97e`.
Ledger length221145983bytes matches the durable journal binding.

## Fill, admission and accounting checks

The canonical all-fill auditor was reexecuted against the closed ledger after
its function AST was matched to the published execution source. It reproduced
all saved result fields:26fills,12settlements,3releases,
PASS_AUTOMATED_ALL_FILLS. Its seven financial ledger fields match the terminal
exactly. This checks activation, post-only legality, fees, cancellation,
compatible aggressor flow, trade-volume reuse, observed depth consumption and
settlement bookkeeping within the declared execution envelope; it does not
certify real-account time priority or live executable performance.

An independent event pass checked all4 adjusted admissions against their BUY
submission: min(LOW,floor_to_tick(ask-tick)), positive/grid-aligned price,
placement-time passivity, flat inventory, causal capture timestamp and bound
policy hash. Original HIGH was retained. There were31orders,31activations,
zero REJECTION events and6cancellations. BUY outcomes:12filled,3canceled,
1active; SELL outcomes:12filled,3canceled. No counter absence was interpreted
as unknown: zero rejections is established by the complete ledger and states.

Two BUY orders (3 and17) filled in multiple pieces and ultimately completed.
Their subsequent pieces used the same admitted order limit and earliest entry
timestamp. There were no canceled partial-entry continuations in this run;
that branch is supported by preflight fixtures, not claimed as realized here.
The summary's BUY_PARTIAL=0 counts terminal partial orders; COUNTS.BUY_PARTIAL=2
and the two had_partial orders preserve the actual partial-fill evidence.
Terminal passive-entry anchor is cleared after settlement.

Positive ordinary profit totals0.099USDT; losses total0.0495; net0.0495.
Funding0.0099 leaves operating100.0891 and reserve9.9604, total110.0495.
Fees explicitly sum0 under the frozen maker0/taker0 profile. Minimum reserve
9.95347 remains above2.5. Release loss/budget pairs were0.0297/0.2,
0.0198/0.20005346 and0/0.20005346; each fits the20bps budget and floor.

FIFO has2 loss cohorts, neither recovered; a third release was zero-profit
and created no debt. Funding0.0099 pays the first cohort down to0.0198;
the second also remains0.0198. Total debt0.0396; no pre-loss funding surplus.
The2 unresolved cohorts are censored, not recoveries with zero duration.
Independent Decimal funding/loss/debt recurrence matches saved accounting.

Two holds exceeded2h:47.867ms and32.842ms. Maximum hold7200047867us,
2.000013296388889h, was reconstructed from first BUY fill to final settlement.
The ledger contains2DEADLINE_VIOLATION events and summary HOLDS_OVER_2H=2.
The first, ordinary H1 release held3603586718us, about1.001h. These are real
measured violations, not exact compliance obtained by rounding. At cutoff
inventory/dust/cost are zero, but BUY31 remains ACTIVE at1.00190 for99USDC,
unfilled. No artificial cutoff liquidation occurred; no open hold is censored.

## Trace caveat — not a financial invalidation

For adjusted BUY8, book_capture_order=52587 and
book_capture_time_us=1735695046830469 identify the most recent feed capture
(a trade), not the latest book capture. The actual preceding OBSERVED_BOOK is
capture52464/time1735695046739573. Both identify native book update1204134160.
The other3 admissions' capture fields match their preceding OBSERVED_BOOK.

Cause is source-level naming/state selection: observed_capture advances on
trades as well as books; the admission logger labels it book_capture. Actual
ask and native book state are not replaced by that trade. Prices, causal order,
queue and financial execution remain valid, and BUY8 never filled. No
financial failure is converted into a technical invalidation. Published
artifacts and execution SHA remain immutable. A later logging correction must
identify its separate, unexecuted source and must not rewrite this evidence.

## Why12 cycles became9: same-day descriptive autopsy

| Adjusted BUY | Admission and observed outcome |
| --- | --- |
| 3 | LOW1.0023→BUY1.0022, HIGH1.0024. Submitted00:11:02 UTC, filled, then ordinary H1 release01:11:59 loses0.0297. |
| 6 | LOW1.0020→BUY1.0019, HIGH1.0021. Filled and completed01:30:46 for+0.0198. |
| 8 | LOW1.0020→BUY1.0019, HIGH1.0021. Active from01:30 until cancellation around06:31, no fill. |
| 14 | LOW1.0021→BUY1.0019, HIGH1.0022. Filled and deadline-released12:39:20 at zero profit. |

The higher early admitted BUY in M018 enters a different serial position than
M017, whose first BUY was1.0020 and first positive exit00:54:33. After M018's
larger positive exit near01:30, its lower order8 remains unfilled; M017 instead
completes another cycle02:44. After the zero release, M018's next BUY is
submitted12:39; M017's corresponding price1.0019 BUY had been submitted11:16
and completes13:03. Thus the new serial path and changed activation/queue
history matter, even though post-only rejections disappear. This is an
observed path comparison, not a claim that simply deleting a release would
reproduce the control or create counterfactual fills.

| Same first-day metric | M017 | M018 |
| --- | ---: | ---: |
| Complete positive ordinary cycles | 12 | 9 |
| Rejected orders | 2546 | 0 |
| Release count / loss-producing releases | 1 / 1 | 3 / 2 |
| Positive ordinary profit | 0.1188 | 0.099 |
| Reserve consumption | 0.0198 | 0.0495 |
| Operating bank | 100.10692 | 100.0891 |
| Reserve | 9.99208 | 9.9604 |
| Total equity | 110.099 | 110.0495 |
| Pending FIFO debt | 0.01188 | 0.0396 |
| Holds beyond2h | 1 | 2 |

The exact equity difference is-0.0495:0.0198 less positive ordinary profit
plus0.0297 additional realized loss. Working/eligible-order uptime improved
but is not productive uptime. Reducing order rejection did not improve the
primary objective or reserve sustainability on this day. No economic or
causal execution bug was established by this autopsy.9<1000; no promotion,
extension, silent retuning or new replay is authorized by this audit.

## Post-run addendum — trace-only correction, not executed

TRACE_FIX_REVIEW=PASS
TRACE_FIX_EXECUTION_STATUS=NOT_EXECUTED_AFTER_RUN
TRACE_FIX_SOURCE_SHA256_LF=b0b070de14425f37b62aa7b85cc41c28c4de7dbdf739d223b78e5c65213167dd
TRACE_FIX_TEST_SHA256_LF=be39da15f7f1c203389f62c3f9c7ee410b11c0c701fd4dbc32991848cb3f1293

Reviewed the author's subsequent delta to observed_l2_execution.py and
test_m018_passive_admission.py: admission logging now takes book_capture_order
from engine.book_id and book_capture_time_us from engine.last_book_us. In this
CAPTURE_ARRIVAL replay those are the actual book capture, unaffected by a later
trade. The fixture distinguishes exchange90/book capture100/trade capture300
and confirms correct metadata, unchanged passive price, PENDING status and no
fill.64 admission/observed/deadline/cap regressions and Ruff passed independently.

Only logging fields changed; no order, fill, selector, timer or accounting
policy changed. This code was not used for the completed economic run. Its
valid historical source remains65b7fe6, with the trace caveat above. No artifact
was rewritten and no economic replay was repeated. The post-run OWNER pause
likewise does not retroactively change the manifest's published authority hash.
