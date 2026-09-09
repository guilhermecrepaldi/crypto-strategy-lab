# M022 independent factual post-run review

STATUS=PASS_FACTUAL_EXECUTION_WITH_REPORTING_CAVEAT
REVIEWER_MODEL=gpt-6-astra
REVIEW_DATE=2026-09-08
STRATEGY_THROUGHPUT_IMPROVEMENT=false
REPORTING_CORRECTION_REQUIRED=true
REPLAY_AUTHORIZED=false

## Economic conclusion

The single completed M022 run produced19 positive complete cycles in the same five
hours as M021:3.8/hour, delta0 and multiplier1. The manager package did not improve
the primary throughput metric. This is a valid measured null improvement, not an
invalid economic run and not a reason to rerun or alter parameters.

| Metric | M021 | M022 |
|---|---:|---:|
| Complete cycles | 19 | 19 |
| BUY-first / SELL-first | 4 / 15 | 5 / 14 |
| Fill events | 42 | 43 |
| Final total USDT | 103.7068 | 104.7089 |
| Final USDC | 96 | 95 |
| Final marked equity | 199.9084 | 199.9084 |
| Realized PnL | 0.0051 | 0.0056 |
| Unrealized PnL | 0.0183 | 0.0178 |
| Productive lanes | 7 | 9 |
| Self-cross rechecks | 183152 | 1 |
| Post-only rejections | 182 | 18493 |

Both began with99.6950USDT and100USDC, marked199.8850. Independent summation of
all43 M022 FILL records reconstructs104.7089USDT,95USDC and0.0056 realized PnL.
Final bid1.0021 gives199.9084 marked equity; the0.0234 increase equals realized
plus unrealized PnL. Total USDT includes reserved cash and buyback proceeds, not
only free cash. Fewer final USDC and more realized PnL are not more complete cycles.

## MAIN_LIMITER

MAIN_LIMITER=FIXED_RETURN_PUBLIC_POST_ONLY_CONFLICT_WITH_QUEUE_LIMITED_REMAINDER

Of18493 post-only rejections,18492 are EXIT orders and only1 is an ENTRY.
S005, S006 and S007 each account for6118 rejections; S004 accounts for138 and
S001 for1. S005's immutable BUY return is1.0024. Its first recorded rejection
has public ask1.0023; its last has ask1.0022. The return would cross the public
ask, so post-only correctly rejects it. S006/S007 returns at1.0025/1.0026 have
the same structural problem. Canceling another owned free quote cannot make a
publicly crossing limit order passive.

The manager submitted18516 return attempts but recorded only21 return activations
and19 return fills. It performed0 return preemptions and0 free cancels for return;
84 cancels were classified as floating placement,83 were acknowledged and1 was
still pending at cutoff. Therefore this run does not measure a realized benefit
from the cancel-for-return branch, although the free-entry conflict pattern changed.

Five obligations remain censored: S005-S007 have pending BUY returns, while S079
and S080 have active BUY returns at1.0020. Queue recorded15505 flow events.
The recorded market range remains1.0017-1.0027. Mean open orders159.8496585 does
not mean capital concentrated near the market: only4.7717484% of activated order-
time was within5ticks of midpoint,11.0065090% within10ticks, and the order-time-
weighted distance was40.9089389ticks. These quantify remaining distant coverage.

The limiter label describes physical constraints, not a counterfactual number of
cycles obtainable by removing them. Recheck/rejection counts are repeated attempts,
not independent market opportunities. No changed execution or alternative was run.

## Waits, ownership and physical checks

Completed-return wait from first entry fill: mean480.457389seconds,
median176.460433seconds and nearest-rankP952279.317512seconds. Five open claims
are censored; maximum cutoff age8139.594962seconds, about2.261hours. These are
not included as completed waits. Mean first-submission wait is0 because claims
can submit during the same reconciliation, but matching still waits for latency
and strictly eligible later trades.

The recorded combined audit is PASS_M022_MANAGER_LEDGER_EXECUTION_LIQUIDITY:
111777 rows,18779 submissions,43 fills,19 cycles and39742 trade deliveries.
Deliveries comprise38963 TRADE and779 TRADE_BLOCKED_FUTURE_BOOK records.
Every recorded trade consumption is nonnegative and does not exceed its original
quantity. The recorded base audit reconciles native causality, queue, ownership,
global one-use liquidity and zero negative exits. This review re-ran only the
read-only manager audit over the closed ledger/checkpoint; it passed. Terminal
restoration validates invariants and reproduces the original canonical state hash.
No historical economic replay or fresh raw-data audit was performed.

The checkpoint is finished with exclusive end1735707600000000us (05:00UTC);
last delivered logical event is1735707599939513us, before cutoff. The final
presentation does not require an invented market event exactly at05:00. The
runner's bounded delivery and completed-state evidence preserve the five-hour
window. There was no forced liquidation.

## Reporting caveats — do not rewrite physical evidence

1. SUM_ROUNDTRIP_CYCLE_PROFIT is physically reported as0.0014, but the independent
   sum of all19 CYCLE.profit records is0.0019: BUY-first0.0005 plus SELL-first0.0014.
   The inherited roundtrip_profit field accounts for the reverse direction; it
   was mislabeled as an all-direction sum. This requires a separately documented
   derived-report correction, not a rerun or financial-state change. The balances,
   realized PnL, cycle count and primary comparison above reconcile independently.
2. The disclaimer text inherits the M021 name, although the manifest, model hash,
   order mode and result identify M022. Its below-minimum-notional warning remains
   correct; the model-name text is a presentation defect.
3. Execution wrote the manifest, completed summary, terminal state and all-fill
   audit before the final __main__ json.dumps presentation. Decimal values in the
   returned metrics are not supported by that bare serializer; reconstructing
   the terminal metrics reproduces this TypeError without any replay. Classify
   the reported process failure as POST_WRITE_PRESENTATION_FAILURE. It does not
   invalidate or authorize repetition of the already written economic run.

## Evidence binding

Execution source: f826b1c09368457c9252874e3dcf85f67ba64ef6

Run identity: c0fc46cca5608cd09035bca7d34943b31d3cfc449f462bc7b1ead5e086fe763a

Directory: artifacts/usdcusdt/l2-monthly-samples/M022/OWNER_GATED_5H/PRICE_PRIORITY

```text
SHA256[summary.json]=a8b4f725379e63d511006d88a456ef53f155dea40cd1bceed2fac39c4d03b2ee
SHA256[terminal-engine-state.json]=fdaf3d2cd5e4dc265d3761d924a279299de9c16b81e2d24173fb3ca649f6601d
SHA256[all-fill-audit.json]=b982a85eac4388a41964ea3e1fcc63de69626e7b6c33603d24a15cbdcdc361ea
SHA256[execution-audit.jsonl]=620c58a6d6a82381e4dcfe48854ab35802db6217fd9b6ba5393ddb1f065cfb19
SHA256[run-manifest.json]=ef7610655f16994bff36b0a942800a7ffe1578d5ac9a7a6e9959a0953441e829
```

The inspected derived result was exactly equal to physical summary at review time.
Only this review file was created. Physical evidence and M021 remain unchanged.
No registry transition, source edit, gate change, commit or push was performed.

## Final scientific boundary

The factual execution evidence passes with the explicit reporting caveats above;
the proposed throughput improvement was not observed. One-USDC orders remain
below minimum notional with zero conditional fees and uncertain real L2 queue
rank. No profitability, live-executability or PnL-bound claim follows. No Day2,
successor, sweep or repeated run is proposed or authorized.
