# CURRENT STATE

ACTIVE_EXECUTION_CAMPAIGN=M028_PREPARATION
CAMPAIGN_STATUS=M028_PREREGISTRATION_AND_IMPLEMENTATION
CAMPAIGN_EXECUTION_SOURCE_SHA=PENDING_PUBLISHED_PRERUN_COMMIT
CAMPAIGN_ACTIVE_ENVELOPE=NONE_PRE_RUN
CAMPAIGN_QUEUED_ENVELOPE=M028_M026_24H_REPLICATION
CAMPAIGN_VERDICT=PENDING
CAMPAIGN_PROGRESS_FILE=docs/research/M028_JOURNAL.md
CAMPAIGN_JOURNAL=docs/research/M028_JOURNAL.md
CAMPAIGN_SCOREBOARD=reports/usdcusdt/M028-m026-24h-result.json
CURRENT_OWNER_WINDOW=docs/microstructure/OWNER_GATED_REPLAY_WINDOW.md
APPROVED_COMPARISON_DAYS=1
EXTENSION_AUTHORIZED=false
CURRENT_ACTIVE_RESEARCH_MODEL=M028
MONTHLY_REPLAY_MODE=OWNER_GATED_DAY1
MONTHLY_CANDIDATES=21
MONTHLY_CSV_AVAILABLE=21
MONTHLY_VALIDATED_AT_OWNER_SELECTION=12
MONTHLY_SELECTED_FOR_CONSECUTIVE_REPLAY=1
MONTHLY_INITIALIZATION=ONCE_100_OPERATING_PLUS_10_RESERVE_PER_ENVELOPE
MONTHLY_ECONOMIC_REPLAYS_STARTED=6
MONTHLY_CONTINUOUS_WEEK_2_AUTHORIZED=false

OWNER_NEXT_RESEARCH=M028_M026_FULL_DAY_TEMPORAL_REPLICATION
OWNER_DIRECTIVE=docs/microstructure/M028_M026_24H_EXTENSION_OWNER_DIRECTIVE.md
NEXT_CAMPAIGN_STATUS=AUTHORIZED_PRE_RUN_GATES_PENDING
NEXT_CAMPAIGN_MODEL_HASH=76305edc1bab271d5358ad6954195ff01ad77319a4a9f5dc7bc4b1c9d46be301
NEXT_CAMPAIGN_WINDOW=2025-01-01T00:00:00Z/2025-01-02T00:00:00Z_EXCLUSIVE
NEXT_CAMPAIGN_ORDER_MODE=NORMALIZED_SLOT_BASE_1_USDT_EQ; WHOLE_USDC_QUANTIZED
NEXT_CAMPAIGN_FUNDING=0; RESERVE=0; RELEASE_DISABLED
NEXT_CAMPAIGN_INITIAL_TOTAL_EQUITY=DERIVED_IDENTICALLY_TO_M026_EXPECTED_156.25220000

Latest OWNER authority selects the unchanged M026 strategy for one full January 1
UTC replay and requests initial/final marked equity plus percentage gain. M026 remains
immutable; M028 changes only the end timestamp from03:00 to24:00. The engine starts
once at midnight with the same physical capital and cannot reset at03:00. Before the
extension is consumed, the complete M026 prefix ledger and economic checkpoint must
match the published result after normalizing only `end_us`. The output separates
total marked return, the incremental return after03:00, realized disposal/cycle PnL,
unrealized PnL, cycles and cycles/hour. This remains a normalized non-live-executable
DEVELOPMENT result. One run only; no other day, rerun, M029 or live action.

M027 is complete on the fixed 2026-05-01 first-three-hour tape using published
source `c653292`. CONTROL retained M026's fifteen coarse levels; TREATMENT replaced
only FAR14/FAR15 with a two-column MICRO line at ±0.00005. Both kept60 orders,
140 operational plus16 mobility slot-units and passed the <=0.01% capital-match
gate. Both produced zero fills and zero cycles. The30,552 trades remained between
1.00013 and1.00015 while hotline stayed1.00014; MICRO entries at1.00009/1.00019
were never touched. FAR14/FAR15 also produced zero in CONTROL. Both physical ledgers
and terminal states passed independent audit. M027 is `INCONCLUSIVE`: the tape did
not exercise the intervention, so it cannot identify its throughput effect. The
normalized probe is below minNotional and not live evidence. No other day, rerun,
M028, extension or live action is authorized.

