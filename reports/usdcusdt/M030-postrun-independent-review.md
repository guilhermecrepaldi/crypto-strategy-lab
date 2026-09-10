# M030 post-run independent scientific review

REVIEWER_MODEL=gpt-6-astra
REVIEW_DATE=2026-09-10
STATUS=PASS_FACTUAL_POST_RUN
STRATEGY_VERDICT=INCONCLUSIVE
EVENT_REPLAY_PERFORMED_BY_REVIEWER=false

REVIEWED_SOURCE_SHA256_LF[scripts/audit_hotline_first_reallocation.py]=e71b9a0694e90f3af3f6c5e60c0eacc8dc3c9ac145e2e61952d774e4330c21f4
REVIEWED_SOURCE_SHA256_LF[scripts/recover_m030_reporting.py]=62365abd11dd3f89b7c03b13dd4565258589f7028f641da6e7afbdc7f9e0e8d1
REVIEWED_SOURCE_SHA256_LF[scripts/finalize_hotline_first_reallocation.py]=5d09dcabbacf097ac39af7dfbe767ef2fedad697240a52f7b16413a59f9db9f1
REVIEWED_RESULT_SHA256_LF[reports/usdcusdt/M030-hotline-first-result.json]=c7a36b824facefd0fb3d98341c1c2c7025d4444b726b7bd798ad725498323851
REVIEWED_REPORT_SHA256_LF[reports/usdcusdt/M030-hotline-first-autopsy.md]=27e86629aab211d1e80e51ca3be7511f430394b94c8c0c7252c558ce2f8747d0

## Decision

PASS factual pós-run. The physical artifact hashes, unchanged economic kernels and
reporting recovery path were checked. Recovery restores the checkpoint and computes
metrics/audit without delivering market events; the original failure remains
preserved.

- Ledger reconciles 254,205 unique trades, 170 full-day physical cycles and 13 in
  the frozen random windows, versus 6 for M029 (+116.67%).
- Matched HOT coverage improves 67.41% to 94.28%; this gate passes.
- Literal reclaimable-stranded time improves 100% to 59.28%, a 40.72% reduction,
  below the frozen 50% threshold; the management gate fails.
- Marked equity reconciles 156.2522 to 156.3188, gain 0.0666 / 0.04262%, with zero
  accounting-identity residual.
- The broad raw administrative counter, 69.09% in the random windows, is preserved
  and separated from the literal 59.28% indicator.

## Scientific interpretation

M030 improved observed frequency but did not pass the complete management gate. It
must remain `INCONCLUSIVE`, normalized and non-live-executable. The repair is solely
reporting-layer recovery and does not repeat the execution. One DEVELOPMENT day
does not demonstrate generalization or identify the causal bottleneck by itself.

The final registry delta was reviewed separately and passed: it only registered the
scenario, run, evaluation and `INCONCLUSIVE` status. Removing those registry fields
reproduced the already-reviewed economic report; the five recorded physical hashes
remained exact and no replay path was invoked.
