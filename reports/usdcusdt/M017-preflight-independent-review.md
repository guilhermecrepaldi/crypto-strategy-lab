# M017 — independent source-bound preflight review

STATUS=PASS_CONDITIONAL_PRE_RUN
REVIEWER=GPT-6 Astra; independent task m016_preflight_audit
DATE=2026-09-08
SCIENTIFIC_PARENT=M015
EXPERIMENTAL_CONTROL=M016
TECHNICAL_ANCESTOR=M016
REGISTRATION_GATE=EXACT_REGISTERED_SPEC_AND_PREREGISTRATION_REQUIRED_BEFORE_RUN
REGISTERED_DESIGN_CHECK=PASS
MODEL_HASH=b82a5ef829ca396db0f80885807aa4895ec359db3f10d7e917d6e8be0db65af8
M017_POLICY_SHA256=88b14751e15093cadc6abbaa9f3e1a70e875ff4e884b1cd911cf7146af494224
M017_SPEC_SHA256_LF=d9afab40660e73c56f68601d4617dd76f7d5abb5dd5d2de94e447e387f977e20
M017_PREREGISTRATION_SHA256_LF=467cc497c78986780c23e427d2ef04ec522bba8cc5f79071f0448b8ee48b3d20

## Scientific decision and scope

The isolated executable-budget alternative is supported as a falsifiable second
case of the existing maximum-three sequential tranche. It is not a promotion of
M016, an optimal-budget claim, an authorization for a third case, or funding80.
The completed M016 control passed independent evidence reconciliation, not
economic viability: 19 positive ordinary cycles, equity109.902, consumption0.2328,
eight holds over2h and maximum119.997830754h across all twelve approved days.
See M016-completed-independent-audit.md and the separately verified D2 autopsy.

The D2 available-prefix depth calculation required16.8120245833bps against the
configured10bps budget, while reserve availability and observed quantity were
sufficient. That specific evidence motivates ONE20bps alternative. It does not
predict an actual fill at that timestamp under another policy or establish a
sufficient budget at other deadlines. Higher allowed losses may worsen reserve
erosion; entries and positive cycles can remain scarce. M016's zero-fill BUY and
flat-time observations do not identify rejection causes by themselves.

## Implementation review

The policy dictionary changes only model identity and the executable cap10→20bps.
The normal B10_H1_B10_F2.5 theoretical opportunity predicate remains10bps. The
actual20bps cap applies consistently to all protected exits, including ordinary
release signals and deadline signals, through the same canonical protected_exit.
No parallel runner, selector, accounting path or liquidity authority was added.

The protected amount remains the minimum of20bps of restored operating bank and
reserve above2.5. Prior partial sold cost/proceeds remain inside the lot budget;
an IOC partial cannot reset it. Deadline preparation, first-fill age, cancellation
response, activation latency, consumed-depth accounting and seam handling are
unchanged. A remaining position strictly after2h is still a violation, including
subsecond lateness. Floor, cap and absent liquidity fail closed without invented
fills, added reserve, grace periods or early economic stops.

Explicit model-to-policy checks reject M016/M017 policy substitution. M015 stays
the default runner choice; M016 retains its original policy hash and10bps result.
M015/M016 specs and preregistrations were checked against execution-source
44d75f9183aa052be20734fac0f244bc4ba238bd and remain unchanged. Source changes after
that run do not relabel its existing artifacts or execution provenance.

Initial100+10, funding10%, serial compounding, PRICE_PRIORITY, frozen profile hash,
exact twelve source dates/order and288h duration remain fixed. This is synthetic
stitched DEVELOPMENT, not continuous history or prospective validation. No other
dates, parity, private account, Testnet or live execution are covered.

## Verification and remaining gates

Independent command:
`.venv/Scripts/python.exe -m pytest tests/test_m017_protected_budget.py tests/test_m016_protected_deadline.py tests/test_high_uptime_recovery.py tests/test_observed_l2_execution.py tests/test_run_l2_monthly_samples.py tests/test_reserve_recovery_diagnostics.py`

Result:102 passed in1.89s. Ruff passed on the three changed runtime/runner files
and the M017 test file. Fixtures cover cross-identity rejection, unchanged M016
hash,15bps eligibility difference, actual deadline fill/provenance, reserve floor,
loss beyond20bps and partial aggregate-budget exhaustion. Existing fixtures cover
M015 defaults, partial BUY/cancellation, original age, missing book, seams, late
fills, the corrected liquidity-veto cache and execution/audit invariants.

