# M020 independent scientific pre-run review

STATUS=PASS_CONDITIONAL_PRE_RUN
VERDICT=PASS_CONDITIONAL_PRE_RUN
REVIEWER_MODEL=gpt-6-astra
REVIEW_SCOPE=M020_NORMALIZED_DEVELOPMENT_2025-01-01_00:00_05:00_UTC_EXCLUSIVE
ECONOMIC_REPLAY_EXECUTED_BY_REVIEWER=false

## Conclusion

No remaining blocking defect was identified in the reviewed, source-bound M020 configuration after the corrections and bounded checks below. This is permission to satisfy the independent-review prerequisite, not a claim of strategy performance, live executability, or completed execution. Registration, explicit OWNER machine authorization, a clean published source snapshot, input-integrity checks and the canonical single-writer gate remain mandatory before execution. No second day or parameter sweep is approved.

M020 uses nine immutable contiguous bands, exactly one-USDC first legs (approximately one USDT), and bypasses minimum notional only. The frozen initial endowment plus cash totals 100 USDT-equivalent at the first valid bid. Completed BUY/SELL and SELL/BUY sequences are separate; initial endowment sales and partial legs alone are not cycles. Reverse proceeds remain segregated until the matching return leg completes. Disposal PnL and reverse roundtrip gain are different views and must not be added.

## Evidence and resolved findings

The review required and checked corrections to actual activation/native-time causality, post-only rejection, unknown coverage, cancellation latency, own-limit execution prices, partial-fill sequence aggregation, reverse-cycle recycling, escrow, free-entry versus owned-exit selection, chronological queue checks, independent financial reconciliation and exact inventory-cost ownership.

Inventory cost now uses exact cost layers instead of repeating rounded pool-average arithmetic. Returned reservations retain their owned cost. The reported pool-basis drift reproductions are regression fixtures. Persisted JSON checkpoints restore Decimal filled quantities and preserve the tested suffix; configuration is bound to the checkpoint.

Reviewer executed:

` .venv/Scripts/python.exe -m pytest -q tests/test_price_occupancy.py tests/test_zonal_ping_pong.py tests/test_run_zonal_ping_pong.py `

Result: 34 tests passed. The tests include geometry, cutoff, cancellation, fragmented forward/reverse cycles, post-only and native gates, queue/liquidity/financial tampering, exact-cost regressions and checkpoint persistence.

Additional in-memory adversarial checks used five fixed synthetic seeds (0 through 4), each with 200 book/trade pairs, finite decimal quantities in tenths, entry latency 1 and cancel latency 12. Each completed kernel invariant checks and the independent execution auditor. These were software fixtures, not market-data replay or strategy measurements.

The history iterator now stops after recognizing the first excluded timestamp; that sentinel is not delivered to the economic engine. Whole-archive byte hashing is integrity verification, not availability of its future events to decisions. Native economic ingestion is restricted to the first thirty slices and rejects out-of-window events.

## Conditions and limitations

- Full-calendar-2025 occupancy geometry is explicitly retrospective DEVELOPMENT selection. D1 is not out-of-sample. No annual tape is supplied to economic decisions.
- The transferred historical profile and zero-fee assumption remain conditional. This approximately-one-USDT normalization is below exchange minimum notional and is not live-executable.
- Observed L2 is not L3 queue identification. Strict trade-through remains a registered execution assumption, not proof of actual fills or a PnL bound.
- The four-by-four window is conditional on finite geometry, capital, ownership, coverage, post-only and self-cross constraints. Open inventory and shortages are valid possible outcomes; there is no forced liquidation.
- Source review and synthetic tests do not replace the post-run physical ledger/financial audit. A dominant limiter is left undetermined pending that autopsy except the explicitly descriptive outside-map case.
- The hashes below bind the exact runner SOURCE_PATHS. Any changed bound source requires delta review before a new execution. Model/spec/preregistration/OWNER/occupancy/profile/input publication bindings are additionally enforced by campaign preflight.

## Exact LF source bindings

REVIEWED_SOURCE_SHA256_LF[scripts/run_b10_reality.py]=90f6852a773ca678570c2347a95e6caa348f11b30811066155e1b18b96a33ff7
REVIEWED_SOURCE_SHA256_LF[scripts/run_high_uptime_recovery.py]=4ce00d03fd86d1c4c09db523e6b1c6fd4b6f01edd72899585151a0b8aa2e8186
REVIEWED_SOURCE_SHA256_LF[scripts/run_l2_monthly_samples.py]=68aafca8598cb70eb34fa4761c3111eac4f39ac33a7f2f482677714d7ec49c80
REVIEWED_SOURCE_SHA256_LF[scripts/run_zonal_ping_pong.py]=b310fbbb781f89d41bb69bc09d09b922960570d99c9aae136953f6fbc3ab90d8
REVIEWED_SOURCE_SHA256_LF[scripts/validate_tardis_l2_samples.py]=6e6d2c799293da4fc6ef5debbf890236fbaa62f7420a047d71f11c532b037f99
REVIEWED_SOURCE_SHA256_LF[src/crypto_strategy_lab/domain.py]=fa3a7839429b6b98a11c971ec79d796fc09207fa182f1629d527a86c7e77c5f5
REVIEWED_SOURCE_SHA256_LF[src/crypto_strategy_lab/microstructure/b10_reality.py]=4345ef764299d5414c29a9411fe00e613e02dac542f147e29064cf48b31bd4cb
REVIEWED_SOURCE_SHA256_LF[src/crypto_strategy_lab/microstructure/data.py]=311de231b02c72f02b5e2e2444c74f7017e9e81b56f3977e5056b57cb4d19922
REVIEWED_SOURCE_SHA256_LF[src/crypto_strategy_lab/microstructure/recovery_reserve_study.py]=6a702dfcfd5130e5cb0308472f5e4237ced54abeff1670ec3623c6591e4045f9
REVIEWED_SOURCE_SHA256_LF[src/crypto_strategy_lab/microstructure/serial_replay.py]=8515862b88842565cfb99295da651521a27eef28290f0e2b0ca742851b924ab0
REVIEWED_SOURCE_SHA256_LF[src/crypto_strategy_lab/microstructure/tardis_l2.py]=1899a0b0d968296b2b9d9a6bba8a1f1602e0b34162b4ca4b7ecfdbe665f9490d
REVIEWED_SOURCE_SHA256_LF[src/crypto_strategy_lab/microstructure/zonal_ping_pong.py]=2bf4c55e2dad462abc9da8821be959d5b8c3e19bc5725eb35e915a283e2f5395
REVIEWED_SOURCE_SHA256_LF[src/crypto_strategy_lab/ml/model_registry.py]=17bdeab57a8d684f70afbe6c11923cc7c7af35ae910af1700cd7054d6791136e
REVIEWED_SOURCE_SHA256_LF[tests/test_run_zonal_ping_pong.py]=3ba4ccc7414829c12d7e222b428d2efa6d05021b0db5fe6b6792ec3713a3c616
REVIEWED_SOURCE_SHA256_LF[tests/test_zonal_ping_pong.py]=bcd0e41b29d375cfdd97c72a1cf3bbda1a576f81c560cbd62781a1aa164fd513

