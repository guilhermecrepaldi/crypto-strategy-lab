# OWNER DIRECTIVE — M025 ORDER-SIZE CAPACITY CURVE
# IDENTIFY THE ORDER-SIZE / LIQUIDITY BOTTLENECK
# USDCUSDT · HISTORICAL L2 · CONTROLLED CAPACITY SWEEP

Repository:
guilhermecrepaldi/crypto-strategy-lab

==================================================
0. ANTES DE QUALQUER ALTERAÇÃO
==================================================

Leia integralmente:

docs/research/CURRENT_STATE.md
docs/research/M024_JOURNAL.md
docs/microstructure/M024_TRIANGULAR_PRE_AGED_QUEUE_OWNER_DIRECTIVE.md
docs/microstructure/M024_TRIANGULAR_PRE_AGED_QUEUE_PREREGISTRATION.md
reports/usdcusdt/M024-3h-result.json
reports/usdcusdt/M024-3h-independent-post-run-review.md

e todo o código/testes usados por M024.

Verificar:

- git status clean;
- HEAD == origin/main;
- M025 está livre no registry;
- M024 permanece imutável.

HEAD esperado no momento da diretiva:

c6a693ba7d513193de907d240ac8af105a127f61

Se o Git estiver à frente, ler o novo estado antes de continuar.
Não resetar trabalho válido.

==================================================
1. OBJETIVO DO OWNER
==================================================

M024 demonstrou que pre-aged same-price FIFO pode aumentar
throughput absoluto:

M024:
35 ciclos em 3h
11.6667 ciclos/h.

Mas M024 usou apenas:

1 USDC por ordem.

Isso é pequeno demais para responder:

QUAL É O TAMANHO DE ORDEM EM QUE
A PRÓPRIA QUANTIDADE COMEÇA A VIRAR GARGALO?

OWNER hypothesis/prior:

500 USDC por ordem pode ainda ser pequeno
e o gargalo talvez comece acima disso.

Isso NÃO é conclusão.

O L2 deve responder.

Queremos construir uma CURVA DE CAPACIDADE:

ORDER_SIZE
→ FILL SPEED
→ COMPLETED CYCLES
→ ROUNDTRIP VOLUME
→ CAPITAL EFFICIENCY
→ REALIZED PNL
→ PARTIAL-FILL PRESSURE.

==================================================
2. O QUE M025 NÃO É
==================================================

M025 NÃO implementa ainda:

- 15 níveis;
- geometria 3 colunas / 2 colunas / 1 coluna;
- hot-line order size 3x;
- medium order size 2x;
- far order size 1x;
- novo algoritmo de recenter;
- nova estratégia;
- novo par;
- novo dia;
- live trading.

Esses elementos ficam para modelo posterior.

M025 deve alterar SOMENTE a dimensão:

ORDER_QUANTITY_USDC.

A geometria econômica/microestrutural deve permanecer
equivalente ao M024.

==================================================
3. MODELO
==================================================

Criar:

MODEL_ID=M025

STRATEGY=
M024_ORDER_SIZE_CAPACITY_CURVE_V1

PARENT_MODEL=M024

SCIENTIFIC_STATUS=
OWNER_AUTHORIZED_CONTROLLED_ORDER_SIZE_CAPACITY_SWEEP

M024 é imutável.

==================================================
4. JANELA HISTÓRICA
==================================================

Usar exatamente o mesmo prefixo de M024:

PAIR=USDCUSDT

SOURCE_DAY=2025-01-01

START=
2025-01-01T00:00:00Z

END_EXCLUSIVE=
2025-01-01T03:00:00Z

Mesmos:

- L2;
- canonical trades;
- latency;
- cancel latency;
- post-only semantics;
- LIMIT_MAKER behavior;
- queue model;
- no cancellation credit;
- global once-only trade quantity;
- strict causality;
- no future information;
- no cutoff liquidation.

Cada tamanho de ordem é um cenário CONTRAFACTUAL INDEPENDENTE.

Nunca compartilhar consumo de liquidez entre cenários.

==================================================
5. GEOMETRIA — CONGELAR M024
==================================================

Preservar a geometria inicial de M024:

50 logical price levels per side.

Levels 01–25:
2 same-price columns.

Levels 26–50:
1 column.

Por lado:

75 orders.

Total inicial:

75 BUY
+
75 SELL
=
150 physical entry orders.

Não reduzir para 15 níveis neste modelo.

Não mudar 2/1 columns.

Não otimizar distância.

Não mudar hot line logic.

