# Grok Hypothesis: Touch-Based Inventory-Skewed Micro-Slots for ~2,000 Cycles/Day

**Author**: Grok (xAI)  
**Date**: 2026-11-26  
**Target**: ~2,000 cycles/day on USDCUSDT (primary) + FDUSDUSDT with ~200 USDT shared bank  
**Compatibility**: Designed to fit (or run alongside) the lab's causal execution, L2/FIFO physical fills, exact capital conservation, and no-self-fill rules.

## 1. Core Idea

The M035 baseline produced zero fills because admitted levels were not touched. The hypothesis is that **high cycle velocity on tight-spread stablecoins requires continuous presence at or very near the touch**, with many tiny independent slots and an inventory-aware skew that keeps the book from locking capital on one side.

Instead of static hotlines or distant grid levels, we run a **dynamic pegged quoting engine**:

- Always quote at or 1 tick inside the current BBO when inventory allows.
- Size each order as a small fixed notional (5–8 USDT).
- Maintain many concurrent slots that share the 200 USDT bank via a simple reservation ledger.
- Skew the bid/ask prices (or sizes) based on current inventory so the strategy mean-reverts.
- Cancel and replace aggressively when the book moves, but only after CANCEL_ACK (respecting the lab invariant).

On USDCUSDT the natural spread is often 0.1 bp or less and trade intensity is high (~600k–1M trades/day). With small size and good queue priority, a large fraction of resting touch orders should fill when the other side arrives.

## 2. Capital and Slot Design

- **Total bank**: 200 USDT (shared).
- **Slot size**: 5–8 USDT notional per order (adjustable).
- **Target concurrent slots**: 20–35 (leaving headroom for inventory skew and temporary imbalance).
- **Reservation**: Each live order reserves its full notional until CANCEL_ACK or full fill. No double-reservation across pairs.
- **Inventory limits**: Soft cap at ±30–40 USDT net inventory per pair; hard cap that stops new orders on the accumulating side.

With 5 USDT slots, 200 USDT can theoretically support ~40 concurrent one-sided reservations, but we keep utilization in the 60–80% range to allow rapid reallocation.

## 3. Quoting Policy (Touch + Skew)

### Price
1. Observe the current best bid and best ask from the L2 book (or best available quote).
2. Compute a fair mid (or simple mid).
3. Inventory skew (simplified Avellaneda-Stoikov style):
   - Let `q` = current inventory in USDT (positive = long USDC / long the base).
   - Skew in ticks: `skew_ticks = k * q / slot_size` (k ≈ 0.3–0.6, tuned).
   - Bid price = best_bid - skew_ticks * tick (or more aggressive when short).
   - Ask price = best_ask - skew_ticks * tick (more aggressive when long).
4. Prefer quoting **at the touch** or **1 tick inside** when the resulting price is still executable and within risk limits. Never quote worse than 1–2 ticks away from touch unless inventory is extreme.

### Size
- Base size = fixed notional (5–8 USDT).
- Reduce size on the accumulating side when |q| is large.
- Optionally increase size slightly on the depleting side (still within slot limit).

### Lifecycle
- Place / replace only after previous cancel is ACKed.
- On fill, immediately free the reserved capital and consider placing a new order on the opposite side (or same side if inventory still allows).
- Periodic re-quote (e.g., every 100–200 ms or on significant book change) to stay at the touch.

## 4. Pair Allocation (USDCUSDT vs FDUSDUSDT)

- Primary allocation to USDCUSDT (higher volume, tighter spread).
- Secondary allocation to FDUSDUSDT only when it offers better relative value or when USDCUSDT inventory is already skewed.
- Shared bank: a simple score (volume × inverse-spread × inventory-room) decides how many slots each pair receives at any moment.
- Never reserve the same USDT for both pairs simultaneously.

## 5. Data and Simulation Strategy

Given only ~15 days of full L2 (1st of each month):

1. **Primary evaluation set**: those 15 L2 days. Run the full causal L2 + individual-trades FIFO fill engine exactly as the lab does.
2. **Secondary / calibration set**: remaining days using trades + a calibrated simplified queue model (probability of fill given distance to touch, size, and recent trade intensity). The simplified model is tuned on the 15 L2 days so it does not invent fills that the real book would not have produced.
3. Report both: exact L2 results (stricter) and hybrid results (more volume of cycles).

This preserves the lab's philosophy that the first-of-month days are a forced, harder contextual benchmark.

## 6. Expected Cycle Count (Reasoning)

Rough order-of-magnitude:

- USDCUSDT: ~700k–1M trades/day.
- Touch orders of 5–8 USDT with decent queue priority can capture a non-trivial fraction of opposite-side flow.
- With 25–30 active slots and continuous presence at the touch, a conservative estimate is 0.5–2 fills per slot per minute in active periods.
- Over a full day that can easily reach 1,000–3,000 one-way fills → 500–1,500 round-trip cycles if inventory is managed well.
- Targeting the upper half (~1,500–2,500 cycles/day) is plausible under zero or near-zero maker fees and good skew control; realistic positive fees reduce the number but do not eliminate it.

The exact number will be measured, not assumed. The hypothesis is that the touch + micro-slot + skew regime is the first design that has a realistic chance of producing four-digit daily cycles under the lab's fill model.

## 7. Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| Adverse selection (informed flow) | Inventory skew + size reduction on accumulating side; optional short-term volatility filter |
| Queue disadvantage | Prefer joining or improving the touch; small size improves relative priority |
| Inventory lock | Hard inventory caps; aggressive opposite-side quoting when skewed |
| Cancel/replace latency | Only re-quote after CANCEL_ACK; keep some orders resting longer |
| Capital fragmentation | Slot size not too small; reservation ledger with headroom |
| Overfit to the 15 L2 days | Treat them as held-out stricter test; calibrate simplified model carefully |

## 8. Compatibility with Lab Invariants

- Causal: all decisions use only already-received book and trade events.
- Physical fills: primary results use L2 + individual trades + FIFO.
- Capital: exact decimal reservation; no double-booking; dust stays with the user.
- No self-fill: own volume is excluded from the public flow.
- Zero-loss spirit: a positive cycle does not offset a negative one in the classification; inventory is marked at cutoff.

## 9. Suggested Next Steps (if implemented)

1. Implement a minimal M036-style touch quoter with the reservation ledger and skew.
2. Run it on 2–3 of the available L2 days first (smoke + fill-rate measurement).
3. Calibrate the simplified queue model on those days.
4. Expand to all 15 L2 days and produce the cycle / inventory / capital reports.
5. Compare against M035 on the same windows.

## 10. Summary

The hypothesis is that **continuous touch quoting with many small inventory-skewed slots** is the missing piece that turns the existing capital and FIFO machinery into a high-velocity cycle engine on tight stablecoin pairs. With ~200 USDT the absolute profit will stay modest; the value is proving that the process can generate ~2,000 realistic cycles per day under the lab's strict causal and fill constraints.

This is a hypothesis, not a result. It is offered as a concrete, implementable starting point for the case.
