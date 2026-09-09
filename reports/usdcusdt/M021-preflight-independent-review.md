# M021 independent scientific pre-run review

STATUS=PASS_CONDITIONAL_PRE_RUN
REVIEWER_MODEL=gpt-6-astra
REVIEW_DATE=2026-09-08
ECONOMIC_REPLAY_EXECUTED_BY_REVIEWER=false

## Verdict and scope

No remaining pre-run blocker was identified in this source snapshot for the
single OWNER-authorized normalized mechanics probe, 2025-01-01 00:00 inclusive
to 05:00 UTC exclusive. This is approval of the reviewed experimental machinery,
not a passed economic experiment. Registration, exact-source publication, clean
published HEAD, explicit M021 gate, input-byte validation, and final all-fill
audit remain mandatory. No Day2, successor, live, or parameter sweep is approved.

The review covered the M021 directive, preregistration, model specification,
enumerated grid, canonical kernel and registry, registration and execution
paths, and their targeted tests. The unchanged M020 execution/audit dependencies
retain their prior reviewed semantics; their exact current hashes are bound below.

## Verified properties

- The registry read returned `get(M020).status=CREATED` and
  `current_status(M020)=REJECTED`. The former is the immutable creation snapshot;
  the latter correctly projects append-only status events. M020's published
  result and identity are not modified or promoted. Base-kernel changes preserve
  M020 decision/fill/accounting defaults and add observational fields; historical
  checkpoints remain evidence tied to their historical source, not a promise of
  cross-version checkpoint compatibility.
- The frozen grid validator passes all 200 exact entries and returns. The first
  valid book has bid 1.00190000, ask 1.00200000, midpoint 1.00195000; deterministic
  half-up quantization gives anchor 1.0020. Initial BUY funding sums exactly to
  99.6950 USDT. The single 100-USDC endowment marked at bid 1.0019 gives total
  initial equity 199.88500000, with no reserve or later injection.
- The subclass reuses the existing book, ownership/cost layers, queue, activation,
  cancellation, trade-budget and cycle authorities. Its fixed geometry and initial
  allocation are M021-specific. No submission precedes the first bridged book;
  the grid does not recenter. Initial entries exclude the anchor; only B001 and
  S001 prescribed returns reach it. Opposing orders are subject to self-cross
  prevention rather than internal fills or price changes.
- Reservations and partial fills retain exact Decimal accounting. A complete
  same-quantity two-leg sequence is required for a cycle. Reverse-sale disposal
  PnL and round-trip profit are distinct; endowment appreciation is not a cycle.
  Partial/cancel and exact cost-layer fixtures cover conservation and restoration.
- Activation-time post-only and observed-coverage checks, native book upper bounds,
  strict trade-native-time eligibility, resting-limit execution prices, and a
  single shared trade budget remain enforced. The independent auditor reconstructs
  submissions, activation, queue flows, fills, cycles, liquidity and financial totals;
  synthetic tamper fixtures exercise its rejection paths.
- The runner reuses the bounded five-hour physical iterators and does not authorize
  post-cutoff delivery or forced liquidation. Config-bound JSON checkpoint restoration
  and suffix equivalence are tested. Existing output directories fail closed.
- Reporting now separates funding shortage from unknown book coverage and leaves
  `MAIN_LIMITER=UNDETERMINED_PENDING_POST_RUN_AUTOPSY`; event counts alone do not
  identify the dominant cause. Canceled active-time accounting uses canonical status
  `CANCELED`. The registration grid-key mismatch found during review was corrected
  and its pure validation path is tested without registering a model.

## Checks performed

The final source passed all 62 focused synthetic tests using:

```text
.venv/Scripts/python.exe -m pytest -q tests/test_dense_ping_pong.py tests/test_run_dense_ping_pong.py tests/test_zonal_ping_pong.py tests/test_run_zonal_ping_pong.py tests/test_model_registry.py
```

Additional bounded synthetic book/trade sequences with fractional quantities,
three deterministic seeds, invariant checks, independent audit and persisted JSON
checkpoint equality passed. These were software checks, not historical replay
results. The frozen-design validator and exact capital arithmetic also passed.

## Explicit limitations

One-USDC orders intentionally bypass minimum notional and are not live-executable.
Zero fees and historical execution-rule transfer remain conditional assumptions.
L2 cannot identify actual individual order rank; no-cancellation-credit queue and
price-priority assumptions are not proven PnL bounds. Two hundred logical slots do
not demonstrate production order-limit compliance or operational headroom.
No-loss realized exits do not prevent mark-to-market loss or indefinitely locked
inventory. Initial inventory reserved to an unsold SELL slot is ownership, not a
new completed trade; slot active time is summed order-active time, not capital-
weighted utilization. Total capital differs from M020, so raw PnL is not a
controlled profitability comparison. Any throughput conclusion requires the
completed physical ledger and final audit; positive cycles alone show only that
the normalized mechanism operated under the stated assumptions.

