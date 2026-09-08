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

## CSV acquisition completed — native validation next

L2_CANDIDATE_DATES=21
L2_AVAILABLE_FREE=21
L2_UNAVAILABLE=0
CSV_TOTAL_BYTES=207733908
CSV_TOTAL_ROWS=22143325
GZIP_AND_SCHEMA_PASS=21
INTEGRITY_PASS=PENDING_NATIVE_SEQUENCE_AND_TRADE_RECONCILIATION
STRATEGY_MODEL_USED=M015
REPLAY_MODE=INDEPENDENT_24H
QUEUE_MODEL=OBSERVED_L2
CSV_ACQUISITION_SOURCE_COMMIT=b46e2123ac1386abba65098c21ebccc5bb9b9403
ECONOMIC_REPLAYS_STARTED=0

All21 HTTP responses200; original files remain local and immutable. January2025
observable book validation:828955rows, zero crossed batches or capture regressions.
First snapshot arrives9.412998s after midnight; startup remains FLAT/idle until
valid bridging snapshot, never an invented opening book. Raw native probe200 for
Jan2026 confirms free ten-minute depth/snapshot/trade slices with U/u. Acquire all
144 slices perday to validate native continuity and capture ordering independently.
Native and CSV data retain separate provenance; this is not yet economic approval.
