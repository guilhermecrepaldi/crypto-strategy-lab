# M031 — 10-level concentrated floating grid preregistration

STATUS=`BLOCKED_PRE_RUN_CAPITAL_IDENTITY`. This is a frozen draft, not an
executable preregistration and not a registered model.

## Question and isolated change

M031 asks whether moving the same 140 operational slot-units from M030's 15-level
3/2/1 geometry into a 10-level grid with a three-level 4×4 CORE increases physical
cycle frequency without weakening capital safety. The M030 manager, returns,
latency, queue semantics, fees, sizing, no-loss rule and 16-unit mobility reserve
are controls, not optimization variables.

## Frozen geometry and bank

Per side: CORE ranks 1–3 = `3×4×4=48`; MID ranks 4–8 = `5×2×2=20`;
FAR ranks 9–10 = `2×1×1=2`. Total is 70 per side, 140 operational and
156 including mobility. Treatment begins with 48 physical entries; control with
60. No capital is injected. Existing aged orders are never resized. Filled or
partial orders are never reclaimed. Zero-fill excess can be reclaimed through the
unchanged M030 causal cancel/ACK policy.

### Failed physical-capital gate

Equal slot counts do not imply equal cash reservations at different ranks. The
M030 BUY rank-weight is 360 coarse ticks; M031's is 235. With 70 whole-USDC BUY
units and the same hotline, M031 costs exactly 0.0125 USDT more. The frozen
synthetic book proves 78.1040 versus 78.1165 USDT, while both require 78 USDC.
Capital-normalized reporting cannot repair unequal starting capital.

The constraints “exact M030 bank”, “48 fully funded M031 orders”, “unchanged
whole-USDC sizing/prices” and “8-unit mobility reserve” are mutually incompatible.
No economic event may run and M031 may not enter `CREATED` until OWNER explicitly
selects a permitted resolution.

## Selection and source gates

Before any performance inspection, all five candidates were physically revalidated
against immutable L2 slices and canonical trades. The output is
`reports/usdcusdt/M031-date-pool-preflight.json`. A single OS CSPRNG draw generated
`DATE_SELECTION_SEED=14895920518136483619`; Python's deterministic PRNG sampled,
without replacement and without redraw:

1. `2025-02-01`
2. `2025-08-01`
3. `2025-06-01`

If any selected source later fails integrity, M031 stops as
`SELECTED_SOURCE_DATE_INVALID`. Each date is an independent replication with the
same normalized slot bank. CONTROL and TREATMENT process 00:00–13:00 UTC in full;
the mask 12:00–13:00 affects reporting only. There is no reset at noon and no
economic stitching across dates.

## Metrics and gates

Primary: aggregate M031 noon physical cycles must exceed aggregate control.
Strong: M031 must be at least 120% of control. Slot cycles are separate and never
relabelled physical. CORE rank 1/2/3 and columns 1/2/3/4 are reported separately;
the CORE gate requires at least one C4 completed cycle. C4 full-fill events report
wait distributions and eligible trade quantity remaining after C4.

Both arms report HOT/CORE coverage, public/own FIFO waits, funding blocks, true
shortfall, reclaim activity, reserve exhaustion, inventory, equity and capital-
normalized frequency/return. Safety requires zero negative forced exits, duplicate
capital/liquidity, pre-ACK reuse, self-fill and filled-order reclamation.

## Local execution and determinism

Numerical replay is deterministic local Python. Independent dates may use at most
three worker processes while observed memory remains below 70% of physical RAM;
each arm's chronology stays single-threaded. GPU is disabled for matching/FIFO and
may not change precision or event order. Hardware, Python, workers, wall/CPU time,
peak RSS and events/second are recorded. Same input and published source must yield
the same terminal/ledger hash.

Source, tests and a source-bound GPT-6 Astra review would be committed and pushed
before a campaign only after the blocker is resolved. The current GPT-6 Astra
review returned BLOCK before replay. `TEST_SUITE_PASS != STRATEGY_PASS`. No sweep,
rerun, M032, other hour/date or live action follows.
