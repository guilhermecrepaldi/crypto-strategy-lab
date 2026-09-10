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

All twelve locally validated Binance dates also have physically validated Kraken
L2 and trades from Tardis first-of-month samples. This is a physical intersection,
not an economic eligible pool: no candidate date has a temporally proven Kraken
fee profile. Official Kraken downloadable history and Tardis do not provide the
historical Spot L3 required for the native ablation.

Decision: publish the reusable implementation and evidence, withhold registry
entry, random draw and replay. `ECONOMIC_REPLAY_RUNS=0`. M033 remains blocked
until owner supplies or authorizes evidence that actually closes a gate; no
economic workaround was improvised.

Draft `MODEL_HASH=b5e9c00ac628a4998cc08856e27cc075c35c91252828d3c224b03316fb406c1f`.
It identifies the blocked model specification and is not a registry identity or
an executed result. Initial validation passed 32 M033 tests plus 82 selected M032
and M030 inherited regressions (114 total), Ruff and strict mypy. Source-bound
independent review remains required before this implementation is considered
reviewed.
