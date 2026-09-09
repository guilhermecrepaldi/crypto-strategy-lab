# M022 independent scientific pre-run review

STATUS=PASS_CONDITIONAL_PRE_RUN
REVIEWER_MODEL=gpt-6-astra
REVIEW_DATE=2026-09-08
ECONOMIC_REPLAY_EXECUTED=false
STRATEGY_APPROVAL=false

## Verdict

No remaining blocking defect was identified in this candidate after the successive
adversarial repairs and final targeted checks. This approval is conditional on the
canonical runner's complete preflight: registered M022 identity, reviewed unchanged
source hashes, exact preregistration and OWNER gate, clean published main, validated
input bindings, and no existing M022 result directory. It covers only the single
2025-01-01 00:00 inclusive to05:00 UTC exclusive experiment. It does not authorize
Day2, M023, a sweep, account access or live orders.

## Scientific contract

M021 remains historical control at19 complete cycles, with its original source
and physical artifacts preserved. M022 retains99.6950USDT plus100USDC, initially
marked199.8850, the same first bridged-book anchor, fixed price lattice, one-USDC
quantity, one-tick return, zero conditional fee, five-hour data window, queue,
latency, compatible price-priority and one-use global liquidity.

The changed package is owned-return priority, floating free-entry placement and
a160-nonterminal-order cap. Explicit lane ownership is also a stronger allocator
constraint than M021's pooled internal accounting; identical aggregate starting
capital does not establish identical internal admission. The preregistration
discloses this and preserves M021 due-ACK precedence instead of silently changing
execution ties. A positive cycle delta would measure this package on the same
development tape, not isolate the contribution of one feature.

## Reviewed implementation properties

- Two hundred lane identities and initial allocations persist. B funding is checked
  against its original allocation plus its realized cycle profits; S inventory and
  exact cost are retained by lane. No borrowing or synthetic funding is permitted.
- Free placement uses the causal book and registered lattice. Already selected
  quotes retain queue; moved zero-fill entries release capital only after ACK.
  Owned claims remain at the filled entry's one-tick target.
- Return preemption examines all crossing free entries. Returns wait for cancellation
  acknowledgments and ordinary activation; they do not internally fill or bypass
  post-only, queue or native-time eligibility. Conflicting obligations have the
  preregistered deterministic ordering.
- The cap includes pending, active and cancel-pending orders. A first partial fill
  freezes an entry. A fill during already-issued cancellation leaves an explicitly
  owned PARTIAL_RESIDUAL_BLOCKED state if the residue cannot satisfy historical step;
  it is not rounded, pooled across lanes or counted as a cycle.
- Matching retains the common physical trade budget and strict activation causality.
  Checkpoint fixtures exercise persisted JSON and continuation equivalence. The
  bounded runner retains the five-hour cutoff with no forced liquidation or automatic
  repeat; existing outputs fail closed.
- Manager audit now links claim/entry, return submission/physical EXIT order and
  return fragments/physical fills. Chronological open-order reconstruction verifies
  the cap. Initial lane allocation, B funding/profits and S free quantity/cost are
  checked against reconstructed physical ownership transitions, not merely copied
  terminal/report mirrors. The reused base audit supplies fill, queue, financial
  and shared-liquidity reconciliation.
- Utilization distinguishes open orders from actually activated orders and parked
  free lanes. Historical activation reach is retained. Return completion waits are
  sampled once per completion, with submission/activation milestones and censored
  open claims separate; units, even-sample median and nearest-rankP95 are registered.

## Evidence from this review

Final command:

```text
.venv/Scripts/python.exe -m pytest -q tests/test_managed_dense_ping_pong.py tests/test_run_managed_dense_ping_pong.py tests/test_dense_ping_pong.py tests/test_run_dense_ping_pong.py tests/test_zonal_ping_pong.py tests/test_run_zonal_ping_pong.py tests/test_model_registry.py
```

