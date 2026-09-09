# M024 independent source-bound pre-run review — round 6

STATUS=PASS_CONDITIONAL_PRE_RUN
REVIEWER_MODEL=gpt-6-astra

## Scope and decision

No remaining blocking defect was identified in the reviewed M024 pre-run contract. This verdict supersedes the preceding BLOCK reviews only for the exact source closure below. It is an engineering/scientific preflight verdict, not an economic result or a promise of profitability, cycle throughput, live executability or target attainment.

The source closure contains exactly 24 runner-declared paths. Round 6 rechecked their LF hashes: only the triangular queue kernel and its unit tests changed since round 5; the other 22 bindings remained unchanged. Review of the repaired delta retained the still-valid earlier reviews of the unchanged dependencies, OWNER directive, model specification and preregistration.

## Blocker closure

The generic CANCEL_ACK path now classifies every partially filled ENTRY as a locked sub-step lot, regardless of whether cancellation originated from rolling or an owned-return conflict. The independently repeated counterexample (SELL 1.0001 and BUY 1.0000 at t1; BUY fills at t2; conflict SELL fills 0.4 before ACK; ACK processed at t13) now produces CANCELED_PARTIAL and SUBSTEP_RETURN_DEBT_LOCKED, count 1, cycles 0, encumbered proceeds 0.40004 USDT, and no fractional RETURN. Invariants pass.

Prior repairs remain present: exactly-one-USDC submissions; residual reservation released once; no full replacement of a partially filled canceled cell; SELL-first obligation proceeds segregated from unrelated OWN/GROWTH funding; protected asset basis; growth not double-spent as principal; native activation/current-book gates; segmented public queue plus own FIFO; globally one-use physical trade volume; separately isolated shadow counterfactual; causal rolling and deferred returns; source/config-bound checkpoints; independent physical-ledger audit and bounded three-hour inputs.

## Verification

Executed the focused M024, M023 and registry suite: **121 tests passed**. Ruff passed for the M024 kernel, runner, registration and two test modules. The original conflict-cancel race was independently rerun in memory and passed its locked-count, no-cycle, no-return and ownership checks.

The preceding reviewed snapshot additionally passed four bounded synthetic stress cases and two closed synthetic physical-ledger audits. Those checks are retained as delta evidence, not represented as reruns on historical data or as new strategy results.

No economic replay, historical input traversal, registration, gate mutation, Git operation, commit or push was performed by this review. Only this review file was edited.

## Explicit limitations and execution conditions

- TEST_SUITE_PASS != STRATEGY_PASS. The normalized minimum-notional exception, zero conditional fees, historical rule assumptions and unobserved true L3 priority remain explicit limitations.
- Queue pre-aging shadow results are conditional counterfactual diagnostics, not additional executable liquidity, realized profit or a guaranteed causal treatment effect.
- Sub-step lots may remain economically locked through cutoff. They must remain visible and must not become fractional orders, forced fills or completed cycles.
- Completed cycle profit, realized disposal PnL, unrealized PnL, capital encumbrance, open inventory and censored waits are distinct quantities. Their post-run reconciliation remains required.
- MAIN_LIMITER requires the physical post-run autopsy, not inference from a low cycle count.
- Only the frozen 2025-01-01 [00:00,03:00) developmental probe is in scope. Existing registry, publication, one-run and OWNER gates remain independently mandatory; this review does not open them or authorize extensions.
- Any later change to a bound source invalidates this binding until reviewed. Actual replay completion and its physical audit remain untested here.

## Exact source closure (LF SHA256)

REVIEWED_SOURCE_SHA256_LF[scripts/run_triangular_pre_aged_queue.py]=1bfc0dc80a447686eb3122b467a0b4673cf43c2d842e6fd4407e9f234d1f71b0
REVIEWED_SOURCE_SHA256_LF[scripts/register_triangular_pre_aged_queue.py]=ee8dea913c7747cb6240fc97268be12cd1605a926ff5cfaa19009b99dec72729
REVIEWED_SOURCE_SHA256_LF[src/crypto_strategy_lab/microstructure/triangular_pre_aged_queue.py]=88419e1615299d2d9847fb160dd4192fbcba94f91c87acb4b215fb062e25f601
REVIEWED_SOURCE_SHA256_LF[tests/test_triangular_pre_aged_queue.py]=941a56fd7c3c2df407338d04b68e654e1f191f333b23f79210bc3a943c9aa5bd
REVIEWED_SOURCE_SHA256_LF[tests/test_run_triangular_pre_aged_queue.py]=549b861605f092e5c57a0b772b19685992671010091f34d963882681f6fbb75d
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
