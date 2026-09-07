# OWNER OVERRIDE — STOP B10 REALITY AND ADVANCE STRATEGY

# RECOVERY RESERVE 5% + 5% PROFIT FUNDING + 24H HARD LOCK LIMIT

Esta instrução substitui qualquer ordem anterior de continuar o B10_BINANCE_REALITY_V1 até o fim.

A campanha atual já respondeu uma questão material:

o B10 histórico perdeu a propriedade de alta permanência do motor sob execução mais realista.

Evidência atualmente publicada inclui aproximadamente:

PROFILE=A_OBSERVED_BEST_SUPPORTED
PROGRESS≈86.54%
FULL_FILL_CYCLES=2458
NET_POSITIVE_CYCLES=2458
ZERO_CYCLE_DAYS_SO_FAR=101
MAX_HOLD≈2411.4h
LOCK_HOURS≈2429.9h
NET_PNL_FIXED_100≈+22.412 USDT
RESERVE≈4.581038 USDT
RELEASES=41

O OWNER considera:

~100 dias de posição presa = INACEITÁVEL.

Portanto NÃO há razão para gastar mais recursos concluindo uma estratégia já materialmente superada.

==================================================

1. INTERROMPER A CAMPANHA ATUAL
   ==================================================

Primeiro:

1. localizar exatamente o processo ativo do B10 Reality;
2. confirmar RUN_ID e profile;
3. preservar checkpoint atômico atual;
4. preservar durable journal prefix;
5. NÃO apagar artifacts;
6. NÃO alterar artifacts concluídos;
7. encerrar o processo de forma limpa;
8. confirmar que nenhum writer B10 Reality continua ativo.

Não matar genericamente todos os processos Python.

Encerrar somente a identidade correta.

==================================================
2. CLASSIFICAÇÃO DO RUN ANTIGO
==============================

A campanha atual não deve ser chamada FAIL simplesmente porque foi interrompida.

Registrar:

STATUS=SUPERSEDED_BY_OWNER_STRATEGY_UPDATE

REASON=
Reality evidence demonstrated unacceptable capital lock / zero-cycle behavior under the current B10 policy.

Preservar:

* run ID;
* último checkpoint;
* simulation timestamp;
* cycles;
* PnL;
* reserve;
* releases;
* zero days;
* max hold;
* lock hours;
* audit status.

==================================================
3. ATUALIZAR O JOURNAL GITHUB
=============================

Append em:

docs/research/B10_JOURNAL.md

TYPE=OWNER_STRATEGY_SUPERSESSION

Registrar exatamente:

LAST_B10_RUN_ID=
LAST_PROFILE=
LAST_SIMULATION_TIMESTAMP=
LAST_PROGRESS=
LAST_FULL_FILL_CYCLES=
LAST_NET_POSITIVE_CYCLES=
LAST_NET_PNL_FIXED_100=
LAST_RESERVE=
LAST_RELEASES=
LAST_ZERO_DAYS=
LAST_MAX_HOLD=
LAST_LOCK_HOURS=

DECISION=
B10 Reality stopped because the OWNER requires substantially higher motor uptime and <=24h capital lock.

Não apagar histórico anterior.

==================================================
4. B10 PASSA A SER HISTÓRICO
============================

A partir daqui:

B10_FROZEN=
HISTORICAL_STRATEGY_REFERENCE

B10_BINANCE_REALITY_V1=
SUPERSEDED_PARTIAL_EXECUTION_EVIDENCE

Não iniciar:

Profile B
Profile C
B_FEE10
Profile D

Não concluir o restante do gauntlet.

Não alterar o B10 histórico.

==================================================
5. NOVO MODELO
==============

Mudanças agora são materiais:

* reserve funding muda 2% -> 5%;
* reserve target proporcional;
* reserve passa a ser explicitamente capital de desbloqueio;
* hard maximum lock de 24h;
* release urgency muda;
* capital management muda.

