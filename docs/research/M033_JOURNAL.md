# M033 research journal

## 2026-09-10 — venue abstraction and physical evidence audit

Starting `HEAD=origin/main=3f53993ae2ffc53fb37ed255f5daa10f7a7145eb`;
worktree was clean and the 218-event registry contained no M033 identity. M032
reviewed source/model identity and the inherited M030/M031 provenance were read
without modifying their evidence.

Implemented venue-explicit books, rules, fees, order semantics, latency profiles,
fills and routes; one M032-compatible capital ledger per venue; Binance/Kraken
adapters; isolated L2 queues; observable-order L3 FIFO; exact L3-to-L2 aggregation;
and a raw-first Kraken L3 recorder. Cross-venue routing and remote capital use fail
closed. Unknown historical latency remains unknown rather than becoming zero.

Public research confirmed current Kraken `USDC/USDT`, current rules, the current
lowest-volume stablecoin fee schedule, individual-order L3 semantics and atomic
amend priority. It also found that Kraken L3 requires an authenticated token.
No account, key, Testnet or trading endpoint was accessed.

All twelve locally validated Binance dates also have structurally valid Kraken L2
and trade files from Tardis first-of-month samples. Venue, symbol, timestamps,
numeric domains, sides and initial snapshots are checked, but the normalized
Kraken files expose no native sequence/checksum; continuous reconstructability is
not proven. This is not a physical replay-ready pool. No candidate date has a
temporally proven Kraken fee profile. Official Kraken downloadable history and
Tardis do not provide the historical Spot L3 required for the native ablation.

Decision: publish the reusable implementation and evidence, withhold registry
entry, random draw and replay. `ECONOMIC_REPLAY_RUNS=0`. M033 remains blocked
until owner supplies or authorizes evidence that actually closes a gate; no
economic workaround was improvised.

Draft `MODEL_HASH=b9603f53224f21a8a1b8c9d151a87848ed86e4da47c458af54719953e72dcc52`.
It identifies the blocked model specification and is not a registry identity or
an executed result. Initial validation passed 32 M033 tests plus 82 selected M032
and M030 inherited regressions (114 total), Ruff and strict mypy. Source-bound
independent review remains required before this implementation is considered
reviewed. Source-bound Astra review of `f903b038...` returned BLOCK:
fill-before-activation, L3 trade/native double mutation, duplicate C1, incomplete
cancel/amend lifecycle, overclaimed Kraken CSV validation, insufficient
raw-normalized binding/sealing and a non-equivalent L3/L2 ablation. Corrections
are in progress under a new source review gate.

The correction now has a causal per-book clock, one active C1/C2 per price,
request-before-ACK cancellation, guarded amendments, and explicit reconciliation
between simulated trade consumption and subsequent native L3 state. Raw-normalized
events carry the exact raw sequence and message hash; gaps/reconnects invalidate
the capture and close seals the writer. The ablation owns independent L3 and L2
queue states fed from one event stream. Kraken CSVs are now classified only as
structurally checked files with continuity unproven. Correction validation passes
39 M033 tests; source-bound rereview is required.

The second Astra review on `3e68a4ca...` returned BLOCK. It reproduced negative
native remaining quantity creating simulated liquidity, native-delete-before-trade
reusing one execution, price amend bypassing destination-column uniqueness and an
optimistic same-timestamp fill. It also showed that bilateral snapshot evidence
was pooled across later resets rather than isolated to the initial snapshot.

The next correction rejects negative remaining quantity before mutation, fails
closed on native-removal/trade ordering that cannot be correlated, validates amend
destination occupancy atomically, requires strict post-activation time for own
fills, and tracks the initial snapshot sides separately from later reset batches.
Focused validation now passes 44 M033 tests. A new published source-bound review
is required; no replay, draw or registry mutation occurred.

The third Astra review on `fcc78d3a...` reduced the remaining defect to mixed
reconciliation: after a trade consumed part of a public order, a native update
could remove more than the expected remainder and still be treated as exact
confirmation. The correction now accepts only equal state as confirmation;
additional native reduction marks the level ambiguous and blocks subsequent own
fill inference. Two adversarial fixtures cover DELETE and MODIFY variants.
