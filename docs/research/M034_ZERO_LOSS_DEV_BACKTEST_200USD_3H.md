# M034 zero-loss development backtest — 200 USD / 3 hours

Identity: `M034_ZERO_LOSS_DEV_BACKTEST_200USD_3H_V1`.

Status: `PREREGISTERED_READY_FOR_ONE_SHOT`. This campaign is a one-shot
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

`NOT_RUN` — populated only after the one authorized execution.