Portanto:

NÃO chamar isso de B10 atualizado.

Criar NOVO Mn.

Antes:

inspecionar registry canônico.

Determinar:

NEXT_FREE_MODEL_ID.

Não assumir M012/M013 sem verificar.

Não sobrescrever nenhum modelo existente.

Registrar:

MODEL_ID=<NEXT_FREE_MODEL_ID>

STRATEGY_NAME=
HIGH_UPTIME_DYNAMIC_RECOVERY

HISTORICAL_PARENT=
B10_FROZEN / RRV2_H1_B10_F0

B10_ARTIFACT_ID=
097abdab8225038b091cb721bdd36bedb8a636c94bed1c87120adc0c9e10953a

==================================================
6. CAPITAL INICIAL
==================

Para estudo principal:

OPERATING_BANK_INITIAL=100 USDT

RECOVERY_RESERVE_INITIAL=5 USDT

TOTAL_INITIAL_EQUITY=105 USDT

A Recovery Reserve é separada da Operating Bank.

==================================================
7. RESERVE TARGET
=================

A reserva deve ser proporcional à Operating Bank.

TARGET_RESERVE_RATIO=5%

Exemplos:

Operating=100
Target Reserve=5

Operating=1,000
Target Reserve=50

Operating=100,000
Target Reserve=5,000.

Ela NÃO é um valor fixo de US$5.

==================================================
8. FUNDING
==========

A cada ciclo líquido positivo realizado:

RESERVE_CONTRIBUTION_RAW =
5% DO REALIZED NET POSITIVE PROFIT.

OPERATING_PROFIT_SHARE =
95%.

Nunca retirar 5%:

* do principal;
* do notional;
* da banca inteira.

Somente do lucro realizado positivo.

==================================================
9. PROPRIEDADE MATEMÁTICA
=========================

Sem releases:

se 5% do lucro vai para Reserve
e 95% para Operating,

o ratio assintótico tende aproximadamente a:

# 5 / 95

5.2631578947% da Operating Bank.

Isso é consistente com o target de aproximadamente 5%.

Registrar essa propriedade.

==================================================
10. RESERVA EXISTE PARA SER USADA
=================================

A Recovery Reserve não é patrimônio que deve permanecer intacto.

Sua função é:

EVITAR CAPITAL LOCK.

Portanto:

RESERVE_USAGE_ALLOWED=YES

RESERVE_USAGE_EXPECTED=YES

RESERVE_HOARDING_OBJECTIVE=NO.

Uma estratégia não é melhor só porque gastou menos reserva.

==================================================
11. RESERVE FLOOR
=================

A reserva pode cair abaixo de 5%.

Isso significa:

RESERVE_REBUILDING.

Mas:

RESERVE_MUST_NOT_REACH_ZERO=YES.

Criar um piso operacional não-zero preregistrado.

O Astra/reviewer científico deve definir antes do replay uma regra exata que impeça:

R <= 0

e evite realizar uma release cujo custo eliminaria completamente a proteção restante.

Não inventar depois de observar resultados.

==================================================
12. HARD CAPITAL LOCK LIMIT
===========================

Nova autoridade do OWNER:

MAX_POSITION_LOCK=24 HOURS.

Isto é uma restrição central da estratégia.

Não é apenas uma métrica.

Objetivo:

NENHUMA posição deve permanecer economicamente presa por mais de 24h.

==================================================
13. RELEASE URGENCY
===================

Projetar política monotônica de urgência:

# AGE < 12h

NORMAL_OPERATION

# 12h <= AGE < 18h

EARLY_WARNING

# 18h <= AGE < 24h

HIGH_RELEASE_URGENCY

# AGE >= 24h

MANDATORY_UNLOCK_STATE.

Os thresholds intermediários podem ser ajustados cientificamente ANTES do replay se houver justificativa melhor.

Mas:

24h é HARD OWNER LIMIT.

