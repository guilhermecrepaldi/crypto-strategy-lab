# OWNER — primeiro dia e progressão condicional de mil ciclos por dia

RECEIVED_DATE=2026-09-08
AUTHORITY=“Simule em 3 dias, caso eu aproveite, aumenta”; correção seguinte “Aprove”.
INTERMEDIATE_OVERRIDE=“2 dias.”
LATEST_OVERRIDE=“1 dia simulador, 1 hora de espera max”.
ONE_HOUR_MEANING=HOLD_ALERT_ONLY; OWNER_SELL_HIGH_ONLY_SUPERSEDES_FORCED_EXIT
INTERPRETATION=“caso eu aprove”; não é aprovação já concedida para ampliar.
APPROVED_COMPARISON_DAYS=1
EXTENSION_AUTHORIZED=false
NEW_REPLAY_AUTHORIZED_NOW=true
AUTHORIZED_MODEL=M028
AUTHORIZED_SCENARIO_COUNT=1

## Latest authority — M028 unchanged M026 strategy, full January 1 day

OWNER_DIRECTIVE=M028_M026_24H_EXTENSION_OWNER_DIRECTIVE.md
CURRENT_EXECUTION_WINDOW=2025-01-01T00:00:00Z/2025-01-02T00:00:00Z_EXCLUSIVE
PARENT_MODEL=M026
ONLY_CHANGE_FROM_PARENT=END_EXCLUSIVE_3H_TO_24H
RUNS_AUTHORIZED=1
PREFIX_EQUIVALENCE_REQUIRED=true
ANOTHER_DAY_AUTHORIZED=false
AUTOMATIC_SUCCESSOR_AUTHORIZED=false

The OWNER explicitly selected M026 and authorized one full-day test with marked
before/after equity and percentage gain. M026 remains immutable; the duration change
is M028. The exact M026 strategy starts once at midnight and runs continuously to
the next midnight, with a hard 00:00–03:00 prefix-equivalence gate. No tuning,
M027 MICRO geometry, reset, capital injection, cutoff liquidation or live action.

## Latest authority — M027 micro-hot controlled A/B, three hours only

OWNER_DIRECTIVE=M027_MICRO_HOT_REALLOCATION_OWNER_DIRECTIVE.md
CURRENT_EXECUTION_WINDOW=2026-05-01T00:00:00Z/2026-05-01T03:00:00Z_EXCLUSIVE
SCENARIOS=CONTROL,TREATMENT
RUNS_PER_SCENARIO=1
VALIDATED_TICK_SIZE_REQUIRED=0.00001
COARSE_GRID_SPACING=0.0001
MICRO_OFFSET=0.00005
INITIAL_PHYSICAL_ENTRY_ORDERS=60
INITIAL_OPERATIONAL_SLOT_UNITS=140
MOBILITY_SLOT_UNITS_PER_ASSET_SIDE=8
MAX_SIMULTANEOUS_NONTERMINAL_ORDERS=200
DAY2_AUTHORIZED=false
AUTOMATIC_SUCCESSOR_AUTHORIZED=false

The OWNER authorizes one matched M027 A/B after the fine-tick data, tests,
independent Astra source review and published-source gates pass. CONTROL uses the
unchanged M026 15-level coarse geometry on the new tape. TREATMENT replaces only
FAR14/FAR15 with two one-slot MICRO columns at hotline ±0.00005. Both preserve 60
initial orders, 140 operational and 16 mobility slot-units; initial marked-capital
mismatch must be <=0.01%. M026 remains immutable. No rerun, another day, M028,
extension, account, Testnet or live action is authorized.

The authorized M027 run is now consumed and complete. Both arms produced zero
fills/cycles because the tape never reached the intervention prices. Audit passed,
but the causal effect is unidentified; M027 is INCONCLUSIVE. The gate is closed.

## Latest authority — M026 dynamic hotline 3/2/1, three hours only

