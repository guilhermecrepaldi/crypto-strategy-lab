# OWNER DIRECTIVE — M027 MICRO-HOT REALLOCATION
# FAR14/FAR15 → 2-COLUMN MICRO-HOT
# FREQUENCY-FIRST CONTROLLED A/B
# NO EXTRA CAPITAL · NO PARAMETER SWEEP

Repository:
guilhermecrepaldi/crypto-strategy-lab

Expected current main:
ef46a118097306a56b1575a9fa5d15afc3a3b8e4

==================================================
0. LEIA O ESTADO REAL PRIMEIRO
==================================================

Antes de alterar qualquer arquivo:

git fetch

confirmar:
HEAD == origin/main
worktree clean

Ler integralmente:

docs/research/CURRENT_STATE.md
docs/research/M026_JOURNAL.md
docs/microstructure/M026_DYNAMIC_HOTLINE_321_OWNER_DIRECTIVE.md
docs/microstructure/M026_DYNAMIC_HOTLINE_321_PREREGISTRATION.md
reports/usdcusdt/M026-3h-result.json
reports/usdcusdt/M026-3h-autopsy.md
reports/usdcusdt/M026-3h-independent-post-run-review.md

e todo o kernel/testes M026.

M026 permanece IMUTÁVEL.

Confirmar que M027 está livre no registry.

Esta diretiva autoriza M027.

==================================================
1. OBSERVAÇÃO QUE MOTIVA M027
==================================================

M026:

PHYSICAL_CYCLES=30
PHYSICAL_CYCLES_PER_HOUR=10

SLOT_EQUIVALENT_CYCLES=90
SLOT_EQUIVALENT_CYCLES_PER_HOUR=30

HOT cycles=30
MID cycles=0
FAR cycles=0

Column cycles:

C1=11
C2=10
C3=9.

Portanto:

- toda produtividade observada nasceu na HOT;
- MID/FAR não fecharam ciclos;
- as três colunas HOT continuaram produtivas;
- PUBLIC_FIFO_WAIT dominou descritivamente o tempo;
- aumentar simplesmente order size não aumentou frequência;
- precisamos aumentar quantidade de oportunidades de preço
  próximo da hotline.

Nova hipótese:

retirar as duas posições FAR mais distantes
e utilizar exatamente o mesmo capital para criar
uma MICRO-HOT entre a hotline e o primeiro nível HOT
pode aumentar frequência sem aumentar banca.

==================================================
2. OBJETIVO
==================================================

FREQUENCY ONLY.

Principal pergunta:

MICRO-HOT aumenta:

PHYSICAL_CYCLES_PER_HOUR

e/ou

SLOT_EQUIVALENT_CYCLES_PER_HOUR

sem adicionar capital?

Não otimizar PnL como objetivo primário.

==================================================
3. IMPORTANTE — MICRO-HOT ≠ MAIS COLUNAS HOT
==================================================

Não alterar a HOT principal.

Ela continua:

HOT rank1-5
3 columns
3 slots/order.

MICRO-HOT é uma NOVA LINHA DE PREÇO
mais próxima da hotline.

Ela terá EXATAMENTE:

2 columns

e NÃO mais que2.

Cada MICRO-HOT order:

1 SLOT.

Portanto:

MICRO-HOT =
2 columns ×1 slot
=
2 slot-units por lado.

==================================================
4. DE ONDE VEM O CAPITAL
==================================================

Não injetar capital.

Remover do desenho operacional:

FAR LEVEL14
FAR LEVEL15

de cada lado.

Hoje:

FAR14 =
1column ×1slot
=
1 slot-unit.

FAR15 =
1column ×1slot
=
1 slot-unit.

Total removido:

2 slot-units por lado.

Esses mesmos2 slot-units financiam:

MICRO-HOT C1=1slot
MICRO-HOT C2=1slot.

Logo:

CAPITAL_DELTA=0.

==================================================
5. GEOMETRIA DO TRATAMENTO
==================================================

Por lado:

MICRO-HOT:
1 price line
2 columns
1 slot/order
=
2 slot-units.

HOT:
5 price lines
3 columns
3 slots/order
=
45 slot-units.

MID:
5 price lines
2 columns
2 slots/order
=
20 slot-units.

FAR:
somente ranks11,12,13
1 column
1 slot/order
=
3 slot-units.

TOTAL PER SIDE:

2 +45+20+3
=
70 slot-units.

Dois lados:

140 operational slot-units.

Preservar:

16 mobility reserve slot-units.

TOTAL ARCHITECTURAL SLOT UNITS:

156.

Exatamente igual ao M026.

==================================================
6. CONTAGEM DE ORDENS
==================================================

M026 por lado:

HOT 15 orders
MID 10
FAR 5

TOTAL=30.

M027 treatment:

MICRO-HOT 2
HOT 15
MID 10
FAR 3

TOTAL=30.

Dois lados:

60 initial physical orders.

Portanto:

INITIAL_ORDER_COUNT_DELTA=0.

==================================================
7. PREÇO DA MICRO-HOT
==================================================

A MICRO-HOT fica no meio do espaço
entre a HOTLINE e o HOT rank1.

Se coarse spacing for:

0.0001

então:

MICRO_OFFSET =
0.00005.

Exemplo BUY:

HOTLINE=0.99980

MICRO-BUY=
0.99975

se esse lado/preço for economicamente coerente
com a convenção BUY adotada no engine.

Exemplo simétrico SELL:

HOTLINE=0.99980

MICRO-SELL=
0.99985.

IMPORTANTE:

seguir a orientação correta de BUY abaixo
e SELL acima da hotline.

Nunca inverter lados.

==================================================
8. TICK SIZE — HARD SCIENTIFIC GATE
==================================================

NÃO executar MICRO-HOT em um tape
onde0.00005 não seja preço válido.

O tape de2025-01-01 utilizava historical tick0.0001.

Portanto:

NÃO usar0.99975 nesse tape.

NÃO virtualizar meio tick.

NÃO arredondar0.99975 para0.9997/0.9998
e fingir que testou MICRO-HOT.

NÃO interpolar book.

NÃO sintetizar trades.

==================================================
9. NOVO TAPE COM FINE TICK
==================================================

Usar o primeiro dataset L2 já disponível no projeto
que satisfaça TODAS estas condições:

A. posterior à mudança do PRICE_FILTER;
B. preço observado suporta tick <=0.00001;
C. 0.00005 é múltiplo legal do tick observado;
D. dataset possui L2 + canonical trades íntegros;
E. janela inicial contínua de3h disponível.

Preferência inicial:

2026-05-01
00:00:00Z
até
03:00:00Z exclusive.

Mas NÃO assumir.

Primeiro validar fisicamente no dataset:

OBSERVED_PRICE_INCREMENT
EXCHANGE_RULE_EVIDENCE
L2_PRICE_GRID.

Se2026-05-01 não satisfizer:

STOP.

Não escolher outro dia depois de olhar performance.

Retornar:

BLOCKED_FINE_TICK_DATASET_NOT_VALIDATED.

==================================================
10. POR QUE NÃO COMPARAR DIRETAMENTE COM M026
==================================================

Mudamos o source day.

Portanto:

M026 vs M027 não é comparação causal direta.

Para medir efeito da MICRO-HOT,
executar DOIS cenários preregistrados
no MESMO novo tape.

A:

M027_CONTROL

B:

M027_MICRO_HOT.

Isso não é parameter sweep.

É um A/B controlado previamente definido.

==================================================
11. M027 CONTROL
==================================================

CONTROL usa arquitetura M026,
mas no novo source day.

Manter DISTÂNCIAS ECONÔMICAS de M026:

COARSE_GRID_SPACING =
0.0001.

Não transformar automaticamente
cada level em1 novo fine-tick.

Ou seja:

mesmo que exchange tick seja0.00001,
os coarse levels continuam separados por0.0001.

CONTROL:

15 coarse levels/side.

HOT ranks1-5:
3columns ×3slots.

MID6-10:
2×2.

FAR11-15:
1×1.

60 initial orders.

140 operational slot-units.

16 reserve.

==================================================
12. M027 TREATMENT
==================================================

Exatamente igual ao CONTROL,
EXCETO:

remove FAR14 and FAR15.

Adiciona:

MICRO-HOT at ±0.00005 from hotline.

MICRO-HOT:

2columns
1slot each.

Nenhuma outra diferença.

ONLY_INDEPENDENT_VARIABLE:

FAR14_FAR15_CAPITAL_REALLOCATION_TO_MICRO_HOT.

==================================================
13. CAPITAL MATCH
==================================================

CONTROL e TREATMENT devem iniciar
com mesmo TOTAL ARCHITECTURAL BANK
em slot terms.

