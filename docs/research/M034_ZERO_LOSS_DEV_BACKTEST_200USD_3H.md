# M034 zero-loss development backtest — 200 USD / 3 hours

Identity: `M034_ZERO_LOSS_DEV_BACKTEST_200USD_3H_V1`.

Status: `RECOVERED_FROM_COMPLETE_PREFIX`. This campaign is a one-shot
`DEVELOPMENT_DIAGNOSTIC_BACKTEST` on calibration data. It is not OOS, does not register
a strategy pass, and makes no live-profitability claim. It is independent from
`M034_OWNER_DIAGNOSTIC_FORWARD_3H_200USD`; the forward claim, process and outputs are
outside this campaign and must not be consumed, changed or restarted.

## Frozen experiment

- Venue and book: Binance Spot `USDCUSDT`; Kraken is `RETIRED_DISABLED`.
- Window: `[2025-01-01T00:00:00Z, 2025-01-01T03:00:00Z)`.
- Initial balance: exactly `200.00 USDT` and zero USDC in every independent scenario.
- Scenarios, in frozen order: maker fee per leg `F0=0`, `F1=1`, `F2=2`, `F5=5`,
  `F10=10` bps. F0 is only a mechanical upper bound/legacy comparison.
- Fee semantics: the maker fee is deducted from the received asset. Any quantity-step
  residue remains physical and prevents a full no-residue cycle; it is never rounded
  away. The taker contingency is 10 bps and only belongs to an authorized risk exit.
- Source: `2a895e5040a9bedd947ad329c1f7c46cfd783b7e`.
- Configuration hash:
  `d85a3bbe2017f77446cebfe67ee74eba7901372b9512554939bbdf667d4a185a`.
- Threshold-registry hash:
  `c2b239f6c89efd64ac22f755cbd76be756cd4c764869e6b99da9a7b246bede76`.
- Independent reviewer: `gpt-6-astra`; final verdict
  `PASS_FOR_DEVELOPMENT_DIAGNOSTIC_BACKTEST` after three published BLOCK reviews and
  their causal/accounting corrections.

The physical input is the already validated Binance tape used by M026: native sequenced
L2 plus individual public trades. The first three hours contain 71,222 BOOK events and
29,538 individual trades. The L2 CSV, validation record and trades ZIP hashes are,
respectively, `cd1fd610...a819305`, `9eb8bf9b...17ccd`, and
`80e7138a...1e572`. Candles, futures and aggTrades are not fill sources.

## Frozen diagnostic assumptions

All values below have provenance `OWNER_DIAGNOSTIC_ASSUMPTION`; none is historical
proof, an official M034 threshold or a value eligible for live promotion.

| Input | Value |
|---|---:|
| Minimum completion probability | 0.90 |
| Maximum expected lock | 300 s |
| Risk buffer | 2 bps |
| Maximum aggregate inventory exposure | 20 USD |
| Peg deviation threshold | 0.0025 |
| Minimum net edge | 1 bp |
| Tail-risk bound | 1 USD |
| Maximum spread | 5 bps |
| Minimum depth inside 10 bps | 1,000 USD |
| Minimum compatible flow over 60 s | 10 asset/s |
| Completion probability used | 0.90 |
| Expected lock used | 300 s |
| Execution cost | 1 bp per complete cycle |
| Adverse selection cost | 1 bp per complete cycle |
| Activation and cancel-ACK latency | 1,179,525 µs |
| Slot base | 10 USDT |
| Exchange rule assumption | tick 0.0001, quantity step 1, minQty 1, minNotional 5 |

The gross minimum decision edge is approximately `2 × fee_per_leg + 5 bps`: two fee
legs, 1 bp execution, 1 bp adverse selection, 2 bps risk buffer and the 1 bp minimum
net edge. The risk buffer is a decision margin, not a second cash debit.

## Physical and zero-loss invariants

Geometry remains seven ranks per side/book with C1 persistent and C2 opportunity.
Orders activate only after the frozen latency and a causal book whose native upper
bound reaches activation. Each individual trade quantity is consumed at most once per
scenario across touched ranks and C1/C2; own volume never becomes public flow. Capital
is released only after cancel ACK. A fill racing a prior cancel preserves
`CANCEL_PENDING` through the ACK and releases only its unfilled remainder.

