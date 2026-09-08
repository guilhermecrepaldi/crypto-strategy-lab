# M019 — adaptive stablecoin ladder V1 journal

Append-only research journal. Git history is provenance; corrections append and
never rewrite economic evidence.

## 2026-09-08 — OWNER direction received

OWNER superseded the unexecuted three-range proposal with a materially new model:
six logical BUY and six logical SELL slots, floating bands, traceable inventory
lots, profit-only exits, no realized loss, no reserve release and global capital/
liquidity conservation. First run is only2025-01-01 L2. B10, M014, M015, M018
and published artifacts remain unchanged.

GPT-6 Astra designed the minimal V1 before implementation: total marked endowment
100, causal approximately50/50 USDT/USDC split at first valid bid, mid center,
one-tick offsets, small safe notional,60s/2tick free-quote refresh,90% projected
USDC cap, FIFO lots and no timeout liquidation. Current fee/filter inputs remain
explicit conditional assumptions. No economic replay has run.

## 2026-09-08 — preregistration, implementation and review completed

M019 was registered CREATED with model hash
`24e5a43a63bc501b4d7fb13931c0fcc39219dedd9cc274e925d9055c33f6d347`.
GPT-6 Astra reviewed the exact source and returned PASS_CONDITIONAL_PRE_RUN for
D1 only after three rounds. The review found and caused correction of premature
activation eligibility, self-cross, partial-fill cycle fragmentation, audit
tamper gaps and CANCEL_ACK/cycle journal ordering. Sixty focused synthetic tests
pass, including checkpoint continuation and deliberate price/side/source/queue/
lot/cost/cash tampering. TEST_SUITE_PASS remains distinct from STRATEGY_PASS.
No economic replay has run at this milestone.

## 2026-09-08 — D1 complete; target failed

The published commit `342b46db4d31b80d1de5d03f4ce66a63a31a040e`
executed only the authorized L2 day2025-01-01. The full254205-trade ledger and
terminal checkpoint passed independent reconstruction. Result:10 ordinary
positive cycles,15.8572USDT and84USDC at cutoff; marked USDC value84.168 and
total equity100.0252. Realized PnL was+0.0336, comprising+0.0162 from ordinary
cycles and+0.0174 from initial-endowment sales. Unrealized PnL was-0.0084, so
total marked PnL was+0.0252. The1000 and2000 gates both failed. Day2 remains
closed.

The dominant observed bottleneck was INVENTORY_LOCK coupled to exit queues, not
a reserve shortage. The last cycle completed at05:29:49.143492UTC, followed by
18.5030h without another cycle. BUY bands1/2 retained60/24USDC. Only12 of84USDC
were reserved by two SELL orders at1.0025; their terminal queue estimates were
444562 and680581. A further minimum BUY would have breached the90% projected
USDC cap, so15.8572 free USDT did not equal admissible capacity. Forty fills and
18898 queue-flow events were audited; raw count comparison alone is not causal.

GPT-6 Astra returned PASS_CONDITIONAL for the evidence and FAIL for the economic
target. The only next hypothesis identified, not authorized or executed, is
causal repricing of already-profitable SELL exits while preserving cost basis,
60s/2tick policy, cancel latency and queue reset. PRICE_PRIORITY, zero fee and
historical filters remain conditional; this is not proof of live behavior.

Canonical registry sealing recorded scenario
`59e9782ad5b4143803518027e46c0cb1bba45fdbd4beabc86ebf63886a53a3ce`,
run `c7da5f0949b7c4361b78f149654d535f92ba6210c9fe9bdf4836d1b7824f6cd2`
and evaluation
`e87e725a86a86be9d2f6cb7aaff7d0c83a1d2d12866916fc5c00e2c4b15c775e`.
M019 status is REJECTED because it failed the explicit D1 throughput gate, not
because the evidence or software audit failed.
