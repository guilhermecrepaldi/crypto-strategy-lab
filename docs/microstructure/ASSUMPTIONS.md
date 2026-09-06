# Assumptions register

| Assumption | Current status | Required evidence |
|---|---|---|
| `0.9988 → 0.9989` repeats | Confirmed for two discovery days | More historical windows and frozen future windows |
| Observed paths equal our fills | Rejected | Sequenced L2 plus aggressive trades and latency |
| Maker fee is zero | Scenario only; not account-verified | Explicit effective fee configuration before any later operational gate |
| A taker exit preserves the tick | Rejected in tested 10 bps scenario | None for this tick; mathematics is negative |
| A locked lot eventually closes | Unknown | Continuous multi-month/year replay; terminal censored inventory |
| Time locked is itself a stop | Rejected by strategy | No timeout or forced exit in S0 |
| Trade volume is scalable capacity | Rejected | Queue-aware lot-size curve and shadow evidence |
| Structural depeg can be inferred from elapsed time | Rejected | Explicit peg/liquidity/redemption/delisting evidence |
| Binary float is safe for finance | Rejected | Decimal/fixed-point throughout critical accounting |

The public archive timestamp change from milliseconds to microseconds in 2025 is handled
explicitly. Fee scenarios are assumptions, not claims about a Binance account.