Latest OWNER authority created M026 from immutable M024, with M025 as supporting
evidence only. Its single three-hour Jan1 run used published source `9e0664f` and
passed the independent physical-ledger audit. The causal hotline uses fifteen levels
per side and a 3/2/1 HOT/MID/FAR
grid: 60 initial physical orders, 140 operating slot units and 8 real mobility slot
units per asset side. Whole-USDC quantity quantization is frozen and the exact bank
is derived from actual prices; the normalized result remains below minNotional and
is not live-executable. Old order price, size, FIFO age, cost and slot epoch cannot
change. It closed30 physical cycles (10/h) and90 slot-equivalent cycles (30/h).
The >=38 physical gate failed while the >=60 slot ruler passed because each HOT
roundtrip carried three slot units. Initial78.104USDT+78USDC became128.2356USDT+
28USDC, marked156.2972; cycle PnL was+0.0108, disposal PnL+0.0380 and unrealized
PnL+0.0070. M026 is `INCONCLUSIVE`, normalized below minNotional and not evidence
of live capacity. No rerun, M027, extension, day2, account, Testnet or live action
is authorized.

Latest OWNER authority creates M025 as a controlled order-size capacity curve derived
from immutable M024. Eleven independent scenarios Q=10 through5000USDC use the exact
same three-hour Jan1 tape, M024 FIFO/latency/order manager and proportional capital.
Only Q changes; physical book/trade quantities never scale. Growth pool is measured but
cannot add cells. A cycle requires full Q entry and full Q profitable return. The curve
must distinguish volume throughput from cycle throughput and may declare a knee only
with a >=20% adjacent cycle-rate drop plus an orthogonal fill/partial/timing signal.
Before execution, the scenario set required source-bound Astra PASS and a published
pre-run commit; both gates were satisfied. No M026, extension, account, Testnet or live
action is authorized.

M025's one published-source campaign (`7745600`) is now complete: all eleven Q scenarios
passed independent physical-ledger audit under campaign run hash
`a2ada49ad8c237ad8b41b7da9096b15e67c5005e81c31fc7ed6e2672090adc22`. Cycle rate
remained between11.33/h and12.33/h; Q500 closed35 cycles in3h and Q5000 closed37.
The preregistered capacity knee was not observed through Q5000. This does not establish
live capacity because the tape is exogenous, true L3 rank/impact are unknown and fees are
conditional. A reporting-only public-queue-zero attribution bug was corrected from the
preserved ledgers/checkpoints with no event replay; all economic metrics and the curve
remained identical, and the raw derived report is preserved. M025 is `INCONCLUSIVE`.
The limiting return-path mixture is not causally decomposed. Gate closed: no M026, day2,
mixed-base replay, account, Testnet or live action is authorized.

Latest OWNER authority creates M024 as a new three-hour normalized mechanics test and
preserves M023. The initial same-price triangle has75 funded BUY orders and75 funded
SELL orders: levels01–25 have two columns and levels26–50 one. `SIDE+PRICE` owns one
segmented public/own FIFO so later columns cannot copy the public queue or inherit old
priority. C2 retains its real activation age after C1 fills; a diagnostic causal branch
estimates the wait of a newly submitted replacement without changing execution. Initial
capital is74.9900USDT plus75USDC, marked at bid1.0019 for150.1325USDT. Profit may grow
depth only after a complete positive cycle and cannot turn USDT into USDC by bookkeeping.
The one-USDC size remains below Binance minimum notional. Code, tests and source-bound
Astra review must be published before the single authorized replay. No rerun, sweep,
M025, day2 or live action is authorized.

M024's only physical run used published source `74baeed`, then preserved its complete
ledger/checkpoint when the original process stopped on an auditor-only activation-state
defect. The corrected auditor at `82999f7` recovered the result read-only, without event
replay:35 complete positive cycles in3h (11.6667/h),9BUY-first and26SELL-first.
Initial74.9900USDT+75USDC marked150.1325; final77.0010USDT+73USDC marked
150.1616. Realized disposal PnL is+0.0108, completed-cycle PnL+0.0068 and unrealized
PnL+0.0183. C2 produced13 cycles; measured pre-aging benefit median82.204886s across
seven completed counterfactual pairs, with ten censored/rejected. Profit0.0068 did not
fund a new1USDC cell, so the triangle did not become a depth2 rectangle. The30-cycle
mechanics ruler passed, but M024 remains INCONCLUSIVE because1USDC is below Binance
minimum notional and M024 used about150.13USDT-equivalent versus about1.00 in M023.
No rerun, M025, extension, executable-notional run or live action is authorized.

