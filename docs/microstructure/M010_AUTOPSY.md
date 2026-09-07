# M010 autopsy — frozen capital release did not trigger

Scientific review: GPT-6 Astra. Calculations were performed with Python and Decimal from
`reports/usdcusdt/M010-capital-release.json` and the independent
`reports/usdcusdt/M010-causal-audit.json`.

```text
MODEL=M010
PARENT_MODEL=M007
M010_AUTHORIZATION_CLASS=OWNER_EXPLORATORY_OVERRIDE
SCIENTIFIC_GATE_PASS=NO
HYPOTHESIS_RESULT=INCONCLUSIVE
FROZEN_RULE_DID_NOT_TRIGGER=YES
M010_BEHAVIORALLY_EQUIVALENT_TO_M007=YES
PROMOTION=NO
CURRENT_CHAMPION=M007
M011_EXECUTION_AUTHORIZED=NO
```

M010 completed the entire frozen DEVELOPMENT interval, from 2026-01-01T00:00:00Z through
the exclusive boundary 2026-09-05T23:59:59.783644Z, with its own initial 100 USDT. The frozen
rule made no capital releases. Exact comparison against the technically reconstructed M007
passed for all cycles, selection decisions, accounting, final inventory, counters and other
behavioral fields. Only model identity and additional release evaluations are excluded from
that behavioral comparison.

## Principal comparison: independent 100-USDT compounded replays

These are zero-fee mathematical price-path results. Final capital includes the terminal
inventory mark; it is not realized cash available for withdrawal or demonstrated executable
capacity. The extremely large compounded value is not a claim that exchange liquidity could
support these quantities.

| Metric | M007 | M010 |
| --- | ---: | ---: |
| Initial capital, USDT | 100 | 100 |
| Final marked capital, USDT | 900,637,402,983.4181046 | 900,637,402,983.4181046 |
| Return, percent | 900,637,402,883.4181046% | 900,637,402,883.4181046% |
| Completed LOW-to-HIGH cycles | 344,704 | 344,704 |
| Mean cycles/calendar day | 1,389.935484 | 1,389.935484 |
| Median cycles/calendar day | 0 | 0 |
| Zero-cycle days | 193 | 193 |
| Days with at least 2,000 cycles | 30 | 30 |
| Capital releases | 0 | 0 |
| Total release loss, USDT | 0 | 0 |
| Mean / maximum release loss | Not applicable | Not applicable |
| Releases recovered / unrecovered, B and K | 0 / 0; no observations | 0 / 0; no observations |
| Recovery cycles p50 / p90, B and K | Not applicable | Not applicable |
| Recovery time p50 / p90, B and K | Not applicable | Not applicable |
| Maximum observed hold, days | 111.279479 | 111.279479 |
| Hold p95, seconds | 2.35068680 | 2.35068680 |
| Inventory-open time, hours | 5,330.681850 | 5,330.681850 |
| Inventory-open share of elapsed time | 89.561188% | 89.561188% |
| Hours in positions already older than 24 hours | 4,571.297364 | 4,571.297364 |
| Idle hours | 621.318090 | 621.318090 |
| Maximum drawdown | 0.2685166700% | 0.2685166700% |
| Temporal stability, canonical descriptive aggregate | 19.7221216532 | 19.7221216532 |

Hold and exposure calculations include terminal right-censored inventory. The maximum hold
was a completed cycle from 2026-02-05T22:15:07.880742Z to 2026-05-28T04:57:34.843455Z.
The separate terminal position entered 2026-08-17T15:01:40.250763Z and remains censored.
Recovery B means
pre-BUY capital; recovery K means the original HIGH target proceeds. There were no releases,
so recovery success rates and quantiles are undefined, not 100% success or zero-time recovery.
The daily denominator includes all 248 calendar dates touched by the frozen interval.

## Separate fixed-notional ruler

This auxiliary calculation reconstructs rounded quantities from a fresh 100-USDT notional
for each position and adds PnL without compounding. It follows the same event path and includes
the terminal mark. It is not the principal replay bankroll.

| FIXED_NOTIONAL_100 metric | M007 | M010 |
| --- | ---: | ---: |
| Reference notional, USDT | 100 | 100 |
| Additive PnL, USDT | 2,292.2243667 | 2,292.2243667 |
| Reference 100 plus additive PnL, USDT | 2,392.2243667 | 2,392.2243667 |
| Release loss, USDT | 0 | 0 |

## Causal mechanism and hypothesis result

The runtime produced 1,439 sealed checkpoints from 461 positions. Independent verification
found no snapshot-hash failure, no last-trade/checkpoint prefix violation, no integer-type
failure, and no discrepancy between the Boolean gate conjunction and the release decision.

| Frozen gate or reason | Checkpoints |
| --- | ---: |
| Same destination / no productive alternative reason | 1,127 |
| Different destination, insufficient causal history reason | 312 |
| Identified original remaining-hold support | 1,015 |
| Activity support C1h >= 30 and C24h >= 120 | 1,033 |
| Positive loss within the frozen 5-bps limit | 1,006 |
| Exact theoretical K-recovery cycle count available | 1,439 |
| Identified destination first-cycle q90 | 0 |
| Other five support/loss gates pass, excluding q90 and RMST comparison | 39 |
| Full release conjunction passes | 0 |

