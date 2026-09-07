# OWNER DIRECTIVE — B10 BINANCE REALITY GAUNTLET

# OBJETIVO: TENTAR DERRUBAR O B10 NO AMBIENTE MAIS REALISTA E DIFÍCIL POSSÍVEL

A partir deste milestone existe apenas UM objeto de pesquisa:

RRV2_H1_B10

Não comparar estratégias.

Não otimizar modelos.

Não executar M011.

Não procurar uma estratégia melhor.

Não modificar o B10 para melhorar seus resultados.

A missão é:

PEGAR O B10 HISTÓRICO VENCEDOR
E TENTAR FALSIFICÁ-LO SOB EXECUÇÃO BINANCE SPOT REALISTA.

QUALITY_FIRST=ON.

TOKEN_SAVING_PRIORITY=OFF.

Use contexto suficiente e reviewers fortes quando necessário.

==================================================

1. PRINCÍPIO CIENTÍFICO
   ==================================================

Não tente provar que B10 funciona.

Tente provar que B10 NÃO funcionaria.

Todo pressuposto favorável deve ser removido quando houver evidência oficial melhor.

Regra:

PRICE_TOUCH != FILL.

TRADE_AT_LEVEL != OUR_FILL.

HISTORICAL_PRICE_PATH_PROFIT != EXECUTABLE_PROFIT.

Se uma hipótese de execução estiver incerta:

não escolher silenciosamente a hipótese favorável.

Classificar:

OBSERVED
OFFICIAL_RULE
MEASURED
INFERRED
PARAMETERIZED
UNKNOWN.

==================================================
2. B10 DEVE FICAR CONGELADO
===========================

Estratégia histórica:

RRV2_H1_B10_F0

artifact identity:

097abdab8225038b091cb721bdd36bedb8a636c94bed1c87120adc0c9e10953a

Antes de qualquer hardening:

reconciliar artifact e hashes.

Referência histórica esperada:

OPERATING_INITIAL=100 USDT
RESERVE_INITIAL=5 USDT
TOTAL_INITIAL=105 USDT

RESERVE_SKIM=
2% do positive realized cycle profit

LOCK_AGE=
1 hour

MAX_RELEASE_LOSS=
10 basis points
===============

0.10%

RESERVE_FLOOR=
0

CYCLES=
3,580,880

ZERO_CYCLE_DAYS=
3

ACTIVE_DAYS=
245/248

RELEASES=
156

MAX_HOLD=
26h

LOCK_HOURS_GT24=
4h

MAX_DRAWDOWN=
~0.16636%.

Não usar esses números por confiança.

Reconciliar fisicamente.

==================================================
3. NÃO ALTERAR A LÓGICA DO B10
==============================

Manter:

selector ancestry;
LOW/HIGH logic;
one serial operating lot;
H1;
B10;
2% reserve skim;
release eligibility;
original-range activity test;
destination activity tests;
full reserve coverage;
FLAT after release;
wait for new LOW;
no DCA;
no martingale;
no second bank;
no second pair.

O que muda é:

EXECUTION ENVIRONMENT.

Não:

STRATEGY.

Portanto NÃO criar um novo Mn apenas porque estamos mudando o simulador.

Registrar:

STRATEGY=B10_FROZEN

EXECUTION_PROFILE=BINANCE_REALITY_V1.

Se posteriormente a lógica B10 mudar:

aí sim criar novo Mn.

==================================================
4. PRIMEIRO: PESQUISA BINANCE OFICIAL
=====================================

Antes de implementar assumptions de execução:

pesquisar as regras SPOT oficiais da Binance.

Prioridade absoluta de fonte:

1. developers.binance.com
2. github.com/binance/binance-spot-api-docs
3. data.binance.vision
4. Binance official announcements / changelog
5. endpoints oficiais Binance.

Não usar como autoridade primária:

blogs;
Reddit;
StackOverflow;
Medium;
artigos de terceiros;
sites de exchange comparativa.

Podem servir apenas para encontrar uma questão,
nunca para determinar uma regra.

==================================================
5. BINANCE RULE MANIFEST
========================

Criar:

