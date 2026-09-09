# M025 independent factual post-run review

STATUS=PASS_FACTUAL_POST_RUN_CORRECTED_REPORT
REVIEWER_MODEL=gpt-6-astra
STRATEGY_PASS=false
NEW_REPLAY_AUTHORIZED=false

## Scope and verdict

The preserved single campaign, its eleven independent scenario ledgers, corrected reporting and final registry projection reconcile. This is a factual evidence PASS, not a strategy or live-capacity approval. M025 remains INCONCLUSIVE. No historical engine event was replayed during this review; no M026, mixed-base experiment, Day2 or live execution is authorized.

Physical run hash: `a2ada49ad8c237ad8b41b7da9096b15e67c5005e81c31fc7ed6e2672090adc22`.
Published execution source: `7745600715bdc321a65296b67b0faba67cfe1b79`.
Each scenario uses the same 29,538 canonical trades in 2025-01-01 [00:00,03:00) UTC, with independent capital, orders and liquidity accounting.

## Independent checks performed

- Ran `.venv/Scripts/python.exe -m pytest -q tests/test_order_size_capacity.py tests/test_run_order_size_capacity.py tests/test_triangular_pre_aged_queue.py tests/test_run_triangular_pre_aged_queue.py`: 141 tests passed. TEST_SUITE_PASS != STRATEGY_PASS.
- Independently restored all eleven terminal checkpoints, called the pure metrics calculation, and ran `independent_scenario_audit` against each preserved physical ledger and the hash-verified canonical three-hour trade prefix. All eleven returned `PASS_M025_INDEPENDENT_SCENARIO_AUDIT`. No receive-book, receive-trade, finish or historical engine replay was invoked.
- Verified ledger and terminal file hashes before/after these read-only audits, manifest identity, raw/corrected run-hash equality, exact equality of every non-queue metric and the entire economic ANALYSIS, and nonnegative corrected queue durations.
- Reconciled every scenario's marked-equity change to realized disposal PnL plus unrealized PnL. Completed-cycle PnL is a separate sequence measure and must not be added again. Completed roundtrip quantity equals Q times complete cycles.
- After finalization, verified all 33 file hashes in REGISTRY.physical_file_sha256 and its aggregate hash. This manifest includes derived scenario summaries as well as immutable ledgers/checkpoints; it does not imply that reporting summaries were never corrected.

## Economic evidence

| Q USDC | Complete cycles | Final USDT | Final USDC | Final marked equity | Disposal PnL | Cycle PnL | Unrealized PnL |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 10 | 35 | 770.0100 | 730 | 1501.6160 | .108 | .068 | .183 |
| 50 | 35 | 3850.0500 | 3650 | 7508.0800 | .540 | .340 | .915 |
| 100 | 34 | 7831.3351 | 7169 | 15016.1069 | 1.080 | .660 | 1.7769 |
| 250 | 34 | 19682.0551 | 17819 | 37540.2569 | 2.700 | 1.650 | 4.4319 |
| 500 | 35 | 39433.3051 | 35569 | 75080.5569 | 5.450 | 3.350 | 8.8569 |
| 750 | 34 | 59184.4551 | 53319 | 112620.7569 | 8.100 | 4.950 | 13.2819 |
| 1000 | 35 | 78935.7551 | 71069 | 150161.1069 | 10.900 | 6.700 | 17.7069 |
| 1500 | 34 | 118067.5041 | 106939 | 225241.7699 | 16.500 | 9.900 | 26.5199 |
| 2000 | 36 | 157570.4041 | 142439 | 300322.7699 | 22.400 | 13.600 | 35.3699 |
| 3000 | 36 | 233569.9041 | 216439 | 450485.0699 | 34.500 | 20.700 | 53.0699 |
| 5000 | 37 | 389577.0041 | 360439 | 750808.9699 | 58.000 | 35.000 | 88.4699 |

Initial equity is 150.1325 times Q, comprising initial USDT 74.99 times Q and USDC 75 times Q. Thus larger absolute PnL and quantity require proportionally more capital.

Q500 completed 35 cycles (6 BUY-first, 29 SELL-first), 39 full entries, 35 full returns and 131 fill fragments. Initial equity 75066.25 became 75080.5569: gain 14.3069 = disposal 5.45 + unrealized 8.8569. Roundtrip quantity was 17500 USDC, or 5833.3333 per hour. At cutoff there were 141 open orders and one residual partial order with 431 USDC remaining; partial-locked capital was 69.1449 USDT.

