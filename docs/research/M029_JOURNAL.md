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