OWNER_DIRECTIVE=M026_DYNAMIC_HOTLINE_321_OWNER_DIRECTIVE.md
CURRENT_EXECUTION_WINDOW=2025-01-01T00:00:00Z/2025-01-01T03:00:00Z_EXCLUSIVE
ORDER_MODE=NORMALIZED_SLOT_BASE_1_USDT_EQ_WHOLE_USDC_NON_EXECUTABLE
INITIAL_PHYSICAL_ENTRY_ORDERS=60
INITIAL_OPERATIONAL_SLOT_UNITS=140
MOBILITY_SLOT_UNITS_PER_ASSET_SIDE=8
MAX_SIMULTANEOUS_NONTERMINAL_ORDERS=200
RUNS_AUTHORIZED=1
DAY2_AUTHORIZED=false
AUTOMATIC_SUCCESSOR_AUTHORIZED=false

The OWNER-authorized M026 mechanics run completed after registration, tests, Astra
source review and publication. M024 remains the scientific parent and M025 only
supplies the best observed 37-cycle comparison. M026 uses a causal whole-tick
hotline, 15 levels per side and HOT/MID/FAR 3/2/1 physical-column and slot sizing.
Old order price, size, FIFO age, basis and epoch remain immutable. Promotions
need real per-asset mobility capital; demotions drain. Physical and slot cycles
are reported separately. The gates are >=38 physical and >=60 slot-equivalent
cycles in three hours. The run produced30 physical cycles and90 slot-equivalent
cycles: the physical gate failed and the weighted ruler passed. M026 is INCONCLUSIVE,
the gate is closed, and no rerun, M027, day2, sweep or live action is authorized.

## Previous authority — M025 order-size capacity curve, three hours only

OWNER_DIRECTIVE=M025_ORDER_SIZE_CAPACITY_OWNER_DIRECTIVE.md
CURRENT_EXECUTION_WINDOW=2025-01-01T00:00:00Z/2025-01-01T03:00:00Z_EXCLUSIVE
SCENARIO_Q_USDC=10,50,100,250,500,750,1000,1500,2000,3000,5000
ONLY_INDEPENDENT_VARIABLE=ORDER_QUANTITY_USDC
SCENARIOS_INDEPENDENT=true
RUNS_PER_SCENARIO=1
GROWTH_STRUCTURAL_EXPANSION=false
ENDOGENOUS_MARKET_IMPACT=false
DAY2_AUTHORIZED=false
AUTOMATIC_SUCCESSOR_AUTHORIZED=false

OWNER authorized one controlled M025 capacity campaign over the exact M024 three-hour
tape. Each of the eleven quantities receives proportional real simulated capital and
an independent copy of the unchanged exogenous tape; book/trade liquidity is not
scaled. Full Q entry plus full Q profitable return is one cycle. Partials are not
cycles. Source, tests and Astra review must be published before any event. On technical
failure after events, preserve and stop without rerun. No M026, day2, live or tuning.

## Latest authority — M024 triangular pre-aged queue, three hours only

OWNER_DIRECTIVE=M024_TRIANGULAR_PRE_AGED_QUEUE_OWNER_DIRECTIVE.md
CURRENT_EXECUTION_WINDOW=2025-01-01T00:00:00Z/2025-01-01T03:00:00Z_EXCLUSIVE
ORDER_MODE=NORMALIZED_1_USDC_NON_EXECUTABLE_PRE_AGED_FIFO
INITIAL_FREE_ENTRY_ORDERS=150
MAX_SIMULTANEOUS_NONTERMINAL_ORDERS=200
ECONOMIC_RUN_AUTHORIZED_ONLY_AFTER_PUBLISHED_PREREG_AND_SOURCE_REVIEW=true
DAY2_AUTHORIZED=false
AUTOMATIC_SUCCESSOR_AUTHORIZED=false

