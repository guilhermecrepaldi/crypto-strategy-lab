# M013 independent preflight review

STATUS=PASS_CONDITIONAL_PRE_RUN

SCIENTIFIC_PREREGISTRATION_REVIEW=PASS

Reviewer: GPT-6 Astra, independent of the execution-module implementation.
No economic replay, registration, commit or push performed by this reviewer.

## Approved before outcomes

The M013 specification and preregistration incorporate both current OWNER directives:
continuous multi-queue compounding and the five-month first stage. The root reviewer
read and approved the complete documents before registration. Operating 100/reserve10,
10% funding, 90% compounding, active profits retained in reserve, up to three operating
queues plus one active-reserve queue, and no reset or retuning between stages are explicit.

The reserve/core constraint is not treated as a cosmetic 50/50 allocation. Admission
preserves an additional .05O emergency buffer; all concurrent recovery claims share
one escrow authority. Initial Q4 budget2.5 is below the profile minimum order and thus
inactive, not a fabricated fourth trading queue. Partial realized deficits remain claims.

Allocation is causal, score-weighted and strictly disjoint; no forced thirds or duplicate
ranges. Productive-capital accounting explicitly excludes stale/recovery capital and
includes idle core in the principal denominator. Timed exits never fabricate liquidity.
One external front per side/price and one event/depth budget prevent four independent
replays from consuming the same market liquidity. Exact-price passive semantics remain.

Economic thresholds and conservative sustainability (including Q4 losses) are frozen
before results. The OWNER release-only sustainability ratio is reported separately.
Insufficient evidence/technical failure is INCONCLUSIVE, not a negative economic finding.

## Execution evidence limitations

The reused B profile is a conditional public-pilot execution envelope, not reconstructed
historical L2 or authenticated Jan–May commissions. PASS_TO_EXTENSION can therefore only
qualify the registered conditional envelope. Stage2 is sealed for M013, not an unseen
prospective holdout: older B10 history had already exposed that calendar interval.

## Final implementation review

No remaining blocking implementation finding in the reviewed pre-run scope. This
approval permits the registered conditional Stage1 after publication checks; it is not
a strategy PASS, a completed execution audit, or authorization to bypass Stage2 gates.

MODEL_HASH=6a771627bbb820e13f199746c5159100f16cbd0d4c1c91dd0ac6bd500902d57a

REVIEWED_SOURCE_SHA256_LF[src/crypto_strategy_lab/microstructure/continuous_multi_queue.py]=ce578944fb3989c374d12aff626f5ffac3b147961390b7efd8a782ca642954fe
REVIEWED_SOURCE_SHA256_LF[scripts/run_continuous_multi_queue.py]=4f6110a65b994466adbffc37c556e4529bdb84ec554dfbed4d768e7894d4ecb4
REVIEWED_SOURCE_SHA256_LF[scripts/report_continuous_multi_queue.py]=140170142690abd0f52a1bcf2e87ac4c6e2f1c8443de2ecb6e5792692a40e72c
REGISTERED_SPEC_SHA256_LF=30d3cfd92ba20199633032cbcf585281ed4110233f4478d545b258f9d19ae901
REGISTERED_PREREG_SHA256_LF=ef461579c102e7c7a586a048b8a686a4ad10bd7fcd865814a0e56486ac48fdea

Independent execution: 78 tests passed across M013 kernel/runner/reporter, B10 kernel,
M012 kernel and the historical independent-audit tests. Root additionally reports 101
combined tests passed including registry and M012 reporting/runner tests; Ruff passed.
The first reviewer command used a nonexistent audit-test filename and ran no tests;
the corrected commands above passed. No economic run was used to tune these fixes.

Production-path fixtures cover all four queues sharing a single raw event: two IOC
fills consume70, passive fills consume35 and one external front burns5 from a110 print;
shared depth decreases70, not once per queue. JSON checkpoint restoration of the
remaining partial order then produces an identical complete state after the next print.
Other fixtures cover concurrent claims, exact loss coverage, 10/90 funding, Q4 profits,
cancel throttling and retry, cash retained until ACK, distinct proportional allocation,
interior deadlines, capital-time partition and fail-closed extension evidence.

Review corrections incorporated before execution: one global cancellation throttle;
Q4 cancellation cash remains committed until ACK; order objects are relinked by global
ID on restore; allocation remains on the frozen60s cadence; obsolete Q4 eligibility
uses C1>=2; dust is always idle in capital-time accounting; completed-lot Q4 funding is
not replaced by gross per-fill flows. Physical Q4 partial-loss recovery episodes are
separately scoped from completed-lot funding/consumption. Reserve minima observe fills.

Boundary convention reviewed with root: deadlines at an interior timestamp are processed
at that timestamp without fills. Stage1 is end-exclusive, so the timer exactly at June1
is preserved unprocessed; it executes once when the audited extension opens. Open age
at the boundary is censored and reported, not silently closed. No June1 trade is read
by Stage1. Named day and monthly snapshots retain this causal prefix; monthly ordinary
operating/Q4 cycle counts are cumulative-counter differences, with releases separate.

The runner verifies registered spec/prereg hashes, actual class source, published source
and inherited execution dependencies; extension rechecks the original dependency bytes.
Raw timestamps, prices, same-timestamp ordinals and contiguous IDs are reconciled.
Reporter metrics and named snapshots are bound to the durable curve/checkpoint prefix,
not arbitrary unbound files. Economic thresholds come from the registered spec.
Technical/insufficient evidence is INCONCLUSIVE before economic gate evaluation.

## Physical prefix and remaining post-run obligations

PREFIX_TAPE_HASH=f2eb7e98f50fa731202e371facc7c6dbd5f4dc2c7d1f06451f656d42325e31cf
PREFIX_RECORDS_INCLUDING_WARMUP=60870538
WARMUP_RECORDS=391575
EXPECTED_STAGE1_RAW_TRADES=60478963
SOURCE_MANIFEST_SHA256=9ab5db213673e5f0371c86b1aa35cff3d8925287e77af41cff2e54446c16d907

The prepared provenance records freshly hashed authorized archives and a physically
derived prefix; full source-array hashes are explicitly historical, not freshly
rehashed future evidence. The reviewer independently reconciled authorized archive
metadata counts without opening future trades. Full per-event raw reconciliation is
still required during the economic replay, including warmup.

After all151 days: independent audit of at least100 ordinary closures, all traded
queues represented, ALL recovery events and Q4 fills, exact ledgers and shared raw/depth
support. Only the hash-bound final checkpoint plus sufficient independent evidence and
every frozen gate can produce PASS_TO_EXTENSION. Until then Stage2 remains sealed.
No claim of representative historical L2, authenticated historical commissions, positive
economics, or guaranteed executable24h liquidation is made by this preflight approval.
