# M035 random 3h V2 preregistration

Identity: `M035_200USD_RANDOM_3H_PARALLEL_DEVELOPMENT_BACKTEST_V2`  
Classification: `DEVELOPMENT_DIAGNOSTIC_BACKTEST_NOT_OOS_NOT_LIVE`

## OWNER correction and authorization

On 2026-09-12 the OWNER authorized another distinct three-hour test and corrected the prior
interpretation: the M035 economic prompt did not authorize a fixed 25 bps peg-deviation abort.
The V1 evidence remains immutable. V2 removes that unauthorized M034 diagnostic carry-over; it
does not reinterpret or rerun V1.

No replacement numeric peg threshold is invented. Physical books must still be nonempty,
uncrossed, sequence-valid and causally marked. New entries remain subject to the frozen spread,
depth, flow, fee, execution-cost, adverse-selection, risk-buffer and positive-net-edge gates.
Ordinary negative cycle settlement remains prohibited. Open inventory is marked at cutoff; no
cosmetic negative exit is introduced.

## Window draw frozen before economic inspection

Candidate catalog: every 10-minute-aligned three-hour window wholly inside each of the 21
first-of-month evidence days from 2025-01-01 through 2026-09-01. There are 2,667 candidates.

- seed: `bc895e20515f5a6f821419c897fdcf2174359e8082e7730fdcfafa3189af3bef`
- catalog SHA-256: `0b9c97052faa9fd83c87f51701023fd64a24c961c851fa09ba4df6754133d034`
- algorithm: `SHA256(seed|catalog_sha256) mod candidate_count`
- selection digest: `87e24ec2b6ca2f038bda3bf7be6abaf34431cc6d9704af6806b15fe6e991545c`
- selected index: `1657`
- selected window: `2026-02-01T01:00:00Z` inclusive to `2026-02-01T04:00:00Z` exclusive

No price, spread, cycle, volatility or PnL value from this window was inspected before the draw.
If the selected dual tape cannot pass native sequence and exact individual-trade binding, V2 is
invalidated without reroll.

Native reconstruction may consume the same-day L2 prefix from 00:00 to 01:00 solely to obtain a
causally bridged book at the selected start. No strategy state, order, allocation, fill, cycle,
metric or PnL may consume that bootstrap prefix; economic events remain exactly 01:00–04:00.

## Frozen economic comparison

Every fee scenario begins independently with exactly 200 USDT. The baseline is M035 single-pair
USDCUSDT; treatment is M035 parallel USDCUSDT + FDUSDUSDT with the same single global bank and a
single causal merged event stream. Fees per maker leg are exactly 0, 1, 2, 5 and 10 bps. All other
economic, queue, latency, geometry, dust, capital-ownership and zero-loss mechanics remain those
of M035 V1, except for removing the unauthorized fixed peg abort.

The economic run is permitted only after dual-tape validation, conformance, source-bound Astra
review, publication of source/config/hashes, and creation of a new exclusive V2 claim. It is one
V2 run only; no reroll or result-driven tuning is allowed.
