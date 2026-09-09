# M023 independent pre-run review — repaired source

STATUS=PASS_CONDITIONAL_PRE_RUN
REVIEWER_MODEL=gpt-6-astra
REVIEW_DATE=2026-09-09
ECONOMIC_REPLAY_EXECUTED=false

## Verdict

No remaining blocking defect was found in this candidate. This supersedes the
earlier BLOCK after explicit repairs; it does not erase those findings or represent
an economic result. Existing OWNER, registration, clean/published-source and
exact-one-run gates remain mandatory. Scope is M023 on 2025-01-01 [00:00,03:00).
No extension, successor or live execution is covered.

## Repairs and independent evidence

Reserved BUY quote is included in owned USDT/equity. Checkpoints bind window and
latencies. The loader directly selects18 native slices and supplies03:00 to the
canonical history iterator, rather than first collecting five economic hours.
Whole-file byte hashing is provenance verification, not later-event simulation.

Due activation during CANCEL_PENDING now rejects crossing/unknown coverage,
returns quote and releases the virtual card; later books cannot resurrect it.
A passive activation remains CANCEL_PENDING until ACK. Total realized profit now
includes every SELL fragment while cycle profit includes completed SELLs only.

Command:
```text
.venv/Scripts/python.exe -m pytest -q tests/test_serial_hot_line.py tests/test_run_serial_hot_line.py tests/test_model_registry.py
```
37 tests passed:21 M023 tests and16 registry tests. Additional read-only synthetic
checks reproduced the previous blockers:

- Full BUY then SELL quantity .4: realized profit .00004, zero cycles, and
  PASS_M023_SERIAL_HOT_LINE_LEDGER. Unfinished inventory remains accounted for.
- Crossing and outside-coverage activation during cancellation separately produce
  REJECTED_POST_ONLY and REJECTED_COVERAGE, zero quote reservation and no later
  activation of the rejected order after the book becomes valid.

The audit reconciles canonical fill sources, compatible direction/price, native
time after activation, activation-book upper bound, queue transitions, exact trade
consumption, one-order timeline, completed-side alternation, inventory/cost/cash,
equity and rotation counts. This is automated reconciliation, not exchange proof.

## Limitations and conditions

Only this review was edited. No historical loader or economic replay was invoked.
The one-USDC size bypasses minimum notional and is not live executable. Zero fees,
displayed-depth queue and compatible trade-through remain conditional assumptions.
The virtual200-card radar is not200 real opportunities; only one nonterminal order
can reserve capital or consume a print.

Partial fills create owned simulated inventory/cash but not completed legs/cycles.
Cancel-race residuals below historical step can block progress; no forced fill,
rounding or liquidation resolves them. Open orders/positions remain censored.
active_order_time_us means time with a nonterminal order, including pending and
cancel-pending, not exclusively fillable ACTIVE uptime. Completed-order waits
exclude unfinished orders; these denominators must remain explicit post-run.

M021/M022 differ in capital, inventory, parallelism and five-hour duration; their
whole-run results are not matched financial controls. This review certifies no
profitability, minimum cycle count, capacity or pessimistic PnL lower bound.

## Exact reviewed LF source bindings

REVIEWED_SOURCE_SHA256_LF[scripts/run_serial_hot_line.py]=23c80fe05ef36ba90e3f9cc10abf7ee493aa8cccfca297a231645f1ce330fc32
REVIEWED_SOURCE_SHA256_LF[scripts/register_serial_hot_line.py]=37037603d83b12a2f73dee1823376f38a4efcfd9f2a95098bd4a041112b9ecfa
REVIEWED_SOURCE_SHA256_LF[scripts/run_zonal_ping_pong.py]=b310fbbb781f89d41bb69bc09d09b922960570d99c9aae136953f6fbc3ab90d8
REVIEWED_SOURCE_SHA256_LF[scripts/validate_tardis_l2_samples.py]=6e6d2c799293da4fc6ef5debbf890236fbaa62f7420a047d71f11c532b037f99
REVIEWED_SOURCE_SHA256_LF[scripts/run_l2_monthly_samples.py]=68aafca8598cb70eb34fa4761c3111eac4f39ac33a7f2f482677714d7ec49c80
REVIEWED_SOURCE_SHA256_LF[scripts/run_high_uptime_recovery.py]=4ce00d03fd86d1c4c09db523e6b1c6fd4b6f01edd72899585151a0b8aa2e8186
REVIEWED_SOURCE_SHA256_LF[src/crypto_strategy_lab/microstructure/serial_hot_line.py]=f9bbb431755940c6c1094eb2399b5caef8b9377590c0083383ed33b6ad6c5cad
REVIEWED_SOURCE_SHA256_LF[src/crypto_strategy_lab/microstructure/zonal_ping_pong.py]=d8e91f08adc1a0e5a218f1e6feef9ac7543daac3e5a69f3d6d7af500262347ef
REVIEWED_SOURCE_SHA256_LF[src/crypto_strategy_lab/microstructure/data.py]=311de231b02c72f02b5e2e2444c74f7017e9e81b56f3977e5056b57cb4d19922
REVIEWED_SOURCE_SHA256_LF[src/crypto_strategy_lab/microstructure/tardis_l2.py]=1899a0b0d968296b2b9d9a6bba8a1f1602e0b34162b4ca4b7ecfdbe665f9490d
REVIEWED_SOURCE_SHA256_LF[src/crypto_strategy_lab/microstructure/recovery_reserve_study.py]=6a702dfcfd5130e5cb0308472f5e4237ced54abeff1670ec3623c6591e4045f9
REVIEWED_SOURCE_SHA256_LF[src/crypto_strategy_lab/microstructure/serial_replay.py]=8515862b88842565cfb99295da651521a27eef28290f0e2b0ca742851b924ab0
REVIEWED_SOURCE_SHA256_LF[src/crypto_strategy_lab/domain.py]=fa3a7839429b6b98a11c971ec79d796fc09207fa182f1629d527a86c7e77c5f5
REVIEWED_SOURCE_SHA256_LF[src/crypto_strategy_lab/ml/model_registry.py]=864e96864911cc56cf1233a09a91a0287592cf44225c2b9c0d65e1dbe6ab94c2
REVIEWED_SOURCE_SHA256_LF[tests/test_serial_hot_line.py]=8da294b90824354d5676b84aba8b805d5f5ddb6075199a810c520e6b33b78743
REVIEWED_SOURCE_SHA256_LF[tests/test_run_serial_hot_line.py]=85ccbc28f788eaf35942e7aa725c5d7eecadab737ba9803a02b3a5729a6e12df
REVIEWED_SOURCE_SHA256_LF[tests/test_model_registry.py]=ec75f26af7430e6b52d6414f233e44cc5ca767bf56ccca3ece328c7bd8cc9e3a
