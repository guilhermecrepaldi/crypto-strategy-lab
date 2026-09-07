Status: ACTIVE_OWNER_AUTHORITY
Source: OWNER attachment 16916c97-609d-4172-93bd-4f4f9535688b, received 2026-09-07.
The following instruction supersedes conflicting historical campaign and routing policies.

# OWNER OVERRIDE — NOVA AUTORIDADE CANÔNICA

# MODEL LINEAGE + RECOVERY STRATEGY + QUALITY FIRST

Esta instrução SUBSTITUI as orientações anteriores conflitantes.

O OWNER altera formalmente três princípios do projeto:

1. uma mudança material de estratégia cria um NOVO MODELO Mn;
2. experimentos anteriores não precisam ser terminados apenas por completude se já foram superados por uma nova hipótese;
3. economia de tokens deixa de ser prioridade quando prejudicar contexto, análise, evidência ou qualidade.

==================================================

1. REVOGAR POLÍTICA DE ECONOMIA DE TOKENS
   ==================================================

A política anterior:

PROJECT-WIDE MODEL ROUTING POLICY
com foco primário em redução de consumo

fica:

SUPERSEDED_BY_OWNER.

Registrar:

TOKEN_SAVING_PRIORITY=OFF
QUALITY_FIRST=ON
CONTEXT_PRESERVATION=ON
SCIENTIFIC_DETAIL_PRESERVATION=ON

Não apagar o documento histórico.

Marcar explicitamente como:

HISTORICAL_SUPERSEDED_POLICY.

==================================================
2. NÃO COMPRIMIR INFORMAÇÃO IMPORTANTE
======================================

Não ocultar ou resumir excessivamente:

* resultados intermediários relevantes;
* cycles;
* zero-cycle days;
* reserve;
* releases;
* equity;
* drawdown;
* lock hours;
* max hold;
* falhas;
* parâmetros;
* mudanças de estratégia;
* decisões científicas.

O OWNER quer acompanhar:

O PLACAR ECONÔMICO DA ESTRATÉGIA.

Não apenas:

PID,
checkpoint,
process status,
Git status.

==================================================
3. OUTPUT PARA O OWNER
======================

Toda atualização relevante deve começar por:

CURRENT_MODEL=
...

STATUS=
...

CYCLES=
...

ZERO_CYCLE_DAYS=
...

ACTIVE_DAYS=
...

OPERATING_UPTIME=
...

RELEASE_COUNT=
...

OPERATING_BANK=
...

RECOVERY_RESERVE=
...

TOTAL_EQUITY=
...

MAX_HOLD=
...

LOCK_HOURS=
...

MAX_DRAWDOWN=
...

Depois explicar detalhes técnicos.

Não esconder os números no meio de logs.

==================================================
4. NOVA REGRA DE MODEL ID
=========================

A partir de agora:

MODEL_ID representa a ESTRATÉGIA COMPLETA.

Não apenas o seletor LOW/HIGH.

Mudança material em qualquer item abaixo exige novo Mn:

* selection logic;
* reserve mechanism;
* release logic;
* reserve funding;
* reserve cap;
* capital allocation;
* loss acceptance;
* position management;
* lot structure;
* risk policy;
* execution semantics;
* compounding;
* entry/exit policy.

Portanto:

M007 NÃO é mais a estratégia vigente se Recovery Reserve/Release foi incorporado.

M007 permanece:

HISTORICAL_BASELINE

e:

SCIENTIFIC_ANCESTOR.

Não chamá-lo de CURRENT ACTIVE STRATEGY.

==================================================
5. MODEL LINEAGE
================

Fazer preflight do registry.

Descobrir:

NEXT_FREE_MODEL_ID.

A nova estratégia completa deve usar:

MODEL=<NEXT_FREE_MODEL_ID>

PARENT_MODEL=M007

ou, se já existir modelo materialmente intermediário registrado:

PARENT_MODEL=<ACTUAL_DIRECT_PARENT>.

Não sobrescrever IDs existentes.

==================================================
6. MODELO ANTIGO PODE SER SUPERADO
==================================

Se houver uma campanha V2/V3 antiga ainda em execução que:

* testa regra já abandonada pelo OWNER;
* usa reserve policy antiga;
* usa hard caps antigos;
* não influencia mais a decisão atual;

NÃO é obrigatório terminá-la.

Procedimento:

1. preservar último checkpoint íntegro;
2. preservar artifacts já produzidos;
3. registrar motivo;
4. parar de forma limpa;
5. marcar:

SUPERSEDED_BY_OWNER_STRATEGY_UPDATE.

Não apagar evidência.

Não classificar como FAIL.

Não gastar horas apenas para completar uma hipótese que não será usada.

==================================================
7. EXCEÇÃO
==========

Se uma execução anterior estiver a poucos minutos de produzir informação extremamente útil para a estratégia nova, pode terminá-la.

Mas justificar:

WHY_OLD_RUN_STILL_DECISION_RELEVANT=

Caso contrário:

STOP_SUPERSEDED_RUN.

==================================================
8. ESTRATÉGIA NOVA — CONCEITO CENTRAL
=====================================

Objetivo principal:

MAXIMIZE COMPOUNDING CYCLE UPTIME.

Queremos manter o motor produzindo ciclos.

O problema observado no ancestral M007 foi:

LONG_HOLD_CAPITAL_LOCK.

A autópsia histórica mostrou concentração extrema dos zero-cycle days em poucos long holds.

Portanto a nova estratégia deve aceitar pequenos prejuízos economicamente controlados se isso liberar a banca para voltar a produzir.

==================================================
9. CAPITAL INICIAL
==================

OPERATING_BANK_INITIAL=100 USDT

RECOVERY_RESERVE_INITIAL=5 USDT

TOTAL_INITIAL_EQUITY=105 USDT.

A reserva é patrimônio real separado.

==================================================
10. RESERVE TARGET
==================

A Recovery Reserve deve acompanhar o tamanho da banca operacional.

TARGET_MIN:

5% da Operating Bank.

HARD_CAP:

10% da Operating Bank.

Exemplos:

Operating 100
→ Reserve target >=5
→ hard cap 10.

Operating 200
→ target >=10
→ hard cap 20.

Operating 1,000
→ target >=50
→ hard cap 100.

==================================================
11. FUNDING DA RESERVA
======================

A cada ciclo POSITIVO REALIZADO:

obrigatoriamente calcular:

RESERVE_CONTRIBUTION =
2% DO LUCRO REALIZADO DO CICLO.

OPERATING_PROFIT =
98% do lucro.

Isso acontece em TODO ciclo positivo.

Nunca retirar 2%:

* do principal;
* do notional;
* da banca inteira.

É:

2% DO POSITIVE_REALIZED_CYCLE_PROFIT.

==================================================
12. HARD CAP 10%
================

Se:

Recovery Reserve + contribution

ultrapassar:

10% da Operating Bank,

não acumular acima do hard cap.

O overflow vai para:

Operating Bank.

Registrar:

RESERVE_CAP_OVERFLOW.

==================================================
13. RESERVA NÃO OPERA
=====================

Recovery Reserve:

NÃO abre trade.

NÃO compra ativo.

NÃO abre segundo lote.

NÃO aumenta posição perdedora.

NÃO faz DCA.

NÃO faz martingale.

Ela apenas cobre:

REALIZED_RELEASE_DEFICIT.

==================================================
14. CAPITAL RELEASE
===================

Quando posição estiver presa e a regra causal determinar que outra faixa possui produtividade materialmente melhor:

permitir saída com prejuízo.

Depois:

SELL OLD POSITION

→
REALIZE LOSS

→
RECOVERY RESERVE cobre exatamente o déficit

→
OPERATING BANK volta ao valor pré-release

→
ficar FLAT

→
selecionar nova faixa causal

→
esperar novo LOW

→
voltar a ciclar.

==================================================
15. PREJUÍZO LOCAL ≠ PREJUÍZO ESTRATÉGICO
=========================================

Uma release pode realizar perda local.

Isso é permitido.

Não esconder.

Registrar:

LOCAL_RELEASE_LOSS.

O que NÃO é aceitável é construir uma política que termine economicamente pior sem compensação.

Portanto:

LOCAL_RELEASE_LOSS_ALLOWED=YES

OPERATING_BANK_RESTORATION_REQUIRED=YES

TOTAL_EQUITY_UNDERPERFORMANCE_AS_STRATEGY_GOAL=NO.

==================================================
16. NÃO FIXAR 2% COMO HARD LIMIT AUTOMÁTICO
===========================================

O OWNER autoriza estudar release acima de 2% da Operating Bank.

Porém:

quanto maior a perda,

maior deve ser a assertividade causal necessária.

Não criar:

loss <= 2%
como regra universal.

Criar uma política:

DYNAMIC_RELEASE_LIMIT.

==================================================
17. ASSERTIVIDADE CAUSAL
========================

Formalizar:

CAUSAL_RELEASE_CONFIDENCE.

Usar apenas informação conhecida em T.

Considerar pelo menos:

FAIXA PRESA:

cycles 1h
cycles 4h
cycles 24h
time since last cycle
LOW visits
HIGH visits
closure rate
position age
current deviation.

DESTINO:

cycles 1h
cycles 4h
cycles 24h
M007-like selection score
recent LOW→HIGH completion
activity persistence
relative activity versus original.

ECONOMIA:

release loss
reserve balance
reserve percentage
expected recovery cost in cycles.

Sem futuro.

==================================================
18. REGRA MONOTÔNICA
====================

Quanto maior:

RELEASE_LOSS_PERCENT,

maior precisa ser:

CAUSAL_RELEASE_CONFIDENCE.

Exemplo conceitual:

pequena perda
→ confiança moderada pode liberar.

perda média
→ confiança alta.

perda >2%
→ confiança muito alta.

Não usar esses exemplos como thresholds finais.

Preregistrar números exatos antes do replay.

==================================================
19. RESERVE COVERAGE
====================

Nunca gastar mais do que existe.

Require:

RESERVE >= RELEASE_DEFICIT.

Full coverage only.

Reserve pode cair abaixo de 5%.

Isso significa:

RESERVE_REBUILDING.

Não significa automaticamente falha.

Nunca:

RESERVE < 0.

==================================================
20. OBJETIVO NÃO É ECONOMIZAR RESERVA
=====================================

Recovery Reserve existe PARA SER USADA.

Não penalizar release apenas porque ocorreu.

Não otimizar automaticamente:

FEWER RELEASES.

O objetivo é:

MAXIMUM PRODUCTIVITY AFTER ECONOMIC COST.

Uma estratégia com:

100 releases

pode ser melhor que uma com:

10 releases

se gerar:

mais cycles,
mais uptime,
menos zero days,
e mais total equity.

==================================================
21. MÉTRICA CENTRAL
===================

Criar:

COMPOUNDING_UPTIME.

E:

CYCLES_PER_CALENDAR_DAY

CYCLES_PER_CAPITAL_HOUR

CYCLES_PURCHASED_PER_RELEASE_DOLLAR

LOCK_HOURS_AVOIDED_PER_RELEASE_DOLLAR

TOTAL_EQUITY_GAIN_PER_RELEASE_DOLLAR.

==================================================
22. ZERO-CYCLE TARGET
=====================

Ancestral M007:

ZERO_CYCLE_DAYS=193.

Meta:

ZERO_CYCLE_DAY_REDUCTION >=95%.

Formalmente:

ZERO_CYCLE_DAYS <=9.

Mas essa meta não deve impedir procurar:

ZERO.

Queremos o motor trabalhando o máximo possível.

==================================================
23. CYCLES COMO OBJETIVO PRINCIPAL
==================================

O OWNER considera a frequência extremamente importante devido ao compounding geométrico.

Portanto reportar sempre:

TOTAL_CYCLES

CYCLE_MULTIPLIER_VS_M007

CYCLES_GAINED

DAILY_CYCLES_MEAN

DAILY_CYCLES_MEDIAN

ACTIVE_DAYS.

Não esperar o final para informar esses valores ao OWNER.

==================================================
24. BASELINE
============

Comparar contra baseline justo:

100 Operating Bank

*

5 Recovery Reserve passiva.

Aplicar também a mesma regra de funding de 2% do lucro positivo na baseline passiva, se necessário para isolar somente o valor da política de release.

