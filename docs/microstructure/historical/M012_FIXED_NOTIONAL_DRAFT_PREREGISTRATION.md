# M012 — HIGH_UPTIME_DYNAMIC_RECOVERY

Status: SCIENTIFIC_DESIGN_APPROVED_BY_ROOT_BEFORE_REPLAY. Preregistered 2026-09-07.
This is a new model, not a modification of B10. Registry identity was checked through
`ModelRegistry().entries()` / `_next_model_id`: M001–M011 are occupied; M012 is next.
The root reviewer approved the policy and gates below before any M012 outcomes.
Implementation, independent review, tests, registration and publication remain execution gates.

## Authority, lineage and scope

OWNER: `docs/microstructure/HIGH_UPTIME_RECOVERY_OWNER_DIRECTIVE.md` (the root preserves
the exact attachment). Historical parent: B10_FROZEN / RRV2_H1_B10_F0, artifact
`097abdab8225038b091cb721bdd36bedb8a636c94bed1c87120adc0c9e10953a`.
M011's separate preregistration is occupied and is not this policy. M007 remains the
selector ancestor, not an executable control or an automatically promoted model.

B10 A completed before the new override was processed; B began and was stopped by the
root under the OWNER override. Preserve completed A and partial B; no remaining B10
profiles are authorized. The original price-path record is descriptive evidence, not
matched survivor identities or proof of actual fills.

One serial USDCUSDT operational lot; DEVELOPMENT only, 2026-01-01T00:00:00Z through
2026-09-05T23:59:59.783644Z exclusive. Initial operating bank100, reserve5, equity105 USDT.
First main experiment: FIXED_NOTIONAL_100. Compounding is a separate gated later study.
No private API, account keys, Testnet, live orders, leverage, grids, DCA or parallel lots.

## Reuse decision and execution evidence

- ADAPT `b10_reality.py` execution kernel by a separate explicit M012 policy subclass;
  preserve the frozen B10 file and behavior. Reuse queue, aggressor, latency, cancellation,
  filters, immutable checkpoint/trace conventions and exact128-digit accounting.
- ADAPT the existing causal M007 selector; do not invoke B10 `release_signal`, its10bps
  loss cap, one-hour recovery gate or old activity predicates in M012.