==================================================
6. GROWTH DESABILITADO PARA ISOLAMENTO
==================================================

M024 possui profit-funded growth.

Para M025, desabilitar crescimento estrutural DURANTE os
cenários para não contaminar a variável ORDER_SIZE.

Config:

PROFIT_FUNDED_NEW_CELLS=false

GROWTH_POOL may be measured,
but it MUST NOT create new physical cells.

Principal recycling permanece conforme M024.

Owned returns permanecem conforme M024.

Motivo:

se order size maior produzir lucro maior e imediatamente
criar novas ordens, deixaríamos de saber se o aumento de
throughput veio do tamanho ou da expansão da geometria.

==================================================
7. TAMANHOS PRÉ-REGISTRADOS
==================================================

Executar exatamente estes ORDER_QUANTITY_USDC:

10
50
100
250
500
750
1000
1500
2000
3000
5000

Todos devem ser preregistrados ANTES de qualquer replay.

Nenhum tamanho adicional pode ser escolhido depois de ver
os resultados.

OWNER_PRIOR_CANDIDATE=500_USDC

O valor de 500 não recebe tratamento privilegiado.

Ele deve ser medido exatamente como os demais.

==================================================
8. POR QUE INCLUIR 1000 E 1500
==================================================

A arquitetura futura proposta pelo OWNER pretende usar:

HOT:
3x base order size

MID:
2x base order size

FAR:
1x base order size.

Portanto, se futuramente:

BASE=500

teríamos:

HOT=1500
MID=1000
FAR=500.

M025 deve permitir verificar não somente se500 é seguro,
mas também se1000 e1500 já entram na região de saturação.

==================================================
9. QUANTIDADE, NÃO NOTIONAL EXATO
==================================================

ORDER_QUANTITY_USDC é a variável congelada.

Como USDCUSDT está próximo de1:

500 USDC ≈ 500 USDT notional,

mas reportar o NOTIONAL REAL em cada preço.

Não fingir que500 USDC é exatamente500 USDT.

Registrar:

MIN_ORDER_NOTIONAL_USDT
MEDIAN_ORDER_NOTIONAL_USDT
MAX_ORDER_NOTIONAL_USDT

por cenário.

==================================================
10. CAPITAL INICIAL
==================================================

Cada cenário deve possuir capital próprio suficiente para
financiar exatamente a mesma geometria.

Nenhum cenário pode ficar com menos ordens por falta de capital.

Base M024 para quantity=1:

INITIAL_USDT=74.9900
INITIAL_USDC=75
INITIAL_MARKED_EQUITY=150.1325

Portanto, para quantity Q, confirmar matematicamente e no
ledger:

INITIAL_USDT ~= 74.9900 * Q

INITIAL_USDC = 75 * Q

INITIAL_MARKED_EQUITY ~= 150.1325 * Q

Não simplesmente confiar nessa fórmula.

Recalcular usando os preços físicos registrados.

Accounting residual deve ser zero.

No capital injection during run.

==================================================
11. SEM LIMITE ARTIFICIAL DE CAPITAL
==================================================

M025 é um CAPACITY STUDY.

Não bloquear tamanho grande apenas porque exigiria capital
alto em produção.

O objetivo é descobrir o limite microestrutural.

Mas reportar claramente:

CAPITAL_REQUIRED

para cada cenário.

Isto NÃO é recomendação para colocar esse dinheiro em live.

==================================================
12. GENERALIZAR O KERNEL DE 1 USDC
==================================================

M024 atualmente foi desenhado em torno de quantity=1.

M025 precisa generalizar quantidade SEM alterar a semântica
de fila.

Antes de replay histórico, testes sintéticos devem provar:

quantity=10
quantity=500
quantity=5000

funcionam com:

- partial fills;
- own FIFO;
- public FIFO;
- residual quantity;
- returns;
- capital reservation;
- recycling;
- cancel ACK.

Nenhum shortcut pode assumir quantity=1.

==================================================
13. SAME-PRICE OWN FIFO COM QUANTIDADE GRANDE
==================================================

Exemplo:

PUBLIC_QUEUE_AHEAD = 10,000 USDC

C1 quantity = 500
C2 quantity = 500

fila correta:

10,000 PUBLIC
→ C1 500
→ C2 500.

Não:

10,000 → C1
e
10,000 → C2 separadamente.

Não duplicar public queue.

C2 deve carregar os500USDC de C1 à frente
enquanto C1 não estiver totalmente executada/cancelada.