## Reviewed source bindings

Hashes are SHA256 after CRLF-to-LF normalization. Any bound-source change requires
delta review before execution; the preregistration/spec/grid are independently
bound into the registered identity and published preflight.

REVIEWED_SOURCE_SHA256_LF[scripts/run_dense_ping_pong.py]=96ceaa817a30a7c4922b8a638f3b28d86339d2bec7ac9efd4e49775c9fad0e79
REVIEWED_SOURCE_SHA256_LF[scripts/register_dense_ping_pong.py]=9b93629e35e1f551f5a89d532d893dcb7f9d764577d75c821fb4808ad0f79297
REVIEWED_SOURCE_SHA256_LF[scripts/run_zonal_ping_pong.py]=b310fbbb781f89d41bb69bc09d09b922960570d99c9aae136953f6fbc3ab90d8
REVIEWED_SOURCE_SHA256_LF[scripts/validate_tardis_l2_samples.py]=6e6d2c799293da4fc6ef5debbf890236fbaa62f7420a047d71f11c532b037f99
REVIEWED_SOURCE_SHA256_LF[scripts/run_l2_monthly_samples.py]=68aafca8598cb70eb34fa4761c3111eac4f39ac33a7f2f482677714d7ec49c80
REVIEWED_SOURCE_SHA256_LF[scripts/run_high_uptime_recovery.py]=4ce00d03fd86d1c4c09db523e6b1c6fd4b6f01edd72899585151a0b8aa2e8186
REVIEWED_SOURCE_SHA256_LF[scripts/run_b10_reality.py]=90f6852a773ca678570c2347a95e6caa348f11b30811066155e1b18b96a33ff7
REVIEWED_SOURCE_SHA256_LF[src/crypto_strategy_lab/microstructure/zonal_ping_pong.py]=0703425a488c1f90b52d850ccd153bb5ed66a0af79b887b86e48d403513ec1a3
REVIEWED_SOURCE_SHA256_LF[src/crypto_strategy_lab/microstructure/data.py]=311de231b02c72f02b5e2e2444c74f7017e9e81b56f3977e5056b57cb4d19922
REVIEWED_SOURCE_SHA256_LF[src/crypto_strategy_lab/microstructure/tardis_l2.py]=1899a0b0d968296b2b9d9a6bba8a1f1602e0b34162b4ca4b7ecfdbe665f9490d
REVIEWED_SOURCE_SHA256_LF[src/crypto_strategy_lab/microstructure/b10_reality.py]=4345ef764299d5414c29a9411fe00e613e02dac542f147e29064cf48b31bd4cb
REVIEWED_SOURCE_SHA256_LF[src/crypto_strategy_lab/microstructure/recovery_reserve_study.py]=6a702dfcfd5130e5cb0308472f5e4237ced54abeff1670ec3623c6591e4045f9
REVIEWED_SOURCE_SHA256_LF[src/crypto_strategy_lab/microstructure/serial_replay.py]=8515862b88842565cfb99295da651521a27eef28290f0e2b0ca742851b924ab0
REVIEWED_SOURCE_SHA256_LF[src/crypto_strategy_lab/domain.py]=fa3a7839429b6b98a11c971ec79d796fc09207fa182f1629d527a86c7e77c5f5
REVIEWED_SOURCE_SHA256_LF[src/crypto_strategy_lab/ml/model_registry.py]=864e96864911cc56cf1233a09a91a0287592cf44225c2b9c0d65e1dbe6ab94c2
REVIEWED_SOURCE_SHA256_LF[tests/test_dense_ping_pong.py]=1efe2c38e47e0d757baaaf879af834e27037f5db7a0d8c7b974e63630421f1a1
REVIEWED_SOURCE_SHA256_LF[tests/test_run_dense_ping_pong.py]=aba7143672f5a4f280bc3b98d1f42172245dc485b629a5ebc84f716639929a3b
REVIEWED_SOURCE_SHA256_LF[tests/test_zonal_ping_pong.py]=bcd0e41b29d375cfdd97c72a1cf3bbda1a576f81c560cbd62781a1aa164fd513
REVIEWED_SOURCE_SHA256_LF[tests/test_run_zonal_ping_pong.py]=3ba4ccc7414829c12d7e222b428d2efa6d05021b0db5fe6b6792ec3713a3c616
REVIEWED_SOURCE_SHA256_LF[tests/test_model_registry.py]=ec75f26af7430e6b52d6414f233e44cc5ca767bf56ccca3ece328c7bd8cc9e3a