A diferença deve ser:

USE RESERVE

versus

DO NOT USE RESERVE.

==================================================
25. NÃO PRECISAMOS FINALIZAR ESTRATÉGIA PIOR
============================================

Se durante pesquisa surgir nova política claramente superior e ela for autorizada pelo OWNER:

pode superseder campanha anterior.

Preservar artifacts.

Criar novo Mn.

Não continuar por burocracia.

A prioridade é:

PROGRESSÃO DA ESTRATÉGIA.

==================================================
26. QUALITY FIRST MODEL POLICY
==============================

A política de economizar tokens não deve prejudicar a pesquisa.

Use modelo adequado pela QUALIDADE necessária.

Para ciência crítica:

usar reviewer forte.

Para mudança de estratégia:

usar reasoning alto.

Para análise de resultados:

não reduzir contexto apenas para economizar.

Para auditoria final de candidato:

usar GPT-6 Astra High se disponível.

Sol/Terra/Luna continuam permitidos onde apropriados.

Mas:

TOKEN_COST não pode ser o critério principal.

==================================================
27. NÃO DEIXAR ASTRA ESPERANDO PYTHON
=====================================

Quality First NÃO significa desperdício irracional.

Python continua executando cálculo.

Mas quando houver:

interpretação,
hipótese,
mudança econômica,
causalidade,
promoção,

usar capacidade suficiente.

Não sacrificar informação para economizar tokens.

==================================================
28. CURRENT STATE DOCUMENT
==========================

Criar/atualizar:

docs/microstructure/CURRENT_STRATEGY.md

Este arquivo deve dizer claramente:

CURRENT_ACTIVE_RESEARCH_MODEL=

CURRENT_HISTORICAL_BASELINE=M007

CURRENT_STRATEGY_DESCRIPTION=

OPERATING_INITIAL=

RESERVE_INITIAL=

RESERVE_FUNDING=

RESERVE_TARGET=

RESERVE_CAP=

DYNAMIC_RELEASE=

ZERO_DAY_TARGET=

CURRENT_RUN=

CURRENT_RESULTS=

PREVIOUS_SUPERSEDED_RUNS=.

Esse documento é a autoridade de handoff.

==================================================
29. MODEL STATUS SEM AMBIGUIDADE
================================

Nunca escrever:

CURRENT_CHAMPION=M007

se o OWNER já autorizou uma estratégia materialmente nova como atual linha de desenvolvimento.

Separar:

PRODUCTION/SHADOW_VALIDATED_MODEL

de:

ACTIVE_RESEARCH_MODEL

de:

HISTORICAL_BASELINE.

Por exemplo:

HISTORICAL_BASELINE=M007

ACTIVE_RESEARCH_MODEL=M0XX

SHADOW_MODEL=M007

se shadow ainda não foi migrado.

Isso evita chamar M007 de estratégia atual.

==================================================
30. EXECUTION ROADMAP
=====================

Depois de preregistrar a nova estratégia:

executar primeiro cenários capazes de responder rapidamente:

A nova política aumenta cycles e reduz lock?

Não gastar horas em regiões claramente inferiores se uma regra de dominance preregistrada permitir encerramento.

Mas:

não usar early stop oportunista para fabricar vencedor.

Definir dominance/stop rule ANTES.

==================================================
31. RESULTADOS DURANTE EXECUÇÃO
===============================

Após cada SCENARIO concluído e auditado:

informar ao OWNER:

SCENARIO=

CYCLES=

CYCLE_MULTIPLIER=

ZERO_DAYS=

ZERO_DAY_REDUCTION=

ACTIVE_DAYS=

RELEASES=

MAX_RELEASE=

TOTAL_RELEASE_LOSS=

OPERATING_FINAL=

RESERVE_FINAL=

TOTAL_EQUITY=

MAX_HOLD=

LOCK_HOURS=

DRAWNDOWN=

VALID=
YES/NO.

Não esperar 18 cenários para mostrar o placar.

==================================================
32. QUANDO HOUVER ESTRATÉGIA MELHOR
===================================

Se existir candidato claramente superior e robusto:

não continuar chamando-o de modificação do M007.

