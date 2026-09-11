# M034 owner diagnostic — 200 USD / 3 hours / Binance forward paper

Status: `COMPLETE_FAIL_CLOSED_DIAGNOSTIC`. Identity:
`M034_OWNER_DIAGNOSTIC_FORWARD_3H_200USD`.

This is a one-shot `OWNER_DIAGNOSTIC_FORWARD_PAPER`, not a historical replay,
strategy registration, OOS validation, Testnet exercise or live test. It starts with
exactly 200 USDT. It cannot send an order, call an account endpoint or use Kraken.
`STRATEGY_PASS=false` regardless of the numerical result.

## Frozen authorities

- Source: `be78f31d03006a93e0af9165ee744b9b38cb5913`.
- Independent reviewer: `gpt-6-astra`; verdict `PASS_FOR_RUN`, limited to option B.
- Source-review artifact SHA-256:
  `b483e1a35d811eba26c50fd00f387e5f36243f763bbd0d51c02bd6cd8adafa3e`.
- Diagnostic configuration hash:
  `6f7bbf6e44ad84742fb8e9f45bd33beeb889866418b31a25700f30720d8302bf`.
- Configuration artifact SHA-256:
  `4b360e6932ea72199942381326f0775b03f0cb0067b04454aeb7ae50124fe704`.
- Diagnostic threshold hash:
  `0f13694af14cc324b938b4e26d6b7339ba095dcb6eebb4c2fb904d203b1bcf47`.
- Fee-evidence artifact SHA-256:
  `7885ff63d21466b3c244541af56586de52cd5d330bed37fbe8f2a51e48fdd56b`.
- Canonical one-shot claim:
  `data/m034/M034_OWNER_DIAGNOSTIC_FORWARD_3H_200USD.claim.json`.
- Frozen output directory:
  `data/m034/M034_OWNER_DIAGNOSTIC_FORWARD_3H_200USD_RUN`.

The claim is created atomically immediately before opening public market transports.
Its existence prohibits another run with a different output directory and is preserved
after success or failure. The CLI also requires `HEAD=origin/main`, unchanged reviewed
source closure, and published byte-identical config, fee evidence and source review.

## Forward inputs and causal window

The only venue is Binance Spot. The public universe is `USDCUSDT`, `FDUSDUSDT`,
`FDUSDUSDC`, `USD1USDT`, `USD1USDC`, `TUSDUSDT` and `USDPUSDT`. Availability does not
imply eligibility. Initial and 30-minute exchange-info observations preserve full
filters and current status. Full 5,000-level snapshots plus individual public trade and
diff-depth events are stored; candles are never used for fills.

Warm-up is exactly 900 monotonic seconds and has no economic PnL. The first validly
timestamped event after warm-up defines `START_TIMESTAMP_US`; cutoff is exactly
10,800,000,000 market microseconds later. Exchange elapsed time is compared with the
monotonic clock. Events at or after cutoff are preserved as excluded evidence and never
reach the economic state machine. A real timestamp jump, market clock stall or stream
silence invalidates the run rather than fabricating continuity.

## Diagnostic-only policy

The frozen thresholds are assumptions, not calibrated values and not official M034
strategy thresholds.

| Threshold | Value |
|---|---:|
| `MIN_COMPLETION_PROBABILITY` | 0.90 |
| `MAX_EXPECTED_LOCK_TIME` | 300 s |
| `RISK_BUFFER` | 2 bps |
| `MAX_INVENTORY_EXPOSURE` | 20 USD |
| `PEG_DEVIATION_THRESHOLD` | 0.0025 |
| `MIN_NET_EDGE` | 1 bps |
| `TAIL_RISK_BOUND` | 1 USD |
| `MAX_SPREAD` | 5 bps |
| `MIN_DEPTH` | 1,000 USD inside the 10 bps band |
| `MIN_COMPATIBLE_FLOW` | 10 asset/s over 60 s |

Decisions are evaluated at most once every five seconds. Paper activation and cancel-ACK
latencies are one second; book age may not exceed three seconds. Geometry remains seven
ranks with C1/C2 and canonical priority classes.

