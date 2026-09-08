# OWNER OVERRIDE — TWO-STAGE REPLAY

# STAGE 1 = 5 MONTHS ONLY

# EXTEND ONLY IF IT PASSES

Esta instrução altera o horizonte inicial da próxima estratégia multi-queue.

Não executar inicialmente o período completo até setembro.

Objetivo:

ITERAR MAIS RÁPIDO SEM REDUZIR RIGOR.

==================================================

1. MODELO
   ==================================================

Aplicar ao próximo modelo da arquitetura:

CONTINUOUS_MULTI_QUEUE_RECOVERY

com:

* COMPOUNDING;
* 3 Operating Queues máximo;
* 1 Active Reserve Queue máximo;
* Reserve inicial = 10% da Operating Bank;
* 10% de todo positive realized net profit → Reserve;
* 90% → Operating compounding;
* até 50% da Reserve pode alimentar Active Reserve Queue;
* Reserve nunca pode zerar;
* MAX OPERATING LOCK = 24h;
* MOTOR UPTIME como objetivo principal.

Verificar NEXT_FREE_MODEL_ID fisicamente.

Não assumir ID.

==================================================
2. STAGE 1 — CINCO MESES
========================

Primeiro replay:

START=
2026-01-01T00:00:00Z

END_EXCLUSIVE=
2026-06-01T00:00:00Z

Portanto:

JAN
FEB
MAR
APR
MAY

= cinco meses completos.

Não usar junho-setembro durante Stage 1.

==================================================
3. DADOS FUTUROS PROIBIDOS
==========================

Durante Stage 1:

nenhuma decisão pode utilizar:

June
July
August
September

nem estatísticas calculadas sobre esses meses.

Strict causal prefix continua obrigatório.

Dados posteriores ficam:

SEALED_EXTENSION_DATA.

==================================================
4. CONGELAR MODELO ANTES DO STAGE 1
===================================

Antes de executar:

preregister

model spec

allocation policy

queue rules

reserve rules

release rules

24h lock

execution assumptions

success gates

e model hash.

Depois disso:

NÃO ajustar parâmetros usando resultado dos 5 meses.

==================================================
5. OBJETIVO DO STAGE 1
======================

Responder rapidamente:

A NOVA MÁQUINA CONSEGUE:

1. permanecer praticamente sempre produtiva?
2. evitar long locks?
3. crescer geometricamente?
4. formar e preservar a Reserve?
5. utilizar Active Reserve sem colocar Core Reserve em risco?
6. distribuir capital pelas filas sem self-competition destrutiva?
7. permanecer economicamente positiva sob Reality execution?

==================================================
6. GATES DO STAGE 1
===================

Preregister antes do replay.

No mínimo exigir:

MOTOR_UPTIME >= 99%

CAPITAL_WEIGHTED_UPTIME alto e reportado

FULL_STOP_DAYS = 0

ZERO_CYCLE_DAYS próximo de zero

MAX_OPERATING_HOLD <= 24h

HARD_LOCK_VIOLATIONS = 0

RESERVE_MIN > 0

RESERVE_DEPLETION_EVENTS = 0

TOTAL_EQUITY_FINAL > TOTAL_EQUITY_INITIAL

NET_REALIZED_PNL > 0

RESERVE_SELF_SUSTAINABILITY_RATIO >= 1

nenhuma violação contábil

nenhum future leakage

nenhuma duplicação artificial de liquidez entre Q1/Q2/Q3/Q4.

Astra/reviewer deve congelar thresholds exatos antes do replay.

==================================================
7. CHECKPOINTS IMPORTANTES
==========================

Mesmo dentro dos cinco meses, publicar:

DAY 1

DAY 7

DAY 30

DAY 60

DAY 90

DAY 120

FINAL_5_MONTH.

==================================================
8. PLACAR OBRIGATÓRIO
=====================

Para cada checkpoint:

OPERATING_CAPITAL=

RECOVERY_RESERVE=

RESERVE_RATIO=

CORE_RESERVE=

ACTIVE_RESERVE_CAPITAL=

TOTAL_EQUITY=

TOTAL_PROFIT=

OPERATING_QUEUES_ACTIVE=

RESERVE_QUEUE_ACTIVE=

CYCLES=

NET_POSITIVE_CYCLES=

MOTOR_UPTIME=

CAPITAL_WEIGHTED_UPTIME=

FULL_STOP_HOURS=

ZERO_CYCLE_DAYS=

MAX_HOLD=

LOCK_HOURS_GT24=

HARD_LOCK_VIOLATIONS=

RELEASE_COUNT=

TOTAL_RELEASE_LOSS=

RESERVE_CONTRIBUTIONS=

ACTIVE_RESERVE_PROFIT=

RESERVE_CONSUMPTION=

RESERVE_SELF_SUSTAINABILITY_RATIO=

CAPACITY_PRESSURE_EVENTS=

VERDICT=.

==================================================
9. PRINCIPAL PLACAR DO OWNER
============================

Mostrar também:

INITIAL_EQUITY=
110 USDT

DAY_1_TOTAL_EQUITY=

DAY_7_TOTAL_EQUITY=

DAY_30_TOTAL_EQUITY=

DAY_90_TOTAL_EQUITY=

FINAL_5_MONTH_TOTAL_EQUITY=

e:

OPERATING_BANK em cada período.

Não usar FIXED_NOTIONAL_100.

Capital mode:

COMPOUNDING ONLY.

==================================================
10. STAGE 1 PASS
================

Se todos os hard gates passarem:

STAGE_1_DECISION=PASS_TO_EXTENSION.

Então:

NÃO alterar estratégia.

NÃO alterar parâmetros.

NÃO recalibrar thresholds usando junho-setembro.

