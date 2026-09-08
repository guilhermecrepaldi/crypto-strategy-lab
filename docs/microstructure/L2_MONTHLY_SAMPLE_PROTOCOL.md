# L2 monthly samples — consecutive synthetic stress protocol

STATUS=PREREGISTRATION_UPDATED_BEFORE_ANY_ECONOMIC_REPLAY.
OWNER superseded independent resets with SYNTHETIC_CONSECUTIVE_12D. The preceding
protocol remains immutable in Git history; no economic experiment ran under it.
This protocol does not authorize reading the real continuous second week.
Software/data PASS does not imply economic PASS. Historical days remain DEVELOPMENT.

## Frozen strategy and scope

CURRENT_STATE and the physical registry identify M015 as the current strategy.
Registry model hash:
`4231670b19b1ca5c2b5032b1476b83b3182d1463750ea944da5efb867d81a8fa`.
Bind the original M015 spec, registry entry, economic source bytes, adapter source,
this protocol and input manifests by SHA256 in each execution manifest. Preserve
M015/M014 and previous results. This is a new execution-evidence campaign, not M016.

Data inventory remains21 first-of-month samples. Execution is frozen to the12 days
approved when OWNER authorized the sequence: Jan/Feb/Mar/Apr/Jun/Aug2025 and
Jan/Feb/Mar/Apr/May/Jul2026, always day1. Use that source-chronological order without
permutation or economic selection. Other dates remain outside this run even if later
validated. Run both envelopes for all12 logical days, including days below500.
No economic early stop, real January8–14 read, or assertion of real monthly return.
Invalid/unselected sources remain visible, not zero-cycle strategy failures.

Each envelope starts ONCE, FLAT, operating=100 USDT, reserve=10 USDT. Then preserve
capital, positions, dust, orders, queue, escrow, reserve and timers across all12 days.
Compound continuously through this artificial sequence;10% of positive realized
ordinary profit funds reserve and90% remains
operating. Preserve M015 sizing, M007 selector/hysteresis/reselection, B10 H1/B10/F2.5
release predicate, protected IOC/reserve accounting, maker/taker fees, filters,
latency and cancellation semantics. M015 has one operating queue and no active
reserve queue. Do not implement additional queues for this battery.

Cold start occurs only at logical day1. Selector history consists exclusively of
the actually received prefix of the stitched12 days. Do not load December2024 or
the real-calendar preceding day for warmup. Preserve M007 windows/support/hysteresis;
no synthetic support, future event visibility or daily selector reset.

## Logical clock and seams

Logical origin is2025-01-01T00:00:00Z. Source day i maps both capture and exchange
timestamps by the same fixed day offset to logical day i; keep original timestamps,
trade IDs and source hashes alongside every mapping. Timers see12 consecutive24h
days. This is an explicitly manufactured environmental sequence, not missing-history
reconstruction. Map tick-rule periods to the same logical timeline, using each
source day's original historical grid and frozen filter assumptions causally.

At each seam, invalidate the available book before advancing timers. Preserve
financial state and orders; permit no fill or new submission until the next valid
bridged snapshot. Capture ordinals are globally unique; native sequence validity is
verified separately within each source day, never claimed across the calendar jump.
Never synthesize a trade or liquidation at a price jump. Mark equity changes at a
new observed quote as environmental shocks, not realized trades.

Ordinary remaining queue-ahead is carried without cancellation credit or an
automatic re-seed. Cross-seam FIFO priority is UNKNOWN, not observed continuity.
IOC budgets receive no inferred cross-gap replenishment: at the first new snapshot,
previously seen prices retain at most min(old available,new displayed). A previously
consumed/deleted price stays constrained; only within-day observed positive deltas
replenish it. Genuinely unseen prices may contribute their observed displayed depth.
No forced cancel, fill, release, close or treasury reset is introduced by the seam.

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

Startup clarification: all144 native ten-minute slices can be present even when
the first bridging snapshot arrives after source midnight. Only day1 starts FLAT;
subsequent days preserve existing orders/positions but have no executable book
until the new snapshot. Record INITIAL_UNAVAILABLE_US perday and include idle time
in the24h denominator. This does not invalidate an otherwise fully sequenced day; it never
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

Arrival-clock clarification: activation, cancel and holding timers use the mapped
LOGICAL_CAPTURE_ARRIVAL_CLOCK. Preserve each native exchange timestamp
and precision separately. Depth/trade exchange timestamps can legitimately interleave;
do not reorder capture or declare a gap solely for that interleaving. Every selector
and recovery history query is capped by prefix-limited tape/timeline views at the
last actually received contiguous canonical event, excluding the incoming message
during its lifecycle reconciliation. No precomputed future event becomes visible
merely because the capture clock has advanced. A trade whose native event precedes
activation cannot fill that order; a newer-exchange book cannot support an older
trade fill. Consume no trade quantity when these execution-availability gates fail,
but retain the event and its later prefix availability in the audit. Native historical
millisecond timestamps match the canonical microsecond timestamp at native precision,
not by inventing submillisecond equality; IDs/prices/quantities/sides must match exactly.
For native book E in milliseconds the possible interval ends at1000*E+999us;
microsecond E is exact. A fill cannot use a book whose upper bound exceeds the
canonical trade time. Ambiguous prints remain recorded but cannot fill. Snapshot
capture bounds are labeled CAPTURE_BOUND, never fabricated native microsecond E.

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