Não aumentar isso sem nova autorização.

==================================================
14. O QUE SIGNIFICA MANDATORY_UNLOCK
====================================

MANDATORY_UNLOCK não significa fabricar fill inexistente.

Significa:

a estratégia deve iniciar/seguir a melhor saída executável permitida pela microestrutura e pela reserve disponível.

Não fingir:

PRICE_TOUCH=FILL.

Não fingir liquidez.

Se fisicamente não houver execução suficiente para sair dentro de 24h:

registrar:

HARD_LOCK_VIOLATION.

Isso conta contra a estratégia.

==================================================
15. RELEASE LOSS
================

O objetivo NÃO é evitar todo prejuízo local.

Local release loss é permitido quando economicamente necessário para manter o motor produtivo.

A reserve cobre exatamente o déficit realizado dentro das regras da estratégia.

Registrar:

LOCAL_RELEASE_LOSS.

Nunca esconder isso dentro de transfers.

==================================================
16. ECONOMIC TRUTH
==================

Recovery transfer não cria patrimônio.

Se a posição perde:

equity total perdeu.

A Reserve apenas mantém a Operating Bank capaz de continuar produzindo.

Sempre reportar separadamente:

OPERATING_BANK
RESERVE
TOTAL_EQUITY
REALIZED_RELEASE_LOSS
RESERVE_CONSUMPTION.

==================================================
17. OBJETIVO PRINCIPAL
======================

A prioridade passa a ser:

1. MAXIMIZE MOTOR UPTIME
2. MINIMIZE ZERO-CYCLE DAYS
3. ENFORCE MAX HOLD <=24H
4. MAXIMIZE NET POSITIVE CYCLES
5. KEEP TOTAL ECONOMICS POSITIVE
6. KEEP RESERVE NONZERO AND REBUILDABLE.

Não otimizar simplesmente:

FEWER RELEASES.

==================================================
18. ZERO DAYS
=============

O objetivo desejado é:

ZERO_CYCLE_DAYS ≈ 0.

Não aceitar 100 dias parados.

Preregister gates como:

TARGET:
ZERO_DAYS <= very small number

e:

HARD_RESEARCH_FAILURE_SIGNAL:
reappearance of multi-day capital lock.

Definir números exatos antes do replay.

==================================================
19. REALITY-FIRST
=================

A nova estratégia deve ser testada já sob semantics realistas aprendidas no B10 Reality:

PRICE_TOUCH != FILL

ORDER_ACTIVE_AFTER_LATENCY

QUEUE_AHEAD

COMPATIBLE_AGGRESSOR_FLOW

BUY_FULL

SELL_FULL

PARTIAL_FILL

BINANCE quantity filters

spread

latency

release execution.

Não voltar para uma simulação puramente price-path como prova principal.

==================================================
20. PERFIL DE EXECUÇÃO
======================

Reusar a evidência válida já coletada do Binance Reality quando cientificamente compatível.

Não recalibrar desnecessariamente dados ainda válidos.

Mas não carregar automaticamente assumptions específicas do B10 se a nova estratégia mudar sua interação com execução.

Documentar tudo.

==================================================
21. PRIMARY RULER
=================

Primeiro teste econômico:

FIXED_NOTIONAL_100_USDT.

Razão:

queremos saber se:

US$100 de motor

*

US$5 reserve inicial

conseguem operar continuamente

e manter reserve sustentável.

Depois, se passar:

testar COMPOUNDING separadamente.

==================================================
22. NOVA RESERVE ECONOMICS
==========================

Reportar obrigatoriamente:

RESERVE_INITIAL

TARGET_RESERVE_AT_T

RESERVE_CONTRIBUTIONS

RESERVE_CONSUMPTION

RESERVE_MIN

RESERVE_FINAL

RESERVE_RATIO

TIME_BELOW_5_PERCENT

RESERVE_REBUILDING_DURATION

