# M023 — independent factual post-run review

STATUS=PASS_FACTUAL_POST_RUN
REVIEWER_MODEL=gpt-6-astra
RECOMMENDED_SCIENTIFIC_STATUS=INCONCLUSIVE
MECHANISM_OBSERVED=true
MAIN_BOTTLENECK=SERIAL_EXACT_PRICE_QUEUE_WAIT
ECONOMIC_REPLAY_REEXECUTED=false

## Scope and provenance

Reviewed the single closed M023 run on2025-01-01 [00:00,03:00) UTC, not a
new simulation. Source, registry, gate and physical results were not edited.

- Published execution source:68841b11f2bb27bc819d8f60715a8bf45e6dd7a4.
- Model hash:05e2674c64c3698b8d7725b7f24ee21724918067111c9207939c95fa1d2c8733.
- Run hash:9a3c978b9440b546339e1c2ba7965664881c80ab1fe7dc6243dd2fab413f8d15.
- Terminal state canonical hash:fdbbd6951560dc1ff8601f6138dc1b5f6861b1aac9495b963a20e23554a52db2.

All17 manifest source LF hashes matched the bytes read from that published Git
commit. The run identity hash was recomputed after excluding manifest evidence
and run_hash. Summary, derived reports/usdcusdt/M023-3h-result.json and standalone
all-fill-audit agree. Terminal canonical hash is valid and its embedded audit
equals execution-audit.jsonl row-for-row.

Physical directory:
artifacts/usdcusdt/l2-monthly-samples/M023/OWNER_GATED_3H/PRICE_PRIORITY.

| File | SHA256 of physical bytes |
| --- | --- |
| run-manifest.json | 517668050b1ab8da2b50dd12588600bbe053ca0e8533f9fede86ab442cb3ba34 |
| summary.json | 8523ee9101282d7cab0de62f151971db87bebe4829f176ebf546b5e695095900 |
| terminal-engine-state.json | 6880007d9ac5122c35dde60bd6f758eb9028185f5023a1e691d215b7d91b02dd |
| all-fill-audit.json | d6dc3a7419cc0dab83889507a4dc7d23568c43bcaec2ba7c5eadeb5509b40d83 |
| execution-audit.jsonl | a2da3f0067ba8899e7ae765fd3b2da6c9b8629ed8ed30ff86480be8a58584265 |

## Reconciled result

Four complete positive BUY→SELL cycles,1.333333333333333333333333333 per hour.
Each cycle earned exactly0.0001USDT. The nine full one-USDC fills strictly alternate
BUY,SELL,BUY,SELL,BUY,SELL,BUY,SELL,BUY: five BUYs and four SELLs. No partial fill,
negative exit, release, forced liquidation or parallel economic order occurred.

| Balance / result | USDT unless stated |
| --- | ---: |
| Initial cash, no initial USDC | 1.0019 |
| Final free cash | 0 |
| Final reserved BUY quote | 0 |
| Final inventory | 1 USDC |
| Inventory cost | 1.0023 |
| Realized profit | +0.0004 |
| Final executable-book bid mark | 1.0022 |
| Unrealized PnL | -0.0001 |
| Marked equity | 1.0022 |
| Marked change from initial equity | +0.0003 |

Ownership reconciles: cash + reserved quote + inventory cost =1.0023 =
initial1.0019 + realized0.0004. Marked equity includes reserved funds throughout;
the terminal zero cash is invested inventory, not disappearance of capital.
The marked gain is not a fully liquidated result or guaranteed future recovery.

The final order21 is ACTIVE SELL1USDC at1.0024, no fill. Its lot was bought at
1.0023. Terminal book bid/ask is1.0022/1.0023. Remaining simulated queue ahead is
202,725USDC; submission-to-cutoff censored wait is424.652283seconds. State WAIT_SELL
describes the unfinished economic obligation; the actual order status is ACTIVE.

## Event, liquidity and lifecycle checks

The run delivered29,538 unique canonical trades, IDs206597089 through206626626.
Their native times range1735689600006766 through1735700399068235; capture times
range1735689600009568 through1735700399070509. All lie before03:00.
Manifest selects exactly18 ten-minute slices, offsets0 through170. The final book
observation is1735700399939467; the cutoff marker is exactly1735700400000000.
The engine latencies are1,179,525microseconds for entry and cancellation.

