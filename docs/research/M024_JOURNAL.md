# M024 research journal — triangular pre-aged queue

Append-only journal for `M024_TRIANGULAR_PRE_AGED_QUEUE_V1`.

## 2026-09-09 — OWNER authority and design review

- M023 remains immutable: four complete positive cycles in three hours, about99.9%
  order uptime, with public FIFO and price recovery as the observed limiter.
- OWNER authorized one new normalized mechanics test on the same Jan1 `[00:00,03:00)`
  prefix. M024 uses50 levels per side and an initial75+75 order triangle, with a second
  same-price order on the nearest25 levels.
- The one-USDC unit remains below Binance minimum notional. No live, account, extension,
  rerun, sweep or automatic successor is authorized.
- GPT-6 Astra reviewed the design before implementation. It required segmented/cohorted
  public FIFO for orders activated at different times, an isolated causal pre-aging
  counterfactual, exact capital disclosure and no conversion of USDT growth into USDC
  by accounting fiction.
- Frozen initial capital is74.9900USDT plus75USDC, marked at the first bid for total
  equity150.1325USDT. This is not capital-matched to M023; throughput and normalized
  capital efficiency must both be reported.
- Implementation, synthetic tests and source-bound pre-run review are in progress.
  No economic replay has started.
- OWNER clarified after the first draft: the minimum desired research size remains
  approximately one dollar per order (`1USDC` at this price), not the current5USDT
  Binance minimum. The model therefore remains explicitly normalized/non-executable;
  no five- or six-USDC substitution is permitted in this run.
- Quantity remains exactly `1USDC`. A partial below the historical step left by a cancel
  race is preserved as locked capital and cannot create a fractional order or cycle.

## 2026-09-09 — registered pre-run source

- M024 registered append-only with model hash
  `a2f1f9708f222ed0a984318a5fe0c56a44791f7f718bddc93bb24a91c4be6125`.
- The source-bound GPT-6 Astra review closed six adversarial rounds with
  `STATUS=PASS_CONDITIONAL_PRE_RUN`. It is not a strategy verdict.
- Relevant M024/M023/registry suite:121 tests passed. Ruff and `git diff --check`
  passed. `TEST_SUITE_PASS != STRATEGY_PASS`.
- No historical replay had started when this entry was written. The exact source must
  be committed and pushed to `origin/main` before the one authorized run.
