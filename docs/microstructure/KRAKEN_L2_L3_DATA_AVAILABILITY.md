# Kraken L2/L3 data availability

## Historical L2 and trades

Tardis documents Kraken spot coverage from 2019-06-04 and provides normalized
`incremental_book_L2` and `trades`; first-of-month CSV samples are downloadable
without an API key. Its Kraken channel inventory contains L2 `book`, not L3.

All twelve dates already validated locally for Binance USDCUSDT were downloaded
and physically validated for Kraken USDC-USDT without inspecting strategy
performance:

`2025-01-01, 2025-02-01, 2025-03-01, 2025-04-01, 2025-06-01,
2025-08-01, 2026-01-01, 2026-02-01, 2026-03-01, 2026-04-01,
2026-05-01, 2026-07-01`.

Hashes, row counts and delivery-order checks are in
`reports/usdcusdt/BINANCE_KRAKEN_COMMON_DATE_POOL.json`. Raw files remain ignored
locally. Exchange timestamps can regress slightly while Tardis local-delivery
timestamps remain monotonic; both facts are recorded rather than reordered.

## Historical L3

- Kraken's official downloadable history is time-and-sales (trades), not a Spot
  L3 order-event archive.
- Tardis' documented Kraken archive provides L2 and trades, not L3.
- No validated historical Kraken Spot L3 source was found.

Therefore `HISTORICAL_L3_AVAILABLE=false`.

## Forward L3

Kraken documents individual-order L3, including order ID, visible quantity and
order insert/amend timestamp. It excludes hidden iceberg quantity and several
non-resting order classes. The channel requires an authenticated API token.
Because M033 forbids account/key access, a real forward subscription was not made.
The raw-first recorder and parser are implemented but forward capture remains
blocked by authority.

Sources: [Kraken L3](https://docs.kraken.com/exchange/api-reference/spot-websocket-v2/level3),
[Kraken historical trades](https://support.kraken.com/articles/360047543791-downloadable-historical-market-data-time-and-sales-),
[Tardis Kraken coverage](https://docs.tardis.dev/historical-data-details/kraken).