NÃO criar novo modelo somente pela extensão temporal.

O mesmo Mn permanece congelado.

==================================================
11. STAGE 1 FAIL
================

Se houver falha estrutural como:

reserve zero;

long lock >24h;

full-stop relevante;

negative economics;

self-competition severa;

capacity collapse;

ledger violation;

então:

STAGE_1_DECISION=FAIL.

Não gastar recursos executando junho-setembro.

Fazer autópsia.

Uma mudança posterior de estratégia exige:

NOVO Mn.

==================================================
12. STAGE 1 INCONCLUSIVE
========================

Se houver:

bug técnico;

dados incompletos;

audit failure;

evidência de execução insuficiente;

classificar:

INCONCLUSIVE.

Não interpretar como falha econômica.

Corrigir tecnicamente sem mudar semântica quando permitido.

==================================================
13. STAGE 2 — EXTENSÃO
======================

Somente se Stage 1 PASS:

continuar exatamente a mesma estratégia congelada.

EXTENSION_START=
2026-06-01T00:00:00Z

EXTENSION_END_EXCLUSIVE=
2026-09-05T23:59:59.783644+00:00

ou o cutoff físico canônico exato já registrado no repo.

==================================================
14. IMPORTANTE — CONTINUIDADE DE CAPITAL
========================================

Stage 2 NÃO deve reiniciar:

Operating=100
Reserve=10.

O objetivo é testar crescimento real contínuo.

Portanto Stage 2 deve começar exatamente com:

Operating Bank final do Stage 1

Reserve final do Stage 1

open queues/positions

dust

ledger

capital attribution

e demais estados físicos válidos

do fim de maio.

É uma EXTENSÃO DO MESMO REPLAY.

Não um segundo backtest independente.

==================================================
15. SEM TUNING ENTRE STAGES
===========================

Hard rule:

NO_PARAMETER_CHANGE_BETWEEN_STAGE_1_AND_STAGE_2.

Se o OWNER decidir alterar alguma regra depois de ver Stage 1:

isso cria um NOVO Mn

e precisa começar novamente sua própria evidência.

==================================================
16. POR QUE FAZER ASSIM
=======================

Stage 1 serve como teste rápido de viabilidade.

Stage 2 testa se:

a máquina continua funcionando em regimes posteriores

sem termos usado esses dados para desenhá-la.

Isso reduz tempo de pesquisa e melhora a qualidade da evidência.

==================================================
17. PERFORMANCE
===============

O runner deve evitar processar junho-setembro no Stage 1.

Não carregar/traversar desnecessariamente trades posteriores ao cutoff Stage 1.

Criar tape/index prefixado fisicamente se isso reduzir significativamente runtime, desde que:

* evento/order semantics permaneçam idênticas;
* hashes/provenance sejam registrados;
* não haja reordenação;
* não haja perda de causalidade.

==================================================
18. GITHUB JOURNAL
==================

Registrar:

TEST_PLAN=TWO_STAGE

STAGE_1=
2026-01-01..2026-05-31

STAGE_2=
2026-06-01..canonical September cutoff

STAGE_2_STATUS=
SEALED_NOT_AUTHORIZED_UNLESS_STAGE1_PASS

Atualizar continuamente:

CURRENT_STATE

<MODEL>_JOURNAL

scoreboard

report.

==================================================
19. PRIMEIRA AÇÃO AGORA
=======================

Se M012 ou qualquer outro run superseded ainda estiver prestes a iniciar:

NÃO iniciar.

Preservar.

Registrar status.

Criar/preregister o novo modelo multi-queue correto.

Aplicar este TWO-STAGE TEST PLAN ao novo modelo.

==================================================
20. EXECUTION AUTHORITY
=======================

O OWNER autoriza:

preregistration
implementation
tests
review

e execução completa do:

STAGE 1 de cinco meses.

Não pedir nova autorização para iniciar Stage 1.

==================================================
21. AUTORIZAÇÃO DO STAGE 2
==========================

Se e somente se:

STAGE_1_DECISION=PASS_TO_EXTENSION

o sistema está autorizado a iniciar automaticamente Stage 2

SEM modificar a estratégia.

Se Stage 1 não passar:

não executar Stage 2.

==================================================
22. RETORNO AO OWNER
====================

Antes de iniciar:

MODEL_ID=

MODEL_HASH=

STAGE_1_START=

STAGE_1_END=

STAGE_1_CALENDAR_DAYS=

STAGE_2_SEALED_START=

STAGE_2_SEALED_END=

CAPITAL_MODE=COMPOUNDING

INITIAL_OPERATING=100

INITIAL_RESERVE=10

RESERVE_FUNDING=10%

MAX_OPERATING_QUEUES=3

MAX_ACTIVE_RESERVE_QUEUES=1

MAX_ACTIVE_RESERVE_SHARE=50%

MAX_LOCK=24h

STAGE_1_GATES=

IMPLEMENTATION_STATUS=

TEST_STATUS=

REVIEW_STATUS=

RUN_STATUS=

RUN_ID=

COMMIT=

HEAD_EQUALS_ORIGIN_MAIN=.

==================================================
REGRA FINAL
===========

NÃO precisamos gastar o custo de 8+ meses para descobrir uma falha evidente.

Primeiro:

5 MONTH REALITY TEST.

Se funcionar:

EXTEND THE SAME FROZEN MACHINE.

Sem tuning.

Sem reset de capital.

Sem reset da reserve.

Sem trocar parâmetros.

O motor deve provar primeiro que consegue:

CRESCER

SE AUTOFINANCIAR

CONSTRUIR RESERVA

E PERMANECER PRODUTIVO.

STAGE1_FIRST=YES.

FULL_EXTENSION_ONLY_AFTER_PASS=YES.
