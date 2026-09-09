# M025 — independent source-bound preflight review

STATUS=PASS_CONDITIONAL_PRE_RUN
REVIEWER_MODEL=gpt-6-astra

## Scope and verdict

No remaining blocking defect was identified for the frozen eleven-scenario M025 historical-L2 passive-capacity study. This verdict supersedes the two implementation BLOCK rounds and the subsequently corrected stale future-base specification field only for the exact source hashes below. It is not a strategy, profitability, live-capacity or throughput-target approval.

The OWNER directive, model specification and preregistration freeze Q={10,50,100,250,500,750,1000,1500,2000,3000,5000}, the same 2025-01-01 [00:00,03:00) prefix, independent proportional initial capital, 150 initial orders, cap 200, unchanged M024 execution assumptions and disabled structural growth. The runner broadcasts each immutable market event to independent engines in ascending Q; no financial state, queue or consumed volume crosses scenarios.

M024's physical run, original identity, kernel and historical evidence are preserved. The reviewed implementation specializes its execution mechanics rather than substituting a different fill model. The audit operates in physical units and does not divide market or ownership quantities by Q.

## Prior blockers and repairs

1. The first simplified M025 auditor accepted altered latency, compensating negative cash/reservation balances and fabricated public activation barriers. The final auditor restores the full chronological physical reconstruction: scenario configuration, submissions, activation/cancel ordering, public segments, own FIFO, compatible prints and shared per-scenario trade quantity, reservations, lots, disposal/cycle PnL, terminal state and counters.
2. Decimal normalization by Q incorrectly rejected valid fragments for Q750/1500/3000 because divisions introduced repeating decimals. The normalization path was removed. The final auditor reconstructs directly at Q without epsilon, rounding or tolerance.
3. Capacity metrics now distinguish roundtrip USDC, two-way quantity/notional, completed orders and partial fragments, residual inventory, public/own queue quantities and timing distributions. Public-zero counts include reached-zero orders without fills, separately censored.
4. The future diagnostic uses exactly B250={750,500,250}, B500={1500,1000,500}, B1000={3000,2000,1000}. Spec and validator bind B250_B500_B1000_EACH_WITH_3X_2X_1X_SIZES_UNEXECUTED. None of those future mixed-size geometries is executed.

## Verification performed

Executed:
```
.venv/Scripts/python.exe -m pytest -q tests/test_order_size_capacity.py tests/test_run_order_size_capacity.py tests/test_triangular_pre_aged_queue.py tests/test_run_triangular_pre_aged_queue.py
```
Result: **140 passed**, repeated after the final documentary/validator delta.

Ruff passed for the M025 kernel, physical auditor, runner, registration and two test modules.

Additional independent, in-memory synthetic checks:
- Valid non-divisible one-USDC fragment reproductions isolated the earlier normalization failure; the final suite includes all eleven Q values and full fragmented cycles at Q500/750/1500/3000.
- Three 150-book/trade-pair deterministic price-walk fixtures at Q10, Q750 and Q3000 each completed kernel invariant checks and the full physical-unit independent audit.
- A synthetic-only Q1 comparative fixture produced identical M024/M025 common physical state after twenty book/trade pairs, excluding model configuration and diagnostic audit representation. This deliberately bypassed the M025 quantity constructor only inside the in-memory test; production M025 still rejects Q1. It was not an additional capacity scenario or historical replay.
- Q750 checkpoint restore after a partial fill, followed by the same remaining ENTRY/RETURN events, produced exact checkpoint equality, including ledger.
- Final spec/registration alignment and existing fail-closed owner/scenario/output fixtures passed.

The source closure below contains all 30 paths declared by the final runner. Unchanged M024 dependencies retain their previous review evidence; new M025 source, the quantity-specific physical auditor, tests and final deltas received focused adversarial review.

## Scientific interpretation and limitations

TEST_SUITE_PASS != STRATEGY_PASS.

A full cycle requires full Q entry and full Q profitable return. A canceled partial ENTRY stays locked without a fractional return, aggregate rescue, replacement full-Q order or counted cycle. This conservative policy can itself affect measured capacity and must remain visible in the post-run interpretation.