Owned return has priority over new entry. Aggregate exposure includes entry reserves,
owned USDC and USDC reserved for returns. A normal cycle closes only after a complete
physical return to USDT with all attributable costs and no non-origin residue. Partial
positions remain protected, open and marked; one cycle's profit cannot offset another
cycle for the invariant.

Emergency negative exit requires the strict OWNER inequality and a peg trigger. It is
first signalled, waits 1,179,525 µs, and is re-evaluated on the current causal L2. Bid
depth is consumed once in a scenario-local shadow and is replenished only by a positive
subsequent observed L2 delta. The authorization is persisted in the ledger before the
reservation and fill. Any such exit increments `NEGATIVE_RISK_EXITS` and forces
`ZERO_LOSS_ECONOMIC_PASS=false`.

At cutoff, open long USDC is marked at the last causal best bid. The pass formula is:

`negative_closed_cycles == 0 AND negative_risk_exits == 0 AND marked_equity >= 200`.

Zero cycles with unchanged equity can satisfy that boolean mechanically but is explicitly
not evidence of productivity.

## Execution and evidence gate

The atomic claim is
`data/m034/M034_ZERO_LOSS_DEV_BACKTEST_200USD_3H_V1.claim.json`. Its existence consumes
the one shot even after a technical failure. The runner requires clean published
`main`, exact source hashes, configuration hash, input bindings and an independent
GPT-6 Astra PASS bound to the source closure. Success preserves result, cycle CSV,
equity checkpoints, negative-cycle report and per-scenario physical evidence including
ledger audit, fills, eligibility decisions, orders and terminal queue state. Failure
preserves the causal prefix and forbids rerun.

M026 is the descriptive prior on the same tape: 30 physical cycles, 90 slot-equivalent
cycles and 10 physical cycles/hour. It used different initial assets, geometry and a
virtualized minNotional, so the delta is descriptive rather than a causal architecture
effect.

## Result

The single economic campaign consumed all 100,760 causal events in each of the five
frozen scenarios. It then stopped in reporting because numerically zero accounting
residuals were serialized as `0.000000000`/`0.00000000` and compared to the literal
string `"0"`. The complete prefix was preserved with SHA-256
`1cd9447b39b40f9f1fa36753e3b021a2021ebb6e6b3ba8a3849be23bb41df178`.
Independent reconstruction matched every asset balance, ledger total and terminal
checkpoint. Results were therefore recovered by postprocessing only:
`REPLAY_RERUNS=0`, original failure preserved, `STRATEGY_PASS=false`.

| Fee/leg | Cycles | Cycles/h | Final marked equity | PnL | Return % | Negative cycles | Zero-loss |
|---:|---:|---:|---:|---:|---:|---:|:---:|
| 0 bp | 2 | 0.666667 | 200.007193700 | +0.007193700 | +0.00359685% | 0 | PASS |
| 1 bp | 0 | 0 | 200.00000000 | 0 | 0% | 0 | PASS* |
| 2 bps | 0 | 0 | 200.00000000 | 0 | 0% | 0 | PASS* |
| 5 bps | 0 | 0 | 200.00000000 | 0 | 0% | 0 | PASS* |
| 10 bps | 0 | 0 | 200.00000000 | 0 | 0% | 0 | PASS* |

`PASS*` means only that the frozen boolean is true: no negative cycle, no negative
risk exit and marked equity at least 200. The zero-activity scenarios provide no
evidence of productivity or executable profitability.

### Scenario metrics

