# M034 source-bound independent review

## Review 1 — blocked source

- Reviewer: GPT-6 Astra, independent source review
- Reviewed source: `d009653afaf4dd361dcc4095090e97788b2015f4`
- Base: `aafb57ef4203ad2d0c46edacf0df503ec306795e`
- Verdict: `IMPLEMENTATION_REVIEW=BLOCK`
- Replay: `READY_FOR_REPLAY=false`
- Economic execution: none

The reviewer reproduced ten blocking classes: owned-return priority and shortfall
bypass; non-physical inventory-reduction settlement; retroactive exit authorization;
negative conservative cost bounds; incomplete or tier-inapplicable fee evidence;
pair-universe and exchange-rule evidence disconnected from admission; temporally
impossible completion labels and censored lock treated as exact duration;
future-effective thresholds used in past decisions; mixed-currency capital aggregation;
and data/safety blocks mislabeled as idle capital.

Verification on the reviewed SHA: 122 focused tests passed (25 M034, 51 M032 and 46
M033), repository Ruff passed, and strict mypy passed on the seven changed source
modules. `git diff --check` found extra EOF blank lines in two new documents. These
software checks did not override the blocking scientific findings.

## Correction disposition

The correction adds adversarial tests that reproduce every reported defect and changes
the canonical incremental M034 path as follows:

- owned-return capital is protected before new-entry ranking; priority-one returns do
  not require positive productivity and shortfall stops lower priorities;
- inventory-reduction authorization is persisted by `SlotLedger` before the bound exit
  reservation/fills, and settlement proves origin return, cost basis, fill attribution,
  causal times and zero non-origin residue;
- threshold effective time, finite/non-negative conservative bounds, fee tier/context,
  pair evidence and historical/forward symbol-rule evidence are direct gate inputs;
- completion outcomes require physically coherent availability times; censored outcomes
  inform completion probability but not an exact expected-lock duration;
- each allocation batch has one explicit currency and causal USD rate for USD limits;
- capital states distinguish active new/return, locked inventory, blocked data, blocked
  safety and genuinely idle/no-opportunity capital.

The corrected source requires a new review bound to its published SHA. Until that review
passes, `M034_SOURCE_ARCHITECTURE_PASS=false` and `READY_FOR_REPLAY=false`.

## Review 2 — blocked corrected source

- Reviewer: GPT-6 Astra, independent source review
- Reviewed source: `1dd2f3de2c11449bb5f65f9dfae2a076bfccb01b`
- Verdict: `IMPLEMENTATION_REVIEW=BLOCK`
- Replay: `READY_FOR_REPLAY=false`

All ten Review 1 probes were corrected in their original scope. Six additional defects
remained: external-asset fees were omitted from the authorized negative-loss limit;
censored capital was omitted from expected lock; physical order funding was independent
of `capital_required`; only the first route book passed universe/rule gates; the USD
conversion rate had no registry/provenance authority; and dormant Kraken diagnostics
contaminated Binance economic KPI aggregates.

The second correction includes all-in external-fee valuation using preregistered causal
marks; returns unknown lock when the resolved sample contains censoring and no frozen
censoring method exists; binds a candidate to the canonical M033 `VenueRoute` and each
physical order leg; validates universe, temporal rules and fees for every leg; proves
first-leg funding including spent-asset fees; resolves USD conversion through a causal
mark registry; and separates dormant-venue diagnostic counts from Binance KPIs.

The post-review correction locally passes 139 focused checks: 42 M034, 51 M032 and 46
M033. A third independent review must be bound to the next published source SHA.

## Review 3 — blocked corrected source

- Reviewer: GPT-6 Astra, independent source review
- Reviewed source: `e55bb7bb4c768d78fc82c3238ee8ac9120c8f070`
- Verdict: `IMPLEMENTATION_REVIEW=BLOCK`
- Replay: `READY_FOR_REPLAY=false`

The six Review 2 defects were corrected in their reported scope. Two interactions
remained. First, a disabled Kraken `OWNED_RETURN` still entered obligation reservation
and could block valid Binance allocation. The OWNER then clarified that Kraken will no
longer be used; it is now retired before every M034 economic path while historical M033
code/evidence remains intact. Second, physical-exit proof did not count a fee debited in
the spent inventory asset toward the authorized quantity. The third correction counts
that fee exactly as the canonical fill ledger does.

The post-review correction locally passes 141 focused checks: 44 M034, 51 M032 and 46
M033. A fourth independent review must be bound to the next published source SHA.

## Review 4 — source architecture pass

- Reviewer: GPT-6 Astra, independent source review
- Reviewed source: `4054dfd3d02d2075516e9272a4c03046e5e0e277`
- Verdict: `IMPLEMENTATION_REVIEW=PASS`
- Source architecture: `M034_SOURCE_ARCHITECTURE_PASS=true`
- Replay: `READY_FOR_REPLAY=false`
- Strategy: `STRATEGY_PASS=false`

No P1/P2 remained in the reviewed library scope. The reviewer revalidated all sixteen
earlier findings plus the two Review 3 interactions. Twelve Kraken injection variants
left Binance results, decisions, capital states, KPIs and gate calls identical to the
no-Kraken baseline. Spent-asset, received-asset, fragmented-fill and combined external
fee settlements reconciled their exact losses, left no residual inventory, recorded one
negative event and zero positive cycles.

Review gates: 141 focused tests passed (44 M034, 51 M032, 46 M033), repository-wide
Ruff passed, strict mypy passed on the seven affected modules and
`git diff --check aafb57ef..4054dfd` passed. The previously published full suite passed
1,172 with 2 skipped from 1,174 collected tests. No economic replay was executed.

This PASS covers source architecture, contracts and deterministic tests only. Replay
remains blocked until operational thresholds/configuration, pair universe, temporal fee
and rule evidence, causal estimator calibration, dataset/window/hash, model registration,
integrated runner, replay protocol and physical audit/reporting are frozen and published.
