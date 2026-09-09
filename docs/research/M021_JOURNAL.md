# M021 research journal — dense 200-slot ping-pong mechanics probe

Append-only journal for `DENSE_200_SLOT_PING_PONG_MECHANICS_PROBE_V1`.

## 2026-09-08 — OWNER authority and pre-registration draft

- M020 remains preserved and rejected. M021 is a new mechanical hypothesis.
- Only 2025-01-01 00:00–05:00 UTC is authorized, using the same validated M020
  L2, canonical trades, queue, latency, and audit assumptions.
- First causal bridged book: bid 1.00190000, ask 1.00200000, midpoint
  1.00195000 at capture/exchange microsecond 1735689609412998. Deterministic
  half-up tick quantization freezes anchor 1.0020.
- Proposed grid: 100 BUY entries 1.0019–0.9920 and 100 SELL entries
  1.0021–1.0120; fixed one-tick returns, no recenter.
- Exact normalized capital: 99.6950 USDT plus 100 USDC, initially marked
  199.88500000 USDT-equivalent. This cannot be compared directly with M020's
  capital-100 return.
- The one-USDC unit is below Binance minimum notional and is not live
  executable. Only the minimum-notional gate is bypassed.
- GPT-6 Astra pre-implementation verdict is
  `PROCEED_TO_IMPLEMENTATION_CONDITIONAL`. It identified the anchor-return
  conflict: entries never use the anchor, but B001/S001 one-tick returns may;
  self-cross must block/defer without shifting or internally filling.
- No economic replay has started. Implementation, tests, final independent
  source-bound review, registry creation, and preregistration publication remain
  required.

## 2026-09-08 — implementation, review and registry milestone

- The dense kernel reuses M020 execution authority while keeping M021 geometry and
  capital explicit. It reports fill events, active time, partials, queue blocks and
  open economic positions for all200 slots and20 buckets.
- Two pre-run reporting defects were found and corrected: unknown book coverage no
  longer counts as capital shortage, and a canceled order uses the canonical
  `CANCELED` status for active-time termination. The registry grid field was also
  corrected before registration and covered by a frozen-design test.
- Focused validation passed62 tests; the complete repository suite passed with two
  expected skips. Ruff and diff checks passed.
- Independent GPT-6 Astra review status is `PASS_CONDITIONAL_PRE_RUN`, bound to20
  exact source hashes. This validates machinery only, not economic success.
- M021 was append-only registered as `CREATED`, model hash
  `2276cbcf7e3419f6c08d7242bfef2fe19e1a6be8f49ea4c9be333af53394f9f9`.
- The pre-run source publication and clean `HEAD == origin/main` check remain before
  the single authorized five-hour replay. No economic replay has started; Day2 and
  an automatic successor remain closed.