==================================================
14. PARTIAL FILL — CRÍTICO
==================================================

Exemplo:

public queue já consumida.

C1 remaining=500.

trade eligible quantity=200.

Resultado:

C1 filled=200
C1 remaining=300
C2 filled=0.

Próximo trade quantity=250:

C1 remaining=50
C2 filled=0.

Próximo trade quantity=100:

50 completa C1.

Somente o restante50 pode chegar a C2,
se toda causalidade e elegibilidade permitirem.

Nunca descartar residual.

Nunca preencher C2 antes do residual C1.

==================================================
15. IDADE DA FILA
==================================================

Partial fill NÃO reseta:

- submitted time;
- activation time;
- queue age;
- price priority;
- own FIFO position.

Residual C1 permanece à frente de C2.

==================================================
16. DEFINIÇÃO DE CICLO EM M025
==================================================

Um COMPLETE PHYSICAL CYCLE é:

toda a quantidade Q da entrada executada

E

toda a quantidade correspondente Q do retorno lucrativo
executada.

Não contar:

partial entry
ou
partial return

como ciclo completo.

Não transformar500USDC em500 ciclos de1USDC.

Uma ordem de500 completa:

1 physical cycle.

==================================================
17. MÉTRICA DE VOLUME
==================================================

Como physical cycles deixam de ser comparáveis sozinhos,
criar obrigatoriamente:

COMPLETED_ROUNDTRIP_USDC

Para cada ciclo:

+= quantity Q.

E:

COMPLETED_ROUNDTRIP_USDC_PER_HOUR.

Também:

TWO_WAY_TRADED_USDC

soma de todos os fills BUY + SELL.

E:

TWO_WAY_NOTIONAL_USDT.

Essas métricas serão centrais.

==================================================
18. MÉTRICAS DE FREQUÊNCIA
==================================================

Por cenário:

TOTAL_COMPLETE_CYCLES

CYCLES_PER_HOUR

BUY_FIRST_CYCLES

SELL_FIRST_CYCLES

COLUMN_1_CYCLES

COLUMN_2_CYCLES

TOTAL_FILL_FRAGMENTS.

==================================================
19. MÉTRICAS DE CAPACIDADE
==================================================

Por cenário:

ORDER_QUANTITY_USDC

COMPLETED_ROUNDTRIP_USDC

COMPLETED_ROUNDTRIP_USDC_PER_HOUR

TWO_WAY_TRADED_USDC_PER_HOUR

TWO_WAY_NOTIONAL_USDT_PER_HOUR

FULL_ENTRY_ORDERS

FULL_RETURN_ORDERS

PARTIALLY_FILLED_ORDERS

PARTIAL_FILL_RATE

FULL_FILL_RATE

ORDERS_OPEN_AT_CUTOFF.

==================================================
20. TEMPO DE EXECUÇÃO
==================================================

Separar:

TIME_TO_FIRST_FILL

TIME_FIRST_TO_FULL_FILL

TIME_TO_FULL_FILL

TIME_PUBLIC_QUEUE_ZERO_TO_FIRST_OWN_FILL

TIME_PUBLIC_QUEUE_ZERO_TO_FULL_OWN_FILL.

Reportar:

mean
median
P95
max

por ORDER_SIZE.

==================================================
21. FILA
==================================================

Reportar:

PUBLIC_QUEUE_AHEAD_AT_ACTIVATION mean/median/P95

OWN_QUANTITY_AHEAD_AT_ACTIVATION

QUEUE_CONSUMPTION_EVENTS

PUBLIC_QUEUE_QUANTITY_CONSUMED

OWN_QUEUE_QUANTITY_CONSUMED.

Especialmente:

tempo gasto esperando PUBLIC FIFO

versus

tempo gasto executando NOSSO PRÓPRIO TAMANHO
após alcançar o topo.

==================================================
22. INVENTÁRIO E RESIDUAIS
==================================================

Por cenário:

OPEN_INVENTORY_USDC

OPEN_INVENTORY_COST

PARTIAL_ENTRY_RESIDUAL_USDC

PARTIAL_RETURN_RESIDUAL_USDC

CAPITAL_LOCKED_IN_PARTIALS

CAPITAL_LOCKED_IN_OPEN_LOTS

OPEN_ORDERS_AT_CUTOFF.

Isto é fundamental para identificar quando tamanho
começa a ser gargalo.

==================================================
23. ECONOMIA
==================================================

Mesmo fee profile de M024:

FROZEN_PROFILE_ZERO_CONDITIONAL_NOT_ACCOUNT_FACT.

