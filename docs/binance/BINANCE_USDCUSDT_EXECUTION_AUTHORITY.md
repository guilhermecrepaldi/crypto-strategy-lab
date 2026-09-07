# Binance USDCUSDT execution authority

Research date: 2026-09-07. Scope: `STRATEGY=B10_FROZEN`, `EXECUTION_PROFILE=BINANCE_REALITY_V1`, Spot USDCUSDT only. This is an evidence specification, not a claim that a replay or collector has passed. Raw response hashes, exact retrieval instants and observed values belong in `artifacts/binance/usdcusdt-execution-rules.json`; historical intervals belong in `reports/usdcusdt/B10-binance-rule-timeline.json`. Do not invent response values where acquisition failed.

## Evidence contract

`OFFICIAL_RULE` describes documented behavior; `OBSERVED` describes a captured response/tape; `MEASURED` describes a reproducible calculation; `INFERRED` describes an inference with limitations; `PARAMETERIZED` describes an explicit execution assumption; `UNKNOWN` describes missing evidence. A current observation is not a historical interval. Account state remains `UNKNOWN_NOT_AUTHORIZED`; no commission endpoint, test order, account, key or private stream may be accessed.

Research used agent-reach routing. Its configured Exa backend was unavailable (`Unknown MCP server 'exa'`); official-source web search and Jina reading were used. Community Square posts were discarded; the tick announcement below is authored by **Binance Announcement**, not a community account. No external code was adopted: official protocols ADOPT; causal queue/latency envelopes ADAPT; third-party fee claims REJECT.

## Symbol and filters

Capture current `GET /api/v3/exchangeInfo?symbol=USDCUSDT` from an official public host. Preserve status, base/quote assets, precisions, permissions, orderTypes, STP modes, all symbol filters and exchange rateLimits verbatim. `baseAssetPrecision` is not stepSize; `quotePrecision` is not tickSize. Missing optional filters mean absent in that response, not historically absent.

