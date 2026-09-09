# M022 research journal — order manager V2

Append-only journal for `DENSE_PING_PONG_ORDER_MANAGER_V2`.

## 2026-09-08 — OWNER authority and scientific contract

- M021 remains immutable at19 complete cycles in5h. M022 is a new controlled
  order-manager hypothesis, not a retrospective rewrite of M021.
- Frozen controls: same first five hours of2025-01-01, L2/trades, profile,
  latency, queue, tick0.0001, one-USDC normalized quantity, one-tick return,
  zero conditional fee, no negative exits and total initial economics.
- Single change package: owned-return priority, floating free-entry window on the
  fixed M021 lattice and160 simultaneous pending/active/cancel-pending orders.
- GPT-6 Astra identified two contract tensions before implementation. This
  preregistration resolves them conservatively: lane capital is explicitly
  segregated with no transfers; the existing M021 due-ACK precedence is retained
  so event-tie execution is not changed inside the control comparison.
- No economic replay has started. Implementation, tests, source-bound review,
  registration and published clean pre-run HEAD remain required.

## 2026-09-08 — implementation and pre-run review

- The canonical microstructure engine now contains the registered M022 manager;
  M021 code and physical result remain preserved as the control.
- The implementation enforces lane-owned capital, one-use liquidity, return-claim
  priority, cancellation acknowledgement before reassignment, a160-open-order cap,
  deterministic floating placement, partial-cancel residual blocking and resumable
  state.
- The runner's independent audit reconstructs each return from claim through physical
  fills, the chronological open-order cap, every B-lane budget and every S-lane free
  quantity/cost transition. Tampering with two S lanes jointly now fails closed.
-90 focused tests and the complete repository suite passed. GPT-6 Astra issued
  `PASS_CONDITIONAL_PRE_RUN` with23 exact normalized source hashes.
- M022 was registered `CREATED` with model hash
  `3e6c7588e944b63af577e23d21ec4461d0cbf44c55179cd7e71a5a9c75d5e8d8`.
- The OWNER gate now authorizes exactly one run of2025-01-01T00:00:00Z through
  05:00:00Z exclusive after this source is committed and pushed. No economic replay
  has started; Day2 and automatic successors remain closed.

## 2026-09-08 — single five-hour result and autopsy

- Published execution source: `f826b1c09368457c9252874e3dcf85f67ba64ef6`.
  Exactly one economic replay ran through the authorized cutoff; it was not repeated.
- Result:19 complete positive cycles(3.8/hour),5 BUY-first and14 SELL-first.
  M021 also produced19, so delta=0 and multiplier=1. The order-management package did
  not improve the primary throughput metric and M022 is `REJECTED`.
- Final balances:104.70890000USDT and95USDC; final marked equity199.90840000;
  realized PnL0.00560000 and unrealized PnL0.01780000. Audit status is
  `PASS_M022_MANAGER_LEDGER_EXECUTION_LIQUIDITY`.
- Main limiter:18,492 EXIT post-only rejections. Fixed return BUYs for S005-S007
  crossed the public ask and were correctly rejected. There were18,516 return
  submissions,19 return fills,0 return preemptions and0 free cancels for return.
  Floating placement canceled84 and reposted80 free entries, without increasing cycles.
- Mean open orders were159.8497, but only4.77% of active order-time was within5
  ticks of midpoint and11.01% within10;9 lanes produced cycles. Five return claims
  remained censored at cutoff, with maximum age about2.261hours.
- The physical `SUM_ROUNDTRIP_CYCLE_PROFIT=0.0014` inherited a reverse-only
  accumulator. Summing all19 immutable CYCLE events yields0.0019(0.0005 BUY-first +
  0.0014 SELL-first). The tracked derived report corrects the label/value without
  changing balances, cycles or physical artifacts.
- After every artifact had been written, the command's final stdout serialization
  raised on a `Decimal`. Classified `POST_WRITE_PRESENTATION_FAILURE`; no rerun was
  warranted. The canonical presentation path was fixed after the run and is not the
  source that produced the evidence.
- GPT-6 Astra issued `PASS_FACTUAL_EXECUTION_WITH_REPORTING_CAVEAT`. Physical run
  hash: `389fef14f694c2e0af549fd1a23b03b96390d09243a32989dd90087396b05e35`.
  The gate is closed; Day2, M023, sweep and live remain unauthorized.
