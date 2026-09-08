# M018 — independent pre-execution review

STATUS=PASS_CONDITIONAL_PRE_RUN
REVIEW_DATE=2026-09-08
REVIEWER_MODEL=gpt-6-astra
SCOPE=OWNER_GATED_DAY1_PRICE_PRIORITY_ONLY
ECONOMIC_REPLAY_EXECUTED_BY_REVIEWER=false
LATER_DAY_MARKET_DATA_READ_BY_REVIEWER=false

## Findings and scientific verdict

No remaining material implementation or causal-accounting blocker was found in
the reviewed delta. One observability discrepancy was identified before PASS:
the preregistration requested an adjustment reason but the admission event lacked
an explicit reason field. The author added
`SELECTED_LOW_NOT_PASSIVE_AT_SUBMISSION` and a fixture assertion; the bindings
below include that correction. This review changes no strategy/runtime code.

The isolated hypothesis is supported by the already-audited M017 first-day
post-only rejection bottleneck, not by outcomes from later days. Lowering a new
BUY limit can reduce immediate crossing without improving queue priority; it can
also reduce fills and increase distance/time to the original HIGH. This is an
admission-policy experiment, not a matching-engine bug fix or evidence that
1000 profitable cycles/day is attainable. No funding80%, extra queue, indicator
bundle, exchange or newly loaded source date is included.

## Implementation and invariants

M018 requires its separate entry-admission hash in replay identity. Other models
cannot silently enable that policy. It retains the M017 deadline-policy hash;
M015/M016/M017 retain their preexisting economic paths. Checkpoint restore rejects
an incompatible admission-policy identity.

For a new flat BUY, the validated causal book and current symbol tick produce
`min(selected_LOW, floor_to_tick(ask-tick))`, subject to positive-price, known
coverage and unchanged symbol/budget gates. Missing evidence waits. The original
candidate and HIGH remain unchanged. Order creation does not create a fill;
activation-time crossing still rejects. Queue is established by the unchanged
observed-book activation authority, not granted at placement. Book changes do not
cancel/reprice an existing ACTIVE/PENDING order; zero-fill terminal retries use
the newly available book. Adjusted events bind original/admitted prices, ask,
tick, capture identity, native update identity, reason and policy hash.

The first BUY fill freezes the admitted order limit. Canceled partial entries
continue only that limit and the unspent original lot budget; the earliest
entry timestamp remains unchanged. Independent synthetic assertions confirmed
unchanged entry_us, buy_cost and lot_budget after partial cancellation/retry and
remaining order notional<=unspent lot budget. Settlement clears the anchor;
ordinary SELL still uses the selected HIGH. This is neither DCA nor an extra lot.

Existing fee accounting, maker/taker classifications, protected actual20bps cap,
theoretical H1 cap10bps, floor2.5, funding10%, initial100+10, compounding and
shared trade/depth budgets are unchanged. PRICE_PRIORITY remains an explicit
execution envelope, not a claim of exact real-account queue position. Fee-zero
profile is frozen, not assumed universally. Partial fills and releases do not
count toward ordinary complete NET-positive cycle targets.

The registered timer remains2h. The unresolved OWNER phrase concerning1hour was
not converted into a new policy. Latency/cap/floor/liquidity can still cause real
deadline violations, which must be reported rather than rounded into success.

## Effective one-day execution gate

The OWNER guard executes before preflight, input verification and writer access.
It requires unique valid authority fields, AUTHORIZED_MODEL=M018,
NEW_REPLAY_AUTHORIZED_NOW=true, APPROVED_COMPARISON_DAYS=1 and
EXTENSION_AUTHORIZED=false. Missing/invalid/duplicate authority, legacy model
requests and day2/3/12 extension requests fail closed. The permitted tuple was
checked read-only and is exactly `(2025-01-01,)`.

The run passes this selected tuple to evidence verification, stitched mapping,
history input construction and native event iteration. End time derives from
that single mapping, preserving exactly24h and no forced settlement at cutoff.
A poison-day2 fixture verifies the run entry path verifies/builds only day1.
Metadata catalogs containing other dates are not authorization to open their
market-data payloads. The spec's calendar_days=3/source_dates list is only the
maximum conditional stage universe; initial_stage_days=1 is the executable
initial window. No full-state continuation exists merely because an engine
checkpoint exists: future extension remains fail-closed pending audited support.

The canonical preflight requires the published source, spec, preregistration,
review and OWNER authority, clean main worktree, source-hash matching review,
exact registered design/hash and frozen execution profile. The manifest binds
M018 model/entry/deadline identities, OWNER authority hash and selected mapping.
These publication/registration gates were inspected, not bypassed. M018 was
registered while review was being closed; an independent final read and
`validate_registered_design` passed with model hash
`68e9b01e0f4646319364199fe17970c5c1ec9b22e46c6a498df131ac2f0f43e5`.
Publication and successful canonical preflight remain mandatory before execution.
This conditional PASS does not substitute for either or authorize an extension.