Gate counts overlap. The two reason counts are exhaustive and mutually exclusive. No checkpoint
identified the destination first-cycle 90th percentile required by preregistration. Consequently,
even the 39 checkpoints satisfying the other support/loss gates could not establish the frozen
recovery-time inequality. A computable theoretical cycle count does not establish first-cycle
waiting-time support or executable recovery.

This is a valid zero-action result, not a strategy bug. It establishes that the frozen rule does
not relieve the observed capital lock on this DEVELOPMENT tape. It does not test the realized
economics of an actual release, because none occurred. Therefore the economic hypothesis is
INCONCLUSIVE, rather than a positive result or a general rejection of every capital-release
mechanism. No threshold, checkpoint, estimator, lookback or selection rule was relaxed.

There is no promotion: compounded capital and fixed-notional PnL are exactly unchanged, failing
the preregistered improvement requirement, while exposure older than 24 hours fell by 0%, not
the required 10%. M007 remains the DEVELOPMENT champion.

## Technical evidence and provenance

The immutable historical M007 log contained lossy NumPy-to-Pydantic event-ID serialization.
The corrected M007 reconstruction preserved exact integer trade ordinals. A separate directed
audit reproduced the historical log by applying the demonstrated old serialization only to
505 cycle entry IDs, 334 cycle exit IDs and 20 selection-event IDs: 859 field occurrences.
Every other field matched exactly. Original artifacts remain unchanged. These counts describe
serialized field occurrences, not necessarily 859 distinct trades.

The subsequent M007-versus-M010 gate compared exact reconstructed event IDs without rounding
or excluding them. Its complete behavioral hash is
`81757fd64c5dcddbaf6d0b07a9aef4d5152c2456c56dc9698abb5aa8288d261a`.
Thus an audit of a historical evidence defect did not weaken the strict equivalence requirement.

M010 simulation source SHA:
`1e4b85da2dcaf3e6a1ee4ff043c6870d207da0a5`.
Postprocessing recovery and technical reconstruction source SHA:
`f0c7e3029eeadf321591772603646a7aea06f123`.
Run identity:
`5a53ab7dcebbdaf0f4697148c54d3e71b098575b6abc1a3b299c45312a5f4f0c`.

The completed simulation was saved before a parent-config loading failure interrupted
postprocessing. Recovery reused the saved M010 result without rerunning its simulation and
bound the analysis SHA separately. Prior technical failures and invalidation history remain
evidence; their existence is not erased by successful postprocessing recovery.

Raw completed-replay file SHA-256:
`af6a1297144dbb31396d7ca9c51301e4d6d59199b7541ccbb26e00c75a84a9c4`.
Canonical embedded result SHA-256:
`4b781fe79f8c61bd8991c32a6b45e4070d0f3dd159ebd8d059160935f08ef7e9`.
Both were independently reconciled. The earlier causal-audit file correctly retains its
then-pending equivalence status; the completed canonical report supplies the later exact proof.

## Next step and limits

Close M010 as an inconclusive completed experiment and review the campaign findings before
another model. Keep the frozen M010 rule and all technical evidence intact. Any future proposal
must explain what new causal evidence or independently justified hypothesis would address the
destination-start uncertainty; merely reducing the observed blocking threshold is retrospective
tuning. No M011 registration, execution or parameter sweep follows from this autopsy.

All results remain DEVELOPMENT diagnostics, not prospective validation. VALIDATION and
LOCKED_TEST remained closed. No Binance account, Testnet, live orders or deployment was accessed.
Executable release loss remains UNKNOWN without queue, spread, book, slippage and latency
evidence. Temporal stability and regime summaries are retrospective descriptions only.

## Delivery verification

- Full pytest: 215 passed, 2 skipped. The skips are opt-in database integration (no Compose
  database requested for this schema-free change) and the no-GPU-runtime branch on a machine
  with GPU runtime; the separate equivalence tests ran. No migration change was made.
- Ruff check, Ruff format check and mypy strict (68 source files): PASS.
- The canonical CLI returned `SKIPPED_COMPLETED_INCONCLUSIVE` after closure; the registry
  still has the same three M010 technical-attempt run identities. No fourth run was started.
- Playwright opened the generated offline dashboard and verified the M010 100-USDT curve;
  screenshot `output/playwright/m010-temporal-dashboard.png` was visually inspected. Only
  a missing optional favicon produced an HTTP 404; no functional page error was observed.
- The temporary loopback-only QA server and browser were closed. No replay remains active.
- Registry final evaluation: `cd2fd9a834f7c848ce15be8427a527249ef0f66be3caca5a8f1c6b01f8126403`.
  Prior evaluation files remain unchanged, and its raw replay, CSVs, windows and regimes
  are byte-identical in the appended scientific evaluation.
