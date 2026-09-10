# M027 research journal

Append-only journal for `MICRO_HOT_REALLOCATION_CONTROLLED_AB_V1`.

## 2026-09-09 — OWNER authorization and pre-run facts

- M026 remains immutable and `INCONCLUSIVE`: 30 physical and 90 slot-equivalent
  cycles in three hours; every cycle originated in HOT, MID/FAR produced zero.
- M027 is a matched control/treatment experiment, not a silent continuation.
- Source day is fixed before performance observation: 2026-05-01 00:00–03:00Z.
- Published validation reports this L2 day and canonical trade binding as valid.
- Read-only physical grid inspection found observed five-decimal prices and
  supports the required `0.00001` tick; the runner repeats this fail-closed.
- CONTROL preserves all 15 coarse M026 levels. TREATMENT replaces only FAR14/15
  with a two-column, one-slot-per-order MICRO line at ±0.00005.
- Both start with 60 orders, 140 operational plus 16 mobility slot-units.
- Results are normalized mechanics evidence below live minimum notional.
- Replay remains unopened until tests, Astra review, registration and published
  source all pass.
- Registry identity created as M027 with model hash
  `80c8961e3ac9faaf1c2094e42a719a9d9b2853287178fcb214f99858f4e667ca`.
- Physical gate scan reconciled 30,552 canonical trades and18 validated L2
  slices. It inspected103,194 native L2 update prices;37,081 were on the fine
  grid and the L2-only observed increment was0.00001.
- Pre-trade first-book capitalization is155.98394000 for CONTROL and
  155.98674000 for TREATMENT, a0.0017950566% quantization mismatch, below the
  frozen0.01% gate.
- First Astra review: `BLOCK`. It found that the tick proof mixed trade/L2,
  MICRO report counters were not independently reconstructed, capital matching
  ran after the scenarios, and the transitive M026 source closure was incomplete.
  No replay started.
- Corrections now keep L2 and trade grid proofs separate; reconstruct MICRO,
  distance and touch metrics from the ledger/terminal; capital-match both engines
  from the first valid book before any trade; bind the complete M026 source list;
  exclude pending/free-entry queue-zero time from price recovery; and prevent a
  zero/zero comparison from passing the strong ruler. Re-review is pending.
- Second Astra review retained one `BLOCK`: canonical membership alone did not
  prove that a recorded MICRO-only touch actually lay between MICRO and coarse
  rank1. The auditor now independently replays hotline changes and canonical
  trade side/price, requires the exact touch set (including omissions), and binds
  trace time, price and hotline. A false-touch adversarial test now fails closed.
- Final GPT-6 Astra source-bound review: `PASS_CONDITIONAL_PRE_RUN`;49 focused
  tests passed. Publication and clean-HEAD checks remain before the two runs.

Original OWNER attachment SHA-256:
`3cccac13bac77e440d4350496234b8c8dac8a0be8218e5e5cdc0f1f17d1c74a5`.