The canonical history was read only through the existing iter_history(...,
end_exclusive=2025-01-01T03:00:00Z). Running independent_execution_audit over the
closed ledger, terminal and those official canonical trades returned
PASS_M023_SERIAL_HOT_LINE_LEDGER. This was ledger auditing, not rerunning strategy
decisions. No new raw L2 reconstruction or later economic interval was read.

-21 submissions and21 activations; maximum one nonterminal order.
-11 cancel requests and11 ACKs, all unfilled; no post-only/coverage rejection.
-Nine fills, all at the exact print price; zero trade-through fills.
-3,397 QUEUE_FLOW events consuming9,287,955USDC ahead of the simulated orders.
-28,953 ordinary TRADE rows plus585 TRADE_BLOCKED_FUTURE_BOOK rows.
-Nine virtual deck rotations, matching nine complete legs, not four cycles.

The audit reconciles each print's consumption to queue depletion plus our fill,
bounded by that print's quantity. Queue consumption is simulated ahead-of-us flow,
not our own trading turnover. Our actual filled quantity totals9USDC.

Independently applying each logged address/position swap to the original100BUY and
100SELL lattice exactly reproduced terminal card prices, positions and lifecycles.
The terminal decks contain199FREE cards and oneARMED card. Cancellation did not
rotate a card or count as an economic completion. Virtual cards supplied no capital,
queue position or extra fill eligibility.

## Bottleneck, waits and metric denominators

The dominant observed bottleneck is waiting behind exact-price displayed queues in
the enforced serial sequence, not order rejection or lack of virtual alternatives.
The first four filled orders alone waited:

| Order / side | Submitted-to-complete seconds | Activation queue USDC |
| --- | ---: | ---: |
| 1 BUY | 3429.131043 | 4272548 |
| 3 SELL | 1739.348099 | 2198441 |
| 5 BUY | 1551.639491 | 776742 |
| 6 SELL | 2860.726199 | 705166 |

For these orders the logged compatible exact-price flow exhausted those queues
before the one-USDC fill. This demonstrates a physical bottleneck in the stated
queue model, not that every second can uniquely be attributed to queue versus
absence of compatible prints. No causal counterfactual benefit from repricing or
relaxing the queue is estimated here. The terminal SELL also remains price/queue
constrained; its future outcome is censored.

Completed BUY waits: mean1008.117822seconds, max3429.131043seconds (n=5).
Completed SELL waits: mean1224.27315925seconds, max2860.726199seconds (n=4).
These statistics exclude canceled-order waits and the unfinished SELL.

A separate chronological reconstruction gave:

-No order:9.412998seconds, the initial unavailable-book interval.
-PENDING:24.826917seconds.
-ACTIVE:10753.709188seconds.
-CANCEL_PENDING:12.050897seconds.

Together they equal10,800seconds. The summary active_order_time_us=10790587002
means all nonterminal order time, including both pending categories; it must not be
called exclusively executable ACTIVE uptime. High order presence is not high cycle
throughput. Eleven reprices can reset queue position, but their marginal cost is not
identified by this single realized trajectory. Zero suppressed retries does not
contradict the absence of rejections: there was no rejected context to suppress.

## Scientific disposition

PASS applies to factual reconciliation and observation of the preregistered serial
mechanism. INCONCLUSIVE is recommended for strategy promotion/efficacy: four cycles
and positive conditional marked PnL do not establish an effective or executable
strategy. The preregistration specified no numerical rejection threshold, so four
cycles alone must not be relabeled a predeclared FAIL. No evidence here requires
technical invalidation of the completed run.

The order is normalized below minimum notional; fees are conditional zero, not an
account fact. Displayed-depth rank and price-priority behavior remain assumptions.
This is previously studied DEVELOPMENT data. M021/M022 have different starting
capital/inventory, parallelism and duration, so their full five-hour19-cycle totals
are not matched financial controls. No live profitability, superiority, high-cycle
capacity or PnL lower bound is proven. No Day2, extension or successor is authorized
by this review.