docs/binance/BINANCE_USDCUSDT_EXECUTION_AUTHORITY.md

e:

artifacts/binance/usdcusdt-execution-rules.json.

Registrar com fonte oficial e data:

symbol status

baseAsset

quoteAsset

PRICE_FILTER:

* minPrice
* maxPrice
* tickSize

LOT_SIZE:

* minQty
* maxQty
* stepSize

MARKET_LOT_SIZE

MIN_NOTIONAL / NOTIONAL

PERCENT_PRICE

PERCENT_PRICE_BY_SIDE

MAX_NUM_ORDERS

MAX_NUM_ALGO_ORDERS

ICEBERG_PARTS se relevante

order types

timeInForce

rate limits

cancel/replace semantics

order amend semantics se relevante

self-trade prevention se relevante

quantity rounding

price rounding

commission semantics

maker/taker classification

trade/aggTrade semantics

isBuyerMaker semantics

bookTicker semantics

depth semantics

sequence/update IDs

WebSocket ordering

snapshot + diff-depth reconstruction procedure

timestamp precision

connection limits

reconnect requirements

data gaps.

==================================================
6. REGRAS HISTÓRICAS
====================

CRÍTICO:

Não aplicar regra atual retroativamente ao período de 2026 sem evidência.

Período:

2026-01-01
até
2026-09-05 physical cutoff canônico.

Procurar especificamente evidência oficial histórica para:

USDCUSDT tickSize transitions;

stepSize transitions;

minNotional changes;

symbol filter changes;

fee promotions;

zero-fee campaigns;

maker promotions;

stablecoin-pair fee rules;

maintenance;

symbol status interruptions;

API/market-data changes relevantes.

Criar timeline:

BINANCE_RULE_TIMELINE.

Cada regra:

START=
END=
VALUE=
SOURCE=
EVIDENCE_CLASS=.

Se uma regra histórica não puder ser provada:

HISTORICAL_RULE=UNKNOWN.

NÃO projetar a regra atual para trás sem marcação explícita.

==================================================
7. FEE É PRIORIDADE CRÍTICA
===========================

A campanha B10 histórica foi price-path com fee zero.

Isso precisa ser atacado.

Pesquisar Binance oficial por:

historical USDCUSDT trading-fee promotions;

maker fee;

taker fee;

zero-fee stablecoin campaigns;

VIP rules;

BNB fee discount;

special commissions;

tax commissions se aplicável.

Não usar taxa genérica arbitrária como "a taxa da Binance".

Se a taxa exata histórica não puder ser demonstrada:

criar:

FEE_EVIDENCE=UNKNOWN_HISTORICAL_EXACT

e executar uma matriz de sensibilidades baseada somente em ranges oficiais defensáveis.

Exemplo de classes:

OFFICIAL_BEST_CASE
OFFICIAL_PLAUSIBLE
CONSERVATIVE
ADVERSARIAL_PLAUSIBLE.

Não escolher os valores antes da pesquisa.

==================================================
8. ACCOUNT-SPECIFIC COMMISSION
==============================

A documentação Binance possui commission endpoints autenticados.

Não pedir ou usar API key privada nesta fase.

Não acessar conta.

Não enviar ordem.

Se commission exata depender da conta:

marcar:

ACCOUNT_COMMISSION=UNKNOWN_NOT_AUTHORIZED.

Simulação deverá separar isso claramente.

==================================================
9. DADOS HISTÓRICOS OFICIAIS
============================

Baixar/reconciliar os melhores dados públicos oficiais Binance disponíveis para USDCUSDT.

Preferir:

raw trades

e/ou

aggTrades.

Não usar candle como tape principal se trade-level estiver disponível.

Verificar:

arquivo;
data;
checksum;
tamanho;
continuidade;
primeiro/último timestamp;
duplicatas;
gaps;
event ordering.

Preservar arquivos originais imutáveis.

Criar manifest SHA256.

==================================================
10. AGGRESSOR SIDE
==================

Usar somente semântica oficial Binance para:

isBuyerMaker

maker/taker side.

Não inferir pela memória.

Documentar exatamente:

