# L2 monthly sample battery — preregistered execution protocol

STATUS=PREREGISTERED_BEFORE_ECONOMIC_REPLAY. This protocol implements the new
OWNER monthly-sample directive; it does not authorize the continuous second week.
Software/data PASS does not imply economic PASS. Historical days remain DEVELOPMENT.

## Frozen strategy and scope

CURRENT_STATE and the physical registry identify M015 as the current strategy.
Registry model hash:
`4231670b19b1ca5c2b5032b1476b83b3182d1463750ea944da5efb867d81a8fa`.
Bind the original M015 spec, registry entry, economic source bytes, adapter source,
this protocol and input manifests by SHA256 in each execution manifest. Preserve
M015/M014 and previous results. This is a new execution-evidence campaign, not M016.

Candidates are exactly the first UTC day of every month from January 2025 through
September 2026: 21 independent dates inside the canonical trades universe. Run both
envelopes below for every valid date, including days below 500 cycles. Each experiment
covers [00:00 UTC, next 00:00 UTC); no economic early stop, month-to-month carry,
concatenated return path, or January 8–14 replay. Missing/invalid days remain visible
as rows with null economic results, never zero-cycle economic failures.

Each date/envelope independently starts FLAT, operating=100 USDT, reserve=10 USDT,
no inventory, orders, queue, escrow or inherited financial state. Compound within
the day; 10% of positive realized ordinary profit funds reserve and 90% remains
operating. Preserve M015 sizing, M007 selector/hysteresis/reselection, B10 H1/B10/F2.5
release predicate, protected IOC/reserve accounting, maker/taker fees, filters,
latency and cancellation semantics. M015 has one operating queue and no active
reserve queue. Do not implement additional queues for this battery.

Read-only selector warmup is the preceding 24h of canonical trades when available
inside the authorized universe. It carries no financial state. On January 1, 2025,
the prefix begins at the dataset boundary; December 2024 is forbidden. The frozen
selector receives only available causal prefix and retains its existing eligibility
and support rules. Record WARMUP_AVAILABLE_US, COLD_START and FIRST_ELIGIBLE_US.
Do not shorten a selector window or synthesize historical support. This first-day
boundary limitation is reported explicitly when comparing 2025 calibration days.
Using a cold-start reset for all other dates would change the experimental initial
information set and is not silently substituted for the available warmup.

## Data and validity gates

Preserve downloaded CSV gzip bytes immutably under the OWNER path. Record URL,
HTTP status, download UTC, content length when supplied, actual bytes, SHA256,
gzip integrity, exact schema, rows, first/last exchange and capture timestamps.
DATA_STATUS distinguishes AVAILABLE, UNAVAILABLE, INVALID and INCOMPLETE_DOWNLOAD.
Authentication errors are recorded; no keys, owner account, purchases or bypass.

CSV columns do not include U/u/lastUpdateId. Provider sequence validation is
PROVIDER_ATTESTED, not INDEPENDENTLY_VALIDATED. CSV-only results cannot pass the
OWNER update-ID gate. Obtain the documented free monthly raw API sidecar with
depth, depthSnapshot and trade for lowercase usdcusdt. Preserve raw bytes/hashes,
slice coverage, native messages, capture line order and disconnect markers.
Validate native snapshot lastUpdateId and depth U/u: discard covered old updates,
bridge snapshot using U <= lastUpdateId+1 <= u, then reject missing sequence ranges.
Record duplicates, reconnects and resnapshot boundaries separately. Independently
reconcile normalized CSV book evidence with validated raw book evidence. A generic
provider statement cannot fill a missing raw sequence field or response slice.

Reconstruct in physical capture order. Skip and count nonsnapshot prefix rows.
Apply complete consecutive local_timestamp batches atomically before inspecting
the book or permitting execution. New snapshot clears state once, not once per row.
Quantities are absolute nonnegative values; zero deletes the level. Validate symbol,
sides, positive prices, exact decimal grid, capture order, timestamps and ordered
bid/ask maps. Check noncrossed state after the complete message/batch, never midway.
Do not remove crossed levels to manufacture a valid book. Initial top-1000 depth
does not establish zero quantity outside its known coverage; such levels are UNKNOWN.