## Fee and estimator status

No account or key access was authorized. Binance's public table currently gives a
regular-user reference of 0.100% maker/taker, but Binance documents that exact current
commission is account- and symbol-dependent and obtained through signed user data.
Therefore the reference is recorded as `UNPROVEN`, not operational proof. All seven
pairs receive `FEE_UNPROVEN` and zero slots.

Completion probability, expected lock, adverse selection and execution cost also remain
`UNKNOWN`. No future data, zero substitution, ad-hoc bound or online calibration is
allowed. The canonical gate therefore blocks all opportunities before allocation and
paper order placement. Capital time is `BLOCKED_DATA`, not
`IDLE_NO_ELIGIBLE_OPPORTUNITY`.

Consequently, the preregistered and reviewed outcome is expected to be zero orders and
zero cycles. Observing that outcome for three hours validates fail-closed admission and
transport evidence only. It does not prove that the market lacked opportunities and
does not validate cycle execution, profitability or the strategy.

## Required result

The output preserves full snapshots, raw events, every eligibility decision, rules,
checkpoints at 00:00 through 03:00, result and manifest hashes. The final report must
state physical and slot-equivalent cycles, realized and marked PnL/equity, employed,
idle and blocked capital time, fees, costs, locks, residual inventory and rejection
counts without tuning, rerun, early stop or artificial liquidation.

## Observed result

The one-shot forward observation completed from `2026-09-11T13:08:39.103903Z` through
`2026-09-11T16:08:39.103903Z`, exactly `10,800,000,000` market microseconds. The claim
remains consumed; the runner was not restarted or rerun. The observed economics were:

| Metric | Result |
|---|---:|
| Initial bank | 200.00 USDT |
| Final realized equity | 200.0000 USD-equivalent |
| Final marked equity | 200.0000 USD-equivalent |
| Net realized PnL | 0.0000 USD |
| Marked return | 0.0000% |
| Physical cycles | 0 |
| Slot-equivalent cycles | 0 |
| Eligible candidates | 0 / 149,240 |
| Authorized slots | 0 |
| Real/Testnet orders | 0 / 0 |
| Capital utilized | 0.00% |
| Ordinary idle capital | 0.00% |
| Blocked data/estimator capital | 100.00% |
| Residual inventory | none |

All 149,240 decisions were Binance-only, ineligible and authorized zero slots. Every
decision carried `FEE_UNPROVEN`, `EXECUTION_COST_UNKNOWN`,
`ADVERSE_SELECTION_UNKNOWN`, `COMPLETION_PROBABILITY_UNKNOWN` and
`EXPECTED_LOCK_UNKNOWN`. Capital remained `BLOCKED_DATA` for the complete economic
window; it was never relabeled as ordinary idle or employed capital.

The capture contains 343,717 sequential raw records: 343,715 included and two excluded
at cutoff. The headline event counts include warm-up: 306,938 trades and 36,777 depth
events. The economic window itself contains 291,004 trades and 34,258 depth events,
325,262 total. Seven initial depth snapshots, 42 rule observations and zero native
book gaps were independently verified. `DATA_GAP=62,594` refers to stale or missing
evidence at decisions, not native sequence gaps.

All manifest file sizes/hashes, claim, source review, fee evidence, configuration hash,
threshold hash, checkpoints, decisions and rejection counters reconciled. Independent
GPT-6 Astra review returned `PASS_FOR_DIAGNOSTIC_ARTIFACT_PUBLICATION` with no P1/P2.
The review did not start or rerun the process. Detailed evidence is recorded in
`reports/m034/M034_OWNER_DIAGNOSTIC_FORWARD_3H_200USD_RESULT_AUDIT.json`.

This is a transport and fail-closed admission PASS only. It is not evidence that the
market lacked opportunities and does not validate execution mechanics, cycles,
profitability or live readiness. The 200 USD label uses the frozen diagnostic convention
`1 USDT = 1 USD`, not an observed fiat mark. The source enforces the 900-second warm-up,
but its exact duration cannot be independently recomputed from the artifacts because
the starting monotonic timestamp was not persisted. `STRATEGY_PASS=false`.