quando um trade histórico pode consumir uma BUY LIMIT maker nossa;

quando pode consumir uma SELL LIMIT maker nossa.

Criar fixtures.

==================================================
11. HISTORICAL L2
=================

Investigar se existe uma fonte OFICIAL Binance com L2/order-book histórico suficiente para o período.

Se existir:

usar.

Se NÃO existir:

declarar:

HISTORICAL_L2=UNAVAILABLE_OFFICIALLY

ou classificação equivalente.

NÃO reconstruir ficticiamente um book exato a partir de trades.

NÃO dizer que conhece queue ahead.

==================================================
12. NÃO BLOQUEAR POR FALTA DE L2
================================

Se L2 histórico completo não existir:

continuar com um:

TRADE-FLOW EXECUTION ENVELOPE.

Separar claramente:

observado

de

parametrizado.

A simulação histórica deve ser rigorosa e conservadora.

==================================================
13. NOVO ESTADO DE ORDENS
=========================

O replay realista deve possuir ordens reais virtuais.

State machine mínima:

FLAT

BUY_SUBMITTING

BUY_WORKING

BUY_PARTIAL

LONG

SELL_SUBMITTING

SELL_WORKING

SELL_PARTIAL

CYCLE_COMPLETE

RELEASE_SUBMITTING

RELEASE_PARTIAL

RELEASE_COMPLETE

CANCEL_PENDING.

Não transformar partial em full.

==================================================
14. ORDER ACTIVATION LATENCY
============================

Uma ordem não existe no mercado no timestamp do signal.

Modelar:

decision latency

network outbound

exchange processing

ACK

book activation.

A ordem só pode receber fill DEPOIS de:

ORDER_ACTIVE_TIMESTAMP.

Trades anteriores ou no mesmo boundary não podem preencher retroativamente a ordem.

==================================================
15. LATENCY RESEARCH
====================

Medir no ambiente atual, usando somente endpoints públicos:

REST RTT

WebSocket receive delay

event_timestamp → local_receive_timestamp

jitter

disconnect/reconnect.

Não confundir isso com order-ack real.

Para latência de ordem não observável sem conta:

PARAMETERIZED.

Usar distribuição conservadora baseada em:

medição pública

*

limites tecnicamente defensáveis.

Rodar pelo menos:

measured-like

conservative

stress.

Não usar 0 ms.

==================================================
16. NORMAL BUY
==============

B10 quer comprar no LOW.

No reality harness:

não marcar BUY_FILLED apenas porque:

price == LOW.

Exigir evidência de fluxo compatível APÓS nossa ordem estar ativa.

Considerar:

aggressor side

trade quantity

queue assumption

our remaining quantity.

==================================================
17. NORMAL SELL
===============

Igual para HIGH.

Não marcar ciclo completo até:

FULL BUY FILLED

e posteriormente:

FULL SELL FILLED.

Se HIGH for tocado antes do BUY terminar:

isso não é ciclo completo.

==================================================
18. QUEUE AHEAD
===============

Sem L2 histórico exato:

QUEUE_AHEAD é incerto.

Não escolher queue=0 como cenário principal.

Construir envelopes conservadores.

Calibrar os envelopes usando L2 atual coletado oficialmente do mesmo par.

Exemplos conceituais:

LOW_QUEUE
MEDIAN_QUEUE
P90_QUEUE
P99_QUEUE
ADVERSARIAL_PLAUSIBLE_QUEUE.

Valores devem vir da coleta.

Não inventar.

==================================================
19. LIVE PUBLIC L2 CALIBRATION
==============================

Criar um collector PUBLIC-ONLY para:

USDCUSDT trades

bookTicker

depth snapshot

diff depth.

Sem API key.

Sem ordens.

Sem account endpoint.

Reconstruir order book local seguindo EXATAMENTE a documentação Binance oficial:

snapshot

lastUpdateId

U/u sequencing

gap detection

resnapshot.

Capturar dados atuais suficientes para medir:

spread

depth at best

depth 1 tick away

queue/depth distributions

trade intensity

BBO residence time

book churn.

Isso é calibration evidence.

Não é historical 2026 L2.