The OWNER authorized exactly one M024 run after registration, tests, independent
source-bound Astra review and publication. M024 preserves M023 and tests shared-public
same-price FIFO groups with a second independently funded order already aging behind
the first. Initial capital is74.9900USDT plus75USDC; the normalized one-USDC orders
remain below Binance minimum notional. The machine gate permits only the first three
hours of2025-01-01 and closes after the single physical run. No repeat, parameter
sweep, M025, extension, executable notional or live action is authorized.

The one physical run was executed from published source `74baeed`. Its engine ledger
and terminal state completed, but the original process exited on an independent-auditor
lifecycle defect; the four physical artifacts remain preserved. A corrected read-only
audit recovered35 cycles without rerunning market events. M024 is now INCONCLUSIVE:
its10cycles/hour mechanics ruler passed, but the one-USDC normalized result is not
live-executable and is not capital-matched to M023. This gate is closed.

## Latest authority — adaptive stablecoin ladder V1

## Latest authority — M023 serial hot-line three-hour mechanics test

OWNER_DIRECTIVE=M023_SERIAL_HOT_LINE_OWNER_DIRECTIVE.md
CURRENT_EXECUTION_WINDOW=2025-01-01T00:00:00Z/2025-01-01T03:00:00Z_EXCLUSIVE
MAX_SIMULTANEOUS_NONTERMINAL_ORDERS=1
ECONOMIC_SEQUENCE=BUY_THEN_SELL_STRICTLY_ALTERNATING
VIRTUAL_BUY_DECK=100
VIRTUAL_SELL_DECK=100
DAY2_AUTHORIZED=false

The OWNER authorized exactly one three-hour first-day L2 mechanics replay. Two virtual
decks keep candidate capacity ready, but only one physical order may reserve capital,
queue or fill. Executed middle cards are replaced from their same-side edge; unfilled
cancels do not rotate the deck. The one run completed4 cycles and is preserved under
published source68841b1. Expansion remains closed; a new explicit OWNER decision is
required for any additional window or changed strategy.

## Preserved M019 authority

OWNER_DIRECTIVE=ADAPTIVE_STABLECOIN_LADDER_OWNER_DIRECTIVE.md
PROPOSED_MODEL=M019
STRATEGY=ADAPTIVE_STABLECOIN_LADDER_V1
BUY_SLOTS=6
SELL_SLOTS=6
INITIAL_MARKED_EQUITY=100_USDT_EQUIVALENT
NEGATIVE_EXIT_ALLOWED=false
LOSS_RELEASE=DISABLED
CURRENT_EXECUTION_WINDOW=2025-01-01_ONLY

The full latest OWNER directive supersedes the unexecuted three-range proposal.
M019 preparation is authorized, but economic execution remains fail-closed until
the exact implementation, tests, independent GPT-6 Astra review, CREATED registry
identity and pre-run commit are published. At that point the two machine fields
may be switched to authorize M019 before the one-day run.
No day2 payload may be opened. A day1 pass does not itself rewrite this file or
authorize extension; the result and audit must first be published and reconciled.

POST_RUN_STATUS=M019_D1_COMPLETE_FAIL_1000
POST_RUN_EVIDENCE=PASS_CONDITIONAL
DAY2_AUTHORIZED=false
The execution gate is closed again after D1. Any successor or extension requires
a new explicit OWNER decision and a new preregistered identity where material.

## Active successor authority — M020 zonal ping-pong, five hours only

OWNER_DIRECTIVE=STABLECOIN_ZONAL_PING_PONG_OWNER_DIRECTIVE.md
MODEL_ID_CANDIDATE=M020
STATUS=M020_5H_COMPLETE_REJECTED_ZERO_THROUGHPUT
ECONOMIC_RUN_AUTHORIZED_ONLY_AFTER_PUBLISHED_PREREG_AND_REVIEW=true
AUTHORIZED_START=2025-01-01T00:00:00Z
AUTHORIZED_END_EXCLUSIVE=2025-01-01T05:00:00Z
DAY2_AUTHORIZED=false
SAFE_MIN_NOTIONAL_REPLAY_AUTHORIZED=false

