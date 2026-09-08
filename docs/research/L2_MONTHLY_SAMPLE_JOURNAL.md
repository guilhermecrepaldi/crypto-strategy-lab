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
