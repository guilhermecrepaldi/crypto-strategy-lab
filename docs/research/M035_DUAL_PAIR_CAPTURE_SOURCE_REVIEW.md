# M035 dual-pair capture source-bound review

Reviewer model: `gpt-6-astra`  
Final reviewed bundle SHA256: `66ca6fa90a9f47bfe5e0d451b59c2de691f7566f7e2b5e62f81312a52b303813`  
Verdict: `PASS_NO_P1_P2`  
Scope: capture preparation only; no real capture or economic replay

## Reviewed closure

- `src/crypto_strategy_lab/microstructure/m035_dual_pair_capture.py`
- `scripts/run_m035_dual_pair_capture.py`
- `tests/test_m035_dual_pair_capture.py`
- `src/crypto_strategy_lab/microstructure/public_market.py`
- `src/crypto_strategy_lab/microstructure/public_calibration.py`

The deterministic bundle hash uses sorted POSIX-relative paths, each encoded as
`path + NUL + exact bytes + NUL`.

## Final findings

- Binance public market data only; no account or order endpoint exists in the path.
- Exactly `USDCUSDT` and `FDUSDUSDT`, individual `trade`, snapshot-bridged L2 diffs and
  one global receipt sequence.
- Per-pair/per-type freshness, trade/depth sequence and timestamps fail closed.
- Raw wire envelopes and incremental REST evidence are persisted before validation, so the event
  causing invalidation remains auditable.
- The exact three-hour exclusive cutoff does not mutate state with the boundary event.
- The publication gate covers the runner, capture module and both executable transport/validator
  dependencies.
- The M034 one-shot identity and artifacts are not consumed.

The first review returned BLOCK with six P1/P2 findings: global-only silence, accepted post-bridge
depth regression, lost rejected evidence, incomplete source closure, startup timeout dependent on
socket timeout, and cutoff contamination. All six were corrected. The final independent run passed
27 tests, Ruff and strict mypy, plus adversarial probes for regressions, `aggTrade`, third-symbol
injection, stale pair coverage, manifest preservation and a virtual exact three-hour cutoff.

`CAPTURE_SOURCE_PASS != CAPTURE_COMPLETE != ECONOMIC_RESULT != STRATEGY_PASS`.