The OWNER has authorized one new, non-executable normalized throughput case.
It does not reopen, edit or invalidate M019. Full-calendar-2025 price occupancy
may be used for retrospective DEVELOPMENT geometry, but the economic engine must
receive no event at or after05:00UTC. The one-USDT first-leg unit is below Spot
minimum notional and must be reported as virtual structural normalization. The
run gate remains closed until M020 identity/specification, tests, independent
review and the exact source/preregistration commit are published.

POST_RUN_STATUS=M020_5H_COMPLETE_REJECTED
POST_RUN_CYCLES=0
POST_RUN_LIMITER=PRICE_OUTSIDE_FIXED_P80_MAP
POST_RUN_SOURCE_SHA=e211838c9094c58c2fbe33d025a8d4fc80f17b8e
POST_RUN_PHYSICAL_HASH=dd80b82cafbc96c049ed6814b5c91726fc5c758876afa62ddb7795038ba61122
POST_RUN_AUDIT=PASS_M020_LEDGER_EXECUTION_LIQUIDITY

The exact five-hour run is complete. No price entered the frozen P80 map, so
all nine bands recorded zero cycles and M020 was rejected for this window.
This closes the execution gate; a geometry change is a new hypothesis and the
safe-min-notional repetition remains subject to a new OWNER authorization.

## Active successor authority — M021 dense mechanics probe, five hours only

OWNER_DIRECTIVE=M021_DENSE_PING_PONG_OWNER_DIRECTIVE.md
MODEL_ID=M021
STATUS=M021_5H_COMPLETE_INCONCLUSIVE_MECHANIC_OBSERVED
AUTHORIZED_START=2025-01-01T00:00:00Z
AUTHORIZED_END_EXCLUSIVE=2025-01-01T05:00:00Z
ORDER_MODE=NORMALIZED_1_USDC_NON_EXECUTABLE_MECHANICS_PROBE
DAY2_AUTHORIZED=false
AUTOMATIC_SUCCESSOR_AUTHORIZED=false

The OWNER authorized exactly one M021 mechanics run after published pre-registration,
tests, independent source-bound review and CREATED registry identity. Those prerequisites
are prepared for publication. The machine gate above authorizes only M021 at the exact
five-hour cutoff after HEAD equals origin/main and the worktree is clean. It does not
authorize Day2, M022, live execution, a notional-executable replay or parameter changes.
M020 remains immutable and rejected.

POST_RUN_CYCLES=19
POST_RUN_CYCLES_PER_HOUR=3.8
POST_RUN_AUDIT=PASS_M021_LEDGER_EXECUTION_LIQUIDITY
POST_RUN_PHYSICAL_HASH=7508beca1ee232864027204c6e33a92191fe1725d42d2eccd82f7349815a05ae
POST_RUN_STATUS=INCONCLUSIVE

The single run is complete and the gate is closed. The normalized ping-pong
mechanic was observed, but its3.8cycles/hour is not high throughput and the
one-USDC unit remains below exchange minimum notional. No rerun, Day2, M022 or
parameter adjustment is authorized by this result.

## Active successor authority — M022 order manager V2, five hours only

OWNER_DIRECTIVE=M022_ORDER_MANAGER_OWNER_DIRECTIVE.md
MODEL_ID=M022
STATUS=M022_5H_COMPLETE_REJECTED_NO_THROUGHPUT_IMPROVEMENT
AUTHORIZED_START=2025-01-01T00:00:00Z
AUTHORIZED_END_EXCLUSIVE=2025-01-01T05:00:00Z
ORDER_MODE=NORMALIZED_1_USDC_NON_EXECUTABLE_ORDER_MANAGER_PROBE
M021_BASELINE_CYCLES=19
MAX_SIMULTANEOUS_OPEN_ORDERS=160
DAY2_AUTHORIZED=false
AUTOMATIC_SUCCESSOR_AUTHORIZED=false