RESERVE_NEAR_DEPLETION_EVENTS

RELEASE_BLOCKED_BY_RESERVE.

==================================================
23. UPTIME ECONOMICS
====================

Criar métricas principais:

MOTOR_UPTIME

ACTIVE_DAYS

ZERO_CYCLE_DAYS

MAX_HOLD_HOURS

HOLD_P95

HOLD_P99

LOCK_HOURS_GT12

LOCK_HOURS_GT18

LOCK_HOURS_GT24

HARD_LOCK_VIOLATIONS.

HARD TARGET:

LOCK_HOURS_GT24 should approach ZERO.

==================================================
24. CYCLE ECONOMICS
===================

Reportar:

PRICE_PATH_OPPORTUNITIES

FULL_FILL_CYCLES

NET_POSITIVE_CYCLES

REALITY_RETENTION

NET_PNL_FIXED_100

PNL_PER_ACTIVE_DAY

PNL_PER_CALENDAR_DAY

CYCLES_PER_DAY

CYCLES_PER_OPERATING_HOUR.

==================================================
25. RELEASE ECONOMICS
=====================

Reportar:

RELEASE_ATTEMPTS

RELEASE_FILLED

RELEASE_PARTIAL

RELEASE_FAILED

TOTAL_RELEASE_LOSS

MEAN_RELEASE_LOSS

P50_RELEASE_LOSS

P90_RELEASE_LOSS

MAX_RELEASE_LOSS

CYCLES_PURCHASED_PER_RELEASE_USDT

LOCK_HOURS_AVOIDED_PER_RELEASE_USDT.

==================================================
26. NÃO PROTEGER A ESTRATÉGIA
=============================

Se 5% não for suficiente:

mostrar.

Se reserve zeraria:

bloquear conforme regra preregistrada e registrar.

Se mandatory unlock falhar:

registrar.

Se custos destruírem PnL:

mostrar.

Objetivo:

descobrir se a nova política realmente funciona.

==================================================
27. PREREGISTRATION
===================

Antes da nova execução longa:

criar documento canônico:

docs/microstructure/<NEW_MODEL>_HIGH_UPTIME_RECOVERY_PREREGISTRATION.md

e spec:

docs/microstructure/<NEW_MODEL>_MODEL_SPEC.json

Congelar:

* 5% reserve target;
* 5% profit funding;
* nonzero reserve floor;
* 24h hard lock;
* urgency schedule;
* release decision;
* execution assumptions;
* fixed 100 ruler;
* promotion gates;
* dataset/tape identity.

==================================================
28. SCIENTIFIC REVIEW
=====================

Usar reviewer forte.

QUALITY_FIRST=ON.

TOKEN_SAVING_PRIORITY=OFF.

Revisar especialmente:

* reserve sustainability;
* 5% funding math;
* nonzero reserve floor;
* mandatory unlock semantics;
* causal release;
* execution realism;
* possibility of pathological forced exits;
* whether 24h can be enforced without assuming nonexistent liquidity.

==================================================
29. IMPLEMENTAÇÃO
=================

Depois da preregistration:

implementar o novo Mn.

Não modificar B10.

Criar novos modules/configs se necessário.

B10 deve continuar reproduzível como histórico.

==================================================
30. TESTES
==========

Criar testes para:

5% profit funding

dynamic 5% target

reserve rebuilding

reserve never zero

24h state transition

mandatory unlock

failed mandatory unlock

partial release

release fill after latency

reserve accounting

total equity conservation

no future leakage.

==================================================
31. PRIMEIRO REPLAY
===================

Depois de:

preregistration
+
review
+
implementation
+
tests PASS,

INICIAR imediatamente um replay Reality-style do novo modelo.

Não esperar nova autorização, pois esta instrução já autoriza explicitamente a primeira execução.

EXECUTION_AUTHORIZED=YES.

==================================================
32. CHECKPOINT RÁPIDO
=====================

