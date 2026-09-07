# OWNER CORRECTION — COMPOUNDING IS MANDATORY

# FIXED_NOTIONAL_100_USDT AS PRIMARY STRATEGY IS INVALID

Esta instrução corrige imediatamente uma interpretação incompatível com a estratégia do OWNER.

A estratégia NUNCA deve ser tratada como uma operação principal de notional fixo em US$100.

O capital operacional é geométrico e deve crescer com os lucros realizados.

==================================================

1. INVALIDAR A INTERPRETAÇÃO FIXED NOTIONAL
   ==================================================

Qualquer configuração, replay, relatório ou conclusão que trate:

FIXED_NOTIONAL_100_USDT

como:

* estratégia principal;
* sizing operacional real;
* regra de capital;
* base para estimar crescimento da banca;

está:

INVALID_FOR_OWNER_STRATEGY.

Preservar esses artifacts apenas como:

AUXILIARY_DIAGNOSTIC_RULER

se ainda tiverem valor para microestrutura/fill analysis.

Não apagar.

Mas NÃO usar seus resultados como previsão da estratégia real.

==================================================
2. CAPITAL MODE CANÔNICO
========================

A autoridade passa a ser:

CAPITAL_MODE=COMPOUNDING

POSITION_SIZING=
USE_AVAILABLE_OPERATING_BANK

A cada novo ciclo:

o notional deve ser determinado pela Operating Bank atual,

respeitando:

* Binance quantity filters;
* step size;
* min/max quantity;
* min/max notional;
* liquidity;
* fillability;
* rounding;
* future capacity constraints.

Não existe:

TARGET_NOTIONAL=100

depois da inicialização.

==================================================
3. CAPITAL INICIAL
==================

OPERATING_BANK_INITIAL=100 USDT

RECOVERY_RESERVE_INITIAL=5 USDT

TOTAL_INITIAL_EQUITY=105 USDT.

Os US$100 são apenas o capital operacional INICIAL.

Não são o tamanho fixo de todas as operações.

==================================================
4. LUCRO DE CADA CICLO
======================

Para cada ciclo com lucro líquido positivo:

P = REALIZED_NET_PROFIT

calcular:

RESERVE_CONTRIBUTION =
5% * P

OPERATING_REINVESTMENT =
95% * P.

Então:

Operating Bank cresce em 95% do lucro líquido.

Reserve cresce em 5% do lucro líquido.

==================================================
5. EXEMPLO OBRIGATÓRIO
======================

Se:

Operating=100
Reserve=5

e um ciclo gerar:

Net Profit=1

então:

Reserve contribution=0.05

Operating reinvestment=0.95

novo estado:

Operating=100.95
Reserve=5.05.

A próxima ordem deve usar aproximadamente:

100.95 USDT

e NÃO:

100 USDT.

Depois disso:

cada lucro seguinte também aumenta o notional do ciclo subsequente.

==================================================
6. PROGRESSÃO GEOMÉTRICA
========================

O mecanismo central do produto é:

Banca
→
trade
→
net profit
→
5% reserve
+
95% compounding
→
banca maior
→
trade maior
→
novo lucro
→
repeat.

Portanto:

COMPOUNDING é parte da identidade da estratégia.

Não é uma análise opcional posterior.

==================================================
7. RESERVA
==========

Recovery Reserve:

TARGET_RATIO≈5% da Operating Bank.

Funding:

5% de todo positive realized net profit.

A reserva:

* cresce junto com a banca;
* é usada para releases;
* pode cair abaixo de 5%;
* deve reconstruir;
* nunca deve zerar.

Ela NÃO substitui o compounding da Operating Bank.

==================================================
8. RELEASE E RESTAURAÇÃO
========================

Quando houver release:

a perda realizada reduz economicamente a Total Equity.

A Recovery Reserve pode transferir exatamente o necessário para restaurar a capacidade operacional conforme a regra congelada.

Depois:

o motor continua com a Operating Bank restaurada

e volta ao compounding normalmente.

==================================================
9. MAX LOCK
===========

Mantém:

MAX_POSITION_LOCK=24 HOURS

como hard OWNER constraint.

Objetivo:

nenhum capital operacional permanecer preso por dias/semanas/meses.

Em 24h:

MANDATORY_UNLOCK_STATE.

Não fabricar fill inexistente.

Se não houver saída executável:

HARD_LOCK_VIOLATION.

==================================================
10. REALITY HARNESS DEVE PRESERVAR COMPOUNDING
==============================================

Fila, latência, partial fills, spread, taxas e regras Binance devem ser aplicados AO CAPITAL ATUAL.

Exemplo:

se Operating Bank cresceu para 137.42 USDT,

o próximo BUY deve tentar usar aproximadamente:

137.42 USDT

sujeito à execução realista.

Não voltar artificialmente para US$100.

==================================================
11. FIXED NOTIONAL PERMITIDO APENAS COMO DIAGNÓSTICO
====================================================

Se desejado, manter uma régua paralela:

AUX_FIXED_NOTIONAL_100

apenas para responder perguntas como:

* eficiência por US$100;
* fill retention independente de crescimento;
* PnL por unidade de capital.

Mas:

AUX_FIXED_NOTIONAL_100 != STRATEGY.

Nunca usar esse ruler para:

FINAL_BANK
FINAL_EQUITY
GEOMETRIC_GROWTH
OWNER_PROJECTION.

==================================================
12. RESULTADOS DA CAMPANHA ANTIGA
=================================

O resultado:

NET_PNL_FIXED_100≈22.41 USDT

é apenas:

AUXILIARY_EXECUTION_DIAGNOSTIC

da campanha anterior.

Ele NÃO representa:

“quanto a estratégia do OWNER ganhou”.

Registrar explicitamente no Git:

FIXED_100_RESULT_NOT_OWNER_STRATEGY_RETURN=YES.

==================================================
13. NOVA ESTRATÉGIA DEVE SER NOVO Mn
====================================

Como já autorizado:

* 5% reserve funding;
* proportional reserve;
* 24h hard lock;
* compounding obrigatório;

constituem nova estratégia completa.

Verificar registry.

Determinar NEXT_FREE_MODEL_ID.

Não sobrescrever B10.

==================================================
14. PREREGISTRATION DEVE CONTER
===============================

Congelar:

CAPITAL_MODE=COMPOUNDING

INITIAL_OPERATING=100

INITIAL_RESERVE=5

PROFIT_TO_RESERVE=5%

PROFIT_TO_OPERATING=95%

POSITION_SIZE=AVAILABLE_OPERATING_BANK

RESERVE_TARGET_RATIO=5%

MAX_LOCK=24H.

Esses campos devem entrar no model hash.

==================================================
15. RELATÓRIOS OBRIGATÓRIOS
===========================

Para cada checkpoint do novo Mn reportar:

SIMULATION_TIMESTAMP=

OPERATING_BANK=

RESERVE=

TOTAL_EQUITY=

CURRENT_POSITION_NOTIONAL=

CYCLES=

NET_POSITIVE_CYCLES=

CUMULATIVE_NET_PROFIT=

CUMULATIVE_RESERVE_FUNDING=

CUMULATIVE_RELEASE_LOSS=

ZERO_DAYS=

ACTIVE_DAYS=

MAX_HOLD=

HARD_LOCK_VIOLATIONS=

REALITY_RETENTION=

==================================================
16. CURVA DE CAPITAL
====================

Gerar obrigatoriamente:

equity curve

operating bank curve

reserve curve

cycle notional curve.

Salvar também checkpoints de capital em:

DAY_1

DAY_7

DAY_30

DAY_90

FINAL.

==================================================
17. PERGUNTA ECONÔMICA PRINCIPAL
================================

A pergunta da nova campanha é:

COMEÇANDO COM:

Operating=100
Reserve=5

E REINVESTINDO 95% DE TODO LUCRO LÍQUIDO,

COM 5% PARA A RESERVA,

APÓS FILLS, FILA, LATÊNCIA, FEES, RELEASES E MAX LOCK DE 24H:

QUANTO A BANCA REALMENTE CRESCE?

==================================================
18. OUTPUT DO OWNER
===================

Quero respostas diretas como:

DAY_1:
Operating=
Reserve=
Total Equity=
Profit=

DAY_7:
Operating=
Reserve=
Total Equity=
Profit=

DAY_30:
...

FINAL:
...

Nunca substituir isso por:

“PnL fixed 100”.

==================================================
19. GITHUB JOURNAL
==================

Atualizar imediatamente o journal canônico registrando a correção:

TYPE=OWNER_CAPITAL_POLICY_CORRECTION

PREVIOUS_INTERPRETATION=
FIXED_NOTIONAL_100_AS_PRIMARY

STATUS=
INVALID_FOR_OWNER_STRATEGY

CANONICAL_CAPITAL_MODE=
COMPOUNDING

REINVESTMENT=
95%_OF_NET_POSITIVE_PROFIT

RESERVE_FUNDING=
5%_OF_NET_POSITIVE_PROFIT

POSITION_SIZING=
CURRENT_AVAILABLE_OPERATING_BANK.

==================================================
20. TRATAMENTO DO RUN ATUAL
===========================

Se a execução atual ainda estiver usando FIXED_NOTIONAL_100 como sizing principal:

interromper após preservar checkpoint.

Classificar:

SUPERSEDED_BY_OWNER_CAPITAL_POLICY_CORRECTION.

Não continuar gastando recursos em um sizing incompatível.

==================================================
21. NOVA EXECUÇÃO
=================

Depois de:

* corrigir preregistration;
* corrigir implementation;
* corrigir tests;
* audit PASS;

executar imediatamente o novo Mn com:

COMPOUNDING.

Não pedir nova autorização.

==================================================
22. TESTES OBRIGATÓRIOS
=======================

Adicionar testes provando:

a) lucro aumenta próximo notional;

b) 5% do lucro vai para reserve;

c) 95% do lucro vai para operating;

d) nenhum reset para 100 ocorre entre ciclos;

e) release/restoration preserva a regra de capital;

f) position sizing usa current bank;

g) compounding funciona sob partial fills;

h) compounding respeita Binance filters;

i) reserve usage não é contabilizado como lucro;

j) withdrawals não existem nesta campanha.

==================================================
23. SAQUES
==========

Não implementar saque do OWNER nesta campanha.

Saque será política separada futura.

Por enquanto:

NO_OWNER_WITHDRAWALS.

Todo lucro não destinado à reserva continua no compounding.

==================================================
24. CAPACITY
============

Se a banca crescer a ponto de o próprio tamanho prejudicar:

fill probability
queue
slippage
depth
market impact,

não limitar silenciosamente para US$100.

Registrar:

CAPACITY_LIMIT_REACHED.

Isso deve abrir estudo futuro de:

* 2 bancos;
* múltiplos ranges;
* outra paridade.

==================================================
25. REGRA FINAL
===============

US$100 é STARTING CAPITAL.

NÃO FIXED NOTIONAL.

A estratégia é geométrica.

O tamanho de cada ciclo acompanha a Operating Bank atual.

5% do lucro líquido positivo vai para Recovery Reserve.

95% do lucro líquido positivo é reinvestido.

A reserva serve para manter o motor rodando.

Max lock = 24h.

Se qualquer código, relatório ou run contradizer isso:

FAIL CLOSED.

OWNER_CAPITAL_POLICY=COMPOUNDING

FIXED_NOTIONAL_PRIMARY=FORBIDDEN

RESERVE_FUNDING=5%

OPERATING_REINVESTMENT=95%

MAX_LOCK=24H

QUALITY_FIRST=ON
