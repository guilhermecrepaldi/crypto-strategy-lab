# L2 MONTHLY SAMPLE JOURNAL

## 2026-09-08 — autorização e preparação

CAMPAIGN=USDCUSDT_L2_MONTHLY_SAMPLES
STATUS=DATA_ACQUISITION_PREPARATION
L2_CANDIDATE_DATES=21
STRATEGY_MODEL_USED=M015
MODEL_HASH=4231670b19b1ca5c2b5032b1476b83b3182d1463750ea944da5efb867d81a8fa
REPLAY_MODE=INDEPENDENT_24H
OPERATING_INITIAL=100
RESERVE_INITIAL=10
CAPITAL_MODE=COMPOUNDING_WITHIN_DAY
START_STATE=FLAT
QUEUE_MODEL=OBSERVED_L2
ECONOMIC_REPLAYS_STARTED=0
WEEK_2_CONTINUOUS_AUTHORIZED=false

OWNER directive preserved in docs/microstructure/L2_MONTHLY_SAMPLE_OWNER_DIRECTIVE.md.
Registry and CURRENT_STATE agree on M015; no later model or running replay found.
M015's completed weekly artifacts/model remain unchanged. This is a new execution
evidence battery, not a new strategy or continuous compounding path.

Research-first: ADOPT official Tardis data contracts; ADAPT existing acquisition,
book validation and M015 execution authorities; REJECT CSV row numbers as exchange
update IDs, synthetic queue/depth where observed, and inter-month capital carry.

Official sources rechecked through agent-reach/Jina, with direct-document verification:

- [Binance capture](https://docs.tardis.dev/historical-data-details/binance): WS depth,
  REST initial snapshots, provider checks U/u, first-day free access.
- [CSV contract](https://docs.tardis.dev/downloadable-csv-files/data-types): absolute
  amounts, zero deletes, snapshot resets and local-timestamp message batches.
- [Native API](https://docs.tardis.dev/api/http-api-reference): native messages,
  capture ordering and blank disconnect markers; free monthly first-day slices.

Normalized CSV does not expose U/u/lastUpdateId. Independent sequence validation
requires native depth/snapshot sidecars; provider attestation alone is not a local
PASS. Investigate public raw access, without keys or bypass. No fill results yet.

Scientific protocol/review: GPT-6 Astra. Mechanical acquisition: GPT-5.6 Luna.
Python performs validation/accounting; TEST_SUITE_PASS != STRATEGY_PASS.

## CSV acquisition completed — native validation next

L2_CANDIDATE_DATES=21
L2_AVAILABLE_FREE=21
L2_UNAVAILABLE=0
CSV_TOTAL_BYTES=207733908
CSV_TOTAL_ROWS=22143325
GZIP_AND_SCHEMA_PASS=21
INTEGRITY_PASS=PENDING_NATIVE_SEQUENCE_AND_TRADE_RECONCILIATION
STRATEGY_MODEL_USED=M015
REPLAY_MODE=INDEPENDENT_24H
QUEUE_MODEL=OBSERVED_L2
CSV_ACQUISITION_SOURCE_COMMIT=b46e2123ac1386abba65098c21ebccc5bb9b9403
ECONOMIC_REPLAYS_STARTED=0

All21 HTTP responses200; original files remain local and immutable. January2025
observable book validation:828955rows, zero crossed batches or capture regressions.
First snapshot arrives9.412998s after midnight; startup remains FLAT/idle until
valid bridging snapshot, never an invented opening book. Raw native probe200 for
Jan2026 confirms free ten-minute depth/snapshot/trade slices with U/u. Acquire all
144 slices perday to validate native continuity and capture ordering independently.
Native and CSV data retain separate provenance; this is not yet economic approval.

## Arrival ordering and acquisition persistence review

Before any economic outcome, scientific review froze CAPTURE_ARRIVAL_CLOCK for
timers and prefix-limited selector history. Native millisecond/microsecond precision
is preserved separately. This prevents an earlier-exchange print arriving later
from borrowing a future book or being rejected merely because streams interleave.
Full details remain in the single protocol authority.

Native files progressed beyond the incremental manifest (481 recorded slices at
the observed checkpoint). Investigating a persistence exception while executor
workers continue. Original files are preserved; unrecorded originals will require
source/hash verification, not provenance inferred from filenames. Repair must
include durable per-slice metadata and bounded Windows atomic-replace retries.
This is a DATA_PIPELINE issue, not a strategy loss or failed economic experiment.

Reported cycles and PNL remain null until a valid, bound replay exists. The new
scoreboard/report exposes all21 dates and both envelopes, split2025/2026, without
counting unexecuted days as zero-cycle failures or concatenating capital.

## Confirmed persistence fault and recovery preregistration

Old native collector ended exit1 with PermissionError/WinError5 on atomic manifest
replacement. All3024 original slice files exist, but only481 records were persisted.
The executor had drained pending downloads before reporting its main-thread error.
No market original was deleted or changed; no economic replay started.

Repair adds bounded atomic-write retries, pending-future cancellation, per-slice
metadata and explicit orphan verification. Existing hash/provenance-bound records
reuse original bytes. Unknown originals require a fresh public response with equal
SHA/bytes and verified HTTP slice headers; original download time remains UNKNOWN.
Mismatch is INVALID and preserves both payloads. Fourteen acquisition tests pass,
including writer failure, HTTP/hash recovery and sidecar-only recovery.

Read-only full January2025 diagnostic independently reconciled all828955 CSV rows
and254205 canonical trades; native sequence had zero gaps/crossings/disconnects.
This is a data diagnostic, not strategy performance. Before economics, review also
identified an IOC replenishment implementation defect; repair/testing required.
2025 calibration uses explicitly conditional transfer of frozen profile rules,
with the canonical historical tick catalog; no assertion of historical account fees.

## Native recovery complete; full monthly validation

Recovery finished exit0. All3024 expected native slices are provenance/hash-bound:
481 originals reused,2543 originals matched fresh public responses byte-for-byte.
No mismatch, no authentication bypass, no original overwritten. Native564101798bytes;
CSV+native771835706bytes. Original download and recovery execution SHAs are explicit
in the manifest. Every recovered original has unknown original download time and
known verification time; no timestamp was invented.

First three complete day validations (Jan/Feb/Mar2025) passed all data gates under
published c5f57488822ab9beaaf363cfb6ef136f9ffb8955. Their source caches remain preserved.
For the full battery, replace the CPU ThreadPool with bounded3 ProcessPool workers;
the validator function/criteria are unchanged. Synthetic serial/process transport
equivalence and all38 data/report tests pass. Source identity changes explicitly,
so full campaign validation rebinds under the newly published validator rather
than silently reusing results with an old implementation hash.

Independent review tightened hypothetical IOC budget decreases before economics:
both observed negative and positive quantity deltas affect remaining availability.
No cancellation credit reaches the resting-order queue. Review also measured
full-book repeated validation cost; an equivalent incremental execution path is
being reviewed. Economic replays remain0, financial/cycle outcomes unavailable.

## OWNER override — consecutive12-day compounding sequence

Full21-day validation finished under e1525f4 validator sources:12 passed all gates,
9 blocked (8 have disconnects; Nov2025 has a snapshot normalization mismatch).
Report and originals preserved. No independent-day economics were started.

OWNER explicitly superseded independent resets, first asking for consecutive days
with maintained strategy/compounding, then authorizing exactly the12 already-valid
days while the others remain in preparation. Selection is now frozen to
Jan/Feb/Mar/Apr/Jun/Aug2025 and Jan/Feb/Mar/Apr/May/Jul2026, each source day1.

STUDY=SYNTHETIC_CONSECUTIVE_12D
STRATEGY_MODEL_USED=M015
INITIAL_OPERATING=100_ONCE_PER_ENVELOPE
INITIAL_RESERVE=10_ONCE_PER_ENVELOPE
FINANCIAL_STATE_CARRIED=true
ECONOMIC_REPLAYS_STARTED=0
STATUS=CONSECUTIVE_PREFLIGHT_IMPLEMENTATION

The compressed path is deliberately artificial stress, not continuous historical
monthly returns. Preserve original clocks/IDs and explicit mappings, positions,
orders, queues and timers. No invented seam fills or daily capital resets. Source
year is provenance, not independent calibration/evaluation after state is carried.
Other data preparations cannot silently add a13th day. OWNER directive and revised
protocol are canonical; existing registry/model/profile stay frozen.

Independent review identified Nov2025's two zero snapshot tombstones as a validator
representation defect: raw REST+buffer deletes reconcile exactly; executable book
levels were already correct. Fix pending publication/full Novvalidation, outside
the frozen12-day run. Additional execution precision metadata suppresses ambiguous
millisecond fills; first-slice old/new comparisons preserve every pre-existing field
and CSV hash for Jan2025/Jan2026. Data validation under e152 retains its provenance;
new execution sources remain separately bound, never relabeled as the old validator.

## 2026-09-08 — Twelve-day preflight approved for publication and start

Independent GPT-6 Astra review and root source-hash reconciliation completed.
104 focused acquisition/data/report/execution tests and9 frozen B10 weekly tests
passed; Ruff passed. TEST_SUITE_PASS != STRATEGY_PASS. Runtime all-fill audit and
terminal financial reconciliation are still pending, with no economic replay yet.
The published preflight binds the exact12 source days, M015, both independent
execution envelopes, carried100+10 initial capital and all reviewed source hashes.
Next action: publish this milestone, verify HEAD equals origin/main, then execute
the canonical runner. No parameter changes or automatic thirteenth source day.

## 2026-09-08 — Preparation boundary failure, no economic replay

Published source f2490e3b5a474f568909e16b0f7c24d65366fd6b passed campaign
preflight/data bindings but stopped in archive selection before creating any
economic output. Root cause: source midnight preceded the manifest's first actual
trade at2025-01-01T00:00:00.006766Z; the shared validated-history reader correctly
rejected that coverage request. This is a loader boundary bug, not strategy loss.
Read start now clamps to the first actual validated event, leaving logical midnight,
source offsets, day end, cold start, capital, strategy and profiles unchanged.
Regression covers both exact-midnight and6766us first prints;21 runner tests and
Ruff pass. Independent Astra delta review and refreshed source binding precede retry.

## 2026-09-08 — Economic replay started, first conservative prefix

RUN_STATUS=RUNNING; VERDICT=PENDING.
Published execution source9e176dd1d16969c37accbbba36fd763e67ffdde2 passed all
preflight gates. CONSERVATIVE_QUEUE run hash:
2b17e45fb88cb97250c4bcb87ea8db824afc30045eb687ff2e402f8f4750dfc1.
The canonical runner loaded4535834 trades from exactly the12 approved source days.
One writer processes CONSERVATIVE_QUEUE first, then PRICE_PRIORITY independently.
The first durable50000-event checkpoint reached logical2025-01-01T01:25:37.939332Z:
1 positive ordinary cycle, operating ledger100.00891 USDT, reserve10.00099 USDT.
No completed day or final audit yet. This is not a daily-cycle target verdict or
mark-to-market return; daily reports use observed-bid marked equity at closed days.
The report now exposes partial cycles/ledger/reserve while daily cells remain absent
until their checkpoint. Six reporter tests pass. Reporting commits never replace
the execution source SHA embedded in the immutable run manifest.

## 2026-09-08 — First synthetic day closed; day2 running

CONSERVATIVE_QUEUE completed logical day1 (source2025-01-01) and carried its
unchanged financial/order state into logical day2 (source2025-02-01).
DAY_1_ORDINARY_FULL_FILL_CYCLES=8
DAY_1_NET_POSITIVE_CYCLES=8
OPERATING_FINAL=100.07128_USDT
RESERVE_FINAL=9.98812_USDT
TOTAL_EQUITY_FINAL=110.05940_USDT
DAY_1_NET_PNL=+0.05940_USDT
MAX_HOLD_HOURS=3.0010133033333333
MOTOR_UPTIME=0.9967923368865741
OPEN_POSITION_AT_DAY_CLOSE=false
RUN_STATUS=RUNNING; VERDICT=PENDING; RUNTIME_ALL_FILL_AUDIT=PENDING.
The observed first day is below500 cycles, not strategy approval. Continue all12
approved days with frozen M015 and compounding; no tuning or daily reset.
PRICE_PRIORITY remains queued behind the first complete trajectory.

## 2026-09-08 — OWNER-requested external execution research, no replay changes

Delivered reports/usdcusdt/B10-execution-research.html: standalone Portuguese HTML
with first-day evidence, primary-source comparisons, similar reported cases,
source commits, reuse/licensing notes and prioritized research gates. Independent
GPT-6 Astra scientific review PASS; browser QA at1440x1000 and390x844, navigation
and anchors checked, no page overflow or console errors after favicon correction.

Key finding: HftBacktest RiskAdverseQueueModel::depth at5f3ec40 caps ahead volume
to new displayed depth; our frozen ordinary queue does not. Separately, its exchange
fill rules admit price-through evidence while our CONSERVATIVE_QUEUE disables it.
These are modeling differences, not proof of a technical defect or actual fills.
Proposed next diagnostic: intraday time with ahead above displayed, vanished levels
and subsequent prints, excluding seams/unknown coverage. No synthetic fill credit,
parameter optimization, source patch or strategy change was authorized or executed.

The HTML separates observed data from queue inference, software validation from
strategy outcome, and synthetic stress from real historical returns. It does not
claim any external project achieved500/2000 cycles under our identical conditions.
External research used GitHub CLI, Jina Reader and available web search; Exa was
not configured and agent-reach executable/update-check was unavailable. No external
trading package was installed or used to execute economic simulations.

## 2026-09-08 — Deeper exchange/repository research and local adaptation feasibility

Extended the SAME reports/usdcusdt/B10-execution-research.html at OWNER request.
Added Coinbase Exchange, Kraken Spot, Bybit V5 and dated OKX feed contracts;
PythonMatchingEngine, cryptofeed and LEAN; source-pinned code, licensing and
reported bootstrap/coverage cases. GitHub API state was checked separately from
cached search: cryptofeed issues604/1082 CLOSED, PR606 MERGED on2021-10-09.
Those states do not establish a universally corrected or locally reproduced case.

Independent GPT-6 Astra review: adaptation fits existing authorities, no second
backend required; final scientific delta review PASS. Candidate queue cap is a
NEW EXECUTION HYPOTHESIS, not an unannounced fix to frozen M015. Probabilistic
cancellation requires trade/depth reconciliation and explicit ambiguity; repricing
or changed admission requires new Mn. Eight proposed acceptance fixtures are
listed separately from tests actually run. No claim of500/2000 cycles achieved.

Read-only synthetic diagnostic executed in memory using helpers engine/batch/trade
from tests/test_observed_l2_execution.py, envelope CONSERVATIVE_QUEUE:
- batch(t=1,order=2,bids=[(1,100),(.99,100)]); submit BUY at1 at t=1;
- batch(t=12,order=3,same bids): activated queue100;
- batch(t=13,order=4,bids=[(1,40),(.99,100)]): queue100, inventory0;
- trade(t=14,order=5,quantity50,price1,buyer=True): queue50, inventory0.
No historical data were loaded. The alternative cap40 then up-to10 fill example
is explanatory arithmetic, NOT an implemented or Binance-validated fill result.
Command: .venv/Scripts/python.exe -m pytest tests/test_observed_l2_execution.py -q
SOFTWARE_VALIDATION:27 passed,0 failed. TEST_SUITE_PASS != STRATEGY_PASS.

Document distinctions: Kraken L3 authentication remains out of scope; Coinbase L3
is not historical Binance calibration; Bybit standard book excludes RPI; OKX
checksum deprecation is channel/date-specific, not grounds to bypass Binance
validation. PythonMatchingEngine historical-price impact transformation is
incompatible with the current immutable tape. cryptofeed LICENSE at39ff878 is
AGPL-3.0-or-later with added attribution, not assumed permissive. No external
trading library was copied, installed or executed, and no security audit is claimed.

HTML browser checks:1440x1000 and390x844;11 sections, no broken hash anchors,
zero scripts and no page overflow; console0 errors/0 warnings. Existing economic
reference remains the closed FIRST synthetic day, explicitly not a live scoreboard.
This milestone changes only the report and append-only journal. Frozen execution,
profiles, parameters, financial state, existing artifacts and active runner untouched.

## 2026-09-08 — Reserve/rotation autopsy and M016 pre-execution milestone

New OWNER authority: docs/microstructure/RESERVE_ROTATION_OWNER_DIRECTIVE.md.
Reconciled BOTH physical COMPLETE summaries, all-fill audits and terminal state
hashes. Prior progress.json files remain stale PENDING and are not terminal truth.
No historical ledger or published result was changed. Twelve synthetic days only.

M015 CONSERVATIVE_QUEUE:17 positive ordinary cycles; equity109.9764;
operating cost bank100.13608, marked operating100.21108; reserve9.76532;
five releases consuming0.2498; funding0.01512; maximum hold27.1199001464h;
eleven positions above2h including censored exposure. PRICE_PRIORITY:16 cycles;
equity109.8843; operating100.11862; reserve9.76568; five releases consuming0.2475;
funding0.01318; maximum hold132.0009854975h; six positions above2h.
Fees zero are a frozen profile assumption, not a current exchange fee claim.

Root cause evidence: H1 was hourly eligibility, not a holding timeout. The longest
hold had reserve above the floor but daily marked loss above the10bps signal cap.
Only five release signals were emitted, followed by settlement about3.5–3.7s later.
Old per-hour veto reasons are unavailable; no fabricated retrospective attribution.
Low cycles additionally involve admission, buy/sell waiting and execution assumptions.

New reserve_recovery_diagnostics is postprocessing only: exact Decimal FIFO debt,
actual contribution sequence, no double payment, retained surplus and censored debt.
At hypothetical80% on the SAME PRICE_PRIORITY fills only1/5 releases repays;
first repayment takes3 cycles and3.835781964h; final debt0.2173.
Changing accounting does not change109.8843 total equity or demonstrate a new
compounding strategy. Even100% allocation cannot finance all losses on that path.
HTML and JSON show all funding sensitivities as FROZEN_FILL_ACCOUNTING_ONLY.

M016 registered CREATED, not executed at this milestone:
MODEL_HASH=4f582f23ea4f6e09eefbeceaa70a60f5a5013129a57e6628a6a7916f112bdaed.
Same100+10,10% funding and PRICE_PRIORITY. New isolated protected deadline removes
opportunity veto in emergency and binds actual whole-lot loss to10bps and floor2.5.
Time violations remain violations if budget/liquidity cannot close exposure.
Debt trading states and funding optimization are deferred, not silently implemented.
At most three sequential registered cases; no new dates or live access.

Scientific implementation: GPT-6 Astra; pure debt diagnostic: GPT-5.6 Luna.
Separate GPT-6 Astra reviewer found a stale liquidity-veto cache in the NEW M016
path: zero-budget best bid hid replenishment below. Corrected before any economic
run, with regression; this does not invalidate old M015 evidence by itself.
Source-bound independent preflight review is a mandatory separate artifact.
Software validation never means strategy approval. M016 economic verdict PENDING.

Existing canonical HTML now includes twelve-day autopsy, daily cycle bars,
funding/recovery tables and unrecovered cases. Browser visual checks desktop1440x1000
and mobile390x844; no external chart dependency. Full comparison remains pending
the actual successor replay. No optimal funding percentage has been selected.

## 2026-09-08 — M016 launched from published source

SOURCE_SHA=44d75f9183aa052be20734fac0f244bc4ba238bd
PHYSICAL_RUN_HASH=0b4f726bfa4724009a9d37c07c078976a77179dd82cb09ae98871254307fad5a
REGISTRY_RUN_HASH=d753560ef93ea5598fbdcf5c17a538932a5a4b7716ba8262840ff33a9e7b024b
The registry entry binds the canonical monthly runner's unchanged physical run
hash/manifest; these are explicitly different provenance hashes, not a substituted
execution identity. Source was published and clean before the preflight.

Command: .venv/Scripts/python.exe -m scripts.run_l2_monthly_samples --model M016
An initial direct-file invocation failed to import scripts before preflight or any
economic output; correct module invocation uses the existing package workflow.
Bound input revalidation completed and4,535,834 canonical trades were selected
only from the approved12 source dates. One writer, no additional market/history.
Model registry now RUNNING. Economic VERDICT=PENDING; immutable physical daily
checkpoints and terminal audit, when produced, determine progress and results.
Journal/reporting commits do not replace the execution SOURCE_SHA above.

### M016 day1 checkpoint — partial economic evidence, not final approval

Source day2025-01-01, logical day1/12 closed; progress8.3333%.
Positive complete cycles12; operating100→100.10692; reserve10→9.99208;
marked equity110→110.099; net+0.099USDT. One release consumed0.0198;
positive-cycle funding0.01188. Exposure closed at cutoff. Maximum hold
2.0000132964h: deadline exceeded by47.867milliseconds and explicitly counted.
M015 PRICE_PRIORITY same day also12 cycles/equity110.099 but maximum hold3.001h.
This checkpoint improves maximum holding, NOT cycle count or economics so far.
Full-run and all-fill terminal audits pending; VERDICT=PENDING.

### M016 deadlineD2 autopsy — cause isolated, trajectory still partial

Read-only source-prefix reconstruction and separate GPT-6 Astra reproduction:
reports/usdcusdt/M016-deadline-autopsy.md. At source2025-02-01T02:00:10.349574Z,
99USDC fit in the observed remaining bid budget at1.0002. Conditional proceeds
99.0198 against cost99.1881 imply loss0.1683(16.81202458bps), whereas cap10bps
allowed0.10010692 and reserve above floor was7.49208. The logged veto is LOSS_CAP.
Native update1255530829; book age10.502ms; available quantity13,707,359USDC.
Independent audit reproduced48,908 BOOK batches, original hashes and checkpoint
bindings; confirmed five BUY fills and no IOC consumption before this deadline.
This is conditional depth cost, NOT an actual fill or a guaranteed alternative exit.

Closed logical days2/3/4 had zero new ordinary positive cycles. Cumulative marked
equity109.9307/109.9406/109.901; reserve9.99208 unchanged. At day4 close open
position age71.997125h. M016 exposes the incompatible cap/time objectives but does
not yet meet the2h objective. Funding or extra reserve alone cannot remove this
specific cap veto. No parameter changed during the run; successor not selected.

## 2026-09-08 — M016 full12D closed and independently audited

Source44d75f9, physicalrun0b4f726b unchanged; writerEXIT0. No economic early stop.
Independent audit: reports/usdcusdt/M016-completed-independent-audit.md.
78fills/27settlements=19positive ordinary cycles+8releases(7loss/1zero).
Daily cycles[12,0,0,0,0,0,0,0,0,1,3,3]; min0/median0/max12;8zero days;
all12 below500/1000/2000. Operating100→100.12132, reserve10→9.78068,
equity110→109.902; netrealized−0.098, unrealized0, fees0assumption, terminalFLAT.
Funding0.01348, consumption0.2328, mean release cost0.0291 acrossALL8releases.
Independent FIFO debt0.22328,0/7loss tranches recovered; no invented recovery
median/time. Minimum reserve9.78028. Eight holds>2h, max119.997830754h.
All release deficits within actual10bps cap and floor2.5. Fullledger hash and
14 publishedsource hashes verified independently. TEST_SUITE_PASS != STRATEGY_PASS.

Versus M015 same PRICE_PRIORITY12D:19vs16cycles, equity109.902vs109.8843,
consumption0.2328vs0.2475; maxhold119.9978vs132.001h, but2hviolations8vs6.
Modest improvements do not establish sustainability, high frequency or bounded
holding.145.005973h FLAT and170,975 BUY orders withzero fill reveal an additional
admission/execution bottleneck; zero-fill orders are not all presumed rejections.

Model registry EVALUATED thenREJECTED for OWNER objectives, evidence preserved.
Evaluation hashdfb96a4f59df2b06b05fdaccf9121926a13b24adfb9bd1365f5150c3101fb4c9.
Scientific recommendation: ONE registered20bps executable-cap test next, because
the reconstructed D2 deadline cost16.812bps exceeded10 while liquidity/floor did
not bind. Keep H1theoretical10, funding10%,100+10 and all execution/data unchanged.
M015 is scientific parent; M016 is paired control/technical ancestor, not champion.
M017 preparation is not an execution approval before source-bound review/publication.

## 2026-09-08 — M017 registered and independently reviewed; not yet run

MODEL_HASH=b82a5ef829ca396db0f80885807aa4895ec359db3f10d7e917d6e8be0db65af8.
Canonical registry CREATED binds spec d9afab40660e73c56f68601d4617dd76f7d5abb5dd5d2de94e447e387f977e20
and preregistration467cc497c78986780c23e427d2ef04ec522bba8cc5f79071f0448b8ee48b3d20.
Independent GPT-6 Astra review PASS_CONDITIONAL_PRE_RUN binds14 sources;102
focused tests passed. This is software/design validation, not economic success.
Only executable protected cap10→20bps changes; unchanged H1 theoretical10,
funding10%,100+10, floor2.5, serial compounding, PRICE_PRIORITY and same12days.
Publication and exact-data/clean-source preflight remain required before replay.
This is second case of maximum-three tranche; no third case selected or executed.

## 2026-09-08 — entry autopsy and comparative report reconciled

M016-entry-autopsy.md independently reproduced:170975 zero-fill BUYs comprise
170964 LIMIT_MAKER_WOULD_TAKE rejections,10 cancellations and1 terminal active BUY.
Largest unchanged-price rejection sequence43849 attempts over14.366954h.
This is demonstrated selector/admission/retry incompatibility, not proof of an
invalid replay or of the fills another entry policy would produce. Terminal FLAT
means inventory zero, not absence of a working BUY. Existing results stay intact.

Canonical B10-execution-research.html now compares completed M015/M016 with
daily cycles/equity/reserve SVG charts, owner headline and expandable full metrics.
Financial reporter independently reviewed at17225a...; subsequent presentation-only
delta reviewed by main,18 reporting/debt tests PASS. Final reporter LF SHA
a7bfc9d396554583c949e8c0c7968d33454509203a8b3dff380a687d2e8d12ae.
Browser QA via Playwright at1440x1000 and390x844:3 comparison charts,0 broken
local anchors, no document horizontal overflow,0 console errors/warnings.
HTTP local preview verified; tool blocks file-protocol navigation, so no claim
of direct-file browser QA. HTML embeds its charts without script/CDN dependency.
Funding sensitivity remains frozen-fill diagnostics, not extra economic replays.

## 2026-09-08 — M017 running; first closed day

Executed source=b5379f6fee40e33334e3d3cc32f14f42d5c0cf85; physical run
7f55d29131f0e4e8cfdce00594553c48994dbe85ca4262f4a1ddf596fd84585c.
Registry runad0bf7dbbbb21464ca27d78d12dc029e9369e165829904bc8cb93c5bc9f41458
links the unchanged physical manifest; scenario49e8e9bb4dd39e41a668c8c5308345184740e2078f99908782b415bce8237e61.
Canonical clean/published-source, review and exact-data preflight passed before
the process started. Registry RUNNING. Reporting commits do not change run SHA.

Closed prefix day1/12:12 positive cycles, operating100.10692, reserve9.99208,
equity110.099, net+0.099.13 settlements include1 release costing0.0198.
Funding0.01188, debt payments0.00792, surplus0.00396, remaining debt0.01188.
0/1 loss recovered;8 positive cycles after that loss did not yet repay it at10%.
One >2h hold:2.000013296389h (47.867ms excess); no grace applied.
Same-prefix M016 has the same day1 economics. No full-history comparison or
strategy approval. RUN_STATUS=RUNNING; VERDICT=PENDING. Final all-fill audit pending.

## 2026-09-08 — M017 day2: long control hold avoided, economics still negative

Same-prefix two closed days, source b5379f6 unchanged. Positive cycles[12,3],
cumulative15; operating100.13392, reserve9.80678, marked equity109.94070,
realized/net−0.05930, flat inventory at closed prefix.18 settlements include3
loss releases totaling0.20810 (mean0.0693666667). Contributions0.01488;
FIFO debt0.19718;0/3 losses recovered. Three strict2h violations, maximum hold
2.000024801111h (89.284ms excess). Fees0 remains frozen profile assumption.

The D2 control position actually released at loss0.1683 in M017, within cap20;
the earlier observed-cost diagnostic did not itself count as this fill. M016 at
the same D2 cutoff had12 positive cycles, an open position, marked equity109.93070
and reserve9.99208. M017 has3 additional positive cycles and+0.01000 marked equity
relative to that prefix, but a lower reserve after realizing losses. This is not
a comparison of realized-only PnL across different inventory states. Both total
equities remain below110. No optimal funding or final strategy approval follows.
RUNNING/PENDING; full-period automated fill audit and independent final audit pending.

## 2026-09-08 — M017 four closed days, deadline improvement is not reserve recovery

Closed prefix4/12: daily positive cycles[12,3,2,1], total18, min1/median2.5/max12.
All4days below500/1000/2000. Operating100.16092, reserve9.77978, marked equity
109.94070, net−0.05930. Six releases include5losses and1zero; total consumption
0.23810, mean over ALL6 releases0.0396833333. Positive ordinary profits0.17880,
contributions0.01788;0/5 loss cohorts repaid, debt0.22418. Surplus contributions
before debt0.00396 remains separate, not discarded or credited twice.
Six strict2h violations; maximum hold2.000024801111h, still89.284ms over deadline.
The bounded-hold objective improved in this prefix, but profits are less than
release losses even before splitting funding/reinvestment. This is observed
sequence evidence, not proof about every possible funding replay or later days.
Model, parameters and execution source unchanged. RUNNING; VERDICT=PENDING.

## 2026-09-08 — OWNER reduces scope12→3→2→1day; process stopped

OWNER requested extension only after explicit approval, then corrected the
requested window to2days and finally1day. “Aprove” was a correction to “caso eu
aprove”, not approval already granted. New authority:OWNER_GATED_REPLAY_WINDOW.md.
The verified M017 process652 was stopped; session74960 exited1 because of the
OWNER interruption. No matching replay process remained at16:02:32UTC verification.
Five closed days plus a partial sixth had already been processed under earlier
authority. Existing files and published checkpoints remain preserved, outside the
new comparison window. They cannot be relabeled as unseen/locked validation data.

Registry RUNNING→INCONCLUSIVE records the initial3day scope change; subsequent
corrections to2and1day are recorded here, without rewriting the event. The
original12day run is incomplete, not economically failed or technically invalidated.
No forced liquidation, capital reset or new replay occurred. Current comparison
uses day1 only in M015/M016/M017; audit and HTML are being aligned with that limit.
The old M017 policy remains2h. Clarification was requested for “1hora de espera”:
simulated position age versus delivery time. Do not silently change or relabel
the registered policy. No extension or successor is currently authorized to run.

## 2026-09-08 — latest OWNER progression and M018 preparation

The later OWNER directive authorizes conditional day1→2→3, requiring1000 audited
positive complete ordinary cycles EACH day with unchanged strategy/full state and
economic sustainability. Current gate remains one day; M017 has12, not1000.
After three qualifying days, a new2000/day hypothesis returns to day1 and100+10.
OWNER canceled charts/HTML and requested only cycles, operating,reserve,total.
"Continue, use support strategies" authorizes a small preregistered successor.

M017 first-day physical audit PASS_PREFIX_EVIDENCE_NOT_STRATEGY_PASS; reporter
bounded-read fix independently reviewed,24report/debt fixtures passed. Daily1
operating100.10692,reserve9.99208,equity110.099,12cycles,one release0.0198,
debt0.01188,strict2h violation47.867ms. No later day enters current comparison.
No HTML was generated. Stop-time statements above remain chronological evidence.

M018 preparation: ADAPT passive placement support, P=min(selectedLOW,ask−tick
rounded down), preserve original HIGH and all queue/cost/funding/deadline controls.
First-fill partial entry anchors the admitted limit. No active-order repricing.
Day1's2546 post-only BUY rejections motivate this single change; fewer rejections
would not prove more profitable cycles. M015 scientific parent; M017 technical
control. One-day input guard and conditional three-date universe are separate.
The ambiguous1h request remains disclosed; this isolated case uses2h control.
GPT-6 Astra implemented/reviews scientific changes; GPT-5.6 Luna handled bounded
reporter mechanics. No replay has run for M018; source-bound independent review
and publication remain mandatory before execution.

M018 registered CREATED, model hash
68e9b01e0f4646319364199fe17970c5c1ec9b22e46c6a498df131ac2f0f43e5.
Registry enforced the exact M015 ancestry; M017 is separately referenced as
technical control. An initial registration attempt with a noncanonical ancestry
was rejected before append; corrected using the actual parent's recorded chain.
Software validation144 fixtures passed;13 admission fixtures rerun after adding
an explicit adjustment reason. These are software facts, not economic results.

## 2026-09-08 — M018 full first day completed; no extension

Preflight independent159tests/source bindings passed. Configuration published at
65b7fe6aebb91d6c01ee6ef92d90b7c26f84a83c, HEAD==origin/main and clean before
`.venv/Scripts/python.exe -m scripts.run_l2_monthly_samples --model M018`.
Session9736 exited0; no replay writer remained. Actual source2025-01-01 only,
24logical hours,254205 canonical trades; no day2payload accessed.
Physical run219acf9d02fbf954fa4c85342583c047749a87244172a63310441aa2e8279b48;
registry run653012a073793292d9d21685fbda4193fe7e9af69759ebd55d3657bcbfda4703;
scenario5c31dcd93eee744fd9033fcd115f6170cb47a745e1dd377211453cd34e7f76d1.

ECONOMY:9positive complete ordinary cycles; operating100.08910,
reserve9.96040,total110.04950,net realized+0.04950,unrealized0,fees0 under the
frozen profile. Control M017same-day12cycles,operating100.10692,reserve9.99208,
total110.09900. Thus cycles−25% and net profit−50%, not improvement.
Positive ordinary gains0.099;3releases(2loss/1zero) consumed0.0495; funding
0.0099; neither loss recovered, debt0.0396; reserve minimum9.95347,no depletion.
Two strict2h violations,max2h+47.867ms. WorkingBUY remains at cutoff with zero
inventory, no forced closure. The1h holding policy was not tested.

DIAGNOSIS:four adjusted admissions; BUYpost-only rejections2546→0, yet fills
were12vs13 and ordinary positive cycles9vs12. M018 spent14.907792h flat,
9.092208h holding; working-order uptime99.922% is NOT productive profit uptime.
Removing admission rejects is insufficient; existing selector/target/fill waiting
and release economics still govern serial rotation. Increased reserve funding
cannot create missing fills or restore losses without actual positive profit.
Automated26fill/12settlement auditPASS; post-run independent audit pending.
No next model or day2 run initiated. No HTML/graphs generated.

Post-run independent review identified a TRACE_ONLY bug: one adjusted admission
used the latest trade capture cursor in fields named book_capture. The native
book update, decision price and causal execution remain valid; this does not
invalidate the economic loss or explain away the9cycles. The original ledger
and source65b7fe6 are immutable. The subsequent source fix records engine.book_id
and last_book_us, tested with book→trade→admission and distinct exchange/capture
times. No replay under that trace-only revision;121 regression fixtures and Ruff
passed. Runtime economic policy/spec/hash remain unchanged. Current OWNER gate
was closed after completion to prevent accidental repeat/extension.

Observed timeline explains the trade-off: an earlier adjusted BUY at1.0022 led
to the additionalH1 loss0.0297; another BUY1.0019 waited hours and canceled;
another kept originalHIGH1.0022 and ended with a zero-profit release near2h.
Positive ordinary gains declined0.1188→0.099 while losses rose0.0198→0.0495,
exactly explaining the0.0495 lower equity. Removing rejects alone is rejected
as the proposed route to1000cycles/day on this sample, not proof against every
book-aware strategy. Next justified research is causal fill-time/range selection
with expected net edge; it is not implemented or executed by this milestone.

FINAL AUDIT:PASS_WITH_TRACE_CAVEAT;26fills and12settlements reconciled, four
adjusted admissions causally checked. No financial execution bug established.
Report reports/usdcusdt/M018-one-day-independent-audit.md, SHA256 LF
8610ac66f66d10d8b5ebcb06d2eef6771ff6d3a35cd34cdb28059a048ba04f53.
Trace-only post-run fix independently reviewed with64regression fixtures; not
executed as a new replay. Registry RUNNING→EVALUATED→REJECTED; evaluation
669b02e4e3c0e9277918899522bdde0563bf6cbe791cd5dce3a553e5b0064dd2.
REJECT refers to this configuration/day and OWNER gates, not impossible future
strategy performance. Every financial total above remains conditional on the
frozen fee-zero/PRICE_PRIORITY execution assumptions. No day2 was opened.

## 2026-09-08 — OWNER review and live-versus-simulator research

Read-only review; no strategy changes, replay, private API, Testnet or live order.
The previously identified queue-depth discrepancy remains in M018. A current
in-memory fixture confirmed ACTIVE queue100, displayed depth100→40, queue still100,
inventory0. This is a diagnostic of model semantics, not a measured historical
cycle uplift. Changing it requires a separate execution hypothesis and trade/depth
reconciliation, not free cancellation credit. Current first-day34428/34441
compatible exact-price prints left nothing after the estimated queue(99.9623%).

External primary references rechecked through agent-reach GitHub/Jina routes;
Exa was unavailable, so web search was the explicit fallback:

- HftBacktest queue.rs at5f3ec40b2afb764e0fea112f941ed85523ef4e88 caps
  RiskAdverseQueueModel ahead quantity to new displayed depth:
  https://github.com/nkaz001/hftbacktest/blob/5f3ec40b2afb764e0fea112f941ed85523ef4e88/hftbacktest/src/backtest/models/queue.rs#L80
- NautilusTrader documents L2 UPDATE queue caps, DELETE clearing and shared
  liquidity-consumption controls; defaults/features must be explicitly selected:
  https://nautilustrader.io/docs/latest/concepts/backtesting/trade-execution/
- HftBacktest explains queue inference without per-order data and immutable
  market-replay impact limitations. Small orders reduce impact concerns but do
  not bypass queue priority:
  https://hftbacktest.readthedocs.io/en/latest/order_fill.html
- Feed arrival, exchange order arrival and response latency are distinct;
  supplier capture times do not measure our hypothetical account round trip:
  https://hftbacktest.readthedocs.io/en/latest/latency_models.html
- A2023user report described MORE live fills while losing despite profitable
  backtests. Maintainer response recommends matching order/position paths,
  feed/order latency and queue assumptions. Anecdote, not controlled evidence:
  https://github.com/nkaz001/hftbacktest/discussions/54
- QuantConnect recommends same-period/initial-state reconciliation and separates
  data, fill, cost and brokerage-model discrepancies:
  https://www.quantconnect.com/docs/v2/cloud-platform/live-trading/reconciliation
- Binance commission documentation distinguishes account/symbol/rate components;
  fee-zero remains a frozen conditional assumption, not verified account economics:
  https://developers.binance.com/docs/binance-spot-api-docs/faqs/commission_faq

Local constraints also matter independently of simulator fidelity: the executed
deadline was2h, NOT the OWNER's requested possible1h holding policy; four holds
exceeded1h. H1 predicate evaluations included2NONPOSITIVE_DEFICIT and1SAME_CANDIDATE
veto, not reserve insufficiency. BUY8 waited5.004h unfilled; holding clock starts
only at first fill. No PROTECTED_EXIT_BLOCKED occurred; reserve minimum9.95347
was far above floor2.5. A larger reserve alone does not remove these rules.

CONCLUSION: no actual live-order record exists for this strategy in the evidence
reviewed, so live/simulator cycle ratio is UNKNOWN. Neither9 simulated cycles
nor favorable older price-path counts prove live capacity. Prioritize isolated
queue-consistency sensitivity, explicit1h/entry-wait protocol and causal
fill-time/edge-aware selection before tuning funding. Keep paired source/costs,
never optimize the execution model simply until1000cycles appear. Public shadow
data could later validate signals/arrival sequencing, not actual personal fills;
any private/live calibration requires separate OWNER authorization.

## 2026-09-08 — Concrete community complaints and original B10 reconciliation

OWNER requested actual user reports, maintainer conclusions and applicability,
not a generic simulator disclaimer. Read GitHub issue bodies and comments via
agent-reach's gh route; independent scientific reconstruction used GPT-6 Astra.
No implementation, replay, later-day extension or account access occurred.

- NautilusTrader #1537 (March2024): reporter's promising backtest diverged live.
  Reporter traced premature fills to loading completed bars with ts_init at bar
  open, corrected availability timestamps, then reported much closer live
  agreement. This is a resolved data-loading problem, not proof that the engine
  intrinsically leaks future data. Current native-L2 M018 does not use this bar
  path; no matching local timestamp/lookahead defect was established.
  https://github.com/nautechsystems/nautilus_trader/issues/1537#issuecomment-1993986958
  https://github.com/nautechsystems/nautilus_trader/issues/1537#issuecomment-2002336687
- HftBacktest #299 (December2025): maintainer acknowledged local-state handling
  of partial fills needed investigation. CLOSED on April23,2026 by inactivity
  automation, NOT evidence of a fix. #316 (June2026), still open when inspected,
  supplies another reproduction alleging uncredited partial executions.
  We do not run this engine. M018's independent audit reconciled all26 fills,
  including the two multi-piece BUY orders; this particular accounting failure
  was not found locally. Audit validity remains conditional on execution model.
  https://github.com/nkaz001/hftbacktest/issues/299
  https://github.com/nkaz001/hftbacktest/issues/316
- Hummingbot #7286 (November2024): reporter found delayed order recognition,
  resolved a Bybit demo-domain issue, but continued reporting paper-trade delay.
  Contributor closed with clarification that paper connectors send no actual
  orders; the thread does not demonstrate a complete paper-latency fix. This
  connector-specific cause is not present in our offline execution engine.
  https://github.com/hummingbot/hummingbot/issues/7286
- HftBacktest discussion54 remains an unresolved live/backtest anecdote, not a
  controlled validation or a promise that switching queue models restores edge.
  More live fills coexisted with losses in the reporter's account; exact cause
  was not established. Source already recorded above.

Independent physical lineage check: historical097abdab / RRV2_H1_B10_F2.5
completed artifact records3580880 cycles, COMPOUNDING100+5, funding2%, source
2026-01-01 through2026-09-05. serial_replay.py matches LOW/HIGH price events,
not our order's actual queue/acknowledgement/executable-volume path; historical
recovery_reserve.py labels release THEORETICAL_RELEASE_PRICE_PATH and executable
loss UNKNOWN. Those counts do not establish live fills or scalable compounding.
B10 Reality additionally used a fixed100 ruler and parameterized trade-derived
book; its name alone does not mean native historical L2 execution.

M018 is a changed policy/capital allocation (100+10, funding10%, passive BUY
admission and2h deadline) on native-L2 source2025-01-01, not the original B10 on
its original period. Do not attribute the multi-million-to-nine comparison to a
single change. The controlled local decline is M01712 to M0189 positive cycles
on the same first day, already reconciled above. Neither result includes fees
under the frozen profile. A queue estimate staying above displayed depth is a
separate confirmed modeling difference; its historical economic effect remains
unmeasured. No evidence yet demonstrates that original B10 returns are achievable
live, or that current low rotation is a definitive live upper bound.

## 2026-09-08 — OWNER proposes three100USDT ranges without reserve

New direction: three separate buy-low/sell-high ranges,100USDT each, reserve0,
focus on inactivity and completed cycles. Preparation only; no new model was
registered or executed, and no historical model/ledger changed. Independent
GPT-6 Astra reviewed scope, accounting and the remaining OWNER decision.

Read-only inspection found reusable disjoint-range/shared-liquidity concepts in
continuous_multi_queue.py, but its historical implementation pools operating
cash and manages a reserve/fourth lane; it is not this proposed model or a native
L2 three-lane implementation. Do not resume M013 or transplant its semantics.

Working interpretation is300 total, segregated per-lane compounding, no transfers,
non-overlapping price ranges selected causally, and one shared liquidity budget.
No guaranteed three eligible ranges or continuous productive operation. Measure
per-lane cycles/equity and waiting, aggregate no-completion intervals, idle cash,
inventory waiting for SELL, and eligible-order activity separately. Comparison
with old110-capital outcomes is not capital-matched evidence.

Blocking OWNER decision before exit policy is frozen: if a position cannot sell
profitably after1h, must it wait for HIGH or may its own capital absorb a loss?
The proposal does not authorize forced losses, unlimited waiting or another lane
paying the loss. No new run until this choice and normal experimental gates.
First-day scope and no account/Testnet/live access remain unchanged.

OWNER then resolved the decision: "Fazer1dia somente" and "Vender em alta
somente". Thus the proposed three-lane case has no forced-loss exit;1h becomes
a reported hold alert and open inventory remains marked/censored at cutoff.
No more human clarification on this exit policy is required. Implementation,
registration, software validation, independent review and publication gates
remain before any new replay. Latest question asks the range count needed for
90%cycle coverage. Analyze the same day descriptively with explicit denominator;
do not use retrospective optimal ranges as causal decisions or equate coverage
with executable fills. Three100 allocations and one day are not expanded by
that question.

### First-day90%range coverage diagnostic — not an economic replay

Independent GPT-6 Astra read only the closed M018 day1 ledger, SHA256:
4bc2f823be46436581869d390f98d78401f19ee6172d329d36825de3ae57a793.
254205 canonical trades,2025-01-01 only. Source operator/serial lineage checked.
Method: M007 one-tick(.0001) CandidateTimeline LOW-to-HIGH cycles; denominator is
the union of canonical HIGH completion events across the ten eligible ranges.
No event duplicated between ranges in this one-tick universe:29182 opportunities.
These are price-path events, not100USDT orders, L2 fills or profitable live cycles.

| LOW | HIGH | Price-path completions |
| --- | --- | ---: |
|1.00170|1.00180|55|
|1.00180|1.00190|1558|
|1.00190|1.00200|11194|
|1.00200|1.00210|8755|
|1.00210|1.00220|4057|
|1.00220|1.00230|2964|
|1.00230|1.00240|520|
|1.00240|1.00250|77|
|1.00250|1.00260|1|
|1.00260|1.00270|1|

Allowing adjacent ranges to share endpoints, sorted cumulative coverage is:
1range11194(38.3593%);2ranges19949(68.3606%);3ranges24006(82.2630%);
4ranges26970(92.4200%). Thus four is the retrospectively minimal count for90%
under this stated universe/definition. Main independently checked arithmetic
with Python Decimal. At100 per lane the hypothetical capital would be400,
not the currently approved300; no fourth lane was funded or executed.

If closed intervals must be strictly disjoint (even shared endpoints forbidden),
interval scheduling gives optimal1/2/3/4/5 coverage11194/15251/15771/15826/15827.
Maximum54.2355%, so90%of the29182 denominator is unattainable under that EXTRA
geometric restriction. This is not a claim of physical market impossibility.
Financial segregation does not require forbidding shared boundaries. Adjacent
BUY/SELL endpoints need self-cross prevention and shared-volume execution tests.

CLASSIFICATION=RETROSPECTIVE_DIAGNOSTIC_ONLY. Ranges selected after observing the
day are not the causal M019 selector. No profile/queue relaxation, new replay,
day2 access or model promotion. This answers coverage only, not achieved uptime,
net returns or actual four-lane capacity. Three-lane implementation remains in
preparation and unexecuted; OWNER has not authorized increasing to four lanes.
