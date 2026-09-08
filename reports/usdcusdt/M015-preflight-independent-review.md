# M015 — independent scientific preflight

STATUS=PASS_CONDITIONAL_PRE_RUN

Reviewer: Astra, independent of the implementation. Scope: registered first week only, `[2026-01-01, 2026-01-08)` UTC, with December 31 causal warmup. No historical replay or market-data traversal was executed for this review.

MODEL_HASH=4231670b19b1ca5c2b5032b1476b83b3182d1463750ea944da5efb867d81a8fa
SPEC_SHA256_LF=5986b32e359103e5fb5950e685bddc7dba3dea2dc7dd2bcb91b0bf24fea06c46
PREREGISTRATION_SHA256_LF=4bee20299c4ea642615bff76ee778b3d7d3d1943941b4484e09b9657f7cc3c62

REVIEWED_SOURCE_SHA256_LF[src/crypto_strategy_lab/microstructure/high_uptime_recovery.py]=2f47b0b1c0f89a73156330f506002a7e64ef75f70ddb1622876053f0251fb489
REVIEWED_SOURCE_SHA256_LF[src/crypto_strategy_lab/microstructure/b10_reality.py]=4345ef764299d5414c29a9411fe00e613e02dac542f147e29064cf48b31bd4cb
REVIEWED_SOURCE_SHA256_LF[scripts/run_high_uptime_recovery.py]=4ce00d03fd86d1c4c09db523e6b1c6fd4b6f01edd72899585151a0b8aa2e8186
REVIEWED_SOURCE_SHA256_LF[scripts/run_continuous_multi_queue.py]=c8d879cce965d124c544bf808ed655ae8eae960a1d3ea7e74f8a936e6aeecd0e

## Scientific acceptance

The implementation matches the single registered delta: an ordinary order whose actual activation evaluation predates the raw print may infer queue clearance on a strictly through-price print with compatible aggressor. It fills at its own limit, bounded by raw quantity and remaining order quantity. Equality retains canonical queue depletion. A newly activated order cannot use its activation print for this inference; rejected orders cannot be rescued. Pending cancellation permits inference only before its effective timestamp. Releases never use this path.

Clearance is separately logged as an inference, not fabricated observed consumption of the external queue. The same raw print cannot be replayed or consumed by both equality and through-price branches. Partial orders retain their state and activation evidence through checkpoint restoration. Explicit model/priority flags and policy hashes reject cross-policy restoration. M014 matching defaults remain unchanged.

M007 selection, B10 release eligibility, reserve floor, exact loss coverage, compounding, fees, latency and initial queue parameters remain unchanged. This is **COUNTERFACTUAL_CONDITIONAL_PRICE_PRIORITY**, not verified historical L2, actual Binance execution, or a demonstrated correction of M014. The M014 fixed-queue throughput bound no longer applies to this changed premise; that does not establish feasibility of 500/day.

## Runner and evidence gates

Registered design/spec/preregistration binding validated against the physical M015 registry. The runner checks published source bytes and this four-source review, rejects existing run artifacts, and holds a campaign-wide single-writer lock. It derives only the authorized tape prefix, validates raw archive bindings, and reconciles raw price/time events including warmup. Reader bounds and daily checkpoints exclude future prints. Financial state is preserved rather than liquidated at the week boundary; failure handling preserves the last durable checkpoint and labels the uncheckpointed suffix untrusted.

The runner intentionally does not implement week-two continuation yet. Its first-week gate is fail-closed. Continuation requires every day's ordinary net-positive cycles >=500, independent audit, intact invariants, and separately reviewed/published orchestration preserving the economic kernel and complete state. Neither a weekly sum nor releases satisfy the daily minimum. No Jan8+ data access is approved by this review alone.

## Verification

Independent execution: 95 tests passed across `test_priority_trade_through.py`, `test_b10_reserve_weekly.py`, `test_b10_reality.py`, `test_high_uptime_recovery.py`, `test_high_uptime_runner.py`, and `test_continuous_multi_queue.py`. Ruff check passed for all four reviewed sources and the new priority tests. Fixtures include both sides, equality, wrong aggressor, activation timestamps, post-only rejection, cancellation boundary, partial fills, raw duplication, cross-policy rejection, production replay and checkpoint equivalence, plus ancestor treasury/runner invariants.

This PASS permits the registered conditional first-week experiment after publication gates. It does not certify economic success, 500/2,000 cycles per day, historical fill accuracy, or live trading. The post-run independent auditor must validate the entire ledger, required ordinary-cycle sample, all releases, and **all** trade-through fills/inferences as preregistered; that future audit is not certified here.