Latest OWNER authority creates M023 as a three-hour serial hot-line mechanics probe.
Two persistent100-card virtual decks preserve BUY and SELL opportunities, while only
one physical order may be pending, active or cancel-pending. Completed economic legs
must alternate BUY then profitable SELL. When an executed card leaves the hot line,
the same-side edge card fills its address; unfilled cancels do not rotate. The one-USDC
quantity is below Binance minimum notional and remains non-live-executable. M022 and
all earlier published results stay immutable. Source-bound independent review passed
after two explicit BLOCK rounds. The one published-source run completed4 positive
cycles in3h (1.3333/h), with1USDC open at cutoff. Marked equity moved from1.0019 to
1.0022USDT equivalent: realized+0.0004 and unrealized-0.0001. There were no order
rejections or parallel fills, but3,397 queue-flow events consumed9,287,955USDC ahead
of the serial orders. Astra's factual review passed and recommends INCONCLUSIVE for
efficacy: the mechanism completed, but throughput is low and one-USDC is below Binance
minimum notional. Model hash remains
05e2674c64c3698b8d7725b7f24ee21724918067111c9207939c95fa1d2c8733; physical run
hash is8ad59193b69e8df88101a91f3a97a72fe003993f87f9b997cacbe09c2855c074.
Gate closed; no repeat, extension, successor or live execution is authorized.

Latest OWNER authority created M022 as a controlled order-manager comparison against
immutable M021. The single published-source run completed19 cycles in5h, exactly the
M021 baseline(delta0, multiplier1), so the manager hypothesis is REJECTED for its
primary throughput gate. BUY-first/SELL-first were5/14, with43 fill events. Final
balances were104.7089USDT plus95USDC; marked equity199.9084, realized PnL0.0056 and
unrealized PnL0.0178. The physical and independent audits pass. The main limiter was
18,492 EXIT post-only rejections: fixed S005-S007 return buys crossed the public ask;
the manager performed zero return preemptions. Only4.77% of active order-time was
within5 ticks of mid and11.01% within10. A final stdout serialization error occurred
after all physical artifacts were written; it is a presentation failure, not a replay
failure, and no rerun occurred. Physical run hash
389fef14f694c2e0af549fd1a23b03b96390d09243a32989dd90087396b05e35. Gate closed;
Day2, M023, sweeps and live remain unauthorized. The one-USDC orders are below Binance
minimum notional and cannot establish live performance.

Latest OWNER authority creates M021 as a new dense mechanical probe and leaves M020
immutable/REJECTED. M021 freezes anchor1.0020 from the first causal bridged L2 book,
registers100 BUY-first plus100 SELL-first one-USDC slots, and runs only the same first
five hours. The one-USDC unit bypasses minimum notional only and is not live executable.
Initial USDT is the exact99.6950 needed for all BUY entries; initial inventory is100USDC,
marked at bid1.0019 for total199.88500000. GPT-6 Astra source-bound review passed
conditionally after reporting/registration defects were corrected;62 focused tests and
the full suite passed. The single published-source replay completed19 positive cycles
in5h(3.8/h):4 BUY-first and15 SELL-first. Final balances were103.70680000USDT and
96USDC; marked equity199.90840000, realized PnL0.00510000 and unrealized PnL0.01830000.
Execution audit passed with no negative exits or liquidity reuse. Only10 of200 slots
filled and7 completed cycles; the path spanned only10 ticks. Owned buyback exits for
S005-S007 conflicted with lower resting SELL entries, producing self-cross/post-only
blocking. A post-run review hardened the rejected-status predicate, but comparison
proved all200 `ACTIVE_TIME_US` values already matched; no report or economic value
changed and no replay occurred. Physical
hash7508beca1ee232864027204c6e33a92191fe1725d42d2eccd82f7349815a05ae.
Registry M021 status is INCONCLUSIVE. The mechanism existed, but throughput was low
and the normalized order is not live executable. Independent post-run Astra review
is `PASS_FACTUAL_POST_RUN`. Gate closed; Day2/M022 remain closed.

