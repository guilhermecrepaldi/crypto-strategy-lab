# M032 fee and symbol-rule provenance

Binance documents `PRICE_FILTER`, `LOT_SIZE` and `MIN_NOTIONAL` in its official
[Spot filters](https://developers.binance.com/docs/binance-spot-api-docs/filters).
The current public exchange-info observation on 2026-09-10 found a minimum
notional of 5 for the inspected candidate books, with symbol-specific ticks and
step size 1. This is a current observation only and is not projected backward.

The existing USDCUSDT rule artifact is
`artifacts/binance/usdcusdt-execution-rules.json`, SHA-256
`c4f2f9fdb1a8876c8cc869cd12963a1433d66eaf90df9fc11a7c3e299c74ffee`.
It explicitly leaves exact historical fee and account commission unknown.
Binance's account commission endpoint is signed/account-specific; M032 will not
access it. Binance promotions are pair- and interval-specific, so an announcement
such as its [January 2026 zero-fee update](https://www.binance.com/en/support/announcement/detail/4856a6d4e4014d4e8a5a29ec5fb44857)
does not prove universal zero fees.

Consequences:

- `SLOT_BASE=UNRESOLVED`
- `INITIAL_BANKROLL=UNRESOLVED_NOT_TO_EXCEED_200`
- `FEE_PROFILES=[]`
- `HISTORICAL_RULE_PROFILES=[]`
- `ZERO_FEE_ASSUMED=false`

The replay gate requires date-bounded rule and fee provenance for every selected
book. Applying current filters or selecting zero fee for convenience is forbidden.