No artificial gap filling. Resnapshot repairs future state but cannot reconstruct
unknown executions during a disconnected interval. An unrecoverable interval,
sequence gap, missing mandatory raw sidecar, unresolved crossing or missing day
coverage produces L2_DAY_VALID=false and an INCONCLUSIVE data verdict. Record
initial unavailable duration and daily coverage explicitly. Silence alone is not a
sequence gap: a quiet market may have no update. Missing slices are not silence.
Data validation can continue for all candidates even when one date fails.

Startup clarification before any economic replay: a complete inventory of all144
native ten-minute slices may have its first bridging snapshot after midnight.
Because every experiment starts FLAT, forbid any order/activation until that
snapshot, record INITIAL_UNAVAILABLE_US, and include this idle time in the24h
denominator. This does not invalidate an otherwise fully sequenced day; it never
repairs a missing mid-day interval or assumes an initial book that was not observed.

## Causal merge contract

Canonical official trades remain the authority for ID, price, quantity, aggressor
and event timestamp. Tardis raw trades provide capture provenance only after exact
ID/value reconciliation. Verify DATE_MATCH, authorized boundaries, trade-ID order,
timestamp unit, and the existing historical tick/filter authority. Do not replace
canonical prices or quantities with provider rows on mismatch.

Maintain separate exchange-event and capture clocks. A book observation is available
only after its entire message has arrived; exchange-time sorting must not bring
future capture into an earlier decision. Native capture order resolves cross-stream
availability where observed; it does not prove matching-engine order. No book with
exchange timestamp beyond the current canonical event may support that event's fill.
Ambiguous equal-time events cannot activate and fill a newly submitted order through
the same print. Strategy selection continues to use its strict canonical event prefix.
Record the merge mapping and gate rejected/ambiguous events; do not silently reorder
late prints or drop them while claiming full coverage. An unresolved causal mapping
blocks that day's economic replay pending a reviewed correction.

## Two execution envelopes

CONSERVATIVE_QUEUE is the primary displayed-depth envelope. At actual activation,
seed ahead with all displayed same-side quantity at our limit observed before the
insertion, not the quantity at submission. KNOWN_DISPLAYED_AHEAD describes that
observation; UNKNOWN_TIME_PRIORITY_WITHIN_EXISTING_LEVEL remains explicit. Missing
level inside known coverage can yield zero; outside coverage cannot. Store best bid,
best ask, limit, same-level displayed quantity, initial ahead and same-side cumulative
depth within 1/2/5 ticks of the best quote, including that best level.

Compatible canonical exact-price trades deplete ahead then support own fills, with
one quantity budget per trade. Depth decreases do not ALSO deplete queue: that would
double count transactions already present in trades. No cancellation credit is
inferred. Later book increases do not reset ahead or add behind-order volume to ahead.
Cancel/replace creates a new seed; a partial fill of the same order retains its queue.

PRICE_PRIORITY uses the identical observed seed and conservative exact-price branch,
plus the frozen M015 strict trade-through rule: already active before the print,
compatible aggressor, BUY print below limit or SELL print above limit, no effective
cancel, valid available book. Fill at own limit, quantity bounded by raw print and
own remainder, no flow reuse. Log inferred clearance separately from observed queue
consumption. This envelope is a conditional execution inference, not observed rank.
The two envelopes are independent counterfactual runs, not simultaneous consumers.
No additional sensitivities are admitted after seeing economic results.

Release IOC consumes the observed currently available bid ladder in descending price
order down to the existing protected limit, with frozen fees and latency. There is
no synthetic spread, slippage markup, timed depth refresh or unlimited replenishment.
Maintain an external-book map separately from hypothetical consumed liquidity. A
repeated snapshot/unchanged quantity or an update of another level must not restore
consumed quantity. A conservative consumption debt persists per price; only an
observed positive quantity change provides new available budget. Record update/source
IDs and pre/post budgets for every IOC. No order or retry consumes the same budget
twice. M015's existing reserve floor and exact deficit coverage remain authoritative.

## Metrics and interpretation

Every daily row is keyed by DATE and ENVELOPE and includes OWNER-requested counts,
capital, reserve, equity, PNL, cycles, orders/fills, releases, holding, queue, depth,
spread, uptime, capacity and verdict fields. Decimal arithmetic remains authoritative.
ORDINARY_CYCLES counts complete ordinary BUY+SELL settlements only; NET_POSITIVE_CYCLES
counts those with realized net profit >0. Releases/partial cycles are excluded. The
main CYCLES column and >=500/>=2000 gates use NET_POSITIVE_CYCLES; also show ordinary
total. CYCLES_PER_HOUR divides by 24, not active hours or available-data hours.

