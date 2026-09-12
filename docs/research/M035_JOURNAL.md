# M035 research journal

Journal policy: append-only experimental record.  
Campaign: `M035_PARALLEL_PAIR_CAPITAL_MANAGER`.

## 2026-09-11 — OWNER directive received

The OWNER authorized the design and conformance implementation of a two-pair, Binance-only,
simple-cycle manager sharing one physical `200.00 USDT` bank. Pair-local hotline, grid, queue/FIFO,
orders, inventory, dust, cycles and PnL must remain isolated. The global capital pool is the only
shared financial authority. Kraken remains retired.

## 2026-09-11 — Phase 0 repository inspection

- branch: `main`;
- inspected HEAD and `origin/main`: `bad10f9718594f54d5600e082cd91d5b9c11066e`;
- worktree at inspection: clean;
- mandatory M029, M030 and M034 journals/results/source authorities inspected before implementation;
- no M035 source existed at inspection.

### Reconstructed lineage

M029 preserved the M026 one-pair physical engine: 15 ranks per side, HOT/MID/FAR 3/2/1 geometry,
pre-aged segmented FIFO, whole-USDC sizing and one continuous USDCUSDT tape. It produced 98 physical
cycles in 24 hours (4.0833/hour); the frozen first three hours reproduced M026's 30 physical and 90
slot-equivalent cycles. Long queue waits and declining activity after hour three were the main
throughput constraint.

M030 changed management rather than economics: RETURN > HOT > MID > FAR > old zero-fill, direct
multi-tick hotline reconciliation, zero-fill reclaim only, and release only after cancel ACK. It
preserved filled/partial orders and FIFO. The 24-hour run produced 170 physical cycles; in the three
random evaluation hours it produced 13 versus M029's 6 (+116.67%), although the preregistered
stranded-time management gate failed.

M034 added Binance-only temporal evidence gates, exact physical ownership, cycle-local PnL,
owned-return priority, causal risk exits, no self-fill and marked residual exposure. Its frozen
zero-loss development backtest produced two F0 cycles and zero cycles at positive fees. The direct
cause of the latter was the hard `FEE_DUST_PREVENTS_FULL_RETURN` rejection, not an observed physical
market absence. M035 retains the accounting correction but changes dust from rejection to an owned,
marked and aggregatable asset lot.

### Frozen architecture decision

`docs/microstructure/M035_PARALLEL_PAIR_CAPITAL_MANAGER.md` is the pre-implementation authority and
contains the required `M035_ARCHITECTURE_MAP`, state diagrams, invariants and delivery order.

### Pair B data decision

The canonical inventory contains physical L2 and individual public trades only for `USDCUSDT`.
`FDUSDUSDT` and every other Pair B candidate have zero eligible local units, hence there is no aligned
two-pair historical window. The economic run is blocked before tape consumption as:

`MULTI_PAIR_HISTORICAL_TEST_BLOCKED_BY_PAIR_B_DATA`.

Synthetic conformance remains in scope. It must not be reported as PnL, cycles or strategy evidence.

## 2026-09-11 — Implementation and conformance

The canonical M035 module now provides one `GlobalCapitalLedger`, two pair-isolated engines, a
simultaneous allocator, exact dust subledger and settlement-derived cycle attribution. Physical
orders remain unfunded and outside the executable queue until a unique sufficient capital ID is
bound. Entry and return fills are consumed only from public trade events. Partial fills, racing
cancel ACK, causal marks, risk exits, dust aggregation and cycle closure share the same financial
authority.

The deterministic 900-second logical conformance completed with all 18 recorded gates PASS. The
M035-specific suite passed 40 tests; Ruff and strict mypy passed for the affected source/runner.
Targeted M029/M030/M032/M034/M035 regressions remained green.

## 2026-09-11 — Independent source-bound review

GPT-6 Astra reviewed five exact bundles. The first four rounds returned BLOCK and identified real
atomicity/integration defects; each was corrected and covered by adversarial tests. The final bundle
`63cb0cd63d509f5cfe5cff1b89057b79d54636093c5cee3edccdf21775ecf15e` returned
`PASS_NO_P1_P2`. The review is recorded in `docs/research/M035_SOURCE_REVIEW.md`.

