# M016 — independent completed replay audit

STATUS=PASS_EVIDENCE_RECONCILIATION_NOT_STRATEGY_PASS
REVIEWER=GPT-6 Astra; independent task m016_preflight_audit
DATE=2026-09-08
EXECUTION_SOURCE=44d75f9183aa052be20734fac0f244bc4ba238bd
PHYSICAL_RUN_HASH=0b4f726bfa4724009a9d37c07c078976a77179dd82cb09ae98871254307fad5a

Independent reconciliation:78 fills,27 settlements,19 positive ordinary cycles,
8 releases(7 with loss,1 zero). All actual lot deficits respect10bps of restored
operating bank and reserve floor2.5. Fees0 are the frozen assumption. TerminalFLAT.
Daily positive cycles:[12,0,0,0,0,0,0,0,0,1,3,3]; all12 days below500/1000/2000.
Source dates/order and14 source files match published44d75f9, not a later HEAD.

Operating100→100.12132; reserve10→9.78068(min9.78028); equity110→109.902.
Realized and total PnL−0.098; unrealized0. Contributions0.01348, consumption0.2328;
mean cost over ALL8 releases0.0291. Independent FIFO debt0.22328,0/7 loss tranches
recovered. Closed holds>2h8 match8 violation events; maximum119.997830754h.
This is integrity/conditional execution evidence, not strategy approval. The model
fails sustainability/frequency/holding objectives and is not promoted.

SUMMARY_SHA256=7bd14b12f153a226cf916a755732502a88d6f6f86c7fc8915a02731ed523d413
TERMINAL_FILE_SHA256=09fc393462bf4cb97e9f15f7497ffa060b7202f23c17d339a4997160014a9185
TERMINAL_STATE_SHA256=51927d16e16c73c73b00cb234ba5ade81f6d57b30b4b4200cb9d7ae314116a35
ALL_FILL_AUDIT_SHA256=3375c63275ce6d4fe1c3b83eb467c150783ca448d12246a54b2566f9f62336e9
LEDGER_BYTES=3353263655
LEDGER_SHA256=b22abb83aec4fb0988e390f89b6ac0dcc445e483762d272e41105b005cacc873

## Independent entry-autopsy addendum

ENTRY_AUTOPSY_REVIEW=PASS_READ_ONLY_DERIVED_DIAGNOSTIC
ENTRY_AUTOPSY_REPORT=reports/usdcusdt/M016-entry-autopsy.md
ENTRY_AUTOPSY_REPORT_SHA256_LF=3e2a06477b0c619901312ebf1c3c6fd364c9f8583a2be3a7d8355b7cc50645e6

The report's reproduction command was independently executed against the closed
ledger; its full SHA256 and terminal-state hash matched the bindings above.
Verified171002 BUY orders:27 filled and170975 without fills, comprising170964
LIMIT_MAKER_WOULD_TAKE rejections,10 canceled orders and1 terminal ACTIVE order.
All37 BUY activations were evaluated1us after their nominal timestamp; all10
effective BUY cancellations were requested at exact minute boundaries and were
followed by a different limit. The reconstructed145.005973328611h flat duration
and the largest43849-order same-price rejection sequence matched the report.

Executed-source44d75f9 confirms post-only rejection and resubmission at the bound
selected LOW. These observed rejections follow the execution contract; the report
does not demonstrate technical invalidation or how many fills repricing would
produce. Nominal pending/active waiting windows are descriptive, not a causal
decomposition of all idle time. Terminal FLAT means zero inventory: BUY171037
remained ACTIVE without fills. No runtime, policy, ledger or entry report was
changed by this addendum; M017 preflight was not repeated.
