# M010 — frozen capital release / OWNER exploratory override

Authorization: `OWNER_EXPLORATORY_OVERRIDE`, 2026-09-07. This is not
`SCIENTIFIC_GATE_PASS`. The earlier sealed diagnosis remains INCONCLUSIVE.
Parent M007; M008/M009 controls are excluded. Machine-readable creation authority:
[M010_MODEL_SPEC.json](M010_MODEL_SPEC.json).

## Frozen experiment

One USDCUSDT pair, one bank, one serial lot. Independently start with exactly 100 USDT,
COMPOUNDING, at 2026-01-01T00:00:00Z. End exclusive is the physical frozen cutoff
2026-09-05T23:59:59.783644Z. Use the same execution tape and zero-fee price-path scenario as
M007. No early stop for economic results. No live, Testnet, VALIDATION or LOCKED_TEST.

M010 = M007 ALWAYS_BEST + the exact rule in
[CAPITAL_RELEASE_DIAGNOSTIC.md](CAPITAL_RELEASE_DIAGNOSTIC.md). The implementation reuses
its causal evaluator and exact rounded-quantity recovery, not a precomputed decision table.

```text
candidate = M007 best over [T-24h,T), including incumbent
C1h >= 30; C24h >= 120; nu = min(C1h,C24h/24) cycles/hour
0 < (B-R_T)/B <= 0.0005
identified original RMST24 and destination first-cycle q90
N_K = minimum exact rounded-quantity destination cycles restoring original target cash K
t_recovery_K_seconds = q90_seconds + max(N_K-1,0)/nu * 3600
RELEASE iff destination exists, differs, all supports hold,
            and 1.25*t_recovery_K_seconds < original_RMST24_seconds
otherwise KEEP (original HIGH unchanged)
```

Landmarks are BUY-relative wall-clock seconds 60,300,900,1800,3600,7200,14400,21600,
43200,86400,172800, then daily. All decision inputs strictly precede T. At a tie,
the checkpoint precedes same-timestamp trades. Release realizes the last causal marked
price (theoretical, NOT an executable fill); next destination BUY waits for an eligible LOW
at or after T. No bank reset or inherited capital. Checkpoint events do not count as cycles.

RMST and first-cycle q90 support are unchanged: same-band history since 2025-01-01,
30 at-risk episodes/three entry dates/identified 24h restricted residual survival; first-cycle
KM q90 from complete hourly origins over 30 days, 30 origins/three dates, identified within
24h. The separate frozen support tape cannot replace the execution tape.

## Retrospective analysis and gates

Record all causal evaluations and release closures. Recovery B (pre-BUY cash) and K
(original HIGH target proceeds) use subsequent realized exit cash, never future inputs to a
decision. K is the principal recovery target; report B separately. Unrecovered observations
remain censored. Fixed-notional-100 is a separate accounting diagnostic of the realized path,
reconstructing its own rounded quantities, release losses and terminal mark, never scaling
compounded quantities or replacing the primary bank.

Compare full cycles, selection decisions, terminal state and economics against immutable M007.
With zero releases, any difference beyond model identity and extra release evaluations is a
technical error. Zero releases itself is valid: `FROZEN_RULE_DID_NOT_TRIGGER` and hypothesis
INCONCLUSIVE, not an instruction to tune. Preserve all outputs.

Promotion criteria remain those frozen in the diagnostic: >=101% parent compounded equity
and fixed-100 PnL; >=90% daily cycle median; zero days and idle no worse by >5 percentage
points; drawdown no worse by >1 percentage point; nonnegative delta in at least half complete
months; >=10% reduction of hours in positions older than 24h including censoring; hard
causal/accounting gates. No automatic promotion even when numeric gates pass: Astra autopsy
first. Execution-aware evidence remains UNKNOWN.

## Reproduction

Register the JSON with the existing ModelRegistry; run relevant tests, commit and push first.
Then execute one canonical process:

```powershell
uv run crypto-lab microstructure-full-replay --manifest data/manifests/usdcusdt-trades-development-2026.json --models M010
```

The manifest/run must bind the published code SHA, identical scenario, dataset and cutoff.
Subsequent report/decision is a separate milestone. No threshold change in M010.
