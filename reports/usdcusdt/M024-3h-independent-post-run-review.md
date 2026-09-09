# M024 — independent preserved-run recovery review

STATUS=PASS_PRESERVED_PHYSICAL_RUN_RECOVERABLE
REVIEWER_MODEL=gpt-6-astra

## Verdict

The preserved physical run is recoverable by correcting the independent auditor and deriving results from its existing terminal checkpoint and ledger. No economic rerun is needed or justified by this defect. This is a factual technical-recovery verdict, not unconditional strategy approval.

Run identity: dcdfd2697ecf82a9b9cd60c6504d432b1981619d661d09f52d03a5e23492dfe1.
Recorded published execution source: 74baeedfa8e1b36d7cb1f47c7aefda6d93524c5c.
Model hash: a2f1f9708f222ed0a984318a5fe0c56a44791f7f718bddc93bb24a91c4be6125.
Window: 2025-01-01 [00:00,03:00) UTC; no cutoff liquidation or Day 2.

## Cause and repair

The original failure.json records M024_AUDIT_ACTIVATION after the physical ledger and terminal checkpoint had already been written. The execution kernel allows an in-flight cancellation request before exchange activation. Activation can legitimately occur before cancellation becomes effective, retaining CANCEL_PENDING until ACK. The old auditor required PENDING and then unconditionally set ACTIVE.

Physical order 167 establishes this case:
- SUBMIT: 1735690169539462; activation due 1735690170718987.
- CANCEL_REQUEST: 1735690170239634; cancellation effective 1735690171419159.
- ACTIVATED: 1735690170839757; activation-book upper 1735690170837999.
- CANCEL_ACK: 1735690171439350; remaining quantity 1.

The repaired auditor accepts PENDING/CANCEL_PENDING at activation and retains a pending cancellation; rejection is also accepted from either pre-activation state. This matches the frozen kernel lifecycle and does not change economic orders, queues, fills or balances. A focused synthetic full-ledger regression covers the ordering. The two M024 test modules passed **85 tests** in this review.

Compared with the manifest's 24 source bindings, only the runner containing the auditor and its tests differ currently. The economic kernel, model specification and preregistration retain their recorded hashes. The original source identity must remain the execution source; the repaired audit source must be disclosed separately.

RECOVERY_AUDITOR_SOURCE_SHA256_LF[scripts/run_triangular_pre_aged_queue.py]=102c768517c6febe551ebe56dea4d372e72e59b0d6ce142c779161c5efa6fa4d
RECOVERY_TEST_SOURCE_SHA256_LF[tests/test_run_triangular_pre_aged_queue.py]=c41cc102f5e485c6e3f8b83cdb7d61a30296b159e29fbeb9ed5b17a09a0b0bdc

## Independent read-only verification

Loaded the existing JSONL and terminal checkpoint. Verified the canonical daily archive SHA256 against the recorded input binding, then read only the canonical [00:00,03:00) trade prefix through the existing history iterator. Restored the checkpoint and called metrics() without finish(), receive_book(), receive_trade(), or any replay runner. Passed those immutable records and the canonical map to independent_execution_audit.

The audit returned PASS_M024_PHYSICAL_LEDGER:
- 29,538 delivered canonical trades; 72 fill fragments.
- 35 complete positive cycles: 9 BUY-first and 26 SELL-first; 11.6667 cycles/hour.
- Maximum 150 nonterminal orders, below cap 200.
- Capital, segmented FIFO, global canonical trade budgets, lots and actual pre-aging timestamps reconciled.
- Zero new growth-funded cells; growth pool 0.00680000 USDT.
- Final USDT 77.00100000 and USDC 73, including reserved balances.
- Initial marked equity 150.13250000; final 150.16160000; change +0.02910000.
- Completed-cycle PnL 0.00680000; disposal PnL 0.01080000; unrealized PnL 0.01830000. Financial identity residual is zero.
- 138 orders remain open at cutoff; no forced closure.

Recomputed run_hash from the manifest identity excluding run_hash and the separately attached evidence object; independently checked evidence_sha256. Both match. The JSONL hash matches the original failure record, and the terminal's internal state hash and embedded-ledger binding pass the independent audit.

All four physical file hashes were identical before and after review:
PHYSICAL_SHA256[execution-audit.jsonl]=05ccf076f76926428afc5271bfe5f52413ea4dbb0653326cc7b7cea9911149b9
PHYSICAL_SHA256[failure.json]=a25864c6e5d7ec626a16ad061c2e57091b8e863846cdd51ce328aad9cb172878
PHYSICAL_SHA256[run-manifest.json]=832b61044cbfc46d4646e31ad07fd02d85baee1c9955cdc1a29462ec1176daf2
PHYSICAL_SHA256[terminal-engine-state.json]=908deaffe3c708dcaa29f34876ccf8891e73a6b60c9fe5112073307057abea34

## Limits and publication conditions

Preserve the original failure artifact and execution SHA. Finalization may publish derived summaries and the repaired audit with explicit technical-recovery provenance; it must not label the failed original process as an uninterrupted successful exit or replace the physical evidence.

35 cycles exceed the preregistered engineering ruler of 30 in three hours, but this does not establish the long-term throughput goal, capital efficiency superiority, live profitability or true queue rank. The normalized notional, zero conditional fees and observed-L2 queue assumptions remain conditional. Pre-aging shadow quantities are diagnostic only, not extra financial liquidity or an identified live treatment effect. MAIN_LIMITER remains pending a separate physical autopsy.

No engine replay, new economic run, physical artifact mutation, registration, finalization, gate change, commit or push was performed. Only this review file was created.