90 focused tests passed. git diff --check reported no whitespace errors (only the
repository's line-ending warning). Prior adversarial cases include fragmented
returns, cancel-race partials, all-conflict preemption, lane identity/price/quantity
tampering, original-budget tampering and unactivated cancel-pending metrics.

The final independent ownership reproduction swapped manager_s_free for active
S001 and parked S100, updated both reported mirrors and recomputed the terminal
hash. It now fails with M022_S_LANE_OWNERSHIP_RECONSTRUCTION_MISMATCH. The original
untampered synthetic state passes the manager audit. No historical replay or
registration was performed by the reviewer.

## Limits and post-run obligations

These are normalized one-USDC orders below minimum notional, not live-executable
orders. Zero fee and historical execution-rule transfer remain conditional. L2
does not reveal individual order rank, and the execution assumptions are not a
proven PnL bound. Returns can remain blocked by owned obligations, post-only,
financial eligibility, queue or step-size residues. The cap is an upper bound,
not a guarantee of160 useful orders.

No throughput result exists under this approval. Publish the exact source before
the one run; afterward reconcile physical audit, cycles, state, conservation,
wait censoring and metrics before interpreting the delta against19. A changed
bound source requires delta review. This review does not promise detection of
every possible defect or independently authenticate future produced artifacts.

## Exact reviewed source bindings

Hashes are SHA256 with CRLF normalized to LF. All runner SOURCE_PATHS are bound.

REVIEWED_SOURCE_SHA256_LF[scripts/run_managed_dense_ping_pong.py]=d8e977e9972c600c0a4556af2fe3e21c317f0246fbfaf0ade5ba67b6ef0fa17d
REVIEWED_SOURCE_SHA256_LF[scripts/register_managed_dense_ping_pong.py]=d8051155e4183cdfdca5bbe8342a2e2e87055a45d3067398af7d23cf50da6ec5
REVIEWED_SOURCE_SHA256_LF[scripts/run_dense_ping_pong.py]=96ceaa817a30a7c4922b8a638f3b28d86339d2bec7ac9efd4e49775c9fad0e79
REVIEWED_SOURCE_SHA256_LF[scripts/run_zonal_ping_pong.py]=b310fbbb781f89d41bb69bc09d09b922960570d99c9aae136953f6fbc3ab90d8
REVIEWED_SOURCE_SHA256_LF[scripts/validate_tardis_l2_samples.py]=6e6d2c799293da4fc6ef5debbf890236fbaa62f7420a047d71f11c532b037f99
REVIEWED_SOURCE_SHA256_LF[scripts/run_l2_monthly_samples.py]=68aafca8598cb70eb34fa4761c3111eac4f39ac33a7f2f482677714d7ec49c80
REVIEWED_SOURCE_SHA256_LF[scripts/run_high_uptime_recovery.py]=4ce00d03fd86d1c4c09db523e6b1c6fd4b6f01edd72899585151a0b8aa2e8186
REVIEWED_SOURCE_SHA256_LF[scripts/run_b10_reality.py]=90f6852a773ca678570c2347a95e6caa348f11b30811066155e1b18b96a33ff7
REVIEWED_SOURCE_SHA256_LF[src/crypto_strategy_lab/microstructure/zonal_ping_pong.py]=8fc0cd0565d6f635e9c5fc8c9a16f35e06a5b3ae75085249f93e71e289efe6ce
REVIEWED_SOURCE_SHA256_LF[src/crypto_strategy_lab/microstructure/data.py]=311de231b02c72f02b5e2e2444c74f7017e9e81b56f3977e5056b57cb4d19922
REVIEWED_SOURCE_SHA256_LF[src/crypto_strategy_lab/microstructure/tardis_l2.py]=1899a0b0d968296b2b9d9a6bba8a1f1602e0b34162b4ca4b7ecfdbe665f9490d
REVIEWED_SOURCE_SHA256_LF[src/crypto_strategy_lab/microstructure/b10_reality.py]=4345ef764299d5414c29a9411fe00e613e02dac542f147e29064cf48b31bd4cb
REVIEWED_SOURCE_SHA256_LF[src/crypto_strategy_lab/microstructure/recovery_reserve_study.py]=6a702dfcfd5130e5cb0308472f5e4237ced54abeff1670ec3623c6591e4045f9
REVIEWED_SOURCE_SHA256_LF[src/crypto_strategy_lab/microstructure/serial_replay.py]=8515862b88842565cfb99295da651521a27eef28290f0e2b0ca742851b924ab0
REVIEWED_SOURCE_SHA256_LF[src/crypto_strategy_lab/domain.py]=fa3a7839429b6b98a11c971ec79d796fc09207fa182f1629d527a86c7e77c5f5
REVIEWED_SOURCE_SHA256_LF[src/crypto_strategy_lab/ml/model_registry.py]=864e96864911cc56cf1233a09a91a0287592cf44225c2b9c0d65e1dbe6ab94c2
REVIEWED_SOURCE_SHA256_LF[tests/test_managed_dense_ping_pong.py]=9c7cf6d2fc1873f4ba9f18346a6031268257ffcc224bdc56fddb7fa5da360594
REVIEWED_SOURCE_SHA256_LF[tests/test_run_managed_dense_ping_pong.py]=e1078ffeb846d3d7220ce0c5f9b2ee6abe12c85fc5bddfbdb2c631f3b6ee6940
REVIEWED_SOURCE_SHA256_LF[tests/test_dense_ping_pong.py]=8c36163966800c909c20f1cf762d006868bdb2a62b03ca4c1bac31c9fd8e9802
REVIEWED_SOURCE_SHA256_LF[tests/test_run_dense_ping_pong.py]=aba7143672f5a4f280bc3b98d1f42172245dc485b629a5ebc84f716639929a3b
REVIEWED_SOURCE_SHA256_LF[tests/test_zonal_ping_pong.py]=bcd0e41b29d375cfdd97c72a1cf3bbda1a576f81c560cbd62781a1aa164fd513
REVIEWED_SOURCE_SHA256_LF[tests/test_run_zonal_ping_pong.py]=3ba4ccc7414829c12d7e222b428d2efa6d05021b0db5fe6b6792ec3713a3c616
REVIEWED_SOURCE_SHA256_LF[tests/test_model_registry.py]=ec75f26af7430e6b52d6414f233e44cc5ca767bf56ccca3ece328c7bd8cc9e3a