`PRICE_FILTER` validates price bounds and tick divisibility; `LOT_SIZE` validates quantity bounds and step divisibility. `MARKET_LOT_SIZE` adds market quantity constraints. `MIN_NOTIONAL`/`NOTIONAL` include applicability flags and valuation rules. `PERCENT_PRICE` and `PERCENT_PRICE_BY_SIDE` are dynamic. Record `MAX_NUM_ORDERS`, `MAX_NUM_ALGO_ORDERS`, `ICEBERG_PARTS` and every additional returned filter even if unused. Binance validates submitted quantities; rounding down is our explicit sizing policy, not exchange auto-correction. Reject off-grid frozen strategy prices rather than moving LOW/HIGH silently. [Official filters](https://developers.binance.com/docs/binance-spot-api-docs/filters).

## Historical timeline: established facts and gaps

The required economic interval starts `2026-01-01T00:00:00Z` and ends at the physical canonical September 5 cutoff, whose exact timestamp must come from the tape manifest. `END=null` in evidence means unknown end, not permission to extrapolate indefinitely.

| Interval/event | Value and evidence | Limitation |
|---|---|---|
| Announcement dated April 7; completion **by** April 14 05:00 UTC | USDCUSDT tick changes `0.0001 -> 0.00001`; resting pre-update orders retain their original matching tick | Exact switch instant is not stated. Jan 1 continuity and no later changes require additional evidence |
| Whole development period | Historical min/max price, quantity/step, notional, side multipliers, status interruptions and account rates: `UNKNOWN` wherever no dated evidence exists | Current exchangeInfo must never become silently historical |

The tick transition and protection for existing orders are official. A first fine-grid trade provides an observational bound, not an exact exchange filter switch or proof that every earlier tick was unchanged. [Binance tick announcement](https://www.binance.com/en/square/post/309819853676338).

Relevant API timeline: February 11 07:00 UTC iceberg parts becomes 50; March 9 begins approximately three-week Price Range Execution Rule rollout; April 2 approximately 07:00 UTC raw requests becomes 300,000/5 minutes and successful listed order/cancel requests have zero request weight (failures retain weight); May 8 rolling deployment changes dynamic filters to use non-null reference price; July 7 rolling deployment adds `CANCEL_ONLY`; July 9 07:00 UTC starts up-to-one-hour WebSocket maintenance with possible disconnects. Exact symbol rollout and actual downtime remain unknown. SBE timing changes do not establish JSON-stream or order latency. [Official changelog](https://raw.githubusercontent.com/binance/binance-spot-api-docs/master/CHANGELOG.md).

Price Range Execution Rule can expire remaining taker quantity outside its allowed execution range. It is distinct from order-entry filters. Capture public `executionRules` and `referencePrice` when supported; documentation examples are fictional. Historical USDCUSDT configuration/reference series remain unknown without archives. [Execution-rule FAQ](https://developers.binance.com/docs/binance-spot-api-docs/faqs/price_range_execution_rules).

## Fees: preserve favorable evidence as well as adverse evidence

`FEE_EVIDENCE=UNKNOWN_HISTORICAL_EXACT`. Official March and summer 2026 promotional notices expressly include USDC/USDT among zero-fee Spot pairs. This supports a zero-fee hypothesis at those documented periods; it does not establish uninterrupted January–September eligibility, every commission component or our account's rate. The 2022 campaign ended in 2022 and cannot establish 2026 fees. Promotions for USDC/USD or other USDC-quoted symbols are not USDCUSDT authority. [March notice](https://www.binance.com/lo-LA/support/announcement/detail/4c2852795e0a49a0bf72cd83714f743b), [2026 Football notice](https://www.binance.com/en/support/announcement/detail/a6f02526afd1466ab72fe29af4c84c67), [August notice](https://www.binance.com/en/support/announcement/detail/a3e1e3965b904bee87072a903c35fc82), [expired 2022 campaign](https://www.binance.com/en/support/announcement/detail/9327c312af5e41048756693c46f732ed).

Official numeric sensitivity anchors, per executed side:

| Fee hypothesis | Maker / taker | Status |
|---|---:|---|
| Pair zero-fee eligibility | 0 / 0 bps | Officially supported best-case hypothesis; full-span account continuity unknown |
| Ordinary non-promotional regular tier | 10 / 10 bps | Official published rate; counterfactual promotion-absent stress, **not proven actual historical USDCUSDT fee** |
| Regular tier with BNB discount | 7.5 / 7.5 bps | Official conditional reference only; cannot assume BNB holdings or omit their cost |

The public table also shows VIP and USDC-specific columns. They do not establish this pair/account's eligibility. A 105-USDT research bank does not imply VIP holdings. No arbitrary larger tax/special commission is allowed simply to destroy the strategy. [Official fee table](https://www.binance.com/en/fee/trading).

Commission applies on each partial fill. Without BNB, BUY fees reduce received base quantity and SELL fees reduce received quote proceeds. Standard, tax and special components are separate; role and side rates are combined as applicable. BNB discounts require account/symbol eligibility and sufficient balance, and do not discount tax/special components. The FAQ's numeric examples are explicitly fictional: they provide semantics, never calibration rates. Exact commission retrieval is authenticated and prohibited here. [Commission FAQ](https://developers.binance.com/docs/binance-spot-api-docs/faqs/commission_faq).

## Orders and message limits

`LIMIT_MAKER` rejects immediate taker execution; a normal `LIMIT` may take liquidity. `GTC`, `IOC` and `FOK` are distinct execution instructions. Use symbol-supported types only. `cancelReplace` can have separate cancellation and replacement outcomes; `STOP_ON_FAILURE` does not make a delayed cancellation instantaneous. Filters/count are checked before processing, and a non-attempted replacement can still increment count. Transport timeout is unknown order status, not proof of rejection. Virtual cancel-effective and acknowledgment times require explicit latency assumptions. [REST order authority](https://raw.githubusercontent.com/binance/binance-spot-api-docs/master/rest-api.md).

Quantity-reduction amend may retain priority; price replacement is not that operation. No amend, iceberg, algo or STP transfer capability is needed to claim the serial lot works. Unsupported operations fail closed. [Amend authority](https://developers.binance.com/docs/binance-spot-api-docs/faqs/order_amend_keep_priority).

Count accepted/rejected submissions, cancels and replacements separately. Binance `ORDERS` accounting is an unfilled-order counter with fill-related decrements; neither lifetime submissions nor open orders alone reproduce it. Capture current limits and model historical unknowns explicitly. `REQUEST_WEIGHT`, `RAW_REQUESTS`, `ORDERS` and stream-control limits are distinct. Rate-limited actions defer or reject; they never execute for free. [Order count rules](https://developers.binance.com/docs/binance-spot-api-docs/faqs/order_count_decrement).

## Tape and book evidence

Spot archive trades/aggTrades provide price, quantity, trade identity/time and buyer-maker flag. Spot archive timestamps since January 2025 are microseconds. Preserve original ZIPs and official checksums, own SHA256, ordering, duplicates and gap diagnostics. Raw trades are preferred; do not expand an aggregate into invented constituent timings. Public archive documentation lists Spot trades/aggTrades/klines; no sufficient anonymous full historical USDCUSDT L2 series was located. Set `HISTORICAL_L2=NOT_LOCATED_PUBLIC_OFFICIAL`, not a universal claim that Binance never stores books. [Official archive description](https://github.com/binance/binance-public-data), [public archive](https://data.binance.vision/).

An official historical-data article mentions order-book access requiring whitelisted futures accounts. It is not evidence of an authorized public Spot L2 backfill; do not access an account or substitute futures data. [Official historical-data article](https://www.binance.com/en-NG/blog/futures/421499824684901131).

`isBuyerMaker=true` means seller-aggressor flow, compatible with a resting BUY; false means buyer-aggressor flow, compatible with a resting SELL. Compatibility is necessary, not sufficient for our fill. bookTicker is BBO price/quantity/update ID, not queue identity; its documented payload has no event timestamp. Depth updates supply `U/u` and absolute quantities. Buffer diffs, snapshot, discard stale events, bridge sequence, update levels; zero deletes. A sequence jump requires book discard and resnapshot. JSON depth is 100/1000ms; this is not order latency. Streams have 24-hour connections, ping every 20s/pong within one minute, 5 inbound control messages/s, 1024 streams/connection and 300 connection attempts/5min/IP. Default timestamps are milliseconds; microseconds are opt-in. [WebSocket authority](https://raw.githubusercontent.com/binance/binance-spot-api-docs/master/web-socket-streams.md).

No cited rule establishes a total order across independent trade/depth/BBO streams or a measured private ACK. Preserve local receive sequence and monotonic times, report clock skew, and do not invent an event time for bookTicker. Historical queue, hidden liquidity, cancellations ahead, market impact and private order latency remain parameterized. Current calibration never proves a January book.