==================================================
20. PRICE TOUCH RETENTION FUNNEL
================================

Para cada oportunidade original B10:

classificar progressivamente:

PRICE_PATH_OPPORTUNITY

TRADE_AT_PRICE

COMPATIBLE_AGGRESSOR_FLOW

ORDER_ACTIVE_IN_TIME

QUEUE_CLEARED

BUY_PARTIAL

BUY_FULL

SELL_ORDER_ACTIVE

SELL_QUEUE_CLEARED

SELL_PARTIAL

SELL_FULL

GROSS_CYCLE_COMPLETE

NET_POSITIVE_CYCLE.

==================================================
21. REALITY RETENTION
=====================

Criar:

PRICE_PATH_REFERENCE_CYCLES=
3,580,880.

REAL_EXECUTION_CANDIDATE_CYCLES=
X.

REALITY_RETENTION_RATIO=
X / 3,580,880.

Não tentar proteger esse número.

Se der:

1%

reportar 1%.

Se der:

0.01%

reportar 0.01%.

==================================================
22. FIXED NOTIONAL = RÉGUA PRINCIPAL
====================================

O resultado astronômico de compounding NÃO será a principal régua desta campanha.

Primary execution ruler:

FIXED_NOTIONAL_100_USDT.

Cada nova posição:

máximo aproximadamente 100 USDT,

respeitando Binance quantity filters e rounding.

Lucros não fazem o notional automaticamente explodir.

==================================================
23. LEDGER REALISTA
===================

Ainda manter:

operating bank

reserve.

Initial:

Operating = 100
Reserve = 5.

A cada ciclo líquido positivo:

2% do REALIZED NET PROFIT
vai para a reserva.

Não usar lucro bruto.

NET PROFIT deve incluir todos os custos modelados.

==================================================
24. RESERVA
===========

A pergunta agora é:

COM US$100 FIXOS,
OS 2% DO LUCRO REAL CONSEGUEM FINANCIAR OS RELEASES?

Reportar:

RESERVE_INITIAL

RESERVE_CONTRIBUTIONS

RESERVE_CONSUMPTION

RESERVE_MIN

RESERVE_FINAL

RESERVE_DEPLETION_EVENTS

RELEASE_BLOCKED_BY_RESERVE

RESERVE_COVERAGE_RATIO.

Esse teste é mais importante que o capital exponencial.

==================================================
25. QUANTITY / DUST
===================

Aplicar regras Binance reais:

stepSize

minQty

maxQty

notional.

ROUND_DOWN quando exigido pela semântica.

Preservar dust.

Dust não pode magicamente entrar no próximo ciclo.

==================================================
26. ORDER REJECTIONS
====================

Simular rejeição quando a ordem viola:

PRICE_FILTER

LOT_SIZE

MIN_NOTIONAL / NOTIONAL

PERCENT_PRICE_BY_SIDE se aplicável

outros filtros historicamente comprovados.

Registrar:

ORDER_REJECTION_COUNT.

==================================================
27. MAKER/Taker
===============

Não classificar toda ordem como maker automaticamente.

Normal LOW/HIGH:

tentar modelar limit maker.

Se ordem cruzaria o book:

comportamento deve seguir regras oficiais.

Post-only/limit-maker somente se essa for a execução escolhida e suportada.

Registrar claramente.

==================================================
28. RELEASE — MAIOR STRESS
==========================

O release B10 original usa preço histórico teórico.

No Reality Harness isso NÃO basta.

Ao disparar release:

precisamos sair da posição.

Simular execução agressiva realista.

Preferência para estudo:

MARKETABLE LIMIT / MARKET-LIKE LIQUIDATION

conforme ordem Spot oficial adequada.

Preço real da release deve considerar:

best bid

available depth

latency

slippage

partial execution.

Se não houver L2 histórico:

usar envelope conservador calibrado por L2 atual.

==================================================
29. NÃO TRUNCAR RELEASE EM 10 BPS
=================================

10 bps é trigger/cap teórico do B10.

Se a decisão dispara quando perda observada é:

8 bps,

mas execução realista gera:

11.4 bps,

registrar:

ACTUAL_RELEASE_LOSS=11.4 bps.

Não fingir 10.

Isso é essencial para falsificação.

==================================================
30. RELEASE FAILURE
===================

Simular possibilidade de:

partial release

delayed release

price moving during release

release not fully filled.

Enquanto houver inventory:

capital continua ocupado.

Não restaurar Operating Bank antes do fill real correspondente.

==================================================
31. RELEASE RESERVE TRANSFER
============================

Reserva só cobre:

REALIZED EXECUTED DEFICIT.

Não déficit estimado no signal.

Se release parcial:

transferir somente conforme ledger executado

ou aguardar atomic settlement conforme implementação financeira explicitamente definida.

Não criar dinheiro.

==================================================
32. CANCEL / REPLACE
====================

Quando FLAT selector mudar a faixa:

ordem BUY anterior pode precisar ser cancelada.

Cancel não é instantâneo.

Modelar:

cancel requested

cancel pending

fills during cancellation race

new order submission.

Não permitir duas ordens incompatíveis por conveniência.

==================================================
33. SERIAL LOT INVARIANT
========================

B10 continua:

ONE SERIAL LOT.

Não contar múltiplos ciclos paralelos.

Se ordem/posição está parcialmente aberta:

não começar novo lote completo independente.

==================================================
34. RATE LIMITS
===============

Aplicar rate limits oficiais relevantes.

Considerar:

new order count

cancel

replace

REST/WebSocket limits

connection limits.

Se a estratégia geraria mensagens acima das regras:

registrar.

Não assumir que 3.58M ciclos podem ser executados operacionalmente sem verificar order-message load.

==================================================
35. OUTAGES / GAPS
==================

Se dados históricos oficiais mostram gaps:

não preencher silenciosamente.

Classificar.

Durante gap:

fail closed.

No live calibration:

detectar websocket discontinuity.

Rebuild book.

==================================================
36. TEMPORAL ORDERING
=====================

Preservar causalidade estrita.

Nenhum:

future trade

future volume

future book

future high

pode decidir:

entry

fill

release

cancel

reselection.

Equal timestamps devem obedecer ordem canônica comprovada.

==================================================
37. FEES NO CICLO
=================

Calcular:

GROSS_PNL

BUY_COMMISSION

SELL_COMMISSION

SPREAD_COST

SLIPPAGE

OTHER_MODELED_COST

NET_PNL.

Um ciclo executado com:

NET_PNL <= 0

fica:

EXECUTED_NONPROFITABLE_CYCLE.

Não contabilizá-lo como economicamente productive cycle.

Reportar separado.

==================================================
38. GROSS VS ECONOMIC CYCLES
============================

Precisamos de dois números:

FULLY_FILLED_CYCLES

e

NET_POSITIVE_FULLY_FILLED_CYCLES.

O segundo é a métrica econômica principal.

==================================================
39. STRESS PROFILES
===================

Depois de obter fatos oficiais e calibration L2:

congelar ANTES dos resultados pelo menos estes profiles:

A. OBSERVED_BEST_SUPPORTED

Usa a melhor interpretação ainda sustentada por evidência.

B. REALISTIC_CONSERVATIVE

Nossa melhor aproximação prudente de execução real.

C. ADVERSARIAL_PLAUSIBLE

Condições difíceis, mas que poderiam de fato ocorrer.

D. PEG_STRESS

Spread/depth/latency/release deteriorados em regime de stablecoin stress.

Não criar cenário impossível apenas para matar a estratégia.

==================================================
40. NÃO TUNAR O B10 ENTRE PROFILES
==================================

Todos os profiles usam:

MESMO B10.

Nenhum threshold muda.

Nenhuma regra de release muda.

Nenhum H muda.

Nenhum B muda.

Nenhum selector muda.

==================================================
41. PRIMARY QUESTIONS
=====================

Responder:

Q1.
Dos 3,580,880 price-path cycles,
quantos sobrevivem como full fills?

Q2.
Quantos continuam NET POSITIVE?

Q3.
Qual PnL líquido usando notional fixo de 100 USDT?