Pre-execution clarification, tightened by independent review before any economic
outcome: for prior displayed D, available A and new displayed D', use
A'=max(0,min(D',A+(D'-D))). A decrease conservatively removes remaining hypothetical
budget; do not assume it affected only already-consumed liquidity. An increase
provides only its observed positive delta. Unchanged depth never replenishes;
deletion clears availability.
Thus observed deletion followed by reappearance can provide fresh depth, without
resetting an unchanged snapshot. This applies only to hypothetical IOC liquidity,
not cancellation credit for the ordinary resting-order queue.

For 2025 CALIBRATION only, the frozen profile has no dated rules period. Apply
CONDITIONAL_TRANSFER_OF_FROZEN_RULES: the earliest frozen lot/notional/fee/latency
assumptions, with the existing canonical 2025 tick catalog. Disclose this explicitly
in every 2025 manifest/result; these are not independently observed 2025 account fees
or historical filters. Do not mutate the frozen profile or infer guaranteed returns.

## Metrics and interpretation

Every daily row is keyed by LOGICAL_DAY, SOURCE_DATE and ENVELOPE and includes counts,
capital, reserve, equity, PNL, cycles, orders/fills, releases, holding, queue, depth,
spread, uptime, capacity and verdict fields. Decimal arithmetic remains authoritative.
ORDINARY_CYCLES counts complete ordinary BUY+SELL settlements only; NET_POSITIVE_CYCLES
counts those with realized net profit >0. Releases/partial cycles are excluded. The
main CYCLES column and >=500/>=2000 gates use NET_POSITIVE_CYCLES; also show ordinary
total. CYCLES_PER_HOUR divides by 24, not active hours or available-data hours.

Do not close or reset at daily boundaries or the final cutoff. Record inventory, dust, open orders and
reserve escrow. OPERATING_FINAL is cash plus marked operational inventory/dust;
also expose operating cash and cost-basis bank separately. Mark remaining inventory
at the last valid bid, disclose mark age and unrealized PNL. TOTAL_EQUITY_FINAL is
operating marked equity plus reserve. CUMULATIVE_NET_PNL is its difference from110;
daily PNL is the change from prior logical close (110 for day1), with daily opening
operating/reserve carried explicitly. Sequence return is final equity/110-1, labeled
SYNTHETIC_STRESS_RETURN, not real historical monthly performance. A missing
valid terminal mark yields unknown marked equity, not a zero mark.

MAX_HOLD includes completed holdings and elapsed open holding at cutoff, with an
OPEN_HOLD_CENSORED flag. HARD_LOCK_VIOLATIONS counts holds observed at or beyond 24h, not
future conjectures. Synthetic sequence survival cannot establish real historical survival.
BUY/SELL full/partial/zero-fill counts are per submitted order as of cutoff; pending
and canceled states are separately visible. RELEASE_LOSS is actual executed deficit.

MOTOR_UPTIME is the time fraction with an accepted ordinary order working AND a
valid available book, excluding
pending activation, release and canceled/expired/rejected orders. FULL_STOP_HOURS
is 24*(1-MOTOR_UPTIME). CAPITAL_WEIGHTED_UPTIME integrates ordinary committed operating
capital divided by contemporaneous operating cost-basis bank, then divides by24h
for a daily row or288h for the complete sequence;
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

Report the two synthetic equity paths separately. Daily medians/P10/P90/min/max,
days>=500/>=2000, zero-cycle days, uptime, holding and violations describe dependent
days of the same path, not independent return draws. Source year remains provenance;
do not label2026 an untouched prospective test after carrying2025 state. All is
DEVELOPMENT. Best/worst use positive daily cycles, breaking ties by logical day.
Autopsy those days per envelope using
spread/depth, aggressor flow, price moves, range activity, queue and fill latency;
autopsy is descriptive and cannot tune an already run envelope.

## Publication and audit gate

Before any economics: reconcile manifests, validate implementation with targeted
fixtures, obtain independent review, publish the source/protocol and first data
scoreboard, verify HEAD==origin/main, then emit the OWNER first-return fields.
Automatically run exactly the authorized12-day sequence after those gates. One canonical campaign writer;
preserve per-day/envelope manifests, full audit ledgers and failures. Audit all fills
for quantity/source ownership and all releases for depth/fees/reserve accounting.
Final verdict distinguishes COMPLETE_CONDITIONAL_SYNTHETIC_STRESS, INCONCLUSIVE_DATA,
INCONCLUSIVE_TECHNICAL and target attained/not attained. Never certify live returns.

Official sources checked before data acquisition:
[CSV availability/order](https://docs.tardis.dev/downloadable-csv-files),
[CSV schema](https://docs.tardis.dev/downloadable-csv-files/data-types),
[Binance collection/sequence](https://docs.tardis.dev/historical-data-details/binance),
[raw API/free access](https://docs.tardis.dev/api/http-api-reference),
[atomic reconstruction](https://docs.tardis.dev/faq/order-books).
