# M032 divergence audit: M030/M031 to M032

| Requirement | State before M032 | M032 disposition | Class |
|---|---|---|---|
| Strict causal hotline and final-target jump | M030 implemented | Reused as per-book state | MATCH |
| ACK-only reuse of zero-fill capital | M030 implemented | Global reservation ledger enforces it | MATCH |
| Partial/filled economic protection | M030 implemented | Preserved in ledger and manager | MATCH |
| 7 ranks, at most C1+C2 | Neither M030 nor M031 | New explicit geometry | MISSING → IMPLEMENTED |
| Persistent C1 vs opportunistic C2 | Own columns existed without these roles | Explicit role and reclaim comparison | PARTIAL → IMPLEMENTED |
| One PUBLIC queue then C1→C2 | M024 lineage supplied it | Isolated reusable queue group | MATCH |
| Prefix-only fill probabilities and turnover | Not reusable at this scope | Added causal estimator/tracker | MISSING → IMPLEMENTED |
| Global multiasset ownership ledger | Single-pair model-specific accounting | Added exact asset reservations and reconciliation | MISSING → IMPLEMENTED |
| Explainable marginal capital score | Fixed priority and geometry | Added decomposed score after priority class | MISSING → IMPLEMENTED |
| Physical 2/3/4-asset routes | No multi-book route engine | Added enumerator and physical cycle state | MISSING → IMPLEMENTED |
| Historical multi-book L2 intersection | Only USDCUSDT L2 locally validated | Empty; hard replay blocker | CONFLICT |
| Historical fee/rule proof for all books | Only USDCUSDT artifact; exact historical fee unknown | Not backfilled from current API | CONFLICT |
| M031 4×4 capital identity | Pre-run mismatch of 0.0125 USDT | Remains untouched and blocked | MATCH |
| Replay-ready integrated runner | M030 runner is single-book/model-specific | Deliberately not claimed while data gate fails | MISSING / BLOCKED |

`TEST_SUITE_PASS != STRATEGY_PASS`. The implemented library proves mechanics on
synthetic deterministic cases; it does not prove economic performance.
