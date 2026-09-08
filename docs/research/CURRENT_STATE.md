# CURRENT STATE

ACTIVE_EXECUTION_CAMPAIGN=USDCUSDT_L2_MONTHLY_SAMPLES
CAMPAIGN_STATUS=M018_COMPLETE_ONE_DAY; EXTENSION_GATE_FAILED
CAMPAIGN_EXECUTION_SOURCE_SHA=65b7fe6aebb91d6c01ee6ef92d90b7c26f84a83c
CAMPAIGN_ACTIVE_ENVELOPE=NONE
CAMPAIGN_QUEUED_ENVELOPE=NONE
CAMPAIGN_VERDICT=M018_REJECTED; INDEPENDENT_AUDIT_PASS_WITH_TRACE_CAVEAT
CAMPAIGN_PROGRESS_FILE=artifacts/usdcusdt/l2-monthly-samples/M018/OWNER_GATED_DAY1/PRICE_PRIORITY/summary.json
CAMPAIGN_JOURNAL=docs/research/L2_MONTHLY_SAMPLE_JOURNAL.md
CAMPAIGN_SCOREBOARD=artifacts/usdcusdt/l2-monthly-samples/M018/OWNER_GATED_DAY1/PRICE_PRIORITY/summary.json
CURRENT_OWNER_WINDOW=docs/microstructure/OWNER_GATED_REPLAY_WINDOW.md
APPROVED_COMPARISON_DAYS=1
EXTENSION_AUTHORIZED=false
CURRENT_ACTIVE_RESEARCH_MODEL=M018
MONTHLY_REPLAY_MODE=OWNER_GATED_DAY1
MONTHLY_CANDIDATES=21
MONTHLY_CSV_AVAILABLE=21
MONTHLY_VALIDATED_AT_OWNER_SELECTION=12
MONTHLY_SELECTED_FOR_CONSECUTIVE_REPLAY=1
MONTHLY_INITIALIZATION=ONCE_100_OPERATING_PLUS_10_RESERVE_PER_ENVELOPE
MONTHLY_ECONOMIC_REPLAYS_STARTED=5
MONTHLY_CONTINUOUS_WEEK_2_AUTHORIZED=false

OWNER_NEXT_RESEARCH=ADAPTIVE_STABLECOIN_LADDER_V1
OWNER_DIRECTIVE=docs/microstructure/ADAPTIVE_STABLECOIN_LADDER_OWNER_DIRECTIVE.md
NEXT_CAMPAIGN_STATUS=M019_REGISTERED_AND_REVIEWED; PRE_RUN_PUBLICATION_PENDING; NOT_EXECUTED
NEXT_CAMPAIGN_MODEL_HASH=24e5a43a63bc501b4d7fb13931c0fcc39219dedd9cc274e925d9055c33f6d347
NEXT_CAMPAIGN_HOLD_OBJECTIVE_HOURS=1_2_6_24_ALERTS_ONLY; PROFIT_ONLY_EXIT
NEXT_CAMPAIGN_FUNDING=0; NO_RESERVE_PROPOSED
NEXT_CAMPAIGN_INITIAL_TOTAL_EQUITY=100_USDT_EQUIVALENT; CAUSAL_APPROX_50_50_ENDOWMENT

Latest OWNER authority supersedes the unexecuted three-range proposal. M019 is a
new12-slot(6BUY+6SELL) observed-L2 inventory ladder with shared capital/liquidity,
traceable lots, no reserve release and no realized loss. V1 freezes mid center,
one-tick offsets, small safe notional,60s/2tick free-quote refresh and90% projected
USDC cap. First run only2025-01-01; day2 remains closed. Preparation is underway;
registry identity and independent review now exist; pre-run publication and the
economic result are still pending.

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
