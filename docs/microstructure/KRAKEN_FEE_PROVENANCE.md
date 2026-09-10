# Kraken fee provenance

The current Kraken stablecoin/pegged-token/FX table, observed 2026-09-10, applies
when a stablecoin is the base currency. Its lowest-volume tier is 0.20% maker and
0.20% taker. USDC/USDT has USDC as base, so this is the conservative current
account-tier assumption.

A two-leg maker round trip at that tier incurs approximately 0.40% before any
spread/slippage interaction. This is much larger than a one-tick USDC/USDT gross
move near parity (0.01%). It therefore makes the inherited micro-edge economic
hypothesis implausible at the lowest tier unless a different temporally proven fee
profile applies. This is arithmetic, not a replay result.

The current table does not prove fees on any candidate historical date. Public
Kraken pair metadata does not return an account's effective fee tier. Therefore:

- `KRAKEN_CURRENT_FEE=maker 0.20%, taker 0.20%, lowest-volume tier`;
- `KRAKEN_HISTORICAL_FEE=UNPROVEN`;
- primary historical economic replay remains blocked;
- a fee-neutral run, if later authorized, can only be labeled
  `NON_ECONOMIC_MICROSTRUCTURE_DIAGNOSTIC`.

Source: [Kraken fee schedule](https://www.kraken.com/features/fee-schedule).