## Verification

159 synthetic tests passed across test_m018_passive_admission,
test_m017_protected_budget, test_m016_protected_deadline,
test_run_l2_monthly_samples, test_observed_l2_execution,
test_high_uptime_recovery, test_b10_reality, test_b10_reserve_weekly and
test_reserve_recovery_diagnostics. Ruff passed for the changed runtime/runner
and their tests; git diff --check passed. Additional in-memory assertions tested
partial-entry budget and timer preservation. No historical replay, new data
acquisition, HTML/render, registry mutation or source edit was performed by the
reviewer. Software PASS is not STRATEGY_PASS.

## Reviewed bindings

REVIEWED_SOURCE_SHA256_LF[scripts/run_l2_monthly_samples.py]=fad49cf6699ea96b20085f3fb05bdb2d35f727728311dba66ff2283cd210e15f
REVIEWED_SOURCE_SHA256_LF[scripts/validate_tardis_l2_samples.py]=6e6d2c799293da4fc6ef5debbf890236fbaa62f7420a047d71f11c532b037f99
REVIEWED_SOURCE_SHA256_LF[scripts/run_high_uptime_recovery.py]=4ce00d03fd86d1c4c09db523e6b1c6fd4b6f01edd72899585151a0b8aa2e8186
REVIEWED_SOURCE_SHA256_LF[scripts/run_b10_reality.py]=90f6852a773ca678570c2347a95e6caa348f11b30811066155e1b18b96a33ff7
REVIEWED_SOURCE_SHA256_LF[src/crypto_strategy_lab/microstructure/observed_l2_execution.py]=015287406f3fce21e41372cc9ead421048f9bb5b799589707aa45c765edd3a43
REVIEWED_SOURCE_SHA256_LF[src/crypto_strategy_lab/microstructure/tardis_l2.py]=1899a0b0d968296b2b9d9a6bba8a1f1602e0b34162b4ca4b7ecfdbe665f9490d
REVIEWED_SOURCE_SHA256_LF[src/crypto_strategy_lab/microstructure/high_uptime_recovery.py]=c73cbd2ce86003814c18802ce451e2432feb83cd9018cfefadc47afd16b3bcb6
REVIEWED_SOURCE_SHA256_LF[src/crypto_strategy_lab/microstructure/b10_reality.py]=4345ef764299d5414c29a9411fe00e613e02dac542f147e29064cf48b31bd4cb
REVIEWED_SOURCE_SHA256_LF[src/crypto_strategy_lab/microstructure/serial_replay.py]=8515862b88842565cfb99295da651521a27eef28290f0e2b0ca742851b924ab0
REVIEWED_SOURCE_SHA256_LF[src/crypto_strategy_lab/microstructure/recovery_reserve.py]=0882b2d465ed0fc7c163e00046a5ac5b7127b57f586082d222ac05f9b57c9dd5
REVIEWED_SOURCE_SHA256_LF[src/crypto_strategy_lab/microstructure/data.py]=b7b19926c7bbcfb91f377228447a2b750c05150de4f2c514b60b6b2d5be4b080
REVIEWED_SOURCE_SHA256_LF[src/crypto_strategy_lab/microstructure/tape_cache.py]=7640e20446eb02fb9296ba801605318c11993899e47cbdef38540b08a8d732fb
REVIEWED_SOURCE_SHA256_LF[src/crypto_strategy_lab/microstructure/operator.py]=07458aea39284982ed7fe1e08e5527de4ac7dc1acc7d87c2a0bcace1a44d628d
REVIEWED_SOURCE_SHA256_LF[src/crypto_strategy_lab/microstructure/reserve_recovery_diagnostics.py]=19f69ad5a8267d874c5a9368954a01137c641bba2c2a0fa7cb8aeb7ab3ed67a8
REVIEWED_ARTIFACT_SHA256_LF[docs/microstructure/M018_MODEL_SPEC.json]=e8a4f454da94cf0b51cdbacca61ba1b5da8d23553882f562ea89e3411a16d777
REVIEWED_ARTIFACT_SHA256_LF[docs/microstructure/M018_PASSIVE_ADMISSION_PREREGISTRATION.md]=dee6c34183817b17abe17b7d224705934d22d73789b566dc519ba90683d3bf10
REVIEWED_ARTIFACT_SHA256_LF[docs/microstructure/OWNER_GATED_REPLAY_WINDOW.md]=61e83dad88ae66a46b4302242c4b55391831ff2e5959e962a0b00f7b18eae0a6
REVIEWED_ARTIFACT_SHA256_LF[tests/test_m018_passive_admission.py]=7c1f3d4682fa6fd6133cf348dce301a2f87b479e62102dc94ee53542502ab24f
REVIEWED_ARTIFACT_SHA256_LF[tests/test_run_l2_monthly_samples.py]=87f532790efc9642016ede71b95dff69f4e614e06099f3d2df5942b428d7e76f
