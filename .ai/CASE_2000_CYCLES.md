# Case: Stablecoin Parity → ~2,000 Cycles/Day with Small Capital

## Goal

Design and demonstrate (via simulation / backtest) a strategy + execution engine that can produce **approximately 2,000 cycles per day** on stablecoin pairs (primarily USDCUSDT, optionally FDUSDUSDT) using a small shared bank of **~200 USDT**.

Focus is the **process and the motor** (quoting policy, inventory control, fill realism, capital velocity), not large absolute PnL.

## Constraints (must respect)

1. **Capital**: ~200 USDT total. Min notional ~5 USDT. Prefer many small slots.
2. **Pairs**: USDCUSDT (main, high volume ~600k–1M trades/day, ~0.1 bp spread) + FDUSDUSDT (lower volume).
3. **Execution realism**:
   - Causal (no future peeking).
   - Prefer physical L2 + individual trades for fills (FIFO queue).
   - Exact capital conservation.
   - No self-fill.
4. **Data limitation**: Full L2 only available for ~15 days (1st of each month). Treat these as a forced, stricter benchmark. Other days may use trades + simplified queue model.
5. **Zero-loss spirit**: Avoid negative cycles when possible; inventory must be managed; dust and residual inventory are owned by the user.
6. **Fees**: Consider 0 bp (zero-fee maker or rebate scenarios) and realistic positive fees.

## Observed baseline (M035)

- Shared 200 USDT bank, parallel USDCUSDT + FDUSDUSDT.
- Static / hotline levels.
- In a 3-hour window: **0 fills, 0 cycles**, 0 PnL, exact capital conservation.
- Levels were not touched while executable.

## What “success” looks like

- In simulation on available L2 days (or realistic hybrid): hundreds to 1,500–2,500 cycles/day.
- Inventory stays controlled (mean-reverting skew).
- Fill rate explained by queue position / quoting at or near touch.
- Capital turns over many times without violating conservation.
- Clear audit trail of every fill, cancel, and inventory change.

## Suggested directions (not prescriptions)

- Dynamic BBO / pegged quoting instead of static hotlines.
- Inventory-aware skew (Avellaneda-Stoikov style or simpler).
- Many tiny independent slots (5–10 USDT) sharing the bank.
- Explicit queue position model.
- Relative value between the two pairs for allocation.
- Hybrid data path: full L2 on the 15 days, calibrated simplified fills elsewhere.

## Deliverables expected from an AI / researcher

1. A concrete quoting + inventory policy description.
2. How it would be implemented or tested inside (or compatible with) this lab’s causal engine.
3. Expected cycle count range under the data constraints, with reasoning.
4. Risks (adverse selection, queue disadvantage, inventory lock).
5. Optional: code sketch, parameter ranges, or experiment design.

## Capital note

200 USDT is intentional. The point is the engine and the process. Larger capital would change queue dynamics and is out of scope for this case.

---

Read the main README and `docs/research/CURRENT_STATE.md` for full lab context. This case is independent enough that a different implementation is acceptable as long as the goal and realism constraints are met.
