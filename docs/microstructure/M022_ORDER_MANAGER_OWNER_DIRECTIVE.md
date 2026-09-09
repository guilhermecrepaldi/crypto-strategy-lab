# OWNER DIRECTIVE — M022 ORDER MANAGER V2
# SAME M021 ECONOMICS · RETURN PRIORITY · FLOATING QUOTE WINDOW
# 200 ECONOMIC LANES · MAX 160 ACTIVE ORDERS · SAME 5H CONTROL

Repo: crypto-strategy-lab

Antes de qualquer alteração, leia integralmente:

docs/research/CURRENT_STATE.md
docs/research/M021_JOURNAL.md
docs/microstructure/M021_DENSE_PING_PONG_PREREGISTRATION.md
docs/microstructure/M021_MODEL_SPEC.json
reports/usdcusdt/M021-5h-result.json
reports/usdcusdt/M021-5h-autopsy.md
reports/usdcusdt/M021-preflight-independent-review.md
reports/usdcusdt/M021-post-run-independent-review.md
src/crypto_strategy_lab/microstructure/zonal_ping_pong.py
scripts/run_dense_ping_pong.py
tests/test_dense_ping_pong.py
tests/test_run_dense_ping_pong.py

M021 permanece IMUTÁVEL.

M021 baseline:

TOTAL_COMPLETE_CYCLES=19
CYCLES_PER_HOUR=3.8
BUY_FIRST_CYCLES=4
SELL_FIRST_CYCLES=15
TOTAL_FILL_EVENTS=42
FILLED_SLOTS=10
PRODUCTIVE_SLOTS=7
SELF_CROSS_RECHECKS=183152
POST_ONLY_REJECTIONS=182

M021 provou que o ping-pong funciona mecanicamente,
mas revelou conflito entre ORDENS LIVRES e ORDENS DE RETORNO.

Criar nova identidade:

M022

se M022 estiver livre no registry.

==================================================
1. ÚNICA HIPÓTESE DO M022
==================================================

NÃO mudar a estratégia econômica.

NÃO mudar distância.

NÃO mudar notional.

NÃO mudar período.

NÃO mudar dados.

NÃO mudar execução.

NÃO mudar fila.

NÃO mudar taxa.

NÃO mudar capital econômico total.

A única hipótese é:

UM GERENCIADOR DE ORDENS MAIS INTELIGENTE
AUMENTA O THROUGHPUT DO MESMO PING-PONG.

M021:

free orders could block owned returns.

M022:

OWNED RETURN ORDERS HAVE ABSOLUTE PRIORITY
OVER UNFILLED FREE ENTRY ORDERS.

Além disso, as free entries passam a formar uma
FLOATING ACTIVE WINDOW ao redor do mercado.

==================================================
2. MESMO CONTROLE ECONÔMICO DO M021
==================================================

Usar exatamente:

SOURCE_DAY=2025-01-01

START=
2025-01-01T00:00:00Z

END_EXCLUSIVE=
2025-01-01T05:00:00Z

Mesmo dataset.

Mesmo L2.

Mesmos canonical trades.

Mesmo execution profile.

Mesmo queue model.

Mesmo latency/cancel latency.

Mesmo historical tick:

0.0001

Mesmo normalized quantity:

1 USDC

Mesmo fee assumption:

ZERO_CONDITIONAL_FROZEN_PROFILE

Mesmo:

NEGATIVE_EXIT_ALLOWED=false.

Mesmo:

PING_PONG_DISTANCE_TICKS=1.

Mesmo initial causal book / anchor rules.

==================================================
3. CONTINUA NÃO EXECUTÁVEL EM LIVE
==================================================

ORDER_MODE=

NORMALIZED_1_USDC_NON_EXECUTABLE_ORDER_MANAGER_PROBE

Continuar bypassando SOMENTE minNotional.

Não bypassar:

queue
latency
post-only
trade direction
price priority
self-trade protection
global liquidity
capital ownership
causality.