Do not force closure at the day boundary. Record inventory, dust, open orders and
reserve escrow. OPERATING_FINAL is cash plus marked operational inventory/dust;
also expose operating cash and cost-basis bank separately. Mark remaining inventory
at the last valid bid, disclose mark age and unrealized PNL. TOTAL_EQUITY_FINAL is
operating marked equity plus reserve; NET_PNL is its difference from 110; daily
return is NET_PNL/110. Realized PNL and cash transfers remain separate. A missing
valid terminal mark yields unknown marked equity, not a zero mark.

MAX_HOLD includes completed holdings and elapsed open holding at cutoff, with an
OPEN_HOLD_CENSORED flag. HARD_LOCK_VIOLATIONS counts holds observed at or beyond 24h, not
future conjectures. Independent 24h flat starts cannot establish multi-day survival.
BUY/SELL full/partial/zero-fill counts are per submitted order as of cutoff; pending
and canceled states are separately visible. RELEASE_LOSS is actual executed deficit.

MOTOR_UPTIME is the time fraction with an accepted ordinary order working, excluding
pending activation, release and canceled/expired/rejected orders. FULL_STOP_HOURS
is 24*(1-MOTOR_UPTIME). CAPITAL_WEIGHTED_UPTIME integrates ordinary committed operating
capital divided by contemporaneous operating cost-basis bank, then divides by 24h;
cap the ratio at one and report reserve excluded. Preserve the older working-order
metric separately if it includes pending/release states. CAPACITY_PRESSURE is the
requested order quantity / observed displayed same-level quantity at activation;
zero denominator is null with a zero-depth flag, not an invented finite ratio.

Displayed queue percentiles are one sample per ordinary activation; no activations
means null, not zero. Best-level depth and spread percentiles are duration-weighted
over valid reconstructed state. State exactly which side/population each statistic
uses. Use nearest-rank empirical percentiles (ceil(p*n), bounded to 1..n); median is
the middle value or average of the two middle values. Proxy comparison uses exact
frozen old queue from profile (approximately 2.33M), divided by activation median.
Zero/missing median gives null ratio. Preregistered descriptive classification:
old proxy > observed P90 => TOO_CONSERVATIVE; old proxy < observed P10 => TOO_OPTIMISTIC;
otherwise REASONABLE. No activations => INCONCLUSIVE. This labels displayed-size
comparison only, not true FIFO rank or execution certainty.

Aggregate by envelope and separately for 2025 CALIBRATION and 2026 EVALUATION, plus
clearly labeled combined independent-day distribution. Report valid/total candidate
days, median/P10/P90/min/max positive cycles, days >=500 and >=2000, zero-cycle days,
median uptime, weighted uptime, daily return, maximum holding and violation days.
No sum-of-months compounding or geometric return path. Best/worst use positive cycle
count, breaking ties by earlier date. Autopsy those two days per envelope using
spread/depth, aggressor flow, price moves, range activity, queue and fill latency;
autopsy is descriptive and cannot tune an already run envelope.

## Publication and audit gate

Before any economics: reconcile manifests, validate implementation with targeted
fixtures, obtain independent review, publish the source/protocol and first data
scoreboard, verify HEAD==origin/main, then emit the OWNER first-return fields.
Automatically run all valid days after those gates. One canonical campaign writer;
preserve per-day/envelope manifests, full audit ledgers and failures. Audit all fills
for quantity/source ownership and all releases for depth/fees/reserve accounting.
Final verdict distinguishes COMPLETE_CONDITIONAL_EXECUTION, INCONCLUSIVE_DATA,
INCONCLUSIVE_TECHNICAL and target attained/not attained. Never certify live returns.

Official sources checked before data acquisition:
[CSV availability/order](https://docs.tardis.dev/downloadable-csv-files),
[CSV schema](https://docs.tardis.dev/downloadable-csv-files/data-types),
[Binance collection/sequence](https://docs.tardis.dev/historical-data-details/binance),
[raw API/free access](https://docs.tardis.dev/api/http-api-reference),
[atomic reconstruction](https://docs.tardis.dev/faq/order-books).
