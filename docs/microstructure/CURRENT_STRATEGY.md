# Current strategy — OWNER authority, 2026-09-07

Authority: [OWNER_STRATEGY_OVERRIDE.md](OWNER_STRATEGY_OVERRIDE.md). This handoff supersedes
conflicting historical campaign continuation instructions. The canonical registry remains
`artifacts/usdcusdt/models/registry.jsonl`; published registry files are projections, not a
second registry. Historical promotion events are not new research authority.

## Identity and execution gate

```text
CURRENT_ACTIVE_RESEARCH_MODEL=M011
PARENT_MODEL=M007
CURRENT_HISTORICAL_BASELINE=M007
SCIENTIFIC_ANCESTOR=M007
SHADOW_MODEL=M007 (unchanged; no new runtime validation claimed)
REGISTRY_STATUS=CREATED
REGISTERED_AT=2026-09-07T20:07:20.901134+00:00
MODEL_HASH=51b46f5fe064827a0cc3cc60a3b881b4bc3eeb863ef4ee60e7f08c38027588b7
PREREGISTRATION_SHA256_UTF8_LF=1bae95bf418e6ffab2d96cb7f9db8cbbde5296a902cb8bbe5e52ecc94dc30778
IMPLEMENTATION_STATUS=NOT_IMPLEMENTED
CURRENT_RUN=NONE
CURRENT_RESULTS=NOT_RUN
LONG_CAMPAIGN_AUTHORIZED=NO — stop after publishing this preregistration
```

M011 is the next free identity verified against the physical append-only registry and model
directories (M001–M010 existed before this change). It identifies the **complete** new
strategy, not an M007 selector alias. M010 is inconclusive historical evidence, not its parent.
The historical V2 file named `M011_RECOVERY_RESERVE_PREREGISTRATION.md` did not allocate an ID;
it is explicitly superseded. Frozen source documents and prior artifacts remain intact.

## Strategy and capital

```text
CURRENT_STRATEGY_DESCRIPTION=Single serial USDCUSDT operating lot, causal range selection,
  positive-profit reserve funding, dynamic confidence-gated fully covered capital release
OPERATING_INITIAL=100 USDT
RESERVE_INITIAL=5 USDT
TOTAL_INITIAL_EQUITY=105 USDT
CAPITAL_MODE=COMPOUNDING
RESERVE_FUNDING=2% of every positive realized cycle profit; 98% to operating bank
RESERVE_TARGET=5% of operating accounting bank; rebuilding below target is allowed
RESERVE_CAP=10% of operating accounting bank; overflow returns to operating bank
DYNAMIC_RELEASE=Strict causal prefix, monotone loss/confidence tiers, economic advantage,
  exact full reserve coverage, restore operating bank, FLAT, wait for a new LOW
ZERO_DAY_TARGET=<=9 out of 248 frozen calendar days; seek zero
TOKEN_SAVING_PRIORITY=OFF
QUALITY_FIRST=ON
CONTEXT_PRESERVATION=ON
SCIENTIFIC_DETAIL_PRESERVATION=ON
```

The precise decision rules, parameters, arithmetic and experimental gates are frozen in
[RECOVERY_DYNAMIC_PREREGISTRATION.md](RECOVERY_DYNAMIC_PREREGISTRATION.md). The complete
model identity binds that document by SHA256 in [M011_MODEL_SPEC.json](M011_MODEL_SPEC.json).
The old runner must reject the new unsupported strategy, not silently execute an M007/V2
approximation. This delivery does not implement the new runner or claim it is executable.
Publication checks: 14 canonical registry tests passed; the actual legacy SerialModelConfig
rejects M011's unsupported strategy; protocol digest matches the specification; registration
appended M011 while preserving the complete pre-existing registry byte prefix.

**Funding constraint:** 2% of profit does not maintain a 5% reserve ratio under sustained
compounding. Without releases/cap effects, its limiting ratio is 2/98 = 2.040816…%.
The 5% value is a target, not a guaranteed floor. No principal transfer, extra funding,
changed contribution percentage or external recapitalization is implicitly authorized.

## Superseded campaigns and preservation

```text
PREVIOUS_SUPERSEDED_RUNS=RECOVERY_RESERVE V2/V3 predecessor identities listed in evidence
SUPERSEDED_STATUS=SUPERSEDED_BY_OWNER_STRATEGY_UPDATE
STOPPED_PROCESSES_BY_THIS_DELIVERY=NONE
ACTIVE_MATCHING_PROCESSES_AT_PREFLIGHT=NONE
PRIOR_PROCESS_TERMINATION_CAUSE=UNKNOWN
AUTOMATION_CONTINUAR_RECOVERY_RESERVE_V2_E_V3=PAUSED
```

