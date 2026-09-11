# M034 Binance evidence pack

Status: `PUBLISHED_BLOCKED`; `READY_FOR_REPLAY=false`.

This pack was assembled after the ex-ante protocol in
`docs/research/M034_PRE_REPLAY_PROTOCOL.md` was published. No pair, date or window was
selected from PnL, cycles, edge or regime performance. No economic replay was run.

## Scope and methods

Economic venue is Binance only. Kraken is retired before all M034 economics and is not
part of this inventory. The candidate book authority is the existing M032
`CANDIDATE_BOOKS`, not a new hardcoded USDCUSDT-only universe.

Research used the repository's prior official-source captures and the `agent-reach`
routing procedure. The `agent-reach` executable and its Exa backend were unavailable;
the usable backend was authenticated GitHub CLI plus existing official-source/Jina
captures. The captured Binance announcement pages resolved to human-verification
challenges, so their summaries were not promoted to historical proof.

Authoritative public references:

- Binance documents current Spot filters, but not a historical per-symbol snapshot
  archive: [Spot filters](https://developers.binance.com/docs/binance-spot-api-docs/filters).
- Binance documents commission composition and a signed account-specific query; its
  examples are semantics, not historical rates:
  [Commission FAQ](https://developers.binance.com/docs/binance-spot-api-docs/faqs/commission_faq).
- Binance public data lists trades, aggregate trades and klines, not sufficient public
  historical Spot L2:
  [Binance public data](https://github.com/binance/binance-public-data).
- The official WebSocket specification defines current depth reconstruction and
  sequence handling, not historical client/order latency:
  [WebSocket streams](https://github.com/binance/binance-spot-api-docs/blob/master/web-socket-streams.md).

These references are adopted for semantics only. A current observation is never
back-projected into a historical interval.

## Structured artifacts and hashes

Hashes below are SHA-256 over the exact LF artifact bytes at registration.

| Artifact | SHA-256 | Meaning |
|---|---|---|
| `reports/usdcusdt/M034-pair-universe.json` | `b9637e30323b9da4885706b805ef7a482616eaab76224cb2b4e105eb1471d66d` | candidate books and per-stage state |
| `reports/usdcusdt/M034-binance-fee-evidence.json` | `ff25c6ff1b31c202f6b6779f1b0832053f0d9d3906df75a12bd1b6b003fa68da` | historical/forward fee distinction |
| `reports/usdcusdt/M034-binance-rule-evidence.json` | `ed7b810c5541cdc208ff12f974884d3d3bdba6ad696d6c2124db475e855f73ef` | historical/forward symbol-rule distinction |
| `reports/usdcusdt/M034_BINANCE_DATASET_MANIFEST.json` | `31307132cd9227f6e85d0ac453396d3b679ca0bd9758b9183c77d6c77b81b6fa` | physical L2+trades inventory |
| `reports/usdcusdt/M034-dataset-role-registry.json` | `ad23787f86e4429f7ea58e590cb80b8a4ef6c7ef51a2685186b6493ce2da4ec4` | calibration/OOS roles |

`PAIR_UNIVERSE_HASH=b9637e30323b9da4885706b805ef7a482616eaab76224cb2b4e105eb1471d66d`
`FEE_EVIDENCE_HASH=ff25c6ff1b31c202f6b6779f1b0832053f0d9d3906df75a12bd1b6b003fa68da`
`EXCHANGE_RULES_HASH=ed7b810c5541cdc208ff12f974884d3d3bdba6ad696d6c2124db475e855f73ef`
`DATASET_MANIFEST_HASH=31307132cd9227f6e85d0ac453396d3b679ca0bd9758b9183c77d6c77b81b6fa`

## Pair universe

Seven canonical candidate books were inventoried: USDCUSDT, FDUSDUSDT, FDUSDUSDC,
USD1USDT, USD1USDC, TUSDUSDT and USDPUSDT. Only USDCUSDT has local physical L2 and
individual-trade units. The other six have zero data-eligible dates and are not silently
discarded or labeled economic candidates.

USDCUSDT is available and has 12 data-eligible days, but has
`FEE_ELIGIBLE=false`, `RULES_ELIGIBLE=false`, `SAFETY_ELIGIBLE=false`, and therefore
`ECONOMIC_CANDIDATE=false`. The frozen economic candidate list is empty.

## Physical dataset

The existing validator inventories 21 first-of-month UTC units from 2025-01-01 through
2026-09-01. Twelve pass native sequence, normalized binding, trade binding and coverage
gates. Nine are rejected; no gap tolerance or clipping was introduced. The manifest
records every eligible file's path, byte size, SHA-256, event counts, coverage bounds,
initial unavailable interval and validation hash, plus the failed gates for rejected
units.

Physical source semantics are Tardis free native Binance depth with initial snapshot
and sequence-validatable deltas, bound to individual Binance public trades. Aggregate
trades and OHLC were not substituted. The 12 validated units are:

`2025-01-01`, `2025-02-01`, `2025-03-01`, `2025-04-01`, `2025-06-01`,
`2025-08-01`, `2026-01-01`, `2026-02-01`, `2026-03-01`, `2026-04-01`,
`2026-05-01`, and `2026-07-01`.

This is data eligibility only. `dataset_frozen_for_replay=false` because there is no
economic-eligible or OOS unit and no final window.

## Fee evidence

No data-eligible historical unit has a date-bounded `PROVEN_HISTORICAL` record for the
exact pair, maker/taker intent, account/tier/promotion context and fee-debit asset.
Current ordinary fee-table values are preserved only as `PROVEN_FORWARD` reference and
are not applied to historical data. The signed account commission endpoint was not
accessed.

Result: `HISTORICAL_FEE_ELIGIBLE_UNITS=[]` and `FEE_EVIDENCE=UNPROVEN`.

## Symbol and exchange-rule evidence

The captured public exchangeInfo response from 2026-09-07 is a valid forward observation
for USDCUSDT. It reports, among other fields, tick size `0.00001000`, step size
`1.00000000`, quantity limits, and a `5.00000000` minimum notional. It does not prove
those values at historical timestamps.

The existing timeline contains partial dated tick evidence but lacks full historical
continuity for symbol status, quantity, price, notional and dynamic filters. A partial
tick timeline cannot validate the complete rule set.

Result: `HISTORICAL_RULE_ELIGIBLE_UNITS=[]` and
`EXCHANGE_RULE_EVIDENCE=UNPROVEN`.

## Calibration/OOS separation

All 12 physical data-eligible units were already exposed to M016-M030 development,
execution or reporting. They are therefore irreversibly `CALIBRATION` for M034.

`CALIBRATION_SET_HASH=694752eb0f83ce10315e7cfffdb86dea5601c60ea92373d5821dbfb508f814a0`

There is no independent physical L2+trades unit. Consequently:

`VALIDATION_OOS_POOL_HASH=null`
`VALIDATION_OOS_POOL=[]`

No normalized copy, alternate filename or new model identity can restore OOS status.

## Estimators, execution cost and latency

`reports/usdcusdt/M034-estimator-readiness.json` records every required estimator as
`NOT_CALIBRATED`; SHA-256
`346243d2875d0976e28ae0b4450f64a73dac157d2fb1d7b4f47fc12b70a72708`.
Suitable joint completion/lock outcomes are unavailable without a prohibited economic
replay, and no censoring method, adverse-selection label contract or execution-cost
population has been frozen.

`reports/usdcusdt/M034-latency-execution-policy.json` leaves each latency/cost component
explicitly `UNKNOWN`; SHA-256
`2ef87111fd3e0c94a9ea79d007c9b86870afbde38669e07476c54bcdf890b348`.
Zero latency and zero cost are not authorized.

## Disposition

- `ADOPT`: official filter/commission/depth semantics; existing physical validators.
- `ADAPT`: current M032 data inventory to book+date evidence and semantic role identity.
- `INSPIRE`: survival analysis only after a method and labels are independently justified.
- `BUILD`: an OOS acquisition path, complete historical evidence, frozen estimator/cost
  artifacts and integrated runner.
- `REJECT`: current-to-historical extrapolation, captcha text as evidence, OHLC as L2,
  aggregate trades as public queue, and observed M034 performance as selection input.

`READY_FOR_REPLAY=false`
`ECONOMIC_REPLAY_RUNS=0`
`STRATEGY_PASS=false`