The coordinator registered M017 during this review. Independent read-only
validate_registered_design passed against the exact spec and normalized
spec/protocol hashes above; registration was not performed by this reviewer.
The coordinator must still publish these reviewed sources/review/spec/protocol
and registration normally, and pass the canonical clean/published-worktree and
exact-data preflight before economic run. The registration gate remains mandatory
for that preflight. A changed reviewed source invalidates its binding and requires
delta review. No economic replay was performed here.

TEST_SUITE_PASS != STRATEGY_PASS. No claim of guaranteed2h flatness, sufficient
cycle frequency, positive equity or sustainable reserve follows from this review.
The third tranche case remains conditional on the full M017 autopsy and its own
identity, preregistration, tests, independent review and publication.

Scope: changed paths and relevant consumers; unchanged source dependencies are
bound below to preserve the existing reviewed execution and data authorities.

REVIEWED_SOURCE_SHA256_LF[scripts/run_l2_monthly_samples.py]=86f4fd45432d9f8cc66184200494a4775f3b35de3c727d851507bb55812ed046
REVIEWED_SOURCE_SHA256_LF[scripts/validate_tardis_l2_samples.py]=6e6d2c799293da4fc6ef5debbf890236fbaa62f7420a047d71f11c532b037f99
REVIEWED_SOURCE_SHA256_LF[scripts/run_high_uptime_recovery.py]=4ce00d03fd86d1c4c09db523e6b1c6fd4b6f01edd72899585151a0b8aa2e8186
REVIEWED_SOURCE_SHA256_LF[scripts/run_b10_reality.py]=90f6852a773ca678570c2347a95e6caa348f11b30811066155e1b18b96a33ff7
REVIEWED_SOURCE_SHA256_LF[src/crypto_strategy_lab/microstructure/observed_l2_execution.py]=1cbb9e05aa5e9a2fd094647d887424503ab92fb54d66f34bfcb217653ee1f2b2
REVIEWED_SOURCE_SHA256_LF[src/crypto_strategy_lab/microstructure/tardis_l2.py]=1899a0b0d968296b2b9d9a6bba8a1f1602e0b34162b4ca4b7ecfdbe665f9490d
REVIEWED_SOURCE_SHA256_LF[src/crypto_strategy_lab/microstructure/high_uptime_recovery.py]=ee9ec5d263bad227a18448cf9caeab9fb0b8aeca5507f601db95ff7cad8cac6a
REVIEWED_SOURCE_SHA256_LF[src/crypto_strategy_lab/microstructure/b10_reality.py]=4345ef764299d5414c29a9411fe00e613e02dac542f147e29064cf48b31bd4cb
REVIEWED_SOURCE_SHA256_LF[src/crypto_strategy_lab/microstructure/serial_replay.py]=8515862b88842565cfb99295da651521a27eef28290f0e2b0ca742851b924ab0
REVIEWED_SOURCE_SHA256_LF[src/crypto_strategy_lab/microstructure/recovery_reserve.py]=0882b2d465ed0fc7c163e00046a5ac5b7127b57f586082d222ac05f9b57c9dd5
REVIEWED_SOURCE_SHA256_LF[src/crypto_strategy_lab/microstructure/data.py]=b7b19926c7bbcfb91f377228447a2b750c05150de4f2c514b60b6b2d5be4b080
REVIEWED_SOURCE_SHA256_LF[src/crypto_strategy_lab/microstructure/tape_cache.py]=7640e20446eb02fb9296ba801605318c11993899e47cbdef38540b08a8d732fb
REVIEWED_SOURCE_SHA256_LF[src/crypto_strategy_lab/microstructure/operator.py]=07458aea39284982ed7fe1e08e5527de4ac7dc1acc7d87c2a0bcace1a44d628d
REVIEWED_SOURCE_SHA256_LF[src/crypto_strategy_lab/microstructure/reserve_recovery_diagnostics.py]=19f69ad5a8267d874c5a9368954a01137c641bba2c2a0fa7cb8aeb7ab3ed67a8
REVIEWED_TEST_SHA256_LF[tests/test_m017_protected_budget.py]=08245248e0d59b2e5292fe078b4728a2933e02dc2fb9146c1fbdf72c55fea995