Q4.
A reserva de 5 + 2% net profits consegue financiar as releases?

Q5.
Quantas releases seriam realmente executadas perto do custo teórico?

Q6.
Quantas passam de 10 bps depois de spread/slippage/latency?

Q7.
Quantos zero-cycle days retornam?

Q8.
Qual max hold realista?

Q9.
Quanto lock >24h reaparece?

Q10.
O B10 ainda vale a pena?

==================================================
42. SCOREBOARD OBRIGATÓRIO
==========================

Para cada profile:

PRICE_PATH_REFERENCE_CYCLES=3580880

FULLY_FILLED_CYCLES=

REALITY_RETENTION_RATIO=

NET_POSITIVE_CYCLES=

ECONOMIC_RETENTION_RATIO=

ZERO_CYCLE_DAYS=

ACTIVE_DAYS=

AVG_CYCLES_DAY=

MEDIAN_CYCLES_DAY=

BUY_FULL_FILL_RATE=

SELL_FULL_FILL_RATE=

PARTIAL_FILL_RATE=

MISSED_BY_LATENCY=

MISSED_BY_QUEUE=

MISSED_BY_FILTER=

MISSED_BY_FEE=

GROSS_PNL_FIXED_100=

TOTAL_FEES=

TOTAL_SLIPPAGE=

NET_PNL_FIXED_100=

NET_EDGE_PER_COMPLETED_CYCLE=

RELEASE_SIGNALS=

RELEASE_FILLED=

RELEASE_PARTIAL=

THEORETICAL_RELEASE_LOSS=

EXECUTED_RELEASE_LOSS=

RELEASES_ACTUAL_GT10BPS=

RESERVE_INITIAL=5

RESERVE_FUNDING=

RESERVE_CONSUMPTION=

RESERVE_MIN=

RESERVE_FINAL=

RESERVE_DEPLETION_EVENTS=

MAX_HOLD=

LOCK_HOURS_GT24=

MAX_DRAWDOWN=

VERDICT=.

==================================================
43. VERDICT CLASSES
===================

Não usar só PASS/FAIL.

Classificar:

A. DESTROYED

Edge realista <=0
ou
execução destrói o mecanismo central.

B. SEVERELY_DEGRADED_BUT_POSITIVE

Perde enorme quantidade de ciclos,
mas conserva edge líquido positivo.

C. SURVIVES_REALISTIC_CONSERVATIVE

Edge, reserve e continuidade continuam fortes no profile conservador.

D. SURVIVES_ADVERSARIAL_PLAUSIBLE

Resultado extraordinariamente robusto.

E. INCONCLUSIVE_EXECUTION_DATA

Ausência de evidência impede conclusão.

==================================================
44. NÃO USAR CAPITAL 1E128 COMO PROVA
=====================================

Não destacar como evidência:

1e128 USDT

ou outros valores inviáveis.

Pode manter em appendix como:

PRICE_PATH_COMPOUNDING_ARTIFACT.

Primary:

FIXED_NOTIONAL_100.

==================================================
45. SECONDARY COMPOUNDING
=========================

Depois do fixed-100:

pode executar um compounding secundário,

MAS:

notional deve ser limitado pela capacidade que o execution model consegue suportar.

Sem evidência de depth:

não escalar lote arbitrariamente.

==================================================
46. CURRENT L2 COLLECTOR
========================

Implementar collector prospectivo oficial para USDCUSDT:

trades

bookTicker

depth diff

periodic depth snapshot.

Persistir:

event time
receive time
sequence IDs
prices
quantities
book levels.

Este collector é:

PUBLIC MARKET DATA ONLY.

Pode continuar sendo usado posteriormente para SHADOW evidence.

==================================================
47. NÃO CONFUNDIR CALIBRATION COM BACKFILL
==========================================

L2 coletado hoje NÃO prova o book de janeiro de 2026.

Usá-lo apenas para:

calibrar ranges plausíveis de:

queue
spread
depth
latency.

Marcar:

PROSPECTIVE_CALIBRATION.

==================================================
48. TESTES
==========

Antes do replay completo:

unit/integration fixtures para:

touch without fill

wrong aggressor side

