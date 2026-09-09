# M023 research journal — serial hot line

Append-only journal for `M023_SERIAL_HOT_LINE_PING_PONG_V1`.

## 2026-09-09 — OWNER authority and preregistration

- OWNER authorized one test covering only the first three hours of the first validated
  L2 day. Any expansion requires later explicit approval.
- Two hundred M022 addresses remain a virtual opportunity radar. Only one selected
  order can be pending, active or cancel-pending, so candidates cannot reserve capital,
  enter queue or fill in parallel.
- The larger manager is represented as two100-card virtual decks. A middle hot-line
  card that fills leaves a positional gap; the same-side outer edge refills it, then
  the executed template returns to the free edge after preserving its lifecycle.
  BUY promotes the highest-priced free BUY edge card and SELL the lowest-priced free
  SELL edge card. This permutation cannot arm a second order or change inventory.
- Economic execution must start BUY and alternate strictly BUY→SELL. One complete,
  profitable BUY→SELL settlement is one cycle; repricing attempts do not become legs.
- The controlled diagnostic keeps one-USDC normalized quantity, historical tick,
  queue, latency, L2/trade evidence and fee-zero conditional profile. It begins with
  1.0019USDT and zeroUSDC, with no reserve or injection.
- GPT-6 Astra reviewed the concept and found no remaining specification blocker. The
  implementation, tests, source-bound review, registry entry and published clean HEAD
  remain required before the single replay. No economic replay has started.

## 2026-09-09 — implementation reconciliation before source review

- The virtual decks were bound to the published1.0020 M021/M022 anchor. Card address
  and position now move together when an executed middle card is replaced from the
  same-side edge; cancel/rejection without fill does not falsely rotate the deck.
- The physical audit was corrected to allow multiple partial fragments inside one
  economic leg while still rejecting consecutive completed BUY or SELL legs.
- The runner now binds its source review, registry hash, published input authorities,
  writer lock, terminal checkpoint and independent result artifacts before execution.
- Focused M020–M023 regression set:89 tests passed. Replay has not started.

## 2026-09-09 — independent review block and repairs

- GPT-6 Astra blocked the first source review. It reproduced four defects: reserved
  BUY cash missing from marked equity; checkpoint configuration not bound; insufficient
  canonical fill/cash audit; and a five-hour parser called before the three-hour cut.
  It also found that an in-flight order could not activate while cancellation awaited ACK.
- No registry mutation or economic replay occurred under the blocked review.
- Repairs now include reserved cash in equity, bind window and both latencies into the
  checkpoint, independently reconcile canonical prints/fills/queue/cash, parse only the
  first18 native slices and three-hour canonical prefix, and preserve activation during
  cancellation latency without overlapping another order.
- New adversarial fixtures cover reserved equity, configuration mismatch, partial fills,
  noncanonical source, tampered cash and activation-before-cancel-ACK. The expanded
  focused M020–M023 plus registry set passes109 tests. A fresh source review is required.

## 2026-09-09 — second block, final review and registration

- Astra's second review found that partial SELL profit was incorrectly compared only
  with completed-cycle profit and that invalid activation during a pending cancel could
  survive until a later book. No replay occurred under that block.
- The independent audit now reconciles total realized profit from every SELL fragment
  while cycle profit covers only completed SELL orders. Invalid due activation during
  cancellation is terminally rejected and cannot resurrect.
- Final independent review: `PASS_CONDITIONAL_PRE_RUN`;37 review tests passed and17
  runner source paths are hash-bound. Focused regression after repair:111 tests passed.
- M023 registered `CREATED` with model hash
  `05e2674c64c3698b8d7725b7f24ee21724918067111c9207939c95fa1d2c8733`.
- No economic replay has started. Published clean HEAD remains the last gate.
