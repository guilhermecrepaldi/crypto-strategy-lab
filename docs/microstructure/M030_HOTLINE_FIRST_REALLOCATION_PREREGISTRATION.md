# M030 — hotline-first capital reallocation preregistration

Status: `FROZEN_BEFORE_RUN`

## Observation and hypothesis

M029 moved the hotline through 72 ticks but recorded 1,907 underfunded promotions,
including 1,250 quote-capital and 657 base-asset blocks. It completed 93 HOT, 5 MID
and zero FAR physical cycles. The hypothesis is that zero-fill legacy reservations
and repeated same-book intermediate reconciliations administratively starved the
current HOT.

M030 preserves all M026 economics and changes only capital management. Returns and
filled/partial economic positions remain protected. Missing current-HOT cells first
use operational free capital; if insufficient, the manager requests cancellation of
same-asset zero-fill ENTRY orders. Capital remains unavailable until ACK. Eligible
victims are ordered outside-grid, FAR, MID and demoted former-HOT, then farthest and
youngest. Only when no eligible/pending reclaim can cover the deficit may HOT use the
existing mobility reserve and then record true shortfall. MID/FAR never preempt HOT.

Current-HOT zero-fill cells carrying an obsolete smaller slot weight are canceled and
recreated after ACK at the frozen HOT weight; partial fills are never canceled. Cycle
principal returns to the central priority arbiter rather than automatically recreating
an obsolete source entry. These rules do not alter same-price FIFO priority.

One causal book that implies N crossed ticks records N but jumps directly to the final
hotline, creates one epoch and performs one physical grid reconciliation. N separate
books still create N reconciliations. Half-tick equality retains the M026 hotline.

## Random evaluation frozen before hourly inspection

- OS-CSPRNG draw count: one;
- seed: `13525809254189156280`;
- deterministic sampler: `random.Random(seed).sample(range(3,24),3)`;
- selected UTC hours: `06`, `12`, `13`;
- windows: [06,07), [12,13), [13,14);
- no reroll; invalid physical data stops the experiment;
- the engine still processes every event continuously from 00:00 through 24:00;
- completion time assigns a cycle to the reporting mask;
- the mask cannot affect decisions.

## Baseline and gates

M029 is not rerun. Its published result and physical ledger are read-only baseline
evidence for the same three hours. Primary frequency improvement requires strictly
more M030 physical cycles. Strong improvement is at least 20%. Management success is
separate: time-weighted HOT funding coverage must improve and reclaimable capital
stranded while HOT is missing must be eliminated or materially reduced.

Mechanical pass requires independent ledger/terminal reconciliation and zero forced
filled-order cancellation, negative realized exit, cost-basis rewrite, owned-return
capital theft, duplicated capital, duplicated liquidity or future data. Test pass is
not strategy pass.

## Evidence limits and authority

This is one normalized DEVELOPMENT day below minimum notional, with frozen conditional
zero fees, unknown live L3 rank and no endogenous impact. Publish exact source, tests,
registry and source-bound GPT-6 Astra review before the sole run. No rerun, M031,
another day, account, Testnet or live action is authorized.
