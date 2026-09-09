# M022 — dense ping-pong order manager V2

STATUS=PREREGISTERED_PRE_RUN  
MODEL=DENSE_PING_PONG_ORDER_MANAGER_V2  
PERIOD=2025-01-01T00:00:00Z/2025-01-01T05:00:00Z_EXCLUSIVE  
ORDER_MODE=NORMALIZED_1_USDC_NON_EXECUTABLE_ORDER_MANAGER_PROBE

> The one-USDC orders remain below Binance minimum notional. This is a
> historical-L2 mechanics comparison, not a live-executable result.

## Observation, hypothesis and single change package

M021 is immutable and produced 19 complete positive cycles in five hours. Its
physical ledger showed that owned one-tick returns could remain blocked by free
opposite entries and that most free entries rested far outside the ten-tick path.
M022 tests one package only: an order manager with owned-return priority, a
floating window of free entries over the fixed M021 lattice, and a hard 160-open-
order cap. Distance, quantity, period, evidence, fees, queue, latency, price
priority, no-loss rule and total starting economics remain frozen.

The primary comparison is `M022 cycles - 19`. A positive delta answers only
whether this manager package improved normalized throughput in this five-hour
development window. It does not identify the separate contribution of return
preemption versus floating placement, and it is not proof of profitability,
capacity at valid notional or live performance.

## Fixed economics and lane ownership

There are 100 BUY-first and 100 SELL-first economic lanes. Each B lane initially
owns exactly the USDT equal to its original M021 entry price; the 100 budgets sum
to 99.6950 USDT. Each S lane initially owns one USDC with the same 1.0019 initial
basis used by M021. Profit stays with its lane. A lane may not borrow from another
lane, so a free B lane lacking enough owned USDT for a chosen address is parked as
`PARKED_INSUFFICIENT_FUNDS`. Aggregate starting balances and marked equity remain
99.6950 USDT, 100 USDC and 199.88500000 USDT-equivalent.

This makes explicit ownership that M021's aggregate engine represented through
pooled cash and endowment layers. It preserves aggregate economics but is an
implementation-level strengthening of ownership; it must be disclosed in the
interpretation rather than treated as a proven-identical internal allocator.

## Fixed lattice and causal floating window

The anchor is still half-up quantized from the first valid bridged book. The free-
entry address set is the union of M021's 200 entry prices, 0.9920 through 1.0120,
excluding the anchor. No address is learned from the future and no new price is
generated. A free BUY address must be strictly below the current causal midpoint;
a free SELL address must be strictly above it. Post-only and known-book coverage
still apply.

Owned obligations are allocated first. Remaining capacity is split as evenly as
possible toward 80 free BUY and 80 free SELL orders when both sides have eligible,
funded candidates. At most 160 `PENDING + ACTIVE + CANCEL_PENDING` orders may
exist. Existing unfilled free orders already in the selected nearest-price set
are retained to preserve queue. Remaining addresses are ranked by distance from
mid, passive price, then lane ID. A price has at most one free entry per side.
Only a zero-filled `ENTRY` can be canceled and moved; capital is unavailable until
its cancel ACK. Parked lanes retain identity and capital.

## Return claims and preemption

The first positive fill of an entry freezes that economic sequence and creates an
immutable one-tick `RETURN_PRICE_CLAIM`. The M021 partial policy is preserved: the
partially filled entry cannot be canceled or floated, and its return is submitted
only after the full one-USDC entry completes. The claim prevents a new free
opposite entry that would cross it.

If a previously empty free entry fills partially while its already-sent cancel is
in flight, the ACK cancels only the remainder. The filled fraction and claim stay
owned by that lane as `PARTIAL_RESIDUAL_BLOCKED`; because historical step size is
one USDC, the fraction is neither rounded, aggregated with another lane, returned
as an invalid order nor counted as a cycle.

Before an owned return is submitted, every crossing free opposite entry is sent a
cancel request. The return waits for every ACK; it then receives ordinary latency,
post-only evaluation, displayed-depth queue and shared trade budget. No internal
fill or price shift is permitted. An owned return is never canceled by the manager.
Conflicting owned returns are ordered by first obligation fill, entry activation,
lane ID and source order ID; later obligations wait visibly.

## Event-time clarification

M021 processes a due activation or cancel ACK at the next causal delivery before
matching that delivery. The OWNER directive also says execution must remain the
same as M021, while its illustrative A–H list places ACK after fills. Both cannot
hold on an identical timestamp. This controlled comparison freezes M021's existing
precedence. Newly submitted orders still cannot fill on their creating event and
all fills require a strictly later native trade. The result must disclose this
narrow clarification.

## Metrics and audit

The primary fields are cycles, cycles/hour, delta and multiplier versus 19. The
manager records return claims/submissions/fills, preemptions, cancels for return or
floating placement, reposts, waits from first fill to return submission/activation/
completion, free- and owned-return blockers, self-cross checks, post-only rejects,
queue blocks and order-cap compliance.

All return waits are integer microseconds. For an even sample, the median is the
arithmetic mean of the two central observations; P95 is nearest-rank. Completion
wait is recorded once per fully completed return, never once per fill fragment.
Claims still open at the cutoff are reported as censored, including count and
maximum observed age, and are not silently removed from the completed distribution.

Open-order counts include pending, active and cancel-pending orders, matching the
hard-cap definition. Parked-lane time counts only genuinely free lanes without an
order, lot or proceeds obligation. Distance and shares within five and ten ticks
use exchange-active/cancel-pending order-time; pending-latency orders are excluded.
All are duration-weighted from the previous causal snapshot, never the newly seen
state retroactively. Warmup begins at the first activation evaluation. Unique
lanes, prices, productive lanes and cycle concentration are reported. Financial
totals remain sanity checks.

The independent audit must reconstruct every cycle and prove no duplicated
liquidity/capital, no future data, no self-trade, no negative exit, cancel-ACK
conservation, traceable preemption and reassignment, conserved parked ownership
and exact checkpoint recovery.

## Gates

Synthetic tests A–J from the OWNER directive plus cross-lane ownership, crossing
claims, partial/cancel interaction, cap inclusion, stable selection and tamper
failures must pass. GPT-6 Astra performs a source-bound review. M022 is registered
and its exact preregistration source is committed and pushed before the one allowed
run. One configuration runs once. Day2, M023, live and parameter sweeps remain
closed.