- ADOPT official IOC semantics: immediate available execution, unfilled remainder expires.
  [Binance Spot enums](https://developers.binance.com/docs/binance-spot-api-docs/enums).
- BUILD only the urgency/floor/protected-release policy and its audit metrics.
- REJECT deadline-manufactured fills, arbitrary raw-volume reuse, fake depth refresh,
  account-specific fee claims, and retrospective candidate selection.

Primary execution profile: existing B_REALISTIC_CONSERVATIVE from config SHA
`a77e0c67fdff8c618cbfc28fdd3d49d2fa831626560aed7fe1ec27007293537d`.
Reuse its measured conditional pilot parameters without new calibration or tuning:
queue2330544 USDC; order/cancel latency1179525us; refresh299570us; spread0.00001;
release depth1144901 USDC; extra release slippage0; maker/taker fee0 CONDITIONAL.
All other rule/envelope fields must be imported exactly from the hash-bound source;
numbers in this paragraph are not an alternative config authority.
The source contains current-pilot BBO proxies, not historical L2. Protected release prices
may be more permissive than B10's limits, but execution still uses only its existing
available depth: no deeper book levels are invented. Profiles A/B comparisons are not
paired controls when profiles differ. Fee10 remains a separately preregistered, later
gated sensitivity, not an assumed historical charge or permission to claim fee robustness.

## Exact capital and funding

Let C be operating cash, I remaining inventory cost basis, D dust cost basis, and R reserve.
Operating book bank O=C+I+D. Keep marked operating and total equity separately; cost basis
is not a liquidation valuation. Target T=.05O; protected floor F=max(0.00000001,.001O).
The0.1% floor is a prospective safety-design choice, not a measured optimum: initial F=.10,
leaving4.90 reserve available. No floor sweep is authorized.

Each completed serial lot, ordinary or forced, has realized NET P=sale_net-sold_cost.
If P>0, transfer exactly .05P from C to R, including profitable forced closures. Retain
.95P in operating cash. No funding from principal, notional, unrealized marks or transfers;
no target cap or funding suspension above5%. If a forced lot realizes P<0, cover exactly
-P from reserve only under the protected execution budget; do not hide loss in transfers.
No `min(deficit,R)` fallback is allowed. Ordinary nonpositive P is reported, never funded.
Release transfers conserve C+R; actual trading loss reduces total equity.

Without releases and other losses, R=5+.05ΣP and O=100+.95ΣP, so R/O approaches
5/95=5.2631578947%. After cumulative covered release loss L, target shortfall is
T-R=L-.0025ΣP. Thus1USDT consumed needs20USDT positive profit for absolute replenishment
but400USDT positive profit to recover the moving5% target. This severe sustainability
constraint is intentional evidence, not grounds to reduce the target after results.

A NEW entry requires C>=100; submit the largest filter-rounded quantity within exactly
100USDT budget, with the unused amount remaining cash. Cash below100 blocks a new entry
and counts downtime; never silently reduce the operational budget. A partial entry may
complete only the unused part of its original100 budget, never create a second lot.

## Urgency and causal decision

Age begins at FIRST actual BUY fill and never resets on partial fill, cancel, retry,
reselection or IOC expiry. Existing market processing order remains causal. A timer sees
only observations already available before that timer; raw canonical ordinal resolves ties.

1. Age<12h: normal fixed LOW/HIGH LIMIT_MAKER operation. No B10 recovery predicate.
2. 12h<=age<18h: EARLY_WARNING. At the existing one-minute decision clock, allow protected
   release only if the same causal24h M007 selector returns a DIFFERENT valid candidate
   with positive existing selector score and the protected exit below is currently feasible.
   This score is price-path evidence, not a probability of executable recovery. On a release
   decision cancel any working ordinary BUY/SELL; fills before cancel acknowledgement count.
3. 18h<=age<24h: HIGH_RELEASE_URGENCY. Cancel any ordinary order, including uncompleted BUY,
   and seek protected liquidation irrespective of destination, old range activity, old10bps
   cap or positivity of local realized P. Six hours is an execution opportunity window,
   not a liquidity guarantee. Absence of a new range never prevents an affordable exit.
4. Age>=24h: MANDATORY_UNLOCK. Continue the same best feasible protected exit, without
   relaxing reserve, filters or causal liquidity. Enter this state at24h exactly. If still
   operationally unresolved at any time strictly beyond24h, record HARD_LOCK_VIOLATION
   once per lot, with cause, deadline and eventually achieved exit. This record is permanent.

Schedule exact12/18/24h boundaries in the timer queue, including gaps with no trades.
Failed release attempts retry on each NEW eligible book epoch after prior IOC/cancel
acknowledgement, subject to existing rate limits. A reused source ID cannot replenish depth.
At18h and later never resume partial BUY accumulation. After a completed exit, select again
from the then-current causal prefix; do not force a stale12h destination. Reentry is later
than the exit/cancel acknowledgement and uses no event that already financed another fill.

## Protected executable release and partials

After cancellation acknowledgement, let q=floor_step(inventory), K=sold_cost plus the cost
basis allocated pro rata to q, N=sell_net already realized in this lot, and f=taker fee.
For escrow use F_guard=max(0.00000001,.001*max(O,O+sold_cost-sell_net)) and B=max(0,R-F_guard).
O+sold_cost-sell_net reconstructs the operating book bank restored after any prior partial
ordinary-sale deficit is covered. This protects against the floor rising on that transfer;
using only the already-reduced current O would be unsafe. Zero q, invalid book or filter
violations do not manufacture an order.
Required minimum price p_min=ceil_tick(max(exchange_min_price,(K-N-B)/(q*(1-f)))).
Check all existing price/quantity/notional/dynamic filters. Submit protected SELL LIMIT IOC
only if current valid bid>=p_min; f must be<1. IOC execution is at actual eligible prices
>=p_min after activation latency, never at the deadline's unobserved price.

Worst-case full residual loss W=max(0,K-N-q*p_min*(1-f)) must satisfy W<=R-F_guard.
Escrow this amount in reserve accounting while the order/cancel is unresolved; escrow is
not consumption. Recompute from actual inventory, realized sale proceeds and remaining
basis after each partial and before each retry. One serial order means no competing reserve
claims. Exchange rule changes may reject/expire an order but cannot authorize a worse price.
Validate R_after>=max(0.00000001,.001O_after) before final exact transfer;
any accounting violation is technical
invalidity, never permission to silently deplete reserve or truncate the deficit.

Partial liquidation remains the same lot, cost basis is allocated only to sold quantity,
fees are allocated exactly, and age continues. Unsellable remainder may not be swept into
settled dust merely to report a successful forced unlock. A forced release closes only when
inventory is zero or smaller than one quantity step; sub-step dust retains its quantity,
basis and mark in separate reporting. A remainder>=one step rejected by minimum notional
remains operationally unresolved, cannot open a new lot, and can trigger the24h violation.
Aggregate dust basis<=1USDT is an additional acceptance gate, not a hidden write-off.

If reserve or book cannot support an exit, record RELEASE_BLOCKED_BY_RESERVE / NO_LIQUIDITY /
FILTER_REJECTION as applicable and continue attempting under the same rules. No reserve
top-up, borrowing, unexpected stop or forced price-touch sale is authorized.

## Metrics and gates, frozen before replay

Intervals use microseconds and integrate state until cutoff, including censored open lots.
MOTOR_UPTIME=1-downtime/duration, where downtime is the UNION of (position age>12h) and
(flat operating cash<100). No double counting. This is readiness/lock uptime, NOT fill uptime;
also report time with working orders, active cycle days and cycles per operating hour.
Warm-up days remain in all calendar-day denominators; an incomplete current day is separate.

Report every OWNER reserve/uptime/cycle/release metric. In particular:

- Target/floor/ratio/current/marked operating bank; R initial/contributions/consumption/min/
  final; cumulative contribution-to-consumption ratio (UNKNOWN if denominator0).
- Rebuilding integrates R<.05O continuously, with start/end/censored episodes. Near depletion
  is entry into R<=2F, not every raw event. Record reserve-admissibility blocked episodes and
  predicate evaluation counts separately. Never R<=0.
- Full ordinary cycles and positive ordinary cycles separate from forced closures; report
  all-lot realized PnL and fees. Completed UTC zero days, active days, same-event historical
  B10 opportunity ratio (descriptive only), mean/daily/hourly rates.
- Hold max includes open lot age; P95/P99 nearest-rank completed lots and censored ages
  reported separately. LOCK_HOURS_GTx sums max(0,hold-x) for x12/18/24, with one open lot.
- Release signals, orders, partial orders, zero-fill IOC failures, completed forced lots,
  local losses and mean/P50/P90/max, exact reserve transfers and loss denominators.
- CYCLES_PURCHASED_PER_RELEASE_USDT and LOCK_HOURS_AVOIDED_PER_RELEASE_USDT remain UNKNOWN
  as causal quantities without an independently defined matched counterfactual. Report
  descriptively subsequent ordinary cycles until next release or cutoff per consumed USDT;
  do not label these caused or purchased cycles. No extra control replay is implied.

All gates are conjunctive for permission to propose the next compounding/fee study:

1. Full frozen interval completed and independent audit PASS_CONDITIONAL, first100 ordinary
   cycles plus ALL release signals/attempts/closures; raw source and ledger hashes verified.
2. HARD_LOCK_VIOLATIONS=0; LOCK_HOURS_GT24=0; MAX_HOLD<=24h (including current open lot).
3. ZERO_CYCLE_DAYS<=2 across248 calendar dates; MOTOR_UPTIME>=.95.
4. At least100 ordinary full cycles; NET_POSITIVE_CYCLES/FULL_FILL_CYCLES>=.95.
5. Realized NET_PNL_FIXED_100>0 and terminal bid-marked TOTAL_EQUITY>105 after all actual fees;
   dust basis<=1. No positive marks substituted for negative realized economics.
6. R_min>0; R_final>=.05O_final; cumulative contributions>=consumption. Reserve rebuilding
   failures are reported even if absolute equity rose. Target is not a hoarding objective:
   spending is allowed, but the cycle engine must demonstrate ability to rebuild it.

Any hard-lock violation is an immediate HARD_RESEARCH_FAILURE_SIGNAL and blocks acceptance;
it is not a technical error and does not stop the remaining authorized replay. Publish at
first24h,7days,30days and every violation plus material checkpoints. No outcome tuning,
selective months, early stop due poor PnL or silent invalidation. If all gates pass, verdict
remains conditional on execution evidence; no LIVE/TESTNET or production promotion follows.

## Required tests and pre-run gate

Test funding5% on ordinary and forced positive net; negative profit; moving target/floor;
floor budget with adverse prices/fees; exact equity conservation; zero-cash entry block;
first-partial age;12/18/24 boundaries; no fresh data; failed mandatory exit; remaining
minimum-notional lot; partial IOC+cancel race+fee basis; no repeated depth; target rebuilding;
same-timestamp causality; checkpoint/resume identity; fullspan/count integrity. A behavior
parity fixture must demonstrate unchanged inherited normal execution versus B10 kernel.

Run gate: registry M012 creation + hash-bound spec/config + root review + implementation +
tests + pre-execution commit/push. Spec source hashes are specified in M012_MODEL_SPEC.json;
derived run identity must include spec bytes and chosen complete execution profile bytes.
No changing source/code SHA on resume. Publication-only commits do not alter execution SHA.