The OWNER authorized one M022 controlled comparison after exact pre-registration,
tests, a source-bound GPT-6 Astra review, CREATED registry identity and publication.
Only order management changes: owned-return priority plus a causal floating free-
quote window on the fixed M021 lattice. Data, capital, queue, latency, one-tick
economics and the five-hour cutoff remain frozen. The machine gate above permits
exactly one run after HEAD equals origin/main and the worktree is clean. It does not
authorize a rerun, Day2, M023, executable notional, account access or live execution.

POST_RUN_CYCLES=19
POST_RUN_CYCLES_PER_HOUR=3.8
POST_RUN_DELTA_VS_M021=0
POST_RUN_AUDIT=PASS_M022_MANAGER_LEDGER_EXECUTION_LIQUIDITY
POST_RUN_PHYSICAL_HASH=389fef14f694c2e0af549fd1a23b03b96390d09243a32989dd90087396b05e35
POST_RUN_STATUS=REJECTED

The one authorized run is complete. The manager kept almost160 orders open and
changed placement activity, but produced exactly the same19 cycles as M021. Fixed
owned returns generated18,492 EXIT post-only rejections and return preemption was
never exercised. The process raised a stdout serialization error only after all
artifacts were written; no replay was repeated. The gate is closed. Day2, M023,
parameter changes and executable/live runs require a new explicit OWNER authority.

## Superseded preparation — three ranges

## Latest proposal — three independent ranges, no reserve

OWNER_PROPOSED_STRATEGY=THREE_DISJOINT_RANGES_NO_RESERVE
PROPOSAL_STATUS=EXIT_RULE_CONFIRMED; PREPARATION; NOT_REGISTERED_OR_EXECUTED
PROPOSED_INITIAL_CAPITAL=300_USDT; THREE_ALLOCATIONS_OF_100
PROPOSED_INITIAL_RESERVE=0
OWNER_EXIT_RULE=SELL_AT_HIGH_ONLY_WITH_POSITIVE_NET_PROFIT; NO_FORCED_LOSS
OWNER_LATEST_WINDOW=ONE_DAY_ONLY; NO_AUTOMATIC_EXTENSION
OWNER_COVERAGE_QUESTION=HOW_MANY_RANGES_COVER_90_PERCENT_OF_CYCLES

The new OWNER proposal supersedes reserve-based strategy design for the next
case, not immutable historical runs. Preserve the first-day data gate. No new
replay may begin before preregistration, identity, tests, independent review and
publication. The OWNER resolved exit policy with "Vender em alta somente" and
confirmed "Fazer1dia somente". No loss budget is approved. Hold beyond1h must be
reported; no forced exit, no artificial profitable fill or cutoff liquidation.
Capital/inventory/order ownership remains separate per range; all lanes share
realistic market-liquidity consumption. Proposed interpretation: price intervals
do not overlap and each lane compounds its own gains, with no cash transfers.
These details must be explicit in the eventual frozen protocol.

Measure completed positive cycles per lane and total, final marked equity,
unrealized losses, BUY/SELL waiting, longest interval without a completed cycle,
and time with zero/one/two/three eligible working lanes. A working order is not
evidence of realized economic productivity. Never infer fills from chart touches
or choose historical ranges using future highs/lows. If fewer than three causal
ranges qualify, record unavailable lanes rather than manufacture opportunities.
Any paired strategy comparison must account for the new300 initial capital;
the historical100+10 control is not a capital-matched experiment. No promise of
continuous operation,1000 cycles/day or forced profitable exit within1h.
The question about90% coverage authorizes a first-day descriptive calculation,
not a massive strategy sweep. State the denominator and deduplicate shared
opportunities. Retrospective coverage is not prospective selection or actual
L2 fills; it cannot silently set the new strategy's ranges from future events.
Do not increase funded lanes beyond three or read another day on this question.

