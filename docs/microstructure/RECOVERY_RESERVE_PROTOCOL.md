# Recovery reserve v2 — protocolo canônico congelado

Status: PREREGISTERED_BEFORE_V2_RESULTS. Scientific review: GPT-6 Astra, 2026-09-07.
Scope: `USDCUSDT_EXHAUSTIVE`, `DEVELOPMENT` only, parent/champion/operator M007.
Target identity: M011, still unregistered until a robust region exists.

## Question and pre-result evidence

Can rare, fully funded small-loss releases keep the one-lot engine productive without destroying
total equity or the reserve? The physical M007 autopsy precedes this grid. Top 1/3/5/10/20 holds
conservatively explain 111/140/159/187/192 of 193 zero-cycle days and 57.90/72.78/82.85/
97.42/100% of lock hours beyond 24h. This concentration motivates low-frequency intervention;
it does not establish that a release avoids the later zero days.

The formal target is `ZERO_CYCLE_DAY_REDUCTION >= 95%`. Since M007 has 193 zero days, PASS
requires at most 9. The owner's `<=10` description is retained only as an approximation.

The partial v1 study at commit `515eddeb` is immutable superseded evidence. It completed 10/27
scenarios with skim 0/1/5%, which conflicts with the new fixed 2% authorization. It also exposed
Decimal28 rounding at extreme compounded capital. Its artifacts remain under their original
identity and are not inputs to v2 selection.

## Capital and accounting

- Operating bank starts at exactly 100 USDT and alone sizes the one operating lot.
- Recovery reserve starts at exactly 5 USDT and never buys, adds exposure, DCA, grids, or a
  second lot. Total initial equity is 105 USDT.
- Fair baseline is unchanged M007 100 plus an idle 5 USDT reserve. Canonical M007 100 remains
  visible separately.
- After an ordinary positive realized cycle profit `P`, reserve contribution is exactly
  `0.02 * P`; `0.98 * P` remains operating. Nonpositive profit contributes zero.
- A release loss is `inventory acquisition cost including modeled BUY fee - modeled net sale`.
  Release requires full coverage and transfers exactly that deficit. It restores the operating
  bank immediately before the position's BUY, not a fixed 100 and not marked equity.
- Transfers and skims are internal movements, never profit. Economic truth is operating cash +
  marked inventory + reserve.
- Financial arithmetic uses a local Decimal128 context. M007 candidate ranking retains its
  existing default Decimal semantics; the financial context may not leak into `_score`/`_select`.

## Frozen 18-scenario grid

No adaptive refinement is allowed after v2 results:

| Axis | Values |
| --- | --- |
| `RESERVE_SKIM_RATE` | fixed `2%` |
| `LOCK_HOURS` | `1`, `4`, `12` |
| `MAX_RELEASE_LOSS_BPS` | `2`, `5`, `10` |
| `MINIMUM_RESERVE_REMAINING` | `0`, `2.5 USDT` |

The first review is entry + lock age. Later reviews occur each 60 minutes. There is no additional
cooldown dimension. Loss caps stop at 10 bps; 50–100 bps are explicitly excluded peg-risk zones.

## Frozen causal release rule

At review timestamp T, every input below is computed from events with timestamp strictly before T.
An ordinary HIGH strictly before the review settles normally first.

1. Position remains open and meets the scenario age.
2. Last trade strictly before T exists and theoretical net sale produces a positive deficit.
3. Deficit is within the cap, reserve covers it fully, and reserve after transfer meets the floor.
4. The original range completed zero cycles in `[T-1h,T)`.
5. The canonical M007 24h selector's unforced winner is positive-score and different from the
   original range; the original is never excluded to force a switch.
6. That destination completed at least one cycle in `[T-1h,T)` and three in `[T-4h,T)`.

Record original and destination cycles, LOW visits, HIGH visits for 1h/4h/24h plus time since last
completed cycle. After release, remain FLAT, adopt the same causal winner and wait for its next
normal LOW. Never buy at the release price.

`RECOVERY_COST_IN_CYCLES` is deficit divided by the theoretical net profit of one destination
cycle using the quantized quantity affordable by the restored bank. It is causal price-path math,
not executable evidence. Eventual original HIGH, later cycles, replenishment and avoided-time
contrasts are `RETROSPECTIVE_DIAGNOSTIC_ONLY`.

## Metrics and conventions

The replay covers the entire frozen interval from 2026-01-01 through physical cutoff, without
economic early stop. Report cycles, cycle multiplier, zero/active days, fixed-24h operating uptime,
inventory-open share, lock hours, excess hours beyond 1/6/24h, max hold, p95/p99, monthly Jan–Sep
partial, drawdowns, intervention intervals and all reserve balances/flows/depletion/replenishment.

Primary `LOCK_HOURS = sum(max(0, hold - 24h))`; primary uptime is `1 - LOCK_HOURS / interval`.
This convention includes flat time and the first 24h of each hold, so it is not synonymous with
active cycling. Inventory-open share remains separate. Do not sum overlapping per-release
counterfactual avoided-wait horizons.

Burn and funding rates are reported per day, 30 days and 100k cycles. Efficiency denominators use
gross reserve USDT consumed, never consumption net of replenishment. Null denominator yields null.
Zero-day autopsy classifies a day without a fully covering inventory episode as
`FLAT_NO_COMPLETED_CYCLE`; it never invents a causing position.

## Gates, robustness and selection

Each eligible point must satisfy all of:

- cycles strictly above M007 and zero days strictly below M007;
- total final equity at least fair M007+5 plus 0.01 USDT;
- fixed-24h uptime improves and lock hours decline;
- maximum total-equity drawdown no worse than baseline +1 percentage point;
- total reserve funding at least total consumption, final reserve at least 5 and zero depletions;
- accounting, strict-prefix causality, deterministic restart, source/input hashes and complete
  evidence pass.

Target95 is a separate classification and never sufficient for promotion. A robust center and all
its existing immediate neighbors on lock/loss axes and the alternate reserve floor must pass.
An isolated pass is `PARAMETER_CLIFF` / `OVERFIT_WARNING`.

Predeclared maximin ordering across each center plus neighbors is lexicographic: greatest minimum
zero-day reduction; cycles; uptime; equity; hold-p99 improvement; fewer interventions; reserve
funding margin. Remaining ties prefer lower loss cap, longer lock and higher reserve floor.

No robust region means no M011 registration or full candidate replay. Complete valid evidence with
no region is REJECT; technical invalidity or incomplete reconciliation is INCONCLUSIVE. A region
only permits preregistration of one exact M011 config before its full replay. DEVELOPMENT replay is
verification, never independent validation.

## Evidence protocol

Milestone 1 publishes this protocol, physical M007 autopsy, precision correction, tests and Astra
review before any v2 scenario. Milestone 2 executes all 18 scenarios into a fresh hashed identity,
publishes lightweight reports/autopsy/dashboard, and obtains Astra review. Milestone 3 exists only
after a robust region: recheck M011 availability, register exact config/lineage, commit and push,
then full replay, decision and final push.

At no stage access VALIDATION, LOCKED_TEST, Testnet, Live, private account data or orders.
`EXECUTABLE_EDGE=NOT_DEMONSTRATED`; spread, queue, partial fills, latency, impact and liquidity are
unknown. M007 remains the frozen SHADOW operator and its strategy hash is never changed here.