Não introduzir outra taxa neste modelo.

Reportar:

REALIZED_DISPOSAL_PNL

COMPLETED_CYCLE_PNL

UNREALIZED_PNL

FINAL_MARKED_EQUITY

TOTAL_EQUITY_CHANGE

RETURN_ON_INITIAL_EQUITY

REALIZED_PNL_PER_HOUR

COMPLETED_CYCLE_PNL_PER_HOUR

PNL_PER_1000_USDT_INITIAL_CAPITAL.

Não chamar isso de live profitability.

==================================================
24. CAPITAL E EFICIÊNCIA
==================================================

Reportar:

INITIAL_MARKED_EQUITY

ACTIVE_CAPITAL_TIME_WEIGHTED

CAPITAL_UTILIZATION

CYCLES_PER_HOUR_PER_1000_USDT

ROUNDTRIP_USDC_PER_HOUR_PER_1000_USDT

PNL_PER_HOUR_PER_1000_USDT.

Precisamos distinguir:

MAIS CAPITAL GIRADO

de

MELHOR EFICIÊNCIA DO CAPITAL.

==================================================
25. DEFINIÇÃO DO “GARGALO”
==================================================

Não escolher um número subjetivamente.

Reportar pelo menos quatro pontos:

A.
MAX_ROUNDTRIP_USDC_PER_HOUR_ORDER_SIZE

B.
MAX_REALIZED_PNL_PER_HOUR_ORDER_SIZE

C.
MAX_CAPITAL_EFFICIENCY_ORDER_SIZE

D.
FIRST_MATERIAL_CYCLE_RATE_DEGRADATION.

Definir previamente:

FIRST_MATERIAL_CYCLE_RATE_DEGRADATION =
primeiro tamanho Q em que cycles/hour cai >=20%
em relação ao cenário imediatamente menor.

==================================================
26. SATURAÇÃO DE TAMANHO
==================================================

Calcular para cada salto:

SIZE_MULTIPLIER =
Q_new / Q_old

ROUNDTRIP_THROUGHPUT_MULTIPLIER =
roundtrip_usdc_per_hour_new
/
roundtrip_usdc_per_hour_old

SCALING_EFFICIENCY =
ROUNDTRIP_THROUGHPUT_MULTIPLIER
/
SIZE_MULTIPLIER.

Interpretação:

~1.0:
volume escalou proporcionalmente ao tamanho.

<1:
começou perda de eficiência.

muito abaixo de1:
ordem está ficando grande demais para o fluxo.

Não transformar esse indicador sozinho em estratégia pass.

==================================================
27. KNEE / JOELHO DA CURVA
==================================================

Criar diagnóstico:

CAPACITY_KNEE_ORDER_SIZE.

Mas não inventar se não houver evidência clara.

Se nenhuma saturação material aparecer até5000USDC:

CAPACITY_KNEE_ORDER_SIZE=
NOT_OBSERVED_UP_TO_5000_USDC.

Se aparecer:

reportar o primeiro tamanho em que a combinação de:

- cycle-rate degradation;
- partial-fill growth;
- residual duration;
- flattening/decline of roundtrip USDC/h

indica saturação.

Explicar evidência.

==================================================
28. OWNER PRIOR — 500 USDC
==================================================

Responder explicitamente:

ORDER_SIZE_500_USDC:

CYCLES_PER_HOUR=
ROUNDTRIP_USDC_PER_HOUR=
PARTIAL_FILL_RATE=
MEDIAN_FULL_FILL_SECONDS=
P95_FULL_FILL_SECONDS=
REALIZED_PNL_PER_HOUR=
CAPITAL_EFFICIENCY=
BOTTLENECK_OBSERVED=YES/NO.

Também comparar:

250 vs500
500 vs750
500 vs1000
1000 vs1500.

==================================================
29. FUTURA ARQUITETURA 3x/2x/1x
==================================================

M025 NÃO deve executá-la.

Mas ao final fazer diagnóstico matemático:

Se base B fosse usada posteriormente:

HOT_ORDER=3B
MID_ORDER=2B
FAR_ORDER=B.

Para candidatos relevantes:

B=250:
HOT750
MID500
FAR250

B=500:
HOT1500
MID1000
FAR500

B=1000:
HOT3000
MID2000
FAR1000.

Com base na curva medida, dizer somente:

ALL_THREE_SIZES_BELOW_OBSERVED_KNEE=true/false/unknown.

Não executar essa geometria.

==================================================
30. NÃO USAR FUTURO
==================================================