Não esperar 248 dias simulados para descobrir que o novo modelo está ruim.

Publicar checkpoints frequentes.

Especialmente:

first 24h

first 7 days

30 days

e cada evento:

HARD_LOCK_VIOLATION.

==================================================
33. GITHUB JOURNAL
==================

Continuar usando GitHub como memória canônica.

Atualizar:

docs/research/CURRENT_STATE.md

docs/research/B10_JOURNAL.md
como histórico B10

e criar:

docs/research/<NEW_MODEL>_JOURNAL.md

Atualizar também:

reports/usdcusdt/<NEW_MODEL>-reality-scoreboard.json

reports/usdcusdt/<NEW_MODEL>-reality-report.md.

==================================================
34. CURRENT_STATE
=================

Depois da transição:

CURRENT_STATE deve mostrar:

HISTORICAL_STRATEGY=B10_FROZEN

ACTIVE_RESEARCH_MODEL=<NEW_MODEL>

RUN_STATUS=

RESERVE_FUNDING=5%

RESERVE_TARGET=5%

MAX_POSITION_LOCK=24h

CURRENT_SIM_TIMESTAMP=

FULL_FILL_CYCLES=

NET_POSITIVE_CYCLES=

ZERO_DAYS=

MAX_HOLD=

HARD_LOCK_VIOLATIONS=

NET_PNL_FIXED_100=

RESERVE_FINAL=

TOTAL_EQUITY=

VERDICT=.

==================================================
35. COMMIT SEQUENCE
===================

Fazer commits logicamente separados:

1.

research: supersede B10 reality after unacceptable lock evidence

2.

science: preregister <NEW_MODEL> high-uptime recovery

3.

feat: implement <NEW_MODEL> 5pct reserve and 24h unlock

4.

test/audit conforme necessário

5.

research: start <NEW_MODEL> reality replay

Push de cada milestone válido.

==================================================
36. PRIMEIRO RETORNO AO OWNER
=============================

Não retornar só:

“comecei”.

Entregar:

B10_PROCESS_STOPPED=
YES/NO

B10_FINAL_PARTIAL_CHECKPOINT=
...

B10_FULL_FILL_CYCLES=

B10_ZERO_DAYS=

B10_MAX_HOLD=

B10_NET_PNL_100=

B10_RESERVE_FINAL=

B10_STATUS=
SUPERSEDED_BY_OWNER_STRATEGY_UPDATE

NEW_MODEL=

NEW_MODEL_REGISTERED=
YES/NO

RESERVE_FUNDING=5%

RESERVE_TARGET=5%

RESERVE_NONZERO_FLOOR=

MAX_LOCK=24h

PREREGISTRATION_STATUS=

IMPLEMENTATION_STATUS=

TEST_STATUS=

NEW_RUN_STATUS=

NEW_RUN_ID=

COMMIT=

HEAD_EQUALS_ORIGIN_MAIN=

==================================================
37. REGRA FINAL DO OWNER
========================

O objetivo não é conservar a reserva.

O objetivo é conservar a capacidade do motor de operar.

Reserve é capital de recuperação.

Ela deve crescer proporcionalmente à banca.

Ela deve ser usada quando necessário.

Ela pode cair abaixo do target.

Ela NÃO pode zerar.

5% de todo lucro positivo líquido abastece a reserve.

Target da reserve = aproximadamente 5% da Operating Bank.

Nenhuma posição deve permanecer travada economicamente por mais de 24h sem ser classificada como violação.

100 dias parado é inaceitável.

MAXIMIZE_MOTOR_UPTIME=YES

MAX_LOCK_24H=HARD_OWNER_CONSTRAINT

RESERVE_FUNDING_5PCT=FROZEN

RESERVE_TARGET_5PCT=FROZEN

QUALITY_FIRST=ON

START_NEW_REALITY_REPLAY_AFTER_VALIDATION=AUTHORIZED
