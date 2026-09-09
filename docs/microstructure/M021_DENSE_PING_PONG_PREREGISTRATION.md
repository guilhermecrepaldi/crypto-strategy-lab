# M021 — dense 200-slot ping-pong mechanics probe

STATUS=PREREGISTERED_PRE_RUN  
MODEL=DENSE_200_SLOT_PING_PONG_MECHANICS_PROBE_V1  
PERIOD=2025-01-01T00:00:00Z/2025-01-01T05:00:00Z_EXCLUSIVE  
ORDER_MODE=NORMALIZED_1_USDC_NON_EXECUTABLE_MECHANICS_PROBE

> This normalized one-USDC result is below Binance minimum notional. It is a
> mechanical historical-L2 probe, not a live-executable result.

## Observation and hypothesis

M020 is preserved and rejected with zero fills because its 0.9994–1.0003 P80
map did not overlap the observed 1.0017–1.0027 five-hour path. M021 does not
repair or reinterpret that result. It tests whether the same audited execution
mechanics can complete any physical ping-pong round trip when 200 fixed entry
slots densely surround the first causal market state.

The falsifiable informational criterion is `TOTAL_COMPLETE_CYCLES > 0`. Passing
it means only that the normalized mechanism was observed under the registered
queue/latency assumptions. Profitability, capacity at executable notional, and
live performance remain untested.

## Causal anchor and exact frozen grid

The first valid bridged L2 for the frozen evidence is:

```text
EXCHANGE_US=1735689609412998
CAPTURE_US=1735689609412998
FIRST_VALID_BID=1.00190000
FIRST_VALID_ASK=1.00200000
FIRST_VALID_MID=1.00195000
TICK_SIZE=0.0001
ANCHOR=ROUND_HALF_UP(MID/TICK)*TICK=1.0020
```

The grid cannot submit before that book. After it, the anchor never changes.
P80/P90/P95/P99 do not select geometry. The separately published grid artifact
enumerates every exact entry and return price and is hash-bound before replay.

- B001..B100 enter from 1.0019 down to 0.9920; each returns one tick above.
- S001..S100 enter from 1.0021 up to 1.0120; each returns one tick below.
- No initial entry equals the anchor and no entry price is duplicated.
- B001 and S001 returns equal the anchor by the OWNER's explicit one-tick rule.
  If both compete there, the second is blocked and deferred deterministically;
  no price shift, internal fill, or future selection is allowed.
- `ROLLING_RECENTER=OFF`; a rejected fixed quote may retry only at its identical
  registered price.

## Capital and ownership

Each slot's economic quantity is exactly one USDC. Initial USDT is the exact sum
of the 100 BUY entry prices: 99.6950 USDT. Initial inventory is 100 USDC. At the
first valid bid, initial marked equity is therefore 199.88500000 USDT-equivalent.
This is not comparable to M020's capital-100 return.

All 100 BUY reservations and 100 SELL inventory reservations must reconcile at
once without duplication. No capital is added later. Reserve is zero, release
is disabled, and no forced liquidation occurs at 05:00.

## Persistent slot machines

Every slot retains its ID and initial side. BUY-first performs entry P, return
SELL P+tick, then rearms BUY P. SELL-first performs owned SELL P, segregated
BUYBACK P-tick, restores the same base quantity, then rearms SELL P. Only a full
same-quantity strictly positive round trip is a cycle. Partial fills and
breakeven count zero. Each slot may have only one unresolved economic sequence
and one nonterminal order.

The 200-slot ceiling includes pending and active orders. Post-only and self-cross
rejections release only their own unfilled reservation and never change slot
identity or fixed price. Return orders are owned exits and may wait.

## Physical execution and audit

Reuse M020's first-30-slice native L2/canonical-trade binding, conservative
latency, displayed depth at activation, no cancellation credit, strict
compatible trade-through, actual activation ordering, and global one-use trade
quantity ledger. `PRICE_TOUCH != FILL`. Better price wins, then activation time,
then order ID. The exact cutoff is 05:00 exclusive.

The physical audit must independently reconstruct all submitted orders, queues,
fills, cycle links, shared liquidity, initial endowment, cash, inventory, cost,
realized PnL, and terminal mark. Checkpoint/resume must reproduce a continuous
suffix exactly.

## Frozen reporting

Report total cycles/hour, direction, fill-event counts, maximum simultaneous
orders, all 200 slot rows, and twenty ten-slot buckets. Slot active time means
actual market-active time from activation until full fill or cutoff, summed over
rearms; pending latency is excluded. `FILLS` means fill events; full-order fills
are additionally reported to avoid ambiguity.

If zero cycles, classify and count price-outside-grid, post-only, queue,
compatible-trade absence, partial stall, capital, self-cross, and implementation
failures without changing parameters. Financial totals are sanity checks, not
selection criteria.

## Gates

Before execution: backward-compatible implementation, M020 regression suite,
M021 adversarial fixtures, independent GPT-6 Astra source-bound review, M021
CREATED registry identity, exact grid artifact, clean published `origin/main`,
and explicit M021-only gate. One configuration may run once. Day2, M022,
safe-minimum-notional replay, account, Testnet, live trading, and parameter sweep
remain closed.
