# M031 research journal

## 2026-09-10 — OWNER authorization and selection

- OWNER authorized one capital-neutral M031 geometry comparison against M030.
- HEAD/origin/main were `89da1762269d9a8c0f28d97296970eec2df7f208` and clean before work.
- The five candidate dates were revalidated without reading noon performance;
  all passed physical L2/trade gates.
- The sole 64-bit CSPRNG seed is `14895920518136483619`; selected dates are
  2025-02-01, 2025-08-01 and 2025-06-01. No redraw occurred.
- Implementation, audit, focused/full tests and source-bound independent review
  remain prerequisites. No economic M031 event has run at this checkpoint.

## 2026-09-10 — physical capital gate failed before registration

- Exact rank-weight reconstruction found M030 BUY weight=360 ticks and M031=235;
  with the same 70 whole-USDC BUY units, M031 needs 0.0125 USDT more.
- Same-book synthetic proof: M030 starts 78.1040 USDT + 78 USDC; M031 would need
  78.1165 USDT + 78 USDC. Both figures include the unchanged mobility reserve.
- GPT-6 Astra independently classified this as a hard pre-run blocker. Dividing
  results by capital does not make the starting banks equal.
- M031 was not registered, no historical event was replayed and no performance
  metric from the selected noon hours was read.
- OWNER must explicitly allow either a common higher bank (+0.0125 USDT versus
  M030) or incomplete initial M031 funding under the original bank. Until then,
  `STATUS=BLOCKED_PRE_RUN_CAPITAL_IDENTITY`.