The V2 published identity
`097abdab8225038b091cb721bdd36bedb8a636c94bed1c87120adc0c9e10953a`
is retired with 9 of 18 scenarios complete and a preserved partial next scenario. It must not
resume. Earlier partial/technically affected identities retain their original evidence and
any original technical classifications; supersession does not retroactively repair them.
Completed valid scenarios remain valid historical **theoretical price-path** evidence, not
M011 results. No process was observed that needed a kill; do not claim a clean stop occurred
here or classify an unexplained earlier process exit as FAIL.

Integrity, file hashes, checkpoints, all completed rows and exact provenance:
[OWNER-strategy-transition-evidence.json](../../reports/usdcusdt/OWNER-strategy-transition-evidence.json).

## Latest valid historical scoreboard

Last completed scenario by grid/progress order, **not a best-result selection**:
`RRV2_H4_B5_F0`, old published V2 identity above.

| Metric | Historical M007 + 5 idle | Latest completed old V2 |
|---|---:|---:|
| Cycles | 344704 | 853616 |
| Zero-cycle days | 193 | 120 |
| Active days | 55 | 128 |
| Operating uptime | 23.1973% | 52.9402% |
| Releases | 0 | 69 |
| Operating final marked equity, USDT | 900637402983.4181046 | 42703590628952142570393713.536842724 |
| Reserve, USDT | 5 | 788273846327940535536529.522650776 |
| Total equity, USDT | 900637402988.4181046 | 43491864475280083105930243.059493500 |
| Max hold, hours | 2670.7074896425 | 2659 |
| Lock hours | 4571.2973641253 | 2801 |
| Maximum drawdown | 0.268517% | 0.263147% |

Old V2 cycle multiplier = 2.4763739324; cycles gained = 508912; zero days eliminated = 73;
zero-day reduction = 37.8238341969%, **below** the >=95% target. Total realized release loss
= 83228003242511353655181.8760603 USDT in the theoretical compounded ledger.
Exact source metrics, including any unavailable fields, remain in the evidence file.

Other completed V2 results must not be hidden by the last-completed convention. Grouped below
only where the two reserve-floor scenarios have identical reported economic outcomes:

| Historical scenario(s) | Cycles | Zero days | Active days | Releases | Max hold h | Lock h |
|---|---:|---:|---:|---:|---:|---:|
| H1_B2, floors 0 / 2.5 | 615743 | 157 | 91 | 65 | 2670.7074896425 | 3661.9919975119 |
| H1_B5, floors 0 / 2.5 | 895427 | 119 | 129 | 99 | 2659 | 2801 |
| H1_B10, floors 0 / 2.5 | 3580880 | 3 | 245 | 156 | 26 | 4 |
| H4_B2, floors 0 / 2.5 | 580653 | 158 | 90 | 42 | 2670.7074896425 | 3673.6433577842 |
| H4_B5, floor 0 | 853616 | 120 | 128 | 69 | 2659 | 2801 |

H1_B10 reaches the historical zero-day target in two old configurations, but is neither a
new-policy test nor a demonstrated robust/executable result. Its reported theoretical equity
is about 1.0097045235e128 USDT. The exact operating/reserve/equity/drawdown values for all nine
scenarios are retained in the linked evidence, including duplicate outcomes, without promotion.

These enormous zero-fee price-path compounded values are not demonstrated executable capital.
Fills, queue, depth, latency, slippage, capacity and market impact are not validated. This is
frozen DEVELOPMENT, not prospective evidence. M007 + 5 idle is NOT the new matched-funding
passive control: that control has not run. M011 has no measured cycles, equity or drawdown.

## Next execution, after a new explicit gate

SCENARIO_COUNT=8 planned full-span comparisons: one matched passive control, M011 center and
six one-axis sensitivity neighbors. Each materially different policy gets its own next-free
Mn before execution; only M011 is registered in this delivery. The remaining seven are
planned policies, not registered runs or permission to auto-launch.

FIRST_SCENARIO_TO_RUN=Matched passive control: same 100+5, 2% funding, 10% cap and strict
causal selection/execution convention, but no reserve releases. WHY=Isolate the release
policy's incremental cost/productivity under equal funding; next run M011 center.
The historical M007 replay is preserved separately, not recomputed as if unchanged semantics.

Before any long run: implement and test the frozen protocol, obtain explicit execution
authority, register each other policy against its actual next-free ID, publish code/config,
bind the published commit SHA and audit the frozen tape/cutoff. No opportunistic early stop;
the preregistration defines allowed stops. Report audited results after each scenario.

Science preregistration/review this delivery: GPT-6 Astra High. Independent physical evidence
audit: GPT-5.6 Terra High. Calculations and hashing use project/Python tools. No model switch
is claimed for the parent session; no LLM per event. No Testnet, live orders, private account,
deployment, second lot, second pair or capacity implementation is authorized here.