The PASS is restricted to source and synthetic conformance. Economic runs remain zero and no tape
was consumed because `FDUSDUSDT` has no aligned canonical physical dataset.

## 2026-09-11 — Publication constraint

The architecture/source commit could not be created in this execution environment because `.git`
was read-only; the push also had no network route to GitHub. `SOURCE_PUBLISHED=false` remains
truthful in the artifacts. This publication constraint does not authorize a replay and does not
change the reviewed bundle hash.

## 2026-09-11 — Pair B forward evidence preparation

The historical gate remains unchanged, but its next evidence action is now executable after source
publication. `M035_DUAL_PAIR_FORWARD_CAPTURE_V1` reuses the canonical public Binance transport to
record `USDCUSDT` and `FDUSDUSDT` simultaneously from one combined connection. It records individual
`trade` events and snapshot-bridged L2 diffs at 100 ms, preserves one global receipt order, rejects
per-pair trade/depth gaps and writes hashed artifacts. It cannot access accounts or orders and does
not run strategy/economic logic.

The source-publication gate prevents execution in the current environment. Therefore
`CAPTURE_STARTED=false`, no websocket was opened and the M035 economic replay remains unstarted.
The frozen protocol and plan are recorded in
`docs/research/M035_DUAL_PAIR_FORWARD_CAPTURE_PROTOCOL.md` and
`reports/m035/M035_DUAL_PAIR_CAPTURE_PLAN.json`.

GPT-6 Astra initially blocked the capture source with six causal/evidence defects. All were fixed:
freshness is now enforced and measured per pair/type across both boundaries; post-bridge depth
regression is invalid; raw wire and REST evidence precede validation; the publication closure is
complete; startup timeout also applies under continuous messages; and the exclusive-cutoff event
cannot mutate the accepted window. Final bundle
`66ca6fa90a9f47bfe5e0d451b59c2de691f7566f7e2b5e62f81312a52b303813` passed with no P1/P2.

## 2026-09-12 — OWNER authorization for Pair B historical acquisition

The OWNER authorized expanding the strategy database when required using safe, reliable public
Binance API/archive data, Tardis data representing Binance, or an explicit mixture of both. Every
artifact must disclose its source; silent mixing is prohibited. No account credentials, private
endpoint, Testnet, live order or paid-data assumption is authorized.

Exactly 21 `FDUSDUSDT` first-of-month days are frozen for acquisition, from 2025-01-01 through
2026-09-01 inclusive. The three-hour economic window is not selected during acquisition and must be
drawn and preregistered later without inspecting PnL. The acquisition pairing is:

- L2: Tardis `incremental_book_L2`, exchange field `binance`, preserved and SHA-256 hashed;
- individual trades: official Binance Vision Spot `trades` ZIP plus official adjacent checksum;
- candles and `aggTrades`: prohibited as fill substitutes.

This authorization changes the evidence-acquisition path, not M035's strategy or conformance
semantics. Download/validation does not itself authorize or constitute the economic replay.

### Acquisition result

The fail-closed acquisition source passed independent GPT-6 Astra review after correcting four
provenance/integrity defects. Commit `6200676` was published before network acquisition. The run then
completed and a separate offline pass revalidated all 21 days:

- L2: 3,437,530 rows, 37,470,494 compressed bytes;
- individual trades: 2,704,621 records, 34,561,612 compressed bytes;
- paired days acquired: 21/21;
- missing/invalid source pairs: 0;
- economic replay runs: 0;
- three-hour window: not selected.

The complete per-day URLs, timestamps, SHA-256 hashes, coverage fields, row counts and explicit
mixed provenance are in `reports/m035/M035_FDUSDUSDT_21_DAY_DATA_REPORT.json`. The originals remain
local under ignored `data/` paths and are not uploaded to Git. Because normalized Tardis L2 does not
prove native Binance `U/u` continuity, the next gate is aligned Pair A/B validation and a later
random, preregistered three-hour draw—not PnL inspection.
