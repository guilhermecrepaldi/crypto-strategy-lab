# M023 — serial hot-line ping-pong V1

STATUS=PREREGISTERED_PRE_RUN
MODEL=M023_SERIAL_HOT_LINE_PING_PONG_V1
PERIOD=2025-01-01T00:00:00Z/2025-01-01T03:00:00Z_EXCLUSIVE
ORDER_MODE=NORMALIZED_1_USDC_NON_EXECUTABLE_SERIAL_HOT_LINE

> The one-USDC order remains below Binance minimum notional. This is a historical
> L2 mechanics experiment, not a live-executable result.

## Observation and hypothesis

M022 kept almost160 orders open but completed the same19 cycles as M021 in five
hours. Only9 lanes were productive;18,492 EXIT attempts were rejected post-only.
The OWNER now removes parallel economic execution while preserving a broad radar of
available price alternatives.

Hypothesis: a serial manager that continuously evaluates many virtual alternatives,
selects one causal hot-line order and forces `BUY fill → profitable SELL fill` before
another BUY can eliminate internal contention and rejection storms. The test asks how
many positive cycles this mechanism physically completes in the first three hours. No
minimum cycle count is preregistered, and no improvement is presumed.

## Fixed controls and scope

Only2025-01-01T00:00:00Z through03:00:00Z exclusive may enter the engine. Data,
validated L2/trade binding, execution profile, latency, cancellation latency, price
priority, queue depletion, global single-use trade volume, historical0.0001 tick and
zero conditional fee are inherited from the published M022 environment. No cutoff
liquidation, future read, release, reserve, new day or automatic extension is allowed.

The order quantity remains one USDC and bypasses only historical minimum notional.
Initial state is1.0019USDT and zeroUSDC. This is enough to fund the first causal BUY
at the first eligible price; no capital is injected later. Profit remains in cash.

M021/M022 use different capital and initial inventory and ran five hours. They are not
financial controls. Any descriptive prefix comparison must count only their already-
published events before03:00 and disclose the different starting states.

## Virtual radar versus real order

The fixed M022 lattice of200 addresses, anchored at the first causal M021/M022
midpoint of1.0020, is retained only as the candidate radar. Radar
rows have no order ID, balance reservation, queue position or fill eligibility. Their
existence is not a market opportunity or cycle.

The radar is two ordered virtual decks with100 BUY cards and100 SELL cards. When the
only armed card from the middle hot-line region fills, that hot-line position becomes
vacant. The manager moves a free card from the same side's outer stack into the gap:
highest-priced free BUY first for the BUY deck, and lowest-priced free SELL first for
the SELL deck. The executed price card's lifecycle is preserved and the template is
then recycled to the free edge. Card address and position move together, so the
promoted card—not the just-executed card—occupies the vacant hot-line address. This
keeps both decks at100 without changing the
economic sequence. It is virtual permutation, not an exchange cancel or new order;
owned or armed state cannot be evicted. Every rotation records filled card, promoted
edge card, side, old/new position and causal timestamp.

Exactly one order may be non-terminal across `PENDING`, `ACTIVE` and
`CANCEL_PENDING`. The economic state machine is:

`WAIT_BUY → BUY_WORKING → WAIT_SELL → SELL_WORKING → WAIT_BUY`.

Only a full one-USDC BUY creates owned inventory. Only a full profitable SELL closes
it and adds one cycle. Consequently physical completed legs must alternate BUY, SELL,
BUY, SELL. Cancel/repost of an unfilled order remains the same leg and does not violate
economic alternation.

## Hot-line prices

All decisions use the current validated causal book.

- BUY: the highest valid tick strictly below current ask that can be funded by free
  USDT: `min(ask - tick, floor_tick(free_usdt))`.
- SELL: the lowest passive profitable tick:
  `max(best_bid + tick, ceil_tick(unit_cost_basis + tick + applicable_costs))`.

The SELL target is an economic floor, not a fixed address. It may improve upward to
remain passive; it may never fall below cost plus one net-positive tick. Coverage and
historical price/quantity filters remain mandatory except for the explicit minimum-
notional diagnostic bypass.

## Reprice, retry and partials

An unfilled order is retained while its desired hot-line price is unchanged. If the
desired price changes, request cancellation but retain its reservation until ACK.
Only after ACK does the manager recompute from the then-current book and submit.
No new order may overlap the cancellation interval.

After a rejection, store stage, balance/inventory, bid, ask, coverage and desired
price. Do not retry until at least one relevant causal field changes. Count suppressed
retries separately. A new order receives normal latency and cannot consume its
creating event.

The first partial fill freezes side, price and economic leg until the full one USDC is
filled. It is not floated. A cancel race leaving a fraction below historical step is
preserved as `PARTIAL_RESIDUAL_BLOCKED`; it is never rounded, pooled, sold as a valid
lot or counted as a cycle.

## Required invariants and audit

- maximum one non-terminal order including cancel pending;
- no SELL without owned USDC and no BUY while inventory/SELL obligation exists;
- completed economic sides strictly alternate BUY/SELL, beginning BUY;
- one cycle requires one fully settled BUY and its fully settled profitable SELL;
- SELL proceeds exceed exact cost basis after all modeled costs;
- cancel releases only the unfilled reservation and only after ACK;
- radar candidates never reserve, queue, fill or duplicate capital;
- BUY/SELL decks remain100/100 and edge rotation never removes owned/armed state;
- trade volume is consumed at most once;
- no future book, internal fill, forced fill or cutoff liquidation;
- checkpoint/resume equals continuous execution.

Independent audit reconstructs order lifecycle, cap1 timeline, sequence, balances,
inventory, basis, cycles, queue and consumed trades from the physical ledger.

## Metrics and decision boundary

Primary: complete positive BUY→SELL cycles and cycles/hour. Secondary: BUY/SELL fills,
orders, cancels, repositions, rejected and suppressed retries, queue blocks, mean/max
BUY and SELL waits, active-order time, no-order time, open state at cutoff, USDT/USDC,
marked equity, realized/unrealized PnL and radar size.

`MECHANISM_OBSERVED=true` only if at least one complete positive cycle exists. Test
suite success is separate. The result does not prove exchange executability, live
profitability or capacity. Expansion remains blocked pending a new OWNER decision.
