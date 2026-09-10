# M029 — unchanged M026 strategy over 24 hours

STATUS=INCONCLUSIVE

This is a normalized DEVELOPMENT replay below Binance minimum notional. It is
not live-executable evidence.

## OWNER scoreboard

- PERIOD=2025-01-01T00:00:00Z/2025-01-02T00:00:00Z_EXCLUSIVE
- INITIAL_USDT=78.10400000
- INITIAL_USDC=78
- INITIAL_TOTAL_MARKED_EQUITY=156.25220000 USDT-equivalent
- FINAL_USDT=69.1272000000000000
- FINAL_USDC=87.00000000
- FINAL_TOTAL_MARKED_EQUITY=156.3012000000000000 USDT-equivalent
- TOTAL_MARKED_GAIN=0.0490000000000000 USDT-equivalent
- TOTAL_MARKED_GAIN_PCT=0.03135955845741691956977245760%
- PHYSICAL_COMPLETE_CYCLES=98
- PHYSICAL_CYCLES_PER_HOUR=4.083333333333333333333333333
- SLOT_EQUIVALENT_CYCLES=289
- SLOT_EQUIVALENT_CYCLES_PER_HOUR=12.04166666666666666666666667
- REALIZED_CYCLE_PNL=0.0427000000000000 USDT
- REALIZED_DISPOSAL_PNL=0.0577996784800000 USDT
- UNREALIZED_PNL=-0.0087996784800000 USDT

The first three hours reproduced M026 exactly and ended at 156.2972000000000000
USDT-equivalent after 30 physical cycles. The following 21 hours added 68 physical
cycles and only 0.0040000000000000 USDT-equivalent, or 0.002559226908735409%.

The full-day rate was 4.0833 physical cycles/hour, versus 10/hour in the first
three hours. The day therefore did not sustain the initial rotation rate and did
not approach the OWNER target of 1,000 cycles/day. HOT produced 93 cycles, MID 5
and FAR 0. Descriptive accounting found extensive public-FIFO waiting and 1,907
underfunded promotion attempts, but these observations do not isolate one causal
bottleneck.

## Evidence limits

Minimum notional alone is virtualized. Fees are the frozen conditional zero-fee
assumption. True exchange queue rank and endogenous market impact are unknown.
The result comes from one DEVELOPMENT day and must not be presented as expected
live return or capacity.

## Audit

- SOURCE_COMMIT=9dde81b16c5cd3144efc88c471d70407f1249af7
- PREFIX=PASS_EXACT_M026_3H_PREFIX_EQUIVALENCE
- AUDIT=PASS_M029_M026_24H_LEDGER_TERMINAL_PREFIX_AND_RETURN_AUDIT
- TRADES_RECONCILED=254205
- LEDGER_SHA256=d9cbe0f426aefdaa3e373aa94c56a678b0a7d6232aacad9a34845ca7d4412be8
- RUN_MANIFEST_SHA256=1787b7de422a1e3c6ede86fbbdc6e1c466409ee2a1ecf878eabeff43c7a7348e
- TERMINAL_ENGINE_STATE_SHA256=f67efdb170029a9c31e08d25ac8431d6a1a5f344821c9855d64fa4281526c186
- INDEPENDENT_AUDIT_SHA256=d9cf51782fad9441f3a5f9af674bb5e38c0e8d481024d5f0ed7d7079b417f4af
- RESULT_JSON_SHA256=52a8e4c2cbdfd8f7f0e59b663998dc4663fcbd03dc1a7480bc2aed211f4cc773

M029 consumed its single authorized run. No rerun, another day, successor, account,
Testnet or live action is authorized.
