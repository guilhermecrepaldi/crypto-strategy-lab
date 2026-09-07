# M007 capital-lock autopsy for M011 target

Status: COMPLETE_BEFORE_V2_SCENARIO_RESULTS. Classification: RETROSPECTIVE_DIAGNOSTIC_ONLY.

The physical reconstructed M007 replay contains 344,704 completed cycles over 248 UTC calendar
days: 55 active days and 193 zero-cycle days. Inventory episodes are serial and the terminal open
episode is censored at the physical cutoff.

| Longest holds | Zero days explained | Share of 193 | Lock hours >24h | Share of lock |
| --- | ---: | ---: | ---: | ---: |
| Top 1 | 111 | 57.512953% | 2646.707490 | 57.898388% |
| Top 3 | 140 | 72.538860% | 3326.913364 | 72.778319% |
| Top 5 | 159 | 82.383420% | 3787.362089 | 82.850924% |
| Top 10 | 187 | 96.891192% | 4453.580662 | 97.424873% |
| Top 20 | 192 | 99.481865% | 4571.297364 | 100.000000% |

The longest hold is `cycle_216716`, about 111.279479 days, from 2026-02-05 to 2026-05-28.
The second-longest is the terminal censored position beginning 2026-08-17. Only 2026-06-24 has no
inventory episode covering its replay-day interval and is classified `FLAT_NO_COMPLETED_CYCLE`.

This concentration supports a low-frequency release hypothesis but does not prove that releases
would avoid the same days: alternate ranges can lock again. Per-scenario avoidability, reserve
availability and costs are evaluated only after the causal grid runs.

The formal 95% target requires no more than 9 zero days: `(193-9)/193 = 95.3368%`. Ten days yield
94.8187% and therefore cannot be labeled PASS.

## Reconciliation of superseded v1

Commit `515eddeb` preregistered 27 scenarios with skim 0/1/5%. Ten physical scenarios completed
under artifact identity `8437a909...` before the new OWNER request fixed skim at 2%. Those artifacts
remain immutable but are `SUPERSEDED_PARTIAL_NOT_V2_EVIDENCE`.

A fixed-event precision audit found Decimal28 inexact settlement arithmetic after capital reached
approximately 1e19: 47,382 inexact settlements and 52,624 cash divergences over 622,782 audited
events. The audit held decisions fixed and did not demonstrate a policy-path difference. V2 uses a
local Decimal128 financial context while preserving M007 selector arithmetic. This is a scoped
technical correction, not a blanket reinterpretation of historical M007 or completed skim-zero
artifacts.
