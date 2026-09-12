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

## 2026-09-11 — Economic campaign authorized and dual tape frozen

The latest OWNER directive supersedes the earlier random-window plan and explicitly authorizes
`M035_200USD_3H_PARALLEL_DEVELOPMENT_BACKTEST_V1`. Its absolute window preference is
2025-01-01 00:00–03:00 UTC when both pairs are physically valid; no economic result was inspected
while selecting it.

Both pairs passed the strengthened native gate. Every exposed book is snapshot-bridged and Binance
`U/u` sequence validated. Every Tardis-native Binance trade matches the official Binance Vision
individual-trade archive by ID, price, quantity, maker side and millisecond timestamp. The merged
timeline contains 149,046 events: USDCUSDT has 71,222 books and 29,538 trades; FDUSDUSDT has 28,540
books and 19,746 trades. The frozen window hash is
`327142fa6be8a51a70b8f845842e97a596b52b8ab744ab95f68ba72261d60b9b`.

The former `MULTI_PAIR_HISTORICAL_TEST_BLOCKED_BY_PAIR_B_DATA` condition is therefore resolved.
The mixed provenance is explicit: Tardis provides Binance-native L2/snapshot and native trade
replay; Binance Vision independently binds the complete individual-trade population. The economic
configuration is frozen in `reports/m035/M035_200USD_3H_CONFIG.json`. No economic event has yet been
consumed; source publication and a new GPT-6 Astra source-bound review remain the final pre-run
gates.

## 2026-09-12 — one-shot economic run consumed; causal safety abort

The hardened economic source passed independent GPT-6 Astra review with no P1/P2 at `4aa5734`.
The bound review JSON produced executed HEAD `65feb3c`. The full regression passed1,302 collected
tests with2 expected skips; targeted M035 tests, Ruff and strict mypy passed. The runner acquired
the exclusive claim before consuming any event.

The single-pair campaign stopped at merged event141,697, local time
2025-01-01T02:49:56.840601Z. The physical USDCUSDT book had bid1.0025 and ask1.0028, midpoint
1.00265: a26.5bps absolute peg deviation against the frozen25bps threshold. This was the first
threshold crossing; maximum prior deviation was24.5bps. Raw slice hashes and normalized event
projection matched. The guard used only the received event and fired before changing book, mark,
hotline or orders. No negative/risk exit was invented.

The common accepted prefix is141,696 events (USDC67,244 books+28,306 trades; FDUSD26,985
books+19,161 trades). F0 advanced its clock/counter to the rejected event but did not apply it;
F1/F2/F5/F10 stop on the immediately preceding event. Partial facts: F0 equity200.003996600 with
one positive cycle, F1/F2/F5/F10 equity200 and zero cycles. All have zero negative cycles, risk
exits, dust and non-USDT inventory, exact conservation and unique ownership. No scenario completed
3h, and the parallel arm did not begin.

The immutable claim records runner status `INVALIDATED_TECHNICAL`; independent Astra audit classifies
the demonstrated cause more precisely as `INCOMPLETE_SAFETY_ABORT`, not data corruption, numerical
bug or economic loss. The 62,637,508-byte prefix is preserved locally with SHA-256
`2b9e2e405d913a8dfc63866b1791298a8f62cea59db8cc1254bb8bb8796763ff`. This identity cannot rerun.
Any attempt to complete the comparison requires an explicitly authorized new identity and protocol.

## 2026-09-12 — OWNER correction and random-window V2 authorization

The OWNER corrected the V1 interpretation: M035 was never given a 25 bps peg-deviation abort and
authorized a different three-hour test so the mechanism is actually measured. Source provenance
shows `0.0025` entered M035 in preparation commit `1013bc7`, matches the earlier M034 diagnostic
value, and has no stated authority in the M035 economic prompt. V1 remains immutable and accurately records
what its published source did, but its abort is not treated as an OWNER M035 economic rule.

Independent GPT-6 Astra review agreed that V2 must remove only the unauthorized abort without
inventing a replacement numeric threshold. Book integrity, native sequence, causal marks, spread,
depth, flow, positive expected edge, capital ownership, FIFO, cancel-ACK, dust and per-cycle
zero-loss gates remain unchanged. A valid price distant from one is economic data, not data
corruption; any open loss remains visible in marked equity.

Before inspecting any new-window economic value, a CSPRNG-derived draw was frozen over all 2,667
10-minute-aligned three-hour candidates within the 21 authorized evidence days. Seed
`bc895e20515f5a6f821419c897fdcf2174359e8082e7730fdcfafa3189af3bef` selected
2026-02-01 01:00–04:00 UTC. No reroll is allowed. One hour of same-day L2 preceding the selected
window is consumed only to bridge the native snapshot causally; it cannot affect strategy state or
economic metrics.

Both selected tapes passed native snapshot/delta sequence validation and exact binding to Binance
Vision individual trades. The economic window contains 151,063 merged events: USDCUSDT 93,795
books + 48,256 trades; FDUSDUSDT 4,417 books + 4,595 trades. Window hash:
`15a4ad3cd557bc931a792a05504132b80225b5f8ab1755bac6c01d01df9849ef`.
Pair hashes: USDCUSDT
`06e77ff1036c2fbc79536d511824f216501598abb3942dd766b160e84d4ffe6a`; FDUSDUSDT
`376f20225fb20a399442150a8fefc9bb9363a857b97b8d4b33b40249873e632b`.
No V2 economic event has been consumed yet. Tests, publication and source-bound review remain
mandatory before the single V2 run.
