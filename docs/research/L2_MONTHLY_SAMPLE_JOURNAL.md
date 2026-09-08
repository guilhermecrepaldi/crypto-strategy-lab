# L2 MONTHLY SAMPLE JOURNAL

## 2026-09-08 — autorização e preparação

CAMPAIGN=USDCUSDT_L2_MONTHLY_SAMPLES
STATUS=DATA_ACQUISITION_PREPARATION
L2_CANDIDATE_DATES=21
STRATEGY_MODEL_USED=M015
MODEL_HASH=4231670b19b1ca5c2b5032b1476b83b3182d1463750ea944da5efb867d81a8fa
REPLAY_MODE=INDEPENDENT_24H
OPERATING_INITIAL=100
RESERVE_INITIAL=10
CAPITAL_MODE=COMPOUNDING_WITHIN_DAY
START_STATE=FLAT
QUEUE_MODEL=OBSERVED_L2
ECONOMIC_REPLAYS_STARTED=0
WEEK_2_CONTINUOUS_AUTHORIZED=false

OWNER directive preserved in docs/microstructure/L2_MONTHLY_SAMPLE_OWNER_DIRECTIVE.md.
Registry and CURRENT_STATE agree on M015; no later model or running replay found.
M015's completed weekly artifacts/model remain unchanged. This is a new execution
evidence battery, not a new strategy or continuous compounding path.

Research-first: ADOPT official Tardis data contracts; ADAPT existing acquisition,
book validation and M015 execution authorities; REJECT CSV row numbers as exchange
update IDs, synthetic queue/depth where observed, and inter-month capital carry.

Official sources rechecked through agent-reach/Jina, with direct-document verification:

- [Binance capture](https://docs.tardis.dev/historical-data-details/binance): WS depth,
  REST initial snapshots, provider checks U/u, first-day free access.
- [CSV contract](https://docs.tardis.dev/downloadable-csv-files/data-types): absolute
  amounts, zero deletes, snapshot resets and local-timestamp message batches.
- [Native API](https://docs.tardis.dev/api/http-api-reference): native messages,
  capture ordering and blank disconnect markers; free monthly first-day slices.

Normalized CSV does not expose U/u/lastUpdateId. Independent sequence validation
requires native depth/snapshot sidecars; provider attestation alone is not a local
PASS. Investigate public raw access, without keys or bypass. No fill results yet.

Scientific protocol/review: GPT-6 Astra. Mechanical acquisition: GPT-5.6 Luna.
Python performs validation/accounting; TEST_SUITE_PASS != STRATEGY_PASS.