Latest OWNER authority creates M020 as a five-hour zonal throughput diagnostic,
not a continuation or repair of M019. The fixed band geometry may use full-year
2025 canonical trade occupancy descriptively; D1 is therefore DEVELOPMENT and
not out-of-sample. Economic state remains hard-bounded to the first five hours.
M020 completed against the published preregistration with zero cycles and zero
fills. The bounded market traded from1.0017 to1.0027 while all immutable bands
were0.9994–1.0003, so the result isolates `PRICE_OUTSIDE_FIXED_P80_MAP`; it is
not evidence of queue rejection. Final marked equity was100.00980000 from
50.90690000USDT plus49USDC; realized PnL was zero and unrealized PnL+0.00980000.
The physical audit passed; registry status is REJECTED. Day2 and an executable
safe-min-notional repetition remain closed.

Latest OWNER authority supersedes the unexecuted three-range proposal. M019 is a
new12-slot(6BUY+6SELL) observed-L2 inventory ladder with shared capital/liquidity,
traceable lots, no reserve release and no realized loss. V1 freezes mid center,
one-tick offsets, small safe notional,60s/2tick free-quote refresh and90% projected
USDC cap. First run only2025-01-01; day2 remains closed. Preparation is underway;
registry identity, published preregistration and D1 result now exist. D1 produced
10 positive cycles and100.0252 marked final equity. Main observed bottleneck was
INVENTORY_LOCK coupled to exit queue:84USDC remained after an18.503h cycle
plateau. No successor is authorized and day2 remains closed.

Superseded unexecuted proposal changed the earlier research direction, not the completed M018
campaign above. It described three separate buy-low/sell-high ranges, no reserve, measuring
inactivity and cycles. First day only; no replay has started. OWNER confirmed
selling at HIGH only: no forced-loss exit,1h measured as alert rather than hard
liquidation. No loss budget has been authorized. The latest question asks how
many ranges cover90%of cycles; this is separate descriptive coverage research,
not permission to increase lanes, capital or days. Existing multi-queue code has pooled capital/reserve semantics
and is not a ready implementation of three independent native-L2 lanes.

## Latest OWNER correction — one day only

M018 completed its full authorized24h at2025-01-02T00:00Z.9positive cycles;
operating100.08910,reserve9.96040,total110.04950,net+0.04950. M017same-day
control12cycles,total110.09900. New passive admission removed BUY rejections
(2546→0) but worsened cycle count and net return. Three releases(2loss/1zero),
consumption0.04950,funding0.00990,unrecovered debt0.03960,minreserve9.95347.
Two strict2h violations,max2h+47.867ms. Terminal inventory0,workingBUY preserved.
All26fills/12settlements automated auditPASS; independent PASS_WITH_TRACE_CAVEAT.
RegistryM018REJECTED. One trace mislabeled the last trade cursor as book capture;
financial execution is valid. Source-only trace fix published after this run;
no rerun, no alteration of original source65b7fe6 or the economic artifacts.
No day2data loaded or extension. Physical run219acf9d02fbf954fa4c85342583c047749a87244172a63310441aa2e8279b48.
Registry run653012a073793292d9d21685fbda4193fe7e9af69759ebd55d3657bcbfda4703
is separately bound, not a replacement for the physical run hash.

Latest continuation authorizes support mechanisms and conditional1→2→3 progression
at1000 audited positive ordinary cycles in EACH day, with sustainable economics
and unchanged full strategy/state. Current authorized input remains day1 only.
After three qualifying days,2000/day is a new hypothesis restarting from day1.
OWNER canceled graphs/HTML; deliver cycles, operating,reserve,total. M018 changes
only passive BUY admission; preserves M0172h control while1h wording is unresolved.
M017 day1 independent physical audit and bounded reporter review passed; strategy
frequency target did not. Statements below describe the earlier stop-time authority.

The OWNER reduced12→3→2→1day and requires approval before any extension. The
M017 process was stopped; its original12-day run is INCONCLUSIVE because of
OWNER_SCOPE_CHANGE, not a technical invalidation or full-run economic failure.
Use only closed day1 for the current comparison, same prefix in both controls.
Physical evidence beyond day1 was produced under previous authority and remains
preserved/previously observed, not unused validation data. Do not resume it.
See owner-scope-stop.json in the M017 run directory. Engine checkpoint01 preserves
capital and orders, but whole-runner resume equivalence has not been demonstrated.
One-day M017:12 positive cycles, operating100.10692,reserve9.99208,
equity110.09900, net+0.09900; final prefix audit/report in preparation.
The executed deadline was2h. OWNER clarification is pending whether the new1h
means maximum simulated holding or delivery waiting time; neither interpretation
authorizes relabeling M017 as having already run a1h strategy.