## Preserved M018 execution authority and earlier progression

CURRENT_CASE_STATUS=M018_COMPLETE_9_POSITIVE_CYCLES; EXTENSION_GATE_FAILED
M018 já completou o primeiro dia. Não repetir o run nem iniciar dia2:9<1000.
A autorização true foi publicada antes do run em65b7fe6; esta atualização é
pós-execução, não altera o vínculo histórico. Nova hipótese precisa dos próprios
registro, revisão e publicação; a pesquisa de suporte continua autorizada.

LATEST_CONTINUATION=Continue, use as estratégias de suporte para novas elaborações.
CONDITIONAL_MAX_STAGE_DAYS=3
MINIMUM_POSITIVE_CYCLES_EACH_DAY=1000

A instrução posterior autoriza dia2 quando dia1 atingir1000 ciclos completos
líquidos positivos auditados, e dia3 quando dia2 também atingir1000, mantendo
mesma estratégia e todo o estado. O limite atualmente liberado continua1dia:
M017 demonstrou12, não1000. EXTENSION_AUTHORIZED=false descreve o gate atual,
não revoga a autorização condicional futura. Exigir também sustentabilidade
econômica, execução e auditoria; não esconder dia fraco numa média acumulada.
Após três dias aprovados, nova hipótese para2000/dia retorna ao dia1 e capital
inicial100+10. Não modificar modelo durante replay nem reinicializar numa extensão.
O runner atual recusa extensão até haver continuação completa auditada.
M018 pode executar somente após registro, testes, revisão independente e publicação.
Usar mecanismos de suporte isolados; não juntar indicadores ou enfraquecer fila.

A ordem mais recente reduz o horizonte anterior. O replay M017 já havia ultrapassado
o limite novo sob a autorização anterior. Seu processo foi interrompido assim
que a nova ordem foi recebida; a interrupção é OWNER_SCOPE_CHANGE, não bug técnico
nem reprovação econômica do período completo. Não apagar ou renomear o run antigo
para fingir que originalmente foi um replay de1dia. Não há liquidação forçada.

Usar agora somente checkpoint fechado do dia1 de M015/M016/M017 para a
comparação principal. É a primeira amostra da sequência existente:2025-01-01.
Relógio lógico:2025-01-01T00:00:00Z inclusive até2025-01-02T00:00:00Z exclusive.
Não é uma semana histórica contínua, nem dados prospectivos. Os dias posteriores
já conhecidos não voltam a ser holdout; ficam separados como evidência histórica.

Preservar 100USDT operacionais+10reserva iniciais, compounding próprio por modelo,
custos e hipóteses de execução identificadas. M017 conserva a configuração original
registrada e seu SHA publicado; o relatório de1dia é um prefixo auditado, não uma
nova configuração executada ou resultado integral de12dias.

No corte, posições, ordens, reserva, dívida e timers permanecem como estavam.
Posição ainda aberta é marcada e censurada, não encerrada ficticiamente.
O checkpoint de engine não prova, sozinho, capacidade de retomar todo o runner:
uma futura extensão deverá verificar também seletor, book, fluxo, cursor e
relógios, ou reconstruir deterministicamente o prefixo e provar equivalência,
sem sobrescrever artifacts. Nada disso autoriza a extensão antes do OWNER.

O OWNER cancelou gráficos/HTML. Entregar ciclos positivos, banca operacional,
reserva e patrimônio total, identificando período e status. Manter auditoria e
diário GitHub; testes de software não aprovam a estratégia. A frase “1hora”
continua pendente de esclarecimento; o caso isolado de admissão conserva2h e
deve declarar isso, sem alegar validação de uma política de1h.