Não chamar este resultado de Binance-live-executable.

==================================================
4. NÃO REMOVER AS 200 BANCAS
==================================================

CRÍTICO.

Continuar possuindo:

100 BUY-FIRST ECONOMIC LANES
+
100 SELL-FIRST ECONOMIC LANES.

TOTAL_ECONOMIC_LANES=200.

Cada lane continua com:

lane identity
side identity
capital ownership
cost basis
cycle lineage.

NÃO reduzir as bancas econômicas para 10, 20 ou outra quantidade.

==================================================
5. REDUZIR APENAS ORDENS SIMULTANEAMENTE ATIVAS
==================================================

M021 permitia até:

200 active orders.

M022:

MAX_SIMULTANEOUS_OPEN_ORDERS=160.

Logo:

40 economic lanes podem permanecer PARKED/FREE
a qualquer instante.

Quando não houver obrigação econômica:

TARGET_FREE_BUY_LANES≈80
TARGET_FREE_SELL_LANES≈80.

Mas 80/80 NÃO é hard invariant.

Owned returns possuem prioridade.

Portanto a composição pode temporariamente ser:

77 free BUY
79 free SELL
4 owned returns

etc.

Hard rule:

TOTAL_PENDING_PLUS_ACTIVE_ORDERS <= 160.

==================================================
6. 40 LANES PARKED NÃO MORREM
==================================================

As 40 lanes fora da janela:

NÃO são deletadas.

NÃO perdem capital.

NÃO mudam de dono.

Estado:

PARKED_FREE.

Podem voltar à operação quando o manager decidir
que sua liquidez é mais útil perto do preço atual.

==================================================
7. FIXED PRICE LATTICE + FLOATING QUOTE WINDOW
==================================================

Preservar o universo de preços registrado no M021.

Não usar futuro.

Mas agora:

FREE ENTRY ORDERS MAY MOVE ACROSS ELIGIBLE GRID ADDRESSES.

Ou seja:

a MALHA DE PREÇOS permanece conhecida/fixa,

mas a localização de uma FREE QUOTE pode mudar.

Somente:

UNFILLED FREE ENTRY

pode flutuar.

Nunca mover economicamente:

filled inventory
cost basis
owned return obligation.

==================================================
8. JANELA FLUTUANTE
==================================================

Em cada reconciliation causal válida:

calcular current causal mid.

Entre os níveis elegíveis disponíveis:

manter as FREE BUY entries
concentradas nos níveis mais próximos ABAIXO do mercado.

manter as FREE SELL entries
concentradas nos níveis mais próximos ACIMA do mercado.

Não precisa ficar exatamente 80/80
quando owned returns ocuparem slots.

Objetivo:

CAPITAL LIVRE DEVE FICAR PRÓXIMO DO MERCADO.

Não deixar uma free entry a dezenas de ticks de distância
se existir lane estacionada ou quote livre que pode ser
reposicionada causalmente para uma região mais útil.

==================================================
9. QUANDO O PREÇO DESCE
==================================================

Se o mercado cair:

identificar BUY coverage abaixo.

Se começam a faltar free BUY quotes próximas:

cancelar primeiro as FREE ORDERS mais distantes
e menos úteis.

Depois do CANCEL_ACK:

reutilizar somente capital compatível
para repostar BUY entries próximas abaixo do preço.

Não criar capital.

Não converter USDC em USDT silenciosamente.

Não vender inventário com prejuízo.

==================================================
10. QUANDO O PREÇO SOBE
==================================================

Comportamento espelhado.

Se começam a faltar SELL quotes próximas acima:

cancelar FREE SELLs distantes.

Depois do CANCEL_ACK:

repostar USDC livre em SELLs mais próximas do mercado.

Nunca vender USDC que já pertence a outra obrigação econômica.

==================================================
11. HIERARQUIA ABSOLUTA DO MANAGER
==================================================

Implementar prioridades:

P0 = OWNED RETURN ORDER
P1 = EXISTING OWNED ECONOMIC OBLIGATION
P2 = NEAR-MARKET FREE ENTRY
P3 = DISTANT FREE ENTRY
P4 = PARKED FREE LANE

P0 sempre vence P2/P3/P4.

==================================================
12. REGRA CENTRAL — RETURN PREEMPTION
==================================================

Este é o principal ajuste do M022.

Exemplo observado no M021:

S006 sells @1.0026

required owned BUYBACK:
1.0025

but free S005 SELL existed:
1.0025

M021:

BUYBACK BLOCKED BY SELF-CROSS.

M022:

OWNED RETURN WINS.

Fluxo obrigatório:

1. Detect return target conflict.

2. Identificar se ordem conflitante é FREE ENTRY.

3. Se FREE:
   emitir CANCEL.

4. NÃO considerar capital liberado antes do CANCEL_ACK.

5. Após CANCEL_ACK:
   submeter OWNED RETURN.

6. RETURN entra na fila normalmente.

7. Sem internal fill.

8. Sem deslocar preço.

9. Sem ignorar queue.

10. Sem usar trade que ocorreu antes da ativação do return.

==================================================
13. NÃO REMOVER SELF-TRADE PROTECTION
==================================================

SELF_CROSS PROTECTION permanece ON.

Nós NÃO queremos permitir self-trade.

A mudança é:

não bloquear eternamente um return
só porque uma FREE order nossa ocupa aquele nível.

Nós removemos a FREE order primeiro.

Depois submetemos o return.

==================================================
14. OWNED RETURN VS OWNED RETURN
==================================================

Se dois OWNED RETURNS reais entrarem em conflito:

NÃO cancelar obrigação econômica.

NÃO internalizar.

NÃO inventar fill.

Aplicar prioridade determinística:

mais antigo ECONOMIC_OBLIGATION_TIME primeiro.

Tie-break:

source entry activation/fill time
then
lane id/order id.

O return posterior espera.

Registrar:

OWNED_RETURN_CONFLICTS.

Isso não deve ser resolvido silenciosamente.

==================================================
15. RESERVA DE PREÇO PARA RETORNO
==================================================

Quando uma entry preencher e seu return target se tornar conhecido:

marcar imediatamente:

RETURN_PRICE_CLAIM.

O manager não deve criar uma nova FREE opposite entry
naquele preço enquanto a claim estiver válida.

Assim evitamos recriar o mesmo conflito repetidamente.

==================================================
16. FREE QUOTE CANCELLATION
==================================================

Só podem ser canceladas/relocalizadas:

FREE
UNFILLED
ENTRY orders.

Nunca cancelar por conveniência:

filled position
owned exit
owned buyback
partial economic obligation.

Para partial fill:

a parcela já preenchida gera obrigação econômica.

A parcela ainda não preenchida deve seguir a política
de partial ownership preregistrada.

Não misturar as duas.

==================================================
17. NÃO RESETAR ECONOMIA AO REPOSICIONAR
==================================================

Cancel/repost de FREE order:

não cria ciclo.

não cria lucro.

não reseta cost basis de nada preenchido.

não cria nova banca.

não duplica reserva.

não duplica USDT.

não duplica USDC.

==================================================
18. ORDEM DE EVENTOS CAUSAL
==================================================

Preservar uma ordenação explícita.

Em cada market event:

A. aplicar book/trade elegível aos orders que já estavam ativos

B. concluir fills

C. atualizar economic obligations

D. processar CANCEL_ACK já elegíveis

E. executar manager reconciliation

F. decidir cancel/submission

G. novos orders recebem latency

H. novos orders NÃO podem preencher no evento que os criou

Nenhuma decisão pode ver informação posterior.

==================================================
19. ROLLING/FLOATING MANAGER NÃO PODE OLHAR FUTURO
==================================================

A decisão de mover free liquidity usa somente:

current causal book
current owned inventory
current pending/active orders
current free balances
registered fixed lattice.

Não usar:

next trade
next candle
future high/low
full 5h path.