## Closed synthetic results reconciled2026-09-08

Both physical summary.json files are COMPLETE with12 closed days and
PASS_AUTOMATED_ALL_FILLS/PASS_CONDITIONAL. Last progress.json snapshots still say
PENDING and are not the terminal authority. Conservative:17 positive cycles,
equity109.9764,reserve9.76532,5 releases,5 zero days,maxhold27.1199001464h.
Price priority:16 positive cycles,equity109.8843,reserve9.76568,5 releases,
9 zero days,maxhold132.0009854975h. Initial100+10,compounding,fees0 assumption.
Neither demonstrates target frequency or reserve sustainability. Synthetic holds
and returns are not continuous historical/live observations. These closed M015
results remain immutable.

## M016 closed2026-09-08; source44d75f9

12/12 days;19 positive cycles;8 releases(7loss/1zero); operating100.12132;
reserve9.78068(min9.78028); equity109.902; net−0.098; terminalFLAT.
Funding0.01348; consumption0.2328; FIFO debt0.22328;0/7 losses recovered.
Eight holds>2h; max119.997830754h; all12days below500/1000/2000.
Independent integrity review passed; strategy objectives failed. RegistryREJECTED.
See reports/usdcusdt/M016-completed-independent-audit.md. One20bps executable-cap
case is justified by the deadlineD2 autopsy; source/spec/review/publication gates
remain mandatory. No later case or optimal funding has been selected.

## Last preserved weekly result — not a monthly L2 replay

RESEARCH_PROTOCOL=WEEKLY_OWNER_GATED
ACTIVE_RESEARCH_MODEL=M015
CAPITAL_MODE=COMPOUNDING
INITIAL_OPERATING=100
INITIAL_RESERVE=10
RESERVE_FUNDING_RATE=10%
DAILY_TARGET=2000
NEXT_WEEK_AUTHORIZED=false
AUTOMATIC_EXTENSION_ALLOWED=false
RUN_ID=e1d151d432da788c2371aad5ef578cb12fe1368313832ad2bf478cac3ff6ab89
RUN_STATUS=COMPLETE
SIMULATION_TIMESTAMP=2026-01-08T00:00:00+00:00
OPERATING_BANK=100.656550000000000
RESERVE=9.954050000000000
TOTAL_EQUITY=110.610600000000000
FULL_FILL_CYCLES=73
NET_POSITIVE_CYCLES=73
NET_REALIZED_PNL=0.610600000000000
TOTAL_FEES_QUOTE=0E-13
RESERVE_FUNDING=0.072950000000000
RESERVE_CONSUMPTION=0.1189000000000
MIN_RESERVE=9.896050000000000
RELEASE_FILLED=3
ZERO_CYCLE_DAYS=0
MAX_HOLD_HOURS=17.873193385555555555555555555555555555555555555555555555555555555555555555555555555555555555555555555555555555555555555555555556
HOLDS_OVER_24H=0
FLAT_HOURS=86.810931767222222222222222222222222222222222222222222222222222222222222222222222222222222222222222222222222222222222222222222222
HOLDING_HOURS=81.189068232777777777777777777777777777777777777777777777777777777777777777777777777777777777777777777777777777777777777777777778
WORKING_ORDER_HOURS=167.99708988722222222222222222222222222222222222222222222222222222222222222222222222222222222222222222222222222222222222222222222
MAX_DRAWDOWN_PCT=0.089975706559229008167794695432233297009807352014955961890289621802113429374069001369630199846041568776430363801773521149289691783
EXTENSION_STATUS=AWAITING_MINIMUM_AND_AUDIT_GATE
VERDICT=MINIMUM_500_NOT_MET; WEEK_2_BLOCKED
NEXT_ACTION=Consultar autópsia e diagnóstico de capacidade no diário; semana 2 bloqueada pelo mínimo/auditoria.
FIXED_100_RESULT_NOT_OWNER_STRATEGY_RETURN=YES
RESEARCH_JOURNAL=docs/research/M015_JOURNAL.md

OWNER_GATE=Week2 preauthorized only after500 positive ordinary cycles each day plus audit.
M013=INVALIDATED_TECHNICAL_PRESERVED
MINIMUM_DAILY_TARGET=500
GATE_TO_WEEK_2=False
OBJECTIVE_COMPLETE=false
