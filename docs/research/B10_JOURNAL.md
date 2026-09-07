# B10 JOURNAL

Append-only research history. Earlier immutable history is preserved in
docs/microstructure/USDCUSDT_EXPERIMENT_JOURNAL.md and Git history; this file is
the canonical continuation from the OWNER GitHub-journal directive.

## 2026-09-07T22:58:29Z

TYPE=ERROR
STRATEGY=B10_FROZEN
PROFILE=A
RUN_ID=a77e0c67fdff8c618cbfc28fdd3d49d2fa831626560aed7fe1ec27007293537d
SIM_TIMESTAMP=2026-07-11T15:04:53.982244Z
PROGRESS=77.2695179464%
CYCLES=2458
NET_POSITIVE_CYCLES=2458
PNL=22.412000 USDT
RESERVE=4.581038 USDT
RELEASES=41
ZERO_DAYS=78 completed UTC days
MAX_HOLD=1859.3709196275 hours
LOCK_HOURS=1877.8956928917 hours
ERROR_TYPE=REPORTING_TEST_EXPECTATION_ARITHMETIC
ERROR_TIMESTAMP=2026-09-07T22:58:29Z
LAST_VALID_CHECKPOINT=a3682ff02b4db3fc10acc918b67f3c488399cf96d175823190e087b0fac113e2
EFFECT_ON_SCIENCE=NONE; new reporting fixture expected53.125% for53 elapsed hours of96; correct value55.2083333%. Reporting calculation was correct.
RUN_VALID=YES_WITHIN_EXISTING_CONDITIONAL_SCOPE
EVENT=One new reporter fixture failed; four other reporter fixtures passed. Active replay unaffected.
DECISION=Correct fixture expectation only, rerun reporter tests; preserve strategy/profile/writer.
EVIDENCE_PATHS=tests/test_b10_checkpoint_scoreboard.py; scripts/b10_checkpoint_scoreboard.py
COMMIT=Containing publication commit, resolvable from git log
EXECUTION_SOURCE_COMMIT=a91811a853bfc5225ce5a2d13750905b6af74991

## 2026-09-07T23:00:06Z

CHECKPOINT_SHA=4b1e67daffb05fc721cd159946440e09381cbca49dc7051a5d544b4f6140b0c7

TYPE=CHECKPOINT

STRATEGY=B10_FROZEN

PROFILE=A_OBSERVED_BEST_SUPPORTED

RUN_ID=a77e0c67fdff8c618cbfc28fdd3d49d2fa831626560aed7fe1ec27007293537d

SIM_TIMESTAMP=2026-08-03T15:07:39.740126+00:00

PROGRESS=86.544485174778722113688452136965107458987772055926971836363870157012651755275037483398951321603546526697697894741595995496973156

CYCLES=2458

NET_POSITIVE_CYCLES=2458

PNL=22.4120000000000000

RESERVE=4.5810380000000000

RELEASES=41

ZERO_DAYS=101

MAX_HOLD=2411.4169634836111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111

LOCK_HOURS=2429.9417367477777777777777777777777777777777777777777777777777777777777777777777777777777777777777777777777777777777777777777778

EVENT=Atomic economic checkpoint published without changing replay

DECISION=Continue unchanged; strategy verdict PENDING

EVIDENCE_PATHS=reports/usdcusdt/B10-reality-scoreboard.json; artifacts\binance\b10-reality-runs\a77e0c67fdff8c618cbfc28fdd3d49d2fa831626560aed7fe1ec27007293537d\A_OBSERVED_BEST_SUPPORTED\checkpoint.json

COMMIT=Containing publication commit; resolve: git log -S'CHECKPOINT_SHA=4b1e67daffb05fc721cd159946440e09381cbca49dc7051a5d544b4f6140b0c7' -- docs/research/B10_JOURNAL.md

EXECUTION_SOURCE_COMMIT=a91811a853bfc5225ce5a2d13750905b6af74991

WHY_UNKNOWN=Isolated slippage unmeasured; current checkpoint not independently audited; historical execution evidence incomplete

PUBLICATION_STATUS_AT_GENERATION=LOCAL_ONLY_UNPUBLISHED

## 2026-09-07T23:03:18Z

TYPE=RECOVERY
STRATEGY=B10_FROZEN
PROFILE=A
RUN_ID=a77e0c67fdff8c618cbfc28fdd3d49d2fa831626560aed7fe1ec27007293537d
SIM_TIMESTAMP=2026-08-03T15:07:39.740126Z
PROGRESS=86.5444851748%
CYCLES=2458
NET_POSITIVE_CYCLES=2458
PNL=22.412000 USDT
RESERVE=4.581038 USDT
RELEASES=41
ZERO_DAYS=101 completed UTC days
MAX_HOLD=2411.4169634836 hours
LOCK_HOURS=2429.9417367478 hours
RECOVERY_ACTION=Corrected only the reporting-test expected percentage;98 focused tests now pass,0 fail. Ruff passes.
RESUMED_FROM=NOT_APPLICABLE; writer was never stopped or restarted
CODE_COMMIT=Containing publication commit
REPLAY_INVALIDATED=NO
EVENT=Reporter fixture repaired; no execution defect and no strategy change
DECISION=Continue same frozen writer and publish economic snapshots during replay
EVIDENCE_PATHS=tests/test_b10_checkpoint_scoreboard.py; scripts/b10_checkpoint_scoreboard.py
COMMIT=Containing publication commit, resolvable from git log

## 2026-09-07T23:03:19Z

TYPE=AUDIT
STRATEGY=B10_FROZEN
PROFILE=A
RUN_ID=a77e0c67fdff8c618cbfc28fdd3d49d2fa831626560aed7fe1ec27007293537d
SIM_TIMESTAMP=2026-03-01T18:49:55.609552Z
PROGRESS=Historical checkpoint reconciliation, not the current simulation position
CYCLES=1128
NET_POSITIVE_CYCLES=1128
PNL=10.535900 USDT
RESERVE=4.570092 USDT
RELEASES=27
ZERO_DAYS=1 of59 completed UTC days
MAX_HOLD=26.0010665336 hours
LOCK_HOURS=2.0010665336 hours
PRICE_PATH_OPPORTUNITIES_SAME_PREFIX=1474430
REALITY_RETENTION_SAME_PREFIX=0.0007650414058314060348744938722
EVENT=Old1128/27 observation independently reconciled from bounded immutable audit prefix; original-cycle denominator validated at sameT
DECISION=Preserve this past observation separately; never substitute full-history3580880 for partial retention
EVIDENCE_PATHS=reports/usdcusdt/B10-A-1128-reconciliation.json; artifacts/binance/b10-reference-prefix/exit-events.json
COMMIT=Containing publication commit, resolvable from git log
WHY_UNKNOWN=Exact old ordinal unavailable, but original count before/through timestamp equal1474430, so denominator exact