Initial capital scales with actual initial reservations; tape/public liquidity does not. Growth profit stays segregated but cannot expand cells. More volume or absolute PnL with larger Q does not by itself establish greater capital efficiency.

Cycle-rate retention and scaling efficiency are algebraically related when roundtrip quantity and initial capital scale with Q; they are not independent confirmations. The preregistered knee is a descriptive threshold on this one developmental path, not a statistical estimate of live capacity. Completed-only timing distributions have selection/censoring limits; open orders and reached-zero-without-fill counts must be reported alongside them. Strict trade-through may fill without a measured public-zero transition; absence of a zero timestamp is not permission to invent one.

The preregistered REALIZED_PNL alias means completed-cycle PnL. Realized disposal PnL and unrealized PnL must remain separately labeled; financial equity reconciliation must use disposal plus unrealized, not the cycle alias. Any final ranking must identify which PnL definition it uses.

The frozen zero conditional fee profile is not an account fact. True L3 rank and endogenous market impact are unknown/unmodeled. M025 measures historical flow under the frozen queue model, not live market capacity or a recommendation to deploy the required capital.

Existing source-publication, registry, exact OWNER gate and one-run/output guards remain independently mandatory. Any technical failure after market events requires preserving every reached scenario prefix; no automatic rerun. No Day 2, M026, size additions, mixed 3x/2x/1x execution or live action is authorized by this review.

No historical engine replay, registration, commit, push or physical artifact modification was performed. Only this review file was created.

## Exact reviewed source closure — LF SHA256

REVIEWED_SOURCE_SHA256_LF[scripts/run_order_size_capacity.py]=020cc493ca8889a05f1692a2875c99162139d42101dca7042189702be7e1e518
REVIEWED_SOURCE_SHA256_LF[scripts/audit_order_size_capacity.py]=63b60b65b6235cc783b3b4118cd50fff024dd6b2259697adcd6d6b637ddf5212
REVIEWED_SOURCE_SHA256_LF[scripts/register_order_size_capacity.py]=489e414f04d6619b0122e0f46e75eed77b485a1aeb8ad64dd05d378675755d21
REVIEWED_SOURCE_SHA256_LF[src/crypto_strategy_lab/microstructure/order_size_capacity.py]=1cf6aa7428140d3f82f0fc3d90928dbddb231b0ccc591d562b3d022ac8f4975e
REVIEWED_SOURCE_SHA256_LF[tests/test_order_size_capacity.py]=b2442106fd30a67c3716b870e9eacd304f41a41e93ba173f57a45e98e10d43b5
REVIEWED_SOURCE_SHA256_LF[tests/test_run_order_size_capacity.py]=c9ce1b7c9a76d2dac6879b8961b40811e4a2b254e7382eed2106ccce530daa7b
REVIEWED_SOURCE_SHA256_LF[src/crypto_strategy_lab/microstructure/triangular_pre_aged_queue.py]=88419e1615299d2d9847fb160dd4192fbcba94f91c87acb4b215fb062e25f601
REVIEWED_SOURCE_SHA256_LF[scripts/run_triangular_pre_aged_queue.py]=102c768517c6febe551ebe56dea4d372e72e59b0d6ce142c779161c5efa6fa4d
REVIEWED_SOURCE_SHA256_LF[scripts/register_triangular_pre_aged_queue.py]=ee8dea913c7747cb6240fc97268be12cd1605a926ff5cfaa19009b99dec72729
REVIEWED_SOURCE_SHA256_LF[tests/test_triangular_pre_aged_queue.py]=941a56fd7c3c2df407338d04b68e654e1f191f333b23f79210bc3a943c9aa5bd
REVIEWED_SOURCE_SHA256_LF[tests/test_run_triangular_pre_aged_queue.py]=c41cc102f5e485c6e3f8b83cdb7d61a30296b159e29fbeb9ed5b17a09a0b0bdc
REVIEWED_SOURCE_SHA256_LF[scripts/run_b10_reality.py]=90f6852a773ca678570c2347a95e6caa348f11b30811066155e1b18b96a33ff7
REVIEWED_SOURCE_SHA256_LF[src/crypto_strategy_lab/microstructure/b10_reality.py]=4345ef764299d5414c29a9411fe00e613e02dac542f147e29064cf48b31bd4cb
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
