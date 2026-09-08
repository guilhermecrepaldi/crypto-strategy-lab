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
