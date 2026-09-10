# M033 — multi-venue Kraken L3 validation — OWNER directive

OWNER authorized a new research identity,
`M033_MULTI_VENUE_KRAKEN_L3_VALIDATION_V1`, from verified starting HEAD
`3f53993ae2ffc53fb37ed255f5daa10f7a7145eb`, reviewed M032 source
`25273367e6d2146a71d0308a423415320e3da8c0` and M032 model hash
`fb35f67e414cce9cb03b0e83824304f9b4286617b679785663e941fca6e11215`.

M032 evidence is immutable. M031 remains `BLOCKED_PRE_RUN_CAPITAL_IDENTITY`.
M033 generalizes physical identity and execution, not the M032 economic policy.

## Frozen invariants

- One economic core; venue adapters translate native events.
- Every physical object is keyed by `venue + native symbol`.
- Binance and Kraken ledgers are independent. No remote reservation, transfer,
  cross-venue route or remote return settlement exists.
- Each comparison arm may use at most 200 USD-equivalent independently. Two
  200-dollar arms mean 400 dollars of experimental capital.
- FIFO, once-only trade quantity, once-only public queue, no self-fill,
  CANCEL_ACK-gated reuse, immutable cost basis and no deliberate negative exit
  remain mandatory.
- The M032 maximum geometry remains seven ranks and C1+C2; C1 is persistent and
  C2 opportunistic. No venue-specific strategy tuning is allowed in the first
  comparison.
- Rules, fees, latency and order semantics are venue/time specific. Unknown
  history is a blocker, never silently replaced by current values.
- All legs of one economic cycle remain on one venue.
- No account, API key, private token, Testnet, live order, withdrawal or transfer.

## Required sequence

1. Audit M032 venue coupling.
2. Introduce venue identity and independent ledgers.
3. Prove Binance L2 compatibility.
4. Implement Kraken L2/L3 normalization and an L3 queue.
5. Implement immutable raw-first recording.
6. Verify current Kraken market/rules/fees and historical availability.
7. Freeze the physical common-date pool before performance inspection.
8. Obtain independent source-bound review.
9. Register M033 only after all applicable replay gates pass.

Kraken L3 economic evaluation may use only actual captured/archived L3. The
same-stream L3-to-L2 ablation is mandatory. If historical fees, L3, or access
requirements cannot be proven, M033 remains unregistered and no economic replay
runs.

`TEST_SUITE_PASS != STRATEGY_PASS`.