==================================================
20. NÃO USAR RANGE ANUAL PARA SELECIONAR A JANELA
==================================================

M022 não deve otimizar P80/P90/P95.

A janela reage ao preço causal presente.

Histórico anual não escolhe onde repostar.

==================================================
21. CAPITAL
==================================================

Preservar exatamente a lógica econômica inicial do M021:

100 BUY-first lanes
+
100 SELL-first lanes.

Mesmo normalized one-USDC economics.

Sem nova injeção.

NO_CAPITAL_INJECTION=true.

A redução 200→160 open orders
não autoriza retirar economic capital.

O capital das 40 parked lanes continua contabilizado como FREE/PARKED.

==================================================
22. RETURNS PODEM USAR HEADROOM
==================================================

Os 40 slots removidos do mercado funcionam como folga operacional.

O manager NÃO deve preencher necessariamente os 160
com free entries se houver returns prestes a ser colocados.

RETURNS FIRST.

Depois:

free entries fill remaining capacity.

==================================================
23. NÃO ALTERAR DISTÂNCIA
==================================================

Continuar:

ENTRY → RETURN = 1 historical tick.

Não testar:

2 ticks
3 ticks
dynamic spread
OBI
OFI
volatility
fair value.

Essas hipóteses ficam para depois.

==================================================
24. NÃO ALTERAR QUEUE MODEL
==================================================

Continuar exatamente com a autoridade física M021:

displayed depth at activation
no cancellation credit
strict compatible trade-through
global one-use liquidity
better-price priority
activation time
order id.

Não tornar fila mais otimista para aumentar ciclos.

==================================================
25. MÉTRICA PRIMÁRIA
==================================================

PRIMARY:

TOTAL_COMPLETE_CYCLES_IN_5H.

Comparação direta:

M021_CONTROL=19.

M022_RESULT=X.

Calcular:

CYCLE_DELTA=X-19

CYCLE_MULTIPLIER=X/19

CYCLES_PER_HOUR.

==================================================
26. MÉTRICAS DO NOVO MANAGER
==================================================

Registrar obrigatoriamente:

RETURN_PREEMPTIONS

FREE_ORDERS_CANCELED_FOR_RETURN

FREE_ORDERS_CANCELED_FOR_FLOAT

FREE_ORDERS_REPOSTED

RETURN_SUBMISSIONS

RETURN_FILLS

RETURN_WAIT_TIME_MEAN

RETURN_WAIT_TIME_MEDIAN

RETURN_WAIT_TIME_P95

RETURN_BLOCKED_BY_FREE_ORDER_COUNT

RETURN_BLOCKED_BY_OWNED_RETURN_COUNT

SELF_CROSS_RECHECKS

POST_ONLY_REJECTIONS

QUEUE_BLOCKED_EVENTS

MAX_SIMULTANEOUS_OPEN_ORDERS

MEAN_ACTIVE_OPEN_ORDERS

MIN_ACTIVE_OPEN_ORDERS_AFTER_WARMUP

PARKED_LANES_MEAN.

==================================================
27. UTILIZAÇÃO DA JANELA
==================================================

Quero saber se os 160 slots realmente acompanharam o mercado.

Registrar:

UNIQUE_LANES_USED

UNIQUE_PRICE_LEVELS_USED

UNIQUE_PRODUCTIVE_LANES

PERCENT_ACTIVE_ORDERS_WITHIN_5_TICKS_OF_MID

PERCENT_ACTIVE_ORDERS_WITHIN_10_TICKS_OF_MID

TIME_WEIGHTED_DISTANCE_FROM_MID.

==================================================
28. CONCENTRAÇÃO
==================================================

Continuar relatório:

TOP_10_LANES_BY_CYCLES

TOP_10_PRICE_LEVELS_BY_CYCLES

BUY_FIRST_CYCLES
SELL_FIRST_CYCLES.

Não gerar gráfico ainda.

==================================================
29. FINANCE SANITY
==================================================

Preservar:

INITIAL_USDT
INITIAL_USDC
INITIAL_MARKED_EQUITY

FINAL_USDT
FINAL_USDC
FINAL_MARKED_EQUITY

REALIZED_NET_PNL
UNREALIZED_PNL

SUM_ROUNDTRIP_CYCLE_PROFIT.

Nenhum destes é a métrica de seleção principal nesta rodada.

==================================================
30. AUDITORIA
==================================================

Independent audit deve provar:

no duplicated liquidity
no duplicated capital
no future data
no self trade
no negative exits
all CANCEL_ACKs reconciled
all return preemptions traceable
all reassignments conserve ownership
parked capital conserved
all cycles reconstructible.

==================================================
31. TESTES SINTÉTICOS OBRIGATÓRIOS
==================================================

Criar casos específicos:

A.
free SELL occupies return BUY price
→ free SELL canceled
→ ACK
→ return BUY submitted
→ no self trade.

B.
free BUY occupies return SELL price
→ same mirror behavior.

C.
owned return conflicts with owned return
→ deterministic defer
→ no cancel of owned obligation.

D.
price moves down
→ far free quotes canceled
→ nearest eligible BUY quotes created
→ capital conservation.

E.
price moves up
→ mirror behavior for SELL.

F.
160-order hard cap never exceeded.

G.
parked lanes can reactivate.

H.
newly submitted order cannot fill on triggering event.

I.
cancel does not release funds before ACK.

J.
checkpoint/resume produces identical state/result.

==================================================
32. NÃO FAZER PARAMETER SWEEP
==================================================

Uma configuração apenas:

200 economic lanes
160 max active orders
1 USDC normalized
1 tick ping-pong
same 5h
floating free quote manager
owned-return priority.

Não testar 140/150/170/180.

Não escolher melhor resultado.

==================================================
33. STATUS CIENTÍFICO
==================================================

M022 é:

ORDER_MANAGER_CONTROLLED_COMPARISON.

É desenvolvimento.

Não é live executable.

Não é prova de rentabilidade.

Não é autorização Day2.

==================================================
34. GITHUB / GATES
==================================================

Preregister M022 ANTES do replay.

Commit/push preregistration.

Review source.

Rodar uma vez.

Commit/push resultado separado.

Atualizar:

CURRENT_STATE
M022_JOURNAL
model registry
M022 result
M022 autopsy.

M021 permanece intacto.

Não autorizar M023 automaticamente.

==================================================
35. RESPOSTA FINAL DO OWNER
==================================================

Responder primeiro:

MODEL=M022
PERIOD=5H

TOTAL_CYCLES=
CYCLES_PER_HOUR=

M021_BASELINE=19
DELTA_VS_M021=
MULTIPLIER_VS_M021=

BUY_FIRST_CYCLES=
SELL_FIRST_CYCLES=

TOTAL_FILLS=

RETURN_PREEMPTIONS=
FREE_CANCELS_FOR_RETURN=
FREE_CANCELS_FOR_FLOAT=

SELF_CROSS_RECHECKS=
POST_ONLY_REJECTIONS=
QUEUE_BLOCKED_EVENTS=

UNIQUE_PRODUCTIVE_LANES=

FINAL_MARKED_EQUITY=

AUDIT=

MAIN_LIMITER=

E por fim responder:

DID_ORDER_MANAGEMENT_IMPROVE_THROUGHPUT=YES/NO.

==================================================
36. INTERPRETAÇÃO
==================================================

Não otimizar após ver o resultado.

Se M022 produzir:

20 ciclos,
registrar 20.

Se produzir:

200,
registrar 200.

Se produzir:

0,
registrar 0.

Nenhuma alteração automática.

A única pergunta desta rodada é:

COM A MESMA ESTRATÉGIA DO M021,
MAS COM RETURN PRIORITY E FREE QUOTES FLUTUANTES,
O GERENCIAMENTO INTELIGENTE DE ORDENS
AUMENTA A ROTAÇÃO NAS MESMAS CINCO HORAS?
