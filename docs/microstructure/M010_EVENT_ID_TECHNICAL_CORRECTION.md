# M010 — immutable M007 event-ID serialization audit

The full physical M010 attempt at code SHA `356039f1d03fca8046bf8a6d695d8dc624d1f0c7`
reached the cutoff with 344704 normal cycles and no releases. Its post-run exact comparison
failed on `cycles` and `selection_changes`, not financial totals. It remains
`INVALIDATED_TECHNICAL`, run `800cb608c8273edff7fa01521044c3d500b57bbb5caa51e8f9abedcc74cc2592`.
The original failure log and failure artifact remain preserved; no valid evaluation was recorded.

## Reproduced cause, not an economic result

The former engine passed `numpy.int64` event IDs into Pydantic integer fields. On this runtime,
`TypeAdapter(int).validate_python(np.int64(7238714823331254273))` produces
`7238714823331254272`: conversion loses low event-order bits through floating point.
Native Python integers preserve the exact ID. Entry/exit timestamps and prices are unaffected
in the reproduced case. This must be audited across the full physical comparison, not assumed.

## Required repair and evidence gates

1. Keep the original M007 artifact immutable. Never round new trading IDs to imitate it.
2. Persist the complete M010 raw output, hash and provenance before any downstream analysis.
   Mark it `COMPUTATION_COMPLETE_PENDING_VALIDATION`, never a passed result by itself.
3. Reconstruct the same frozen M007 configuration on the same physical tape, interval and
   scenario using the exact-integer engine. This is a technical evidence reconstruction,
   not a new hypothesis, model, dataset or altered financial experiment.
4. Require exact complete observable equality of reconstructed M007 and zero-release M010,
   excluding only their model identities and additional capital-release evaluation records.
5. Independently reconcile reconstructed M007 to the immutable original. Permit only the
   reproduced directed legacy projection `int(float(exact_id))` for cycle entry/exit IDs
   and selection-change IDs. All timestamps, prices, quantities, decisions and financial
   fields must otherwise match exactly. Record changed-ID counts, examples and both hashes.
6. Any unexplained divergence still fails closed. No threshold or scientific rule is changed.

The corrected comparison does not claim byte-identical historical event IDs. It proves exact
behavior against the reconstructed reference and explicitly documents the old serialization
defect. The initial NumPy-to-Decimal failure is separately preserved. Technical retries remain
restricted to these diagnosed M010 representation failures; generic invalidation is terminal.

Scientific hypothesis, authorization class, 100-USDT starting bank, support requirements,
5-bps cap, 25% margin, causal lookback and checkpoints are unchanged. Pre-run commit/push
is required again before executing the corrected workflow.

## Postprocessing recovery without another M010 simulation

Run `5a53ab7dcebbdaf0f4697148c54d3e71b098575b6abc1a3b299c45312a5f4f0c`,
simulation SHA `1e4b85da2dcaf3e6a1ee4ff043c6870d207da0a5`, saved its full computation
before analysis. A downstream configuration-loading defect then omitted `model_id` and
`parent_model_id` when assembling the technical M007 reference. The failure remains recorded.

The completed result is retained unchanged, SHA256 of canonical inner result
`4b781fe79f8c61bd8991c32a6b45e4070d0f3dd159ebd8d059160935f08ef7e9`.
The same canonical command now recognizes only this known failure and recovers analysis
from the hash-validated raw result. It must not simulate M010 or register a replacement run.
Original simulation SHA and RUN_HASH remain unchanged; the analysis SHA is recorded separately.
Only successful exact reconstruction/equivalence and an evaluation whose full replay equals
the saved raw result permit the explicit `POSTPROCESSING_RECOVERY_COMPLETED` event. Generic
technical invalidation transitions stay terminal. Original failures are never overwritten.

The independently verified snapshot audit found 1439 valid causal checkpoints in 461
positions, zero releases and zero identified destination q90 support. This establishes
`FROZEN_RULE_DID_NOT_TRIGGER`, not exact parent equivalence before its physical reconstruction.