latency miss

partial buy

partial sell

cancel race

queue depletion

full fill

step-size rounding

min-notional rejection

fee wipes edge

release slippage >10bps

partial release

reserve depletion

reserve funding from NET profit

book gap/resnapshot

same-timestamp causality

restart determinism.

==================================================
49. AUDITORIA INDEPENDENTE
==========================

Antes do resultado ser aceito:

reconstruir independentemente amostra de pelo menos:

100 ordinary cycles

e

TODAS as releases

ou quantidade maior se necessário.

Verificar:

order timestamps

trade support

aggressor side

quantities

fees

fills

reserve ledger.

==================================================
50. NÃO ADAPTAR DEPOIS DO RESULTADO
===================================

Nesta campanha:

NÃO corrigir B10.

Se B10 falhar:

reportar exatamente por quê.

Não mudar:

B10 → B12
H1 → H2
fee handling
release threshold

para salvá-lo.

Adaptação será uma campanha futura e receberá nova identidade estratégica.

==================================================
51. GIT / ARTIFACTS
===================

Criar:

docs/binance/BINANCE_USDCUSDT_EXECUTION_AUTHORITY.md

docs/microstructure/B10_REALITY_GAUNTLET_PROTOCOL.md

reports/usdcusdt/B10-binance-rule-timeline.json

reports/usdcusdt/B10-reality-scoreboard.json

reports/usdcusdt/B10-reality-report.md

artifacts/binance/...

Preservar:

source URLs
retrieved_at
hashes
checksums
rule timeline
data manifest
calibration manifest
profile manifest.

==================================================
52. EXECUTION SEQUENCE
======================

FASE 1
official Binance research.

FASE 2
historical rules/data manifest.

FASE 3
B10 exact reference reconciliation.

FASE 4
execution simulator implementation.

FASE 5
fixtures + deterministic audit.

FASE 6
FIXED_NOTIONAL_100 full replay.

FASE 7
profiles A/B/C/D.

FASE 8
release autopsy.

FASE 9
independent review.

Não parar apenas porque o resultado ficou ruim.

Precisamos saber quanto do B10 sobrevive.

==================================================
53. OWNER UPDATE FORMAT
=======================

Toda atualização material deve começar:

STRATEGY=B10_FROZEN

EXECUTION_PROFILE=

BINANCE_RULE_AUTHORITY_STATUS=

PRICE_PATH_REFERENCE=3580880

FULL_FILL_CYCLES=

NET_POSITIVE_CYCLES=

REALITY_RETENTION=

ZERO_DAYS=

NET_PNL_FIXED_100=

RESERVE_FINAL=

RELEASES_FILLED=

RELEASES_GT10BPS_EXECUTED=

MAX_HOLD=

LOCK_HOURS=

VERDICT=.

Depois detalhes.

==================================================
54. SEGURANÇA
=============

NO LIVE ORDERS.

NO TESTNET ORDERS nesta fase.

NO PRIVATE API KEYS.

NO WITHDRAWAL.

NO ACCOUNT ACCESS.

PUBLIC BINANCE MARKET DATA ONLY.

==================================================
55. REGRA FINAL
===============

DO NOT HELP B10.

DO NOT TUNE B10.

DO NOT PRESERVE ITS 3.58M CYCLES ARTIFICIALLY.

MAKE THE EXCHANGE REAL.

APPLY EVERY OFFICIAL BINANCE RULE THAT MATTERS.

WHERE REAL HISTORICAL EVIDENCE EXISTS:
USE IT.

WHERE IT DOES NOT:
SAY UNKNOWN.

THEN APPLY CONSERVATIVE, EXPLICITLY PARAMETERIZED EXECUTION ENVELOPES.

THE QUESTION IS NOT:

"CAN PRICE MOVE LOW→HIGH?"

THE QUESTION IS:

"COULD OUR REAL 100-USDT BINANCE SPOT ORDER HAVE BEEN FILLED,
PAID ITS COSTS,
COMPLETED THE SELL,
FUNDED THE RESERVE,
AND REPEATED THIS PROCESS?"

TENTE DERRUBAR O B10.
