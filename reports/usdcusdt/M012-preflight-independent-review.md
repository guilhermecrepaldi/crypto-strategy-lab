# M012 independent preflight review

STATUS=PASS_CONDITIONAL_PRE_RUN

The registered COMPOUNDING design and executable implementation were independently
reviewed before economic execution. This is permission to proceed through the remaining
publication gate, not a strategy result, historical fill certification or completed-run audit.

MODEL_ID=M012
MODEL_HASH=d7bcb697bc870703deabfa35e844e23748424a0cefb08ed753bcd74ba35b022e
SPEC_SHA256_LF=1504600b6d51f8d1a62ec47ef75baa2b3f63168492c880d6d52b8bf2211d7443
PREREG_SHA256_LF=005b6ca60ac9a456e86d46c3a4c8c3375cd68f4f871fbde6658b3047c85aadab
REVIEWED_SOURCE_SHA256_LF[src/crypto_strategy_lab/microstructure/high_uptime_recovery.py]=ba2e459916ee434e1faf637d8ef2b6901378f507f8d42529935c9e361305b3ca
REVIEWED_SOURCE_SHA256_LF[scripts/run_high_uptime_recovery.py]=a5c26b86eb0e2f38df820e8ccf408965170a7857f45b05ff3d87823aba33beee

Scope: actual runner/registration binding, imported policy class, policy/kernel accounting,
12/18/24h causal deadlines, protected reserve floor/partial orders, fullspan raw integrity,
day1/7/30/90 capital checkpoints and durable-prefix provenance. Software tests are not a
strategy pass. Historical public L2/queue/latency/fees remain conditional evidence gaps.

Verified runner corrections: prereg+spec match registered model hash;
actual imported class source recorded; named capital checkpoints precede the first trade
at/after the boundary; curves and trace are hash-bound; exceptions preserve the previous
valid checkpoint rather than blessing partially mutated state. The actual imported class is
`crypto_strategy_lab.microstructure.high_uptime_recovery.HighUptimeRecoveryReplay`, with
the expected repository file and B10RealityReplay inheritance. The runner's missing initial
capital-mode identity was corrected and tested before execution. Review source bindings
are checked again at launch; any changed kernel/runner requires renewed review.

## Evidence

Command: `uv run python -m pytest tests/test_high_uptime_runner.py tests/test_high_uptime_recovery.py tests/test_b10_reality.py tests/test_b10_independent_audit.py -q`

Result:55 passed,0 failed (5 runner,23 M012 policy,22 frozen B10,5 historical audit fixtures).
Ruff passed for runner, runner tests, new kernel and policy tests. Direct read-only validation
of the actual registered M012 model against current LF-normalized spec/prereg bytes passed.
No economic replay or long historical data parsing was performed by this reviewer.

Production runner fixture invokes its real orchestration with fake public history and a
bounded replay stub: day1/7/30/90 all precede the next raw event, including an exactly equal
day90 event; all due boundaries are retained across a long gap; capital-curve SHA/bytes
match the durable checkpoint. Another test verifies failures do not overwrite valid state.

Policy fixtures exercise actual kernel fills and genuine driver ordinary-profit → new
compounded entry →18h forced exit → causal reselection → compounded reentry. Verified5%/95%
funding, positive forced funding with separate counters, partial-entry budget/age, protected
fee-inclusive limit, partial release escrow, restored-bank floor, dust basis, no reserve
creation of equity, exact24h violation without fake fill, inherited queue/latency/cancel,
same-epoch depth conservation, JSON resume, fullspan integrity and no100reset.

Review corrections also separated completed-hold quantiles from censored inventory, fixed
capacity-size comparison to use immutable profile support instead of depleted book depth,
and restricted capital downtime to the preregistered minimum-affordability/max-capacity
conditions rather than unrelated price-filter failures. No protocol change after registration.

## Conditions and non-claims

- First replay remains B_REALISTIC_CONSERVATIVE, fee0 conditional pilot. Queue, latency,
  historical L2, fees and unlimited market capacity are not independently established facts.
- All hard-lock failures, losses, reserve blocks and capacity flags must remain in the
  fullspan evidence. This signoff does not permit economic early stop or outcome tuning.
- B10 code remains historical and unmodified. Prior fixed100 returns are auxiliary,
  never M012 OWNER returns. Software validation is not strategy acceptance.
- The existing B10 independent auditor is NOT a drop-in M012 auditor: funding and signal
  schema differ. Post-run M012 audit must independently reconstruct5% funding, protected
  reserve usage, dust/fee basis and raw support for first100 ordinary cycles plus ALL release
  signals/attempts/closures. This completed-run gate remains open, not silently passed.
- Completed economics, sustainability, same-prefix opportunity productivity, day90/final
  curves and OWNER gates are still unknown. The model may legitimately fail those gates.
