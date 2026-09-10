# M029 research journal

Append-only journal for the corrected M026 full-day technical retry.

## 2026-09-10 — OWNER authorization and frozen correction

- OWNER explicitly authorized the requested M029 corrected24-hour retry.
- M026/M027/M028 remain immutable. M028 stopped at03:00 and has no full-day result.
- M029 changes no strategy or execution economics. Its sole correction canonicalizes
  the live and JSON-restored checkpoint states before the strict equality check.
- Period is2025-01-01T00:00:00Z–2025-01-02T00:00:00Z exclusive, one continuous
  engine with no03:00 reset and no cutoff liquidation.
- The byte-identical M026 prefix ledger, exact trade set, metrics and canonical state
  remain mandatory before extension events.
- One run only after registration, tests, Astra review and published clean source.
- No M030, another day, account, Testnet or live action is authorized.

## 2026-09-10 — registration and implementation

- M029 registered `CREATED` with model hash
  `6942e5c0475c9ddaf0f7792c4bd7df399b46ed0cf3f49a624712f439d2c79534`.
- The existing full-day runner remains the canonical implementation. It now accepts
  an explicit model identity and canonicalizes checkpoint states identically; M029
  is a thin authority/identity wrapper rather than a copied replay engine.
- A regression test reproduces `Decimal` values and integer map keys in memory against
  their JSON string forms. The corrected prefix gate accepts them only after canonical
  normalization while all ledger/trade/metric checks remain strict.
- Sixty-eight focused M026/M028/M029/engine/registry tests and Ruff pass.
- No historical event has been replayed. Source-bound Astra review and publication
  remain mandatory before the sole economic run.

## 2026-09-10 — independent pre-run review

- GPT-6 Astra completed source-bound review with `PASS_CONDITIONAL_PRE_RUN`.
- It confirmed the canonical comparator corrects representation only; a semantic
  cash difference remains unequal, and ledger/trade/metric gates remain strict.
- It found and closed one preflight defect: local M026 physical artifacts must be
  verified by hashes, not required to be Git-tracked. No historical replay occurred.
- Publication and clean `HEAD==origin/main` remain before the sole run.

## 2026-09-10 — published source and sole 24-hour run

- Pre-run source/review was committed and pushed as
  `9dde81b16c5cd3144efc88c471d70407f1249af7`; clean-source campaign preflight passed.
- The one authorized M029 run consumed exactly 254,205 canonical trades from
  2025-01-01T00:00:00Z through 2025-01-02T00:00:00Z exclusive.
- Before the first post-03:00 event, ledger bytes, trade set, metrics and canonical
  checkpoint state reproduced M026 exactly. No 03:00 reset occurred.
- Initial 78.10400000 USDT plus 78 USDC marked 156.25220000. Final
  69.1272000000000000 USDT plus 87.00000000 USDC marked
  156.3012000000000000.
- Total marked gain was 0.0490000000000000 USDT-equivalent, or
  0.03135955845741691956977245760%.
- The engine completed 98 physical cycles (4.083333333333333/hour) and 289
  slot-equivalent cycles (12.041666666666667/hour). It added 68 physical cycles
  and 0.0040000000000000 marked gain after the M026 three-hour prefix.
- Realized cycle PnL was +0.0427000000000000; realized disposal PnL was
  +0.0577996784800000; unrealized PnL was -0.0087996784800000.
- HOT/MID/FAR produced 93/5/0 physical cycles. The full-day rate fell materially
  from M026's first-three-hour 10 cycles/hour and did not approach 1,000/day.
- Independent physical audit passed with no duplicated trade consumption. Astra's
  factual post-run review also passed and recommends `INCONCLUSIVE` because the
  normalized, zero-conditional-fee development result is not live-executable.
- M029 is finalized `INCONCLUSIVE`. Its single run is consumed; no rerun, another
  day, successor model, account, Testnet or live action is authorized.
