# Capital release diagnostic

Status: `PREREGISTERED_NOT_RUN`

This document freezes the diagnostic that precedes any `CAPITAL_RELEASE` model. It supersedes
the prior M010 pause only for this explicit hypothesis. It does not register M010, authorize a
replay, change M007, or claim executable fills.

## Scientific question and physical authority

The question is whether a small controlled loss can release a serial lot into a causally known,
more productive band and improve final capital relative to waiting indefinitely for the original
HIGH. The sole parent is M007. Its immutable run is
`f622acb767d0dbaa39edfb7c90e6ef349dfaf6d694ee17dcde29f22a3d740d21`, evaluation
`f46a51ecbd3002f54a46c47d350bc20d14e408a2e53f520111524c0caf7f0b82`, on tape
`505fd6c31b010eac4e8da2d7e290137bb455d475b95409ac306d1ded7be55b6c`.

The universe is every one of M007's 344,704 completed cycles plus its terminal censored cycle.
A completed duration of at least 24 hours is a post-event `LONG_HOLD` label used for reporting,
never an admission filter. Every position that is still open at a scheduled checkpoint is
evaluated.

## Frozen decision landmarks

Age is measured from the BUY event. Checkpoints are exactly 60, 300, 900, 1,800, 3,600, 7,200,
14,400, 21,600, 43,200, 86,400 and 172,800 seconds, then every additional 86,400 seconds until
normal HIGH completion or the physical cutoff. A normal HIGH before a checkpoint removes that
checkpoint. The price-path state at scheduled `T` uses only events strictly before `T`; if no
trade occurred since the preceding landmark, staleness is reported and no price is invented.

Each causal snapshot is hashed and logically sealed before any outcome after `T` is attached.
The first artifact contains no retrospective outcome file. Any later, separately preregistered
KEEP/counterfactual continuation must live outside the sealed snapshots and be marked
`RETROSPECTIVE_DIAGNOSTIC_ONLY`.

## Causal destination and rate

The candidate is exactly the M007 `ALWAYS_BEST` selection over `[T-24h, T)`, on the causal tick
grid known at `T`. The incumbent is not excluded. If the best band equals the original band, the
diagnostic records `SAME_CANDIDATE`; it must not choose the runner-up. For the selected band:

```text
C_1h(T)  = completed serial cycles fully contained in [T-1h, T)
C_24h(T) = completed serial cycles fully contained in [T-24h, T)
nu(T)    = min(C_1h(T), C_24h(T) / 24) cycles/hour
r(T)     = HIGH*(1-fee_sell) / (LOW*(1+fee_buy)) - 1
```

The initial price-path diagnostic uses the frozen zero-fee scenario but retains the fee terms.
If `r <= 0` or `nu = 0`, recovery is unsupported. This conservative rate is descriptive; it
does not model the first wait for a destination LOW or the risk of another long hold.

## Release and recovery mathematics

Let `B` be cash immediately before the original BUY, `q` its rounded quantity, `c` residual
cash, `P_T` the last observed price strictly before `T`, and `K = c + q*HIGH*(1-fee_sell)` the
cash obtained if the original target completes. The hypothetical price-path release cash is:

```text
R_T = c + q*P_T*(1-fee_release)
loss_B = B - R_T
loss_fraction = (B - R_T) / B
```

The signed loss is preserved; a negative value is a gain, not a zero loss. For destination LOW
`l`, HIGH `h`, fees `f_b/f_s`, quantity step `s` and available cash `C`, define the exact ledger
map:

```text
q_A(C) = s * floor(C / (l*(1+f_b)*s))
F_A(C) = C - q_A(C)*l*(1+f_b) + q_A(C)*h*(1-f_s)
N_B = min n >= 0 such that F_A^n(R_T) >= B
N_K = min n >= 0 such that F_A^n(R_T) >= K
recovery_time_rate_proxy_X = N_X / nu
```

`N_B` measures recovery to pre-BUY cash; `N_K` is the stricter original-HIGH opportunity target.
Zero quantity or non-positive exact gain is `UNRECOVERABLE_UNDER_ASSUMPTIONS`. The idealized log
formula from the OWNER is retained as an analytic cross-check, never substituted for exact
fixed-point accounting. The rate-derived duration is named a proxy, not expected recovery time.