| Metric | F0 | F1 | F2 | F5 | F10 |
|---|---:|---:|---:|---:|---:|
| Initial bank | 200 | 200 | 200 | 200 | 200 |
| Final realized equity | 200.007193700 | 200 | 200 | 200 | 200 |
| Final marked equity | 200.007193700 | 200 | 200 | 200 | 200 |
| Realized PnL | 0.007193700 | 0 | 0 | 0 | 0 |
| Unrealized PnL | 0 | 0 | 0 | 0 | 0 |
| Realized/marked return | 0.00359685% | 0% | 0% | 0% | 0% |
| Physical cycles | 2 | 0 | 0 | 0 | 0 |
| Slot-equivalent cycles | 2 | 0 | 0 | 0 | 0 |
| Positive / zero / negative cycles | 2 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 |
| Negative risk exits | 0 | 0 | 0 | 0 | 0 |
| Total maker fees | 0 | 0 | 0 | 0 | 0 |
| Execution cost | 0.001803150 | 0 | 0 | 0 | 0 |
| Adverse-selection cost | 0.001803150 | 0 | 0 | 0 | 0 |
| Capital utilization | 9.009327% | 0% | 0% | 0% | 0% |
| Idle capital | 90.990673% | 100% | 100% | 100% | 100% |
| Time-weighted locked inventory | 5.627669% | 0% | 0% | 0% | 0% |
| Maximum capital/inventory lock | 18.039600 | 0 | 0 | 0 | 0 |
| Final locked capital | 18.036903510 | 0 | 0 | 0 | 0 |
| Final residual inventory | none | none | none | none | none |

F0 cycle net PnLs were `0.003596940` and `0.003596760`; minimum, median and maximum
were respectively `0.003596760`, `0.003596850` and `0.003596940`. Its combined lock
sample (two completed cycles plus two open entry reservations at cutoff) had maximum
`10,187.415888 s`, P50 `5,325.3251145 s`, and P90/P95 `10,187.415888 s`. F1–F10
had no lock sample. The F0 final `18.036903510 USDT` was held in unfilled entry
reservations, not negative inventory; residual USDC and unrealized loss were both zero.

Each F1–F10 scenario recorded 997,108 candidate rejections with reason
`FEE_DUST_PREVENTS_FULL_RETURN`. Under received-asset fees, whole-unit quantity step
and mandatory no-residue return, 1 bp was already structurally ineligible. Therefore
the pure economic fee break-even is **not identified**. The frozen-grid admission
boundary lies between 0 and 1 bp/leg, and the maximum tested fee that produced a
physical cycle was 0 bp/leg. Minimum gross decision edge is `2f + 5 bps`, giving
5/7/9/15/25 bps for F0/F1/F2/F5/F10.

Mean F0 net PnL was `0.003596850` per cycle. Descriptively, holding that observed
mean constant would require 56, 279 and 557 cycles for +0.1%, +0.5% and +1% on 200
USDT. These are arithmetic rulers, not achievable-target claims. F0 net PnL per
initial-capital-hour was `0.0000119895 USD per USD-hour`; marked return averaged
`0.00119895%` per elapsed hour.

### Comparison with M026

M026 recorded 30 physical and 90 slot-equivalent cycles, or 10 physical cycles/hour,
on the same window. M034 F0 recorded 2 physical cycles: delta `-28` or `-93.3333%`,
and `0.6667` cycles/hour. F1–F10 recorded zero: delta `-30` or `-100%`. Because M026
used different initial assets, geometry and virtualized minNotional, this comparison
is descriptive and does not isolate architecture as a causal treatment.

### Evidence

- Canonical result: `reports/m034/M034_ZERO_LOSS_DEV_BACKTEST_200USD_3H.json`.
- Chronological cycle ledger: `reports/m034/M034_ZERO_LOSS_DEV_BACKTEST_200USD_3H_CYCLES.csv`.
- Seven time checkpoints per scenario: `reports/m034/M034_ZERO_LOSS_DEV_BACKTEST_200USD_3H_EQUITY.csv`.
- Negative-cycle report: `reports/m034/M034_ZERO_LOSS_DEV_BACKTEST_200USD_3H_NEGATIVE_CYCLES.json`.
- Independent post-run review:
  `reports/m034/M034_ZERO_LOSS_DEV_BACKTEST_200USD_3H_RESULT_REVIEW.json` (`PASS`, no
  pending P1/P2 and no replay by the reviewer).
- Original failure, complete physical prefix and recovery manifest remain under
  `artifacts/m034/M034_ZERO_LOSS_DEV_BACKTEST_200USD_3H_V1/`.

This development diagnostic rejects the productivity claim for the current frozen
formulation: the best mechanical upper bound produced two cycles and the first nonzero
fee scenario produced none. The individual zero-loss invariant held, but it did not
deliver competitive throughput. This is calibration evidence, not OOS, a strategy
pass or a live-profitability claim.
