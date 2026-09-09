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
