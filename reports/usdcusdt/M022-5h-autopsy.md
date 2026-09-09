# M022 — five-hour order-manager autopsy

STATUS=COMPLETE_REJECTED_NO_THROUGHPUT_IMPROVEMENT
EXECUTION_SOURCE=f826b1c09368457c9252874e3dcf85f67ba64ef6
PHYSICAL_RUN_HASH=389fef14f694c2e0af549fd1a23b03b96390d09243a32989dd90087396b05e35

## Controlled result

M022 completed19 positive cycles in five hours, the same19 as M021. The delta is
zero and the multiplier is1. The composition changed from4/15 to5/14 BUY-first /
SELL-first, but throughput did not improve. Final marked equity was also identical:
199.90840000USDT-equivalent.

## What the manager changed

It kept a mean159.8497 open orders under the160 cap, canceled84 free orders for
floating placement and reposted80. It used165 lanes and166 price levels, but only9
lanes completed a cycle. Only4.77% of activated order-time was within5 ticks of the
midpoint and11.01% within10; average distance was40.91 ticks.

Return-priority preemption was not exercised: zero preemptions and zero free cancels
for return. Therefore this tape does not demonstrate a benefit from that branch.

## Main limiter

`FIXED_RETURN_PUBLIC_POST_ONLY_CONFLICT_WITH_QUEUE_LIMITED_REMAINDER`

Of18,493 post-only rejections,18,492 were exits. S005, S006 and S007 generated
6,118 each; S004 generated138. Their fixed one-tick return BUYs crossed the public
ask and were correctly rejected as post-only. The manager repeatedly resubmitted:
18,516 return submissions produced only19 return fills. Queue limitations remained
secondary at15,505 blocked events.

Five return claims remained censored at cutoff. The longest age was8,139.595seconds
(about2.261hours). No cutoff liquidation or negative exit was invented.

## Accounting and reporting

Final balances were104.70890000USDT plus95USDC. At the final bid this equals
199.90840000; realized PnL was0.00560000 and unrealized PnL0.01780000. The physical
audit passed ownership, causality, queue and global one-use liquidity with no negative
exits.

The physical summary's inherited roundtrip field showed0.0014 because it accumulated
only SELL→BUY profits. The immutable19 CYCLE records sum to0.0019:0.0005 BUY→SELL
plus0.0014 SELL→BUY. This is corrected only in the derived report. A final stdout
serialization error also occurred after all artifacts were written; the economic run
was complete and was not repeated.

The result uses normalized one-USDC orders below Binance minimum notional. It is not
a live-executable performance claim.
