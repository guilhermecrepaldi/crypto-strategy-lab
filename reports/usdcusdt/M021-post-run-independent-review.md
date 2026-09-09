# M021 independent factual post-run review

STATUS=PASS_FACTUAL_POST_RUN
REVIEWER_MODEL=gpt-6-astra
REVIEW_DATE=2026-09-08
STRATEGY_APPROVAL=false
ECONOMIC_REPLAY_REPEATED=false

## Verified result

The immutable five-hour M021 evidence and corrected derived report reconcile:

| Metric | Verified value |
|---|---:|
| Complete positive cycles | 19 |
| Cycles per elapsed hour | 3.8 |
| BUY-first / SELL-first cycles | 4 / 15 |
| Fill events / completed orders | 42 / 42 |
| BUY / SELL fill events | 19 / 23 |
| Slots with fills / completed cycles | 10 / 7 |
| Initial USDT / USDC | 99.6950 / 100 |
| Final total USDT / USDC | 103.7068 / 96 |
| Initial / final marked equity | 199.8850 / 199.9084 |
| Realized / unrealized PnL | 0.0051 / 0.0183 |

Final total USDT includes reservations and buyback escrow; it is not all free cash.
Independent summation of every physical FILL from the single initial endowment
reconstructs the balances and realized PnL above. Final bid 1.0021 gives equity
199.9084; equity change 0.0234 equals realized plus unrealized PnL. Sum of the
19 round-trip cycle profits is 0.0019, distinct from disposal-basis realized PnL.

The physical audit records `PASS_M021_LEDGER_EXECUTION_LIQUIDITY`, 241806 audit
rows, 421 submissions, 42 fills, 19 cycles and 39742 trade deliveries. The latter
comprises 38963 TRADE plus 779 TRADE_BLOCKED_FUTURE_BOOK events. Recorded audit
checks reconcile ownership, native causality, queue and global liquidity, with
zero negative exits. This review verified the audit-file hash and aggregated the
closed ledger; it did not rerun historical market processing or independently
redownload/rebind native data.

## Physical explanation and limits of attribution

Filled slots were B001-B003 and S001-S007. Productive counts were S002=6,
S001=4, S003=3, B001=2, S004=2, B002=1 and B003=1. Thus 190 slots never filled;
the recorded market range 1.0017-1.0027 spans ten historical ticks and leaves
the remote entries outside the observed price path.

S005, S006 and S007 each sold one USDC at 1.0025, 1.0026 and 1.0027 respectively
without completing a buyback. Their fixed BUY returns at 1.0024, 1.0025 and
1.0026 conflict with lower resting SELL quotes. Terminal active SELL orders
include S002 at 1.0022, S003 at 1.0023 and S004 at 1.0024. The ledger records
60666 self-cross rechecks for each of S005-S007, plus S004=1132 and S003=22.
These sum to 183152 manager rechecks, not independent missed opportunities.
There are additionally 182 post-only rejections and 18008 queue-flow events.

The descriptive limiter label is supported as a combination of narrow price
coverage and observed exit conflicts, not a quantified counterfactual claim that
removing one protection would produce a particular number of cycles. No such
alternative was executed or authorized. Queue also constrained compatible fills.

## Reporting clarification resolved

The initial post-run explanation incorrectly claimed that rejected orders had
inflated M021 active time. Exact comparison found all 200 ALL_SLOTS rows identical
between physical summary and derived report. All 182 REJECTED_POST_ONLY orders
had activation_evaluated_us=None, so the original predicate already excluded them.
The source delta from exact REJECTED matching to startswith(REJECTED) is defensive
reporting hardening only. It changed no observed active-time or economic value.

The corrected finalizer, derived metadata and autopsy now state this explicitly.
The append-only journal preserves and supersedes the inaccurate note. Registry
evaluation 9f8085e29a0e0ea5218628718ba714322f4c3c2c0620b62bf9bccc7865e72977
records FACTUAL_CORRECTION without replacing the run or changing its status.
The only preexisting physical-summary field changed in the derived result is
the descriptive MAIN_LIMITER; additional fields provide provenance and autopsy.

Checkpoint restoration validates invariants and reproduces its canonical state
hash. The reporting delta and existing execution fixtures passed 46 focused tests:

```text
.venv/Scripts/python.exe -m pytest -q tests/test_dense_ping_pong.py tests/test_run_dense_ping_pong.py tests/test_zonal_ping_pong.py tests/test_run_zonal_ping_pong.py
```

## Immutable evidence binding

Execution source: f430a07a416dc31e0b06a7198cd8f51fdd0b5a89

Physical directory: artifacts/usdcusdt/l2-monthly-samples/M021/OWNER_GATED_5H/PRICE_PRIORITY

```text
PHYSICAL_RUN_HASH=7508beca1ee232864027204c6e33a92191fe1725d42d2eccd82f7349815a05ae
SHA256[summary.json]=16bd9b7af2ee643409ec113e2239a17a7d5ff4fb5667e21e05405267c5f29a13
SHA256[terminal-engine-state.json]=d14b4c18f8f1429ba86bcb67856291410e7168f71b8d81c8f1b9a898d1b5ee8b
SHA256[execution-audit.jsonl]=7b8356aa43e1abb13ee9398b1f411e9fe673f2615e30809567578c5def28bf81
SHA256[run-manifest.json]=06f8493ee00a6a275ec95e18366c5f62e55d07a3277d6109b298ec3712ed3180
```

These byte hashes matched the derived evidence manifest before and after the
documentary correction. No physical artifact was edited by this review.

## Final boundary

Registry current_status(M021)=INCONCLUSIVE. NEW_REPLAY_AUTHORIZED_NOW=false and
AUTHORIZED_MODEL=NONE_M021_5H_COMPLETE; extension remains false. The mechanism
was observed at normalized one-USDC size, below minimum notional, under frozen
zero-fee and conditional queue/latency assumptions. This factual PASS is neither
strategy promotion, profitability evidence, a live-executability claim nor proof
of a PnL bound. No M022, Day2, replay or change to economic policy is proposed or
authorized here.