Nenhuma decisão durante cenário pode usar:

- future trades;
- future book;
- future high/low;
- resultado do cenário anterior.

Cada cenário possui parâmetros fixos desde preregistration.

O fato de os cenários serem executados em ordem crescente
não pode alterar os próximos.

==================================================
31. INDEPENDÊNCIA DOS CENÁRIOS
==================================================

Cada ORDER_SIZE deve iniciar:

do mesmo timestamp

com estado novo

com capital proporcional

com mesma geometria

com mesmo dataset.

Nenhum:

inventory
queue age
profit
capital
order
trade budget

passa de um cenário para outro.

==================================================
32. HISTORICAL FLOW NÃO REAGE A NÓS
==================================================

Registrar explicitamente:

ENDOGENOUS_MARKET_IMPACT_MODELED=false.

O replay mede capacidade sob fluxo histórico observado.

Uma ordem grande em live poderia alterar:

- comportamento de outros participantes;
- cancelamentos;
- queue behavior;
- spread;
- adverse selection.

M025 não modela essa reação.

Portanto não chamar:

“live market capacity”.

Chamar:

HISTORICAL_L2_PASSIVE_CAPACITY_CURVE.

==================================================
33. TRUE QUEUE RANK
==================================================

Preservar as limitações conhecidas do queue model.

Não afirmar que sabemos posição real exata na Binance.

Reportar:

OBSERVED_L2_CONSERVATIVE_QUEUE_MODEL.

==================================================
34. TESTES SINTÉTICOS OBRIGATÓRIOS
==================================================

Testes mínimos:

A.
quantity500
public10000
C1=500
C2=500
trade5000
→ public remaining5000
→ no own fill.

B.
next trade5000
→ public reaches0
→ no retroactive invented fill.

C.
next eligible trade200
→ C1 fill200
→ residual300
→ C2 zero.

D.
next250
→ C1 residual50.

E.
next100
→ C1 finishes50
→ only remaining50 may reach C2 if eligible.

F.
C1 residual keeps time priority.

G.
Cancel partial C1:
C2 advances only after CANCEL_ACK and residual semantics.

H.
Return quantity must equal legitimately acquired quantity.

I.
No cycle before complete roundtrip Q.

J.
No capital duplication.

K.
No trade quantity duplication.

L.
Checkpoint/resume identical.

M.
quantity10,500,5000 accounting identities pass.

N.
same-price C1/C2 correctly scale own quantity ahead with Q.

O.
large order at cutoff remains censored, never forcibly filled.

==================================================
35. OPEN ORDER CAP
==================================================

Preservar:

HARD_SIMULATED_OPEN_ORDER_CAP=200.

Initial physical orders remain150.

Owned returns and cancels must respect cap.

Do not increase order count with size.

==================================================
36. PRE-RUN REVIEW
==================================================

Antes de qualquer historical replay:

executar independent source-bound review.

Prefer:

GPT-6 Astra.

Review deve verificar especialmente:

- quantity generalization;
- partial fill;
- residual FIFO;
- same-price own queue;
- no duplicated public queue;
- no duplicated liquidity;
- no duplicated capital;
- full-cycle definition;
- scenario independence;
- growth disabled;
- frozen size ladder;
- no future data.

Se reviewer BLOCK:

corrigir antes do replay.

Registrar todas as rodadas.

TEST_SUITE_PASS != STRATEGY_PASS.

==================================================
37. PREREGISTRATION E GITHUB
==================================================

Criar:

docs/microstructure/M025_ORDER_SIZE_CAPACITY_OWNER_DIRECTIVE.md

docs/microstructure/M025_ORDER_SIZE_CAPACITY_PREREGISTRATION.md

docs/microstructure/M025_MODEL_SPEC.json

docs/research/M025_JOURNAL.md

Preregister TODOS os tamanhos antes de replay.

Commit + push.

Confirmar:

worktree clean
HEAD == origin/main

antes do primeiro cenário.

==================================================
38. EXECUÇÃO
==================================================

Executar exatamente UMA vez por tamanho:

10
50
100
250
500
750
1000
1500
2000
3000
5000.

Não repetir cenário porque “ficou estranho”.

Se ocorrer erro técnico após market events:

preservar artifacts
parar
auditar
não rerun silencioso.

==================================================
39. RESULTADOS
==================================================

Publicar:

reports/usdcusdt/M025-order-size-capacity-result.json

reports/usdcusdt/M025-order-size-capacity-autopsy.md

