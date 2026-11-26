# .ai — Case Study for AI Agents

This folder is oriented by the main [README.md](../README.md).

## Purpose

Provide a clear, self-contained problem statement so that AI agents (or researchers) can study the case of **stablecoin parity trading** and propose a practical way to reach **~2,000 cycles per day** with small capital (~200 USDT).

The focus is the **process**, the **execution engine**, and the **strategy** — not maximizing absolute profit. Capital is kept small on purpose.

## What this project is (short)

Crypto Strategy Lab is a reproducible research environment for Spot strategies on stablecoins. Core principles:

- Causal execution (only past events)
- Physical L2 + individual trades fills
- FIFO queue modeling
- Exact decimal capital conservation
- Zero self-fill, auditability
- Shared capital across pairs without double-reservation

Current line of research: M035 Parallel Pair Capital Manager (USDCUSDT + FDUSDUSDT, shared 200 USDT bank). In a 3-hour test window it produced **zero fills** because admitted levels were not touched.

L2 historical data is limited (~15 days available as first-of-month free snapshots). This is treated as a stricter contextual benchmark.

## The case to solve

See [CASE_2000_CYCLES.md](CASE_2000_CYCLES.md).

Agents should read that file first, understand the constraints, and propose (or implement) a solution that can be simulated / backtested inside or alongside this lab, aiming for high cycle count with realistic fills.

## Hypotheses

Each agent places its own detailed hypothesis in a subfolder:

| Agent | Folder | Status |
|-------|--------|--------|
| **Grok** | [grok/](grok/README.md) | Hypothesis published (touch-based inventory-skewed micro-slots) |
| Claude | `claude/` | (pending) |
| GPT | `gpt/` | (pending) |
| Gemini | `gemini/` | (pending) |
| … | … | … |

Each hypothesis should be self-contained, respect the lab invariants where possible, and clearly state expected cycle ranges under the data constraints.