140 operational
+
16 mobility
=
156 slot-units.

SLOT_BASE inicial idêntico.

Se diferenças mínimas surgirem
por quantização/preço:

reportar explicitamente.

Não permitir diferença significativa
de capital inicial.

Criar:

INITIAL_CAPITAL_MATCH_ERROR_PCT.

Gate desejado:

<=0.01%.

==================================================
14. MICRO-HOT DUAS COLUNAS SOMENTE
==================================================

Hard invariant:

MICRO_HOT_COLUMNS=2.

Nunca:

3
4
5
adaptive count.

Sem crescimento automático de colunas MICRO neste modelo.

C1 e C2 entram como ordens distintas.

FIFO:

PUBLIC
→ MICRO C1
→ MICRO C2.

==================================================
15. SLOT DA MICRO-HOT
==================================================

Cada ordem MICRO:

SLOT_COUNT=1.

Portanto:

C1=1slot
C2=1slot.

Não aplicar HOT multiplier3
à MICRO-HOT.

Isso é proposital.

O capital veio de:

FAR14=1slot
FAR15=1slot.

==================================================
16. HOT PRINCIPAL NÃO MUDA
==================================================

A HOT permanece:

rank1-5

C1=3slots
C2=3slots
C3=3slots.

Não aumentar para C4/C5 neste M027.

Queremos isolar MICRO-PRICE RESOLUTION.

==================================================
17. MOVIMENTO DA HOTLINE
==================================================

Preservar M026:

hotline moves causally
whole coarse-grid logic
sem inactivity trigger.

Quando hotline muda:

nova MICRO-HOT target também muda.

Novo target:

BUY:
new_H -0.00005

SELL:
new_H +0.00005.

==================================================
18. ORDENS MICRO ANTIGAS
==================================================

Não teleportar MICRO order antiga.

Se hotline move:

old MICRO order mantém:

absolute price
quantity
slot epoch
FIFO age
cost basis se preenchida.

Se old MICRO order:

ZERO FILL
e
não pertence mais ao active MICRO target:

ela pode ser cancelada
somente via:

CANCEL_REQUEST
→ CANCEL_ACK
→ capital reuse.

Se teve qualquer fill:

owned economic lifecycle normal.

No forced loss.

==================================================
19. NÃO DEIXAR MICRO-HOT ACUMULAR INFINITAMENTE
==================================================

Target MICRO físico atual:

EXACTLY2 FREE ENTRY COLUMNS PER SIDE
na current micro price,

subject to funding/cancel ACK.

Ordens MICRO antigas fora da target line
que continuam zero-fill
devem ser drained/cancelled de forma causal.

Nunca manter dezenas de antigas MICRO lines
e chamar isso da mesma estratégia.

==================================================
20. AGED FIFO
==================================================

Se uma ordem antiga MICRO continuar no mesmo preço
após movimento/reversão da hotline:

preservar sua idade.

Não cancelar/recriar apenas para atualizar epoch.

FIFO age é ativo econômico.

==================================================
21. RETURNS
==================================================

Preservar integralmente M026:

owned return priority.

Adaptive profitable boundary.

No fixed one-tick forced address.

No realized negative exit.

No self-fill.

No future data.

==================================================
22. MOBILITY RESERVE
==================================================

Preservar:

8slot-units per asset side.

Não aumentar reserve.

Não financiar MICRO com reserve na inicialização.

MICRO foi financiada pela retirada FAR14/15.

Durante deslocamento:

reserve pode operar conforme política M026.

==================================================
23. FAR14/FAR15 NÃO EXISTEM NO TREATMENT
==================================================

No TREATMENT:

não criar FAR14.

não criar FAR15.

Nem virtualmente como FREE working entries.

Se preço chegar a essas regiões:

a moving grid continua acompanhando a hotline
conforme M026.

Mas a geometria relativa ativa do tratamento
possui apenas:

FAR11
FAR12
FAR13.

==================================================
24. CONTAGEM DE CICLOS
==================================================

Preservar duas métricas:

PHYSICAL_CYCLES

SLOT_EQUIVALENT_CYCLES.

MICRO cycle:

1 physical cycle
=
1 slot-cycle.

HOT cycle:

1 physical
=
3 slot-cycles.

MID:

1 physical
=
2 slot-cycles.

FAR:

1 physical
=
1 slot-cycle.

==================================================
25. MÉTRICA PRIMÁRIA
==================================================

PRIMARY:

DELTA_PHYSICAL_CYCLES_PER_HOUR =
TREATMENT - CONTROL.

SECONDARY:

DELTA_SLOT_CYCLES_PER_HOUR.

Queremos responder:

subdividir a região imediatamente próxima
aumentou quantidade real de roundtrips?

==================================================
26. MÉTRICAS MICRO-HOT
==================================================

Reportar:

MICRO_HOT_PHYSICAL_CYCLES

MICRO_HOT_SLOT_CYCLES

MICRO_C1_CYCLES

MICRO_C2_CYCLES

MICRO_ORDERS_CREATED

MICRO_FULL_FILLS

MICRO_PARTIAL_FILLS

MICRO_OPEN_AT_CUTOFF

MICRO_MEDIAN_ACTIVATION_TO_FILL

MICRO_P95_ACTIVATION_TO_FILL

MICRO_PUBLIC_FIFO_WAIT

MICRO_OWN_FIFO_WAIT

MICRO_PRICE_RECOVERY_WAIT.

==================================================
27. OPORTUNIDADE ADICIONAL
==================================================

Medir:

MICRO_UNIQUE_PRICE_TOUCHES.

Queremos saber se a nova linha
capturou movimentos que:

não teriam tocado HOT rank1
no CONTROL.

Criar:

MICRO_CYCLES_WITHOUT_CONTROL_EQUIVALENT_TOUCH.

Isto deve ser diagnóstico causal do tape,
não alteração da execução.

==================================================
28. CANIBALIZAÇÃO
==================================================

Importante:

MICRO pode roubar fills
que anteriormente teriam chegado ao HOT rank1.

Medir:

HOT_RANK1_CYCLES_CONTROL

HOT_RANK1_CYCLES_TREATMENT

MICRO_CYCLES_TREATMENT.

E:

NET_NEAR_HOT_CYCLE_GAIN =

(MICRO + HOT_RANK1 treatment)
-
(HOT_RANK1 control).

Isso é essencial.

Não chamar MICRO de sucesso
se apenas deslocou os mesmos ciclos
de rank1 para micro.

==================================================
29. FAR LOSS OF COVERAGE
==================================================

Como removemos FAR14/15,
medir o custo da remoção.

CONTROL:

FAR14 cycles/fills/order-time
FAR15 cycles/fills/order-time.

TREATMENT:

essas células inexistem.

Criar:

FAR14_15_CONTROL_PRODUCTIVITY.

Se CONTROL mostrar zero produtividade
e MICRO gerar ciclos adicionais,
a realocação tem evidência favorável.

==================================================
30. FREQUÊNCIA POR DISTÂNCIA
==================================================

Reportar para CONTROL e TREATMENT:

MICRO
RANK1
RANK2
RANK3
RANK4
RANK5
MID
FAR11
FAR12
FAR13
FAR14
FAR15.

Por cada:

physical cycles
slot cycles
fills
order hours
median fill wait.

==================================================
31. MESMO MARKET EVENT NÃO PODE SER DUPLICADO
==================================================

Dentro de cada cenário:

trade quantity consumed once.

CONTROL e TREATMENT são universos independentes.

É permitido que ambos usem
o mesmo historical trade,
porque são contrafactuais separados.

Não compartilhar budgets entre cenários.

==================================================
32. TESTES SINTÉTICOS
==================================================

A.

Coarse hotline=1.00000.

fine tick=0.00001.

MICRO BUY=
0.99995.

MICRO SELL=
1.00005.

Valid prices.

----------------------------------

B.

Historical tick=0.0001.

Attempt micro0.99995.

Must BLOCK/raise.

Nunca quantize silenciosamente.

----------------------------------

C.

Remove:

FAR14
FAR15

releases exactly2 slot-units per side.

----------------------------------

D.

Create:

MICRO C1=1slot
MICRO C2=1slot.

Consumes exactly2 slot-units.

Capital delta zero.

----------------------------------

E.

Initial physical order count remains60.

----------------------------------

F.

Operational slot-units remain140.

----------------------------------

G.

MICRO own FIFO:

public100
C1
C2.

C1 before C2.

----------------------------------

H.

C1 partial blocks C2.

----------------------------------

I.

Hotline move:

old zero-fill MICRO requires cancel ACK
before its capital funds new MICRO.

----------------------------------

J.

Filled old MICRO:
cannot be canceled economically.

Owned return required.

----------------------------------

K.