reports/usdcusdt/M025-order-size-capacity-independent-review.md

e artifacts individuais de cada cenário.

Atualizar append-only:

registry
journal
CURRENT_STATE

sem alterar evidência física M024.

==================================================
40. TABELA PRINCIPAL
==================================================

Resultado deve começar por:

M025 ORDER SIZE CAPACITY CURVE

| Q USDC | Initial Equity | Cycles/h | Roundtrip USDC/h | Partial Rate | Median Full Fill | P95 Full Fill | Realized PnL/h | PnL/1000/h |

Ordenar por Q crescente.

==================================================
41. SCOREBOARD DO OWNER
==================================================

Depois da tabela:

MODEL=M025
PERIOD=3H_PER_SCENARIO

SCENARIOS_COMPLETED=

BEST_CYCLES_PER_HOUR_SIZE=

MAX_ROUNDTRIP_USDC_PER_HOUR_SIZE=

MAX_REALIZED_PNL_PER_HOUR_SIZE=

MAX_CAPITAL_EFFICIENCY_SIZE=

FIRST_MATERIAL_CYCLE_RATE_DEGRADATION=

CAPACITY_KNEE_ORDER_SIZE=

OWNER_500_BOTTLENECK=
YES/NO/INCONCLUSIVE

OWNER_500_CYCLES_PER_HOUR=

OWNER_500_ROUNDTRIP_USDC_PER_HOUR=

OWNER_500_PARTIAL_FILL_RATE=

OWNER_500_MEDIAN_FULL_FILL_SECONDS=

OWNER_500_P95_FULL_FILL_SECONDS=

OWNER_500_REALIZED_PNL_PER_HOUR=

BASE500_FUTURE_3X_SIZE=1500
BASE500_FUTURE_2X_SIZE=1000
BASE500_FUTURE_1X_SIZE=500

BASE500_ALL_BELOW_CAPACITY_KNEE=
YES/NO/UNKNOWN

AUDIT=

STATUS=

==================================================
42. COMO INTERPRETAR O RESULTADO
==================================================

Não escolher “melhor size” apenas pelo maior PnL bruto.

Precisamos responder:

1. Até qual tamanho o volume por hora cresce quase
proporcionalmente?

2. Em qual tamanho cycles/hour começa a cair?

3. Em qual tamanho partial fills começam a aumentar
materialmente?

4. Em qual tamanho o tempo entre FIRST FILL e FULL FILL
explode?

5. Qual tamanho maximiza ROUNDTRIP USDC/H?

6. Qual tamanho maximiza REALIZED PNL/H?

7. Qual tamanho maximiza eficiência por capital?

8. 500 USDC já é gargalo?

9. 1000 USDC já é gargalo?

10. 1500 USDC já é gargalo?

11. A futura estrutura base500:
1500 / 1000 / 500
estaria toda antes do joelho?

==================================================
43. NÃO CRIAR M026
==================================================

Ao fim:

não criar M026.

não implementar 15-level geometry.

não implementar 3/2/1 columns.

não implementar 3x/2x/1x order sizes.

não rodar Day2.

não rodar live.

Gate fecha.

A próxima decisão pertence ao OWNER.

==================================================
44. PRINCÍPIO CIENTÍFICO
==================================================

M025 deve encontrar a CURVA DE CAPACIDADE,
não provar que uma hipótese favorita está certa.

Se500 for pequeno:

dizer pequeno.

Se500 já for grande:

dizer grande.

Se1000 for melhor:

registrar.

Se5000 ainda não saturar:

CAPACITY_KNEE_NOT_OBSERVED_UP_TO_5000.

Se volume crescer mas eficiência de capital cair:

mostrar as duas coisas.

Não esconder partial fills.

Não esconder inventário censurado.

Não otimizar depois de ver resultado.

==================================================
45. PERGUNTA FINAL
==================================================

Responder objetivamente:

QUAL É O MAIOR TAMANHO DE ORDEM QUE O REPLAY HISTÓRICO
SUPORTA COM BOA ROTAÇÃO ANTES DE O PRÓPRIO TAMANHO
COMEÇAR A REDUZIR MATERIALMENTE A FREQUÊNCIA OU
A EFICIÊNCIA?

E especificamente:

500 USDC É PEQUENO, ADEQUADO OU JÁ É GARGALO?

E:

SE USARMOS BASE=500 NO FUTURO,
ORDENS HOT DE1500 E MID DE1000
AINDA ESTÃO NA REGIÃO EFICIENTE?

Não confundir historical replay capacity com live capacity.
