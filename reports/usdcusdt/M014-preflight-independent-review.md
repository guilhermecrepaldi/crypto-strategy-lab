# M014 independent pre-run review

STATUS=PASS_CONDITIONAL_PRE_RUN

MODEL_ID=M014
MODEL_HASH=e612c45b069fef4c5c71cf092f76dadfa314476848e2663d6315693c7b953469
SPEC_SHA256_LF=03e7131f2ebefc3c08c30283829473d1ce22f8b4fefd57a18f7751b7790285da
PREREG_SHA256_LF=9740ae1014ed1d77d4c8c7ee30853894373a0af19aecc16d3e7a166bf5fe05a7
REVIEWED_SOURCE_SHA256_LF[src/crypto_strategy_lab/microstructure/high_uptime_recovery.py]=705dc59cf7386eeb3b70f9b88b24b56dece74ba85380a3d62b1ed717270b5645
REVIEWED_SOURCE_SHA256_LF[src/crypto_strategy_lab/microstructure/b10_reality.py]=4345ef764299d5414c29a9411fe00e613e02dac542f147e29064cf48b31bd4cb
REVIEWED_SOURCE_SHA256_LF[scripts/run_high_uptime_recovery.py]=634db734cee00365a9afc4729eb94269cd5987c34b7ca540c1780b8175e43478
REVIEWED_SOURCE_SHA256_LF[scripts/run_continuous_multi_queue.py]=c8d879cce965d124c544bf808ed655ae8eae960a1d3ea7e74f8a936e6aeecd0e

Independent source review completed after the implementer confirmed these sources stable.
This signoff permits the remaining publication/preflight gates for the first authorized week,
not economic approval, historical Binance fill certification or authorization to extend.

## Verified scope and authority

- Executable class is `crypto_strategy_lab.microstructure.high_uptime_recovery.B10ReserveReplay`
  in the expected repository file. It inherits B10 decisions, not M012/M013 urgency or M013
  allocation. Explicit F2.5 injection leaves historical bridge defaults unchanged.
- Registered model and model hash match the complete current spec and LF-normalized prereg.
  Execution profile B and its complete configuration remain hash-bound. Sources/dependencies
  must match published HEAD; these four review bindings are rechecked at launch.
- Initial operating100, reserve10, compounding, positive completed-lot funding10%, absolute
  floor2.5, exact executed deficit coverage and segregated dust match the design. Partial IOC
  deficits retain their claim; theoretical probe transfers never mutate the execution ledger.
- Weekly scope is exactly `[2026-01-01,2026-01-08)` UTC. Dec31 warmup is separate. The prefix
  helper derives/hashes the authorized slice; no later array suffix is traversed. Raw ID,
  timestamp, price and ordinal reconciliation covers warmup and execution. The expected
  2,489,204 execution records and last physical event are checked rather than inferred from
  iterable exhaustion. These physical checks have not been executed by this reviewer.
- The canonical campaign lock now covers preparation, registration and streaming regardless
  of output directory. This closes the identified output-local-lock race. Existing artifacts
  fail closed. Registry state also rejects an already running canonical model.
- All seven daily checkpoints precede the next raw event at/after their boundary. Finalization
  does not cancel, fill, reset capital or liquidate inventory. JSON checkpoints retain orders,
  costs, dust, claims, clocks and shared book budget. Journal/curve fsync precedes the atomic
  checkpoint; exceptions preserve the prior durable checkpoint and identify the suffix as
  untrusted. No automatic resume or extension is exposed in this first-week gate.

## Executed software evidence

Command: `.venv/Scripts/python.exe -m pytest -q -o addopts='' tests/test_b10_reserve_weekly.py tests/test_high_uptime_runner.py tests/test_high_uptime_recovery.py tests/test_b10_reality.py tests/test_b10_independent_audit.py tests/test_continuous_multi_queue.py tests/test_continuous_multi_queue_runner.py`

Result: **97 passed, zero failed**. Ruff passed on the four bound execution sources and the
M014 policy/weekly-runner tests. All fixtures are synthetic; no market replay, archive scan,
account access or exchange operation was performed by this reviewer.

New M014 fixtures verify100→100.90 operating and10→10.10 reserve after synthetic profit1;
floor protection; partial40/60 IOC exact coverage with JSON restart; policy mismatch rejection;
closed-day accounting; and F2.5 signal equality against the original runtime using actual
reserve10 and remaining inventory60, without live-ledger mutation. The genuine driver fixture
executes H1 signal→cancel/ACK→protected IOC→selected destination BUY. Its actual synthetic loss
differs from the theoretical trigger because the supplied envelope applies slippage; the test
does not substitute theoretical proceeds for actual fills. Ancestor regressions also pass.

## Conditions and non-claims

1. Publish this report, implementation, tests and registered design before execution. Changed
   bound sources require renewed review. Run-time physical preflight must still succeed.
2. B profile is a conditional public-pilot execution envelope, not historical L2 or verified
   account commission/queue/latency. This review does not certify unlimited capacity or fills.
3. The target is at least2,000 **ordinary full BUY/full SELL net-positive cycles in each of
   seven UTC days**. Releases, partials and attempts do not qualify. No target achievement,
   economic pass or prospective profitability is established by these tests.
4. Complete the authorized week without economic early stop. Preserve losses, rejects, open
   holdings and all releases. Working-order time is not automatically productive uptime.
5. Completed-run independent audit remains required: deterministic ordinary sample100 or all
   if fewer, with insufficiency explicit, plus every release/partial/escrow. The historical B10
   auditor alone cannot certify M014 funding10% and initial reserve10 without reconciliation.
6. Final status remains `AWAITING_OWNER_APPROVAL` regardless of results. January8 onward requires
   explicit OWNER approval; no automatic extension, parameter tuning or capital reset is approved.