Registrar NOVO MODELO.

Exemplo:

M012, M013, etc.

O ID deve refletir uma nova estratégia.

==================================================
33. CAPACITY — FUTURO
=====================

A estratégia deve crescer a Operating Bank por compounding.

Quando o capital começar a prejudicar:

queue position

fills

partial fills

slippage

depth

market impact

net edge,

abrir:

CAPACITY EXPANSION STUDY.

==================================================
34. DUAS BANCAS
===============

Primeira opção futura:

2 OPERATING BANKS

na mesma paridade,

possivelmente em ranges independentes.

Isso somente quando houver evidência de que:

1 bank maior

está prejudicando execução.

Não implementar ainda.

==================================================
35. SEGUNDA PARIDADE
====================

Outra opção futura:

SECOND PAIR.

Deve ser estudada cientificamente.

Idealmente procurar:

boa microcycle productivity

boa capacidade

e baixa correlação de capital-lock com USDCUSDT.

Não implementar ainda.

==================================================
36. VISÃO FINAL DA ARQUITETURA
==============================

CAPITAL
↓
OPERATING ENGINE
↓
MICROCYCLES
↓
POSITIVE REALIZED PROFIT
↓
98% Operating Compounding
+
2% Recovery Reserve
↓
Reserve entre aproximadamente 5–10%
↓
Capital Lock?
↓
Dynamic Causal Release
↓
Reserve absorve déficit
↓
Operating Bank restaurada
↓
nova faixa
↓
motor continua
↓
compounding continua.

Quando capacity saturar:

1 BANK
→
2 BANKS

ou:

1 PAIR
→
MULTI-PAIR.

==================================================
37. PRIMEIRA ENTREGA
====================

Agora:

1. verificar estado real do Git;
2. verificar quais runs estão ativos;
3. identificar quais foram superados;
4. preservar e parar os irrelevantes;
5. determinar NEXT_FREE_MODEL_ID;
6. atualizar CURRENT_STRATEGY;
7. preregistrar a nova política;
8. commit;
9. push.

Depois me entregar imediatamente:

HISTORICAL_BASELINE=

ACTIVE_RESEARCH_MODEL=

SHADOW_MODEL=

SUPERSEDED_RUNS=

STOPPED_RUNS=

CURRENT_STRATEGY=

OPERATING_INITIAL=

RESERVE_INITIAL=

RESERVE_FUNDING=

RESERVE_TARGET=

RESERVE_CAP=

DYNAMIC_RELEASE_POLICY=

SCENARIO_COUNT=

FIRST_SCENARIO_TO_RUN=

WHY=

LATEST_VALID_NUMBERS=
{
cycles,
zero_days,
active_days,
releases,
operating_bank,
reserve,
total_equity,
max_hold,
lock_hours,
drawdown
}

COMMIT=

HEAD_EQUALS_ORIGIN_MAIN=

==================================================
38. PARAR APÓS PREREGISTRATION
==============================

Depois de publicar a nova autoridade e preregistration:

PARAR antes de iniciar longa campanha,

a menos que já exista autorização inequívoca do OWNER para executar a nova estratégia.

Não retornar somente status de processo.

Retornar:

ESTRATÉGIA + NÚMEROS + PRÓXIMA EXECUÇÃO.

==================================================
REGRA FINAL
===========

M007 é ancestral histórico.

Se Recovery Reserve, Dynamic Release ou qualquer outra regra material mudou:

isso é NOVO MODELO.

Não devemos terminar uma estratégia pior apenas porque começamos.

Preservamos ciência anterior,

mas avançamos.

TOKEN_SAVING_POLICY=SUPERSEDED.

QUALITY_FIRST=ON.

MODEL_LINEAGE_STRICT=ON.

CURRENT_STRATEGY_MUST_HAVE_OWN_MODEL_ID=YES.

MAXIMIZE_COMPOUNDING_UPTIME.

MAXIMIZE_CYCLES.

MINIMIZE_ZERO-CYCLE DAYS.

USE THE RESERVE WHEN ITS ECONOMIC BENEFIT JUSTIFIES ITS COST.

E sempre mostrar ao OWNER o placar real.