Control has FAR14/15.
Treatment does not.

----------------------------------

L.

Checkpoint/resume:
same cycles, queues, micro history,
capital and terminal state.

==================================================
33. PRE-RUN ASTRA REVIEW
==================================================

Antes de qualquer replay:

independent source-bound review.

Prefer:

GPT-6 Astra.

Auditor deve verificar:

- actual fine tick;
- no fake half-tick;
- matched control/treatment capital;
- same tape;
- same coarse0.0001 geometry;
- only FAR14/15→MICRO change;
- MICRO exactly2 columns;
- MICRO exactly1slot/order;
- no extra capital;
- no duplicated queue;
- no duplicated trade flow;
- no future data;
- old order FIFO preservation;
- cancel ACK before reuse;
- no realized negative exit.

Se BLOCK:

corrigir antes do replay.

==================================================
34. PREREGISTRATION
==================================================

Criar:

M027_MICRO_HOT_REALLOCATION_OWNER_DIRECTIVE.md

M027_MICRO_HOT_REALLOCATION_PREREGISTRATION.md

M027_MODEL_SPEC.json

M027_JOURNAL.md.

Registrar ambos cenários ANTES do replay:

CONTROL
TREATMENT.

Nenhum terceiro cenário.

==================================================
35. EXECUÇÃO
==================================================

Somente após:

tick validated
dataset validated
Astra PASS
tests PASS
source committed/pushed.

Rodar exatamente:

CONTROL once

TREATMENT once.

Mesmo tape.

Mesmo3h prefix.

Sem rerun.

==================================================
36. GATE
==================================================

Micro-hot mechanics favorable if:

TREATMENT_PHYSICAL_CYCLES
>
CONTROL_PHYSICAL_CYCLES.

Strong frequency evidence if:

TREATMENT_PHYSICAL_CYCLES_PER_HOUR
>=
1.20 × CONTROL_PHYSICAL_CYCLES_PER_HOUR.

Também reportar slot-cycle delta.

Não exigir20% para preservar resultado;
é apenas strong-evidence ruler.

==================================================
37. OWNER SCOREBOARD
==================================================

Responder primeiro:

MODEL=M027

SOURCE_DAY=

VALIDATED_TICK_SIZE=

COARSE_GRID_SPACING=0.0001

MICRO_OFFSET=0.00005

CONTROL_INITIAL_CAPITAL=

TREATMENT_INITIAL_CAPITAL=

CAPITAL_MATCH_ERROR_PCT=

CONTROL_PHYSICAL_CYCLES=

TREATMENT_PHYSICAL_CYCLES=

CONTROL_PHYSICAL_CYCLES_PER_HOUR=

TREATMENT_PHYSICAL_CYCLES_PER_HOUR=

PHYSICAL_DELTA=

PHYSICAL_DELTA_PCT=

CONTROL_SLOT_CYCLES=

TREATMENT_SLOT_CYCLES=

CONTROL_SLOT_CYCLES_PER_HOUR=

TREATMENT_SLOT_CYCLES_PER_HOUR=

MICRO_HOT_PHYSICAL_CYCLES=

MICRO_C1_CYCLES=

MICRO_C2_CYCLES=

CONTROL_HOT_RANK1_CYCLES=

TREATMENT_HOT_RANK1_CYCLES=

NET_NEAR_HOT_CYCLE_GAIN=

CONTROL_FAR14_CYCLES=

CONTROL_FAR15_CYCLES=

MICRO_HOT_STRONG_FREQUENCY_GATE_PASS=

AUDIT=

STATUS=

==================================================
38. CONCLUSÃO OBRIGATÓRIA
==================================================

Responder:

1. Retirar FAR14/FAR15 e colocar o mesmo capital
   numa MICRO-HOT de2 colunas aumentou frequência física?

2. A MICRO-HOT criou ciclos novos
   ou apenas canibalizou HOT rank1?

3. Quanto de produtividade foi perdido
   ao remover FAR14/FAR15?

4. C1 e C2 da MICRO-HOT foram ambas produtivas?

5. A resolução adicional de preço
   parece mais eficiente do que manter cobertura distante?

==================================================
39. NÃO CRIAR M028
==================================================

Ao fim:

não adicionar terceira coluna MICRO.

não alterar micro slot size.

não aumentar HOT columns.

não alterar mobility reserve.

não testar outro offset.

não testar outro dia.

não criar M028 automaticamente.

OWNER decide próximo passo.