The fixed-100-USDT ruler reconstructs its own rounded quantity and residual under the same fees;
it never scales the compounded quantity. For horizon `H` and `n=floor(nu*H)`, the idealized
break-even release loss is:

```text
RELEASE_BREAK_EVEN(H) = 1 - (1+r)^(-n)
```

The report also records the exact symmetric per-leg break-even fee `(h-l)/(h+l)`. These are
mathematical price-path quantities, not executable evidence.

## Remaining-hold support

The diagnostic estimates a 24-hour restricted residual survival quantity for the same absolute
LOW/HIGH only. At checkpoint `T` and age `a`, eligible historical episodes entered on or after
2025-01-01 and strictly before `T`. The focal episode is included exactly once as right-censored
at `T`; its future exit is never read. A completion strictly before `T` is observed, while every
episode still open at `T` is right-censored at `T`.

Condition on episodes still at risk at age `a`. For residual observed/event pairs `(Z_i, delta_i)`,
the Kaplan-Meier curve is `S(u)=product_(v<=u)(1-d_v/n_v)` and
`RMST_24h=integral_[0,24h] S(u)du`. Full support requires at least 30 at-risk episodes, entries
from at least three distinct UTC dates, and follow-up through the 24-hour residual horizon.
Without it, expected remaining hold is `UNKNOWN`; the diagnostic reports the supported integral,
lower/upper truncation bounds, maximum supported age and an explicit reason. It never replaces
censored episodes with completed means.

## Destination-start support and candidate rule

The first-cycle wait for the causal destination is estimated separately. Origins are every
complete UTC hour in `[T-30d,T)`. From each origin, observe the first serial destination
LOW-to-HIGH completion using only the prefix; incomplete observations are censored at `T`.
The Kaplan-Meier 90th percentile must be identified inside 24 hours with at least 30 origins on
three UTC dates. Overlapping origins are dependent and must be labelled as such.

The sole candidate rule, frozen before calculation, is:

```text
RELEASE only when:
  destination exists and differs from the original band;
  original RMST24 and destination first-cycle q90 are identified;
  C_1h >= 30 and C_24h >= 120;
  0 < loss_fraction <= 0.0005;
  t_recovery_K = q90_first_cycle + max(N_K - 1, 0) / nu;
  1.25 * t_recovery_K < original_RMST24;
otherwise KEEP.
```

Five basis points bounds the hypothesis to small losses. The factor 1.25 requires a material
25% safety margin. These are design limits, not values selected from checkpoint outcomes; they
must not be changed if the diagnostic produces zero releases.

## Outputs and forbidden lookahead

Each snapshot records event identity, timestamps, age, last known price/staleness, integer ticks,
LOW/HIGH, worst prefix mark, `B/q/c/R_T/K`, loss USDT/fraction/bps, causal candidate and score,
`C_1h/C_24h/C/r`, survival support, recovery cycles/times, break-even and source hashes.
The first artifact ends at sealed causal snapshots, coverage and support aggregates. It does not
calculate future KEEP/RELEASE branches, actual recovery or remaining focal duration. A separately
preregistered continuation may later add those outcomes. Groups by month, tick regime and
`LONG_HOLD` are post-mortem only.

Forbidden in a causal snapshot: future HIGH time, future cycle count or volume, future best band,
future Oracle result, realized remaining duration, later recovery success, and any threshold
chosen after viewing outcomes. The diagnostic is persisted even if all checkpoints are
unsupported. No window, support threshold or landmark may be changed to manufacture a signal.

## Gate after the diagnostic

The Astra scientific review must verify estimator coverage and either authorize the frozen rule
unchanged or decline M010. Only then may M010 be registered. A subsequent replay must use a Git
SHA already on `origin/main`, the complete frozen DEVELOPMENT interval, initial capital 100
USDT, no economic early stop, and a separate fixed-100-USDT productivity ruler.

Promotion requires compounded final capital at least 101% of M007; fixed-100-USDT additive PnL
at least 101% of M007's corresponding ruler; daily-cycle p50 at least 90% of M007; zero-cycle
days and idle each no worse by more than five percentage points; drawdown no worse by more than
one percentage point; non-negative delta in at least half of complete months; and at least 10%
fewer hours in positions older than 24 hours, including terminal censored exposure. Accounting
and causal audits are hard gates. L2/fill evidence remains a later execution-aware gate.