No adjacent tested size exhibits the preregistered >=20% cycle-rate drop. `CAPACITY_KNEE_ORDER_SIZE=NOT_OBSERVED_UP_TO_5000_USDC` is supported under that definition. Q500's `OWNER_500_BOTTLENECK=NO` means no such threshold was observed, not that queue, partials, impact or capacity constraints do not exist. Rates remain 11.33–12.33 cycles/hour; Q5000 adds only two cycles versus Q10/Q50/Q500.

## Reporting correction and provenance

The original public-zero metric could assign a zero occurring after first fill or terminal ACK, producing negative durations. The correction accepts zero only in the eligible chronological ledger prefix, using ordinal rather than timestamp alone. Same-timestamp fill-then-zero and ACK-then-zero are excluded; zero-then-fill is included. Strict trade-through without an earlier observed zero remains missing, not an invented zero or a clipped negative duration.

Q500 now reports 62 observed public-zero orders: 56 later filled, six censored without fill; 19 first-fill orders lack a prior observed zero. Their omission from zero-to-fill duration estimates is explicit censoring/selection, not proof of zero waiting.

Original derived report is preserved as `reports/usdcusdt/M025-order-size-capacity-result-reporting-bug.json`, SHA256 `1423926232ca8a20e782384eeb92c6f3a8f18121c7e7b8985ecae136ceb96703`.
Final corrected-and-registered result SHA256: `a637e0e8923db89334c013a6e3b8d04b5eda3138270fb32ed5df96092ac8dde6`.
Final 33-file manifest aggregate: `602568620c20b51f20915906486cc448fba4326bb832641743d72f6c9fea3379`.

Reviewed recovery code restores checkpoints and recomputes reporting/audit without delivering historical events. Finalizer only records the already-completed campaign and derived metadata. The reported first finalization attempt stopped after the Q10 scenario append at an unsupported capital-mode enum, before run/status registration. The final physical registry contains exactly 11 SCENARIO_REGISTERED, 11 RUN_REGISTERED and 11 EVALUATION_RECORDED events for M025, with no duplicate Q10 run; current_status(M025)=INCONCLUSIVE. The finalizer retry reused the scenario identity and did not rerun the experiment.

## Limiter and limitations

MAIN_LIMITER=UNDETERMINED_RETURN_PATH_COMPOSITE
ORDER_SIZE_CAPACITY_KNEE_NOT_OBSERVED_THROUGH_Q5000

The corrected autopsy no longer identifies price recovery as a proven primary cause. Public-FIFO wait and completed-cycle duration medians describe different selected cohorts and cannot be subtracted or added to attribute a bottleneck. Price path, public return queue, own FIFO and deferred cancel time require per-lot phase attribution before ranking causes. The flat cycle-rate curve supports only the limited finding that increasing Q did not materially improve cycle frequency here.

This is one developmental three-hour exogenous tape, modeled rank/latency, a conditional zero-fee profile, and no endogenous market impact. Audit consistency does not validate actual exchange queue position or live capacity at Q5000. Future B250/B500/B1000 mixed-size recommendations are unexecuted diagnostics; no knee means their below-knee claims correctly remain unknown.

## Current reviewed reporting source hashes (LF-normalized)

REVIEWED_SOURCE_SHA256_LF[src/crypto_strategy_lab/microstructure/order_size_capacity.py]=fcc75d046b7be05e6d461a6cd0ac81d7106456974cca079ea79f56b6afbf8533
REVIEWED_SOURCE_SHA256_LF[scripts/recover_order_size_capacity_report.py]=95c9d7c2d81a1a8aaf39b43740f9654331f231db43577ab1929d0c8c5e5022ed
REVIEWED_SOURCE_SHA256_LF[scripts/finalize_order_size_capacity.py]=786cf33ea7a0047c077308b2f1ebe1fe77c64acc29aec4566fc1a8cacf780ebd
REVIEWED_SOURCE_SHA256_LF[scripts/audit_order_size_capacity.py]=63b60b65b6235cc783b3b4118cd50fff024dd6b2259697adcd6d6b637ddf5212
REVIEWED_SOURCE_SHA256_LF[reports/usdcusdt/M025-order-size-capacity-autopsy.md]=9042bb0e545a76a5df62e8a7e37cc19b2c774ba7df1d85da2e15ad9b2628a98f

These correction-source hashes do not replace the original published execution SHA or its immutable manifest bindings.
