# M012 JOURNAL

Append-only research journal. M012 has not run at the time of this entry.

## OWNER capital policy correction — 2026-09-07

TYPE=OWNER_CAPITAL_POLICY_CORRECTION
PREVIOUS_INTERPRETATION=FIXED_NOTIONAL_100_AS_PRIMARY
STATUS=INVALID_FOR_OWNER_STRATEGY
CANONICAL_CAPITAL_MODE=COMPOUNDING
REINVESTMENT=95%_OF_NET_POSITIVE_PROFIT
RESERVE_FUNDING=5%_OF_NET_POSITIVE_PROFIT
POSITION_SIZING=CURRENT_AVAILABLE_OPERATING_BANK
INITIAL_OPERATING=100
INITIAL_RESERVE=5
NO_OWNER_WITHDRAWALS=YES
FIXED_100_RESULT_NOT_OWNER_STRATEGY_RETURN=YES
NEW_RUN_STARTED_BEFORE_CORRECTION=NO
MODEL_REGISTERED_BEFORE_CORRECTION=NO
DECISION=Correct unpublished M012 preregistration and implementation before model registration, audit and first replay. Fixed100 historical artifacts remain auxiliary execution diagnostics only.
AUTHORITY=docs/microstructure/OWNER_COMPOUNDING_CORRECTION.md
COMMIT=Containing publication commit; resolve with Git history.

## Reporter fixture validation — before replay

TYPE=ERROR
ERROR_TYPE=TEST_ASSUMED_LF_ON_WINDOWS
EVENT=New reporter test expected an LF-only literal although fixture write_text created CRLF. Reporter preserved the original bytes; one test failed,16 passed.
EFFECT_ON_REPLAY=NONE; no M012 run exists.
DECISION=Compare with actual fixture bytes captured before publication, then rerun.

## Reporter fixture recovery — before replay

TYPE=RECOVERY
EVENT=17 reporter/registry tests pass,0 fail; original journal byte prefix and idempotence verified on Windows. Fixed-notional primary capital is rejected by the unchanged canonical RunSpec.
REPLAY_INVALIDATED=NO; no M012 run exists.

## M012 registered before replay

TYPE=PREREGISTRATION
MODEL_ID=M012
MODEL_HASH=d7bcb697bc870703deabfa35e844e23748424a0cefb08ed753bcd74ba35b022e
CAPITAL_MODE=COMPOUNDING
POSITION_SIZING=USE_AVAILABLE_OPERATING_BANK
PREREGISTRATION_SHA256_LF=005b6ca60ac9a456e86d46c3a4c8c3375cd68f4f871fbde6658b3047c85aadab
SPEC_SHA256_LF=1504600b6d51f8d1a62ec47ef75baa2b3f63168492c880d6d52b8bf2211d7443
RESERVE_FUNDING=5%
OPERATING_REINVESTMENT=95%
RESERVE_TARGET=5%
RESERVE_FLOOR=max(1e-8,0.001*operating_book_bank); escrow also protects restored post-transfer floor
MAX_LOCK=24h
RUN_STATUS=NOT_STARTED
DECISION=Register final compound policy and conservative max-filter capacity rejection before outcome observation. Execution waits for code/tests/independent audit and published source.
COMMIT=Containing preregistration commit.

## Implementation and preflight — before first economic replay

TYPE=IMPLEMENTATION_VALIDATION
MODEL_ID=M012
CAPITAL_MODE=COMPOUNDING
IMPLEMENTATION=HighUptimeRecoveryReplay over unchanged frozen B10 execution kernel
TESTS_PASSED=144
TESTS_FAILED=0
RUFF=PASS
INDEPENDENT_PREFLIGHT=PASS_CONDITIONAL_PRE_RUN
AUDIT_SCOPE=55 independently reviewed focused fixtures; full144 regression set passed separately. No M012 economic run yet. Final raw/ledger audit remains required.
TEST_SUITE_PASS_IS_STRATEGY_PASS=NO
DECISION=Publish validated implementation and reviewed source hashes, then start the first OWNER-authorized compound replay without further permission.
EVIDENCE=reports/usdcusdt/M012-preflight-independent-review.md
COMMIT=Containing implementation commit.

## Publication whitespace correction — before execution

TYPE=ERROR
EVENT=Implementation publication command did not stop on two whitespace-only diff-check findings in historical archival helper. No kernel or economic semantics affected; no M012 run started.
DECISION=Remove trailing whitespace, enforce command failure checks, publish correction before execution.
