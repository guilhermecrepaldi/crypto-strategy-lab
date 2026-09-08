# OWNER OVERRIDE — CONTINUOUS COMPOUNDING ENGINE

# 3 OPERATING QUEUES + 1 ACTIVE-RESERVE QUEUE

# OBJECTIVE: THE MACHINE SHOULD PRACTICALLY NEVER STOP

Esta instrução substitui qualquer política anterior incompatível.

A visão do OWNER passa a ser:

O sistema não é apenas uma estratégia de um único lote.

É um MOTOR DE CAPITAL que:

1. opera continuamente;
2. reinveste automaticamente;
3. constrói uma Recovery Reserve proporcional;
4. usa essa reserve quando necessário;
5. permite que parte da reserve também produza;
6. distribui capital entre filas independentes para reduzir capital parado;
7. prioriza MOTOR UPTIME acima de elegância operacional.

QUALITY_FIRST=ON.

TOKEN_SAVING_PRIORITY=OFF.

==================================================

1. OBJETIVO CENTRAL
   ==================================================

PRIMARY_OBJECTIVE=

MAXIMIZE_CONTINUOUS_PRODUCTIVE_CAPITAL.

Queremos:

MOTOR_UPTIME -> 100%

ZERO_CYCLE_DAYS -> 0

CAPITAL_IDLE_TIME -> mínimo

MAX_POSITION_LOCK -> mínimo

COMPOUNDING -> contínuo.

Não otimizar simplesmente:

few releases
few queues
few trades.

O objetivo é:

MANTER CAPITAL PRODUTIVO.

==================================================
2. NOVO MODELO
==============

Esta arquitetura altera materialmente:

* capital allocation;
* number of queues;
* reserve behavior;
* reserve investment;
* position management;
* release policy;
* compounding.

Portanto:

CRIAR NOVO Mn.

Não editar B10.

Não reutilizar model ID existente.

Verificar registry físico.

MODEL_ID=<NEXT_FREE_MODEL_ID>

STRATEGY_NAME=
CONTINUOUS_MULTI_QUEUE_RECOVERY

HISTORICAL_ANCESTOR=
B10_FROZEN

B10 continua como evidência histórica.

==================================================
3. CAPITAL INICIAL
==================

Canonical first study:

OPERATING_CAPITAL_INITIAL=100 USDT

RECOVERY_RESERVE_INITIAL=10 USDT

TOTAL_INITIAL_EQUITY=110 USDT.

Os US$100 são capital inicial.

Nunca notional fixo.

==================================================
4. COMPOUNDING OBRIGATÓRIO
==========================

CAPITAL_MODE=COMPOUNDING.

Todo capital operacional disponível deve continuar participando do crescimento.

A cada ciclo líquido positivo:

NET_PROFIT=P

RESERVE_FUNDING=
10% * P

OPERATING_REINVESTMENT=
90% * P.

Não resetar order notional para 100.

Nunca.

==================================================
5. RESERVE FLOOR
================

Recovery Reserve possui:

TARGET_MIN_RATIO=10% da Operating Capital.

10% é PISO ESTRUTURAL DESEJADO.

Não é teto.

A reserve pode crescer:

10%
15%
20%
30%
ou mais

se:

* releases forem poucos;
* funding superar consumption;
* Active Reserve produzir lucro.

Não cortar reserve automaticamente em 10%.

==================================================
6. RESERVE NEVER ZERO
=====================

Hard invariant:

RECOVERY_RESERVE > 0.

Nunca permitir:

R <= 0.

A estratégia precisa possuir:

RESERVE_SURVIVAL_FLOOR.

Preregister um piso operacional estritamente positivo.

Não permitir uma release que matematicamente zere a reserve.

==================================================
7. RESERVE É CAPITAL PRODUTIVO
==============================

A Recovery Reserve não deve necessariamente permanecer 100% ociosa.

Dividir conceitualmente:

CORE_RESERVE

e

ACTIVE_RESERVE.

CORE_RESERVE existe para:

* releases;
* emergency unlock;
* preservar continuidade do motor.

ACTIVE_RESERVE pode produzir lucro separadamente.

==================================================
8. ACTIVE RESERVE — LIMITE
==========================

No máximo:

50% DA RECOVERY RESERVE

pode ficar alocada na fila ativa da reserve.

Portanto:

ACTIVE_RESERVE_MAX =
0.50 * TOTAL_RESERVE.

CORE_RESERVE_MIN =
0.50 * TOTAL_RESERVE.

Exemplo:

Reserve=10

até 5 podem operar na Reserve Queue.

Pelo menos 5 permanecem líquidos/protegidos.

Reserve=1,000

até 500 podem operar.

Pelo menos 500 permanecem Core Reserve.

==================================================
9. MÁXIMO DE FILAS
==================

Estrutura máxima por paridade:

QUEUE_1 = OPERATING

QUEUE_2 = OPERATING

QUEUE_3 = OPERATING

QUEUE_4 = ACTIVE_RESERVE

TOTAL_MAX_QUEUES_PER_PAIR=4.

Não ultrapassar 4 nesta versão.

==================================================
10. SIGNIFICADO DAS 3 OPERATING QUEUES
======================================

As três filas principais pertencem à banca operacional.

Não são martingale.

Não são DCA.

Não são grid automático.

São:

INDEPENDENT SERIAL CAPITAL QUEUES.

Cada fila deve possuir:

* capital attribution;
* own LOW;
* own HIGH;
* own position state;
* own entry timestamp;
* own hold age;
* own execution state;
* own PnL;
* own release history.

Nunca misturar ledger entre filas.

==================================================
11. NÃO DUPLICAR A MESMA FILA
=============================

As três filas não devem simplesmente colocar três ordens idênticas no mesmo LOW/HIGH.

O objetivo é:

DIVERSIFY CAPITAL LOCK WITHIN SAME PAIR.

Quando possível, selecionar:

distinct productive ranges.

Evitar competição desnecessária entre nossas próprias ordens.

==================================================
12. QUEUE ALLOCATION
====================

Não congelar arbitrariamente:

33.33 / 33.33 / 33.33.

Preregister uma política causal de distribuição.

Possível princípio:

capital deve ser distribuído entre ranges produtivos conforme:

* causal recent cycle productivity;
* fill probability;
* queue/depth;
* expected capital lock;
* current queue occupancy;
* available operating capital.

Mas:

não otimizar depois de ver resultado.

Congelar antes do replay.

==================================================
13. START SIMPLE
================

Não abrir 3 filas obrigatoriamente desde o primeiro segundo.

A estratégia deve usar:

1 até 3 operating queues

conforme haja ranges independentes suficientemente produtivos.

Se só existir um range bom:

1 fila.

Se existirem dois:

2.

Se existirem três:

3.

Nunca criar fila ruim apenas para atingir quantidade.

==================================================
14. ACTIVE RESERVE QUEUE
========================

QUEUE_4 usa exclusivamente:

ACTIVE_RESERVE.

Nunca utilizar CORE_RESERVE como capital normal de trade.

A Active Reserve Queue:

* pode abrir posição;
* pode gerar profit;
* possui ledger próprio;
* possui own release logic;
* nunca pode comprometer a capacidade mínima de recuperação.

==================================================
15. LUCRO DA ACTIVE RESERVE
===========================

Lucro líquido produzido pela Active Reserve:

primeiro permanece na RECOVERY RESERVE.

Não transferir automaticamente seu lucro para Operating Bank.

Objetivo:

permitir que reserve cresça organicamente.

Assim:

Reserve 10%
→ pode crescer para 15%
→ 20%
→ 30%.

==================================================
16. RESERVE GROWTH REGIMES
==========================

Reportar:

RESERVE_RATIO =
Recovery Reserve / Operating Capital.

Classificar:

# <10%

RESERVE_REBUILDING

# 10–15%

RESERVE_PROTECTED

# 15–20%

RESERVE_GROWING

# 20–30%

RESERVE_STRONG

> 30%
> =
> RESERVE_EXPANSION_READY.

Não reduzir automaticamente reserve em nenhuma dessas zonas.

==================================================
17. AGRESSIVIDADE DINÂMICA
==========================

Quanto maior:

RESERVE_RATIO,

maior pode ser a liberdade para:

* early release;
* tolerate controlled release loss;
* keep Active Reserve deployed;
* unlock operating queues aggressively.

Mas:

não aumentar risco arbitrariamente.

Preregister uma função monotônica.

Higher reserve coverage
→
higher allowable recovery expenditure.

==================================================
18. OPERATING BANK MUST NOT SHRINK FROM RELEASE
===============================================

Hard design objective:

OPERATING_BANK_AFTER_RECOVERY

> =
> OPERATING_BANK_BEFORE_RELEASE

quando reserve possui capital suficiente.

A perda econômica é absorvida pela reserve.

Não esconder:

TOTAL_EQUITY sofre a perda real.

Mas:

o motor operacional mantém sua potência.

==================================================
19. RESERVE TRANSFER
====================

Quando Operating Queue precisa sair com perda:

realize loss

→
calculate exact deficit

→
Recovery Reserve covers deficit

→
Operating Queue capital restored

→
queue becomes FLAT

→
select productive range

→
motor continues.

==================================================
20. CORE RESERVE PRIORIDADE
===========================

Antes de executar uma release:

considerar:

TOTAL_RESERVE

minus

capital currently locked in ACTIVE_RESERVE_QUEUE.

Reserve disponível imediatamente precisa continuar suficiente.

A Active Reserve não pode bloquear o emergency unlock do motor principal.

==================================================
21. ACTIVE RESERVE LIQUIDITY RULE
=================================

A Reserve Queue deve ter política mais conservadora de liquidez.

Ela NÃO pode entrar em posição com alto risco de impedir que capital reserve seja recuperado quando necessário.

Preregister:

MAX_ACTIVE_RESERVE_HOLD

menor ou igual ao limite das Operating Queues.

Idealmente mais curto.

==================================================
22. MAX LOCK
============

Hard OWNER constraint:

MAX_OPERATING_QUEUE_LOCK=24 HOURS.

Nenhuma Operating Queue pode permanecer economicamente presa por mais de 24h sem:

HARD_LOCK_VIOLATION.

Mas objetivo real é muito menor.

==================================================
23. URGENCY SCHEDULE
====================

Preregister comportamento progressivo.

Exemplo estrutural:

0–3h:
NORMAL

3–6h:
WATCH

6–12h:
RECOVERY_ELIGIBLE

12–18h:
HIGH_RECOVERY_PRIORITY

18–24h:
MANDATORY_EXIT_PRIORITY

> =24h:
> HARD_LOCK_VIOLATION.

Astra/reviewer pode melhorar thresholds antes do replay.

24h não pode ser aumentado sem OWNER.

==================================================
24. MACHINE NEVER STOP
======================

Se uma fila fica presa:

as outras filas continuam.

Este é o principal motivo da arquitetura multi-queue.

Uma posição ruim NÃO deve parar:

toda a banca.

Portanto medir:

NUMBER_OF_PRODUCTIVE_QUEUES_AT_T

OPERATING_CAPITAL_ACTIVE_RATIO

OPERATING_CAPITAL_LOCKED_RATIO

TOTAL_CAPITAL_PRODUCTIVE_RATIO.

==================================================
25. DEFINIÇÃO DE MOTOR PARADO
=============================

Criar:

MOTOR_FULL_STOP

quando:

nenhuma Operating Queue
e nenhuma Active Reserve Queue

está:

* trabalhando;
* aguardando fill válido;
* ou apta a entrar em range produtivo.

Medir:

FULL_STOP_MINUTES

FULL_STOP_HOURS

FULL_STOP_EVENTS.

PRIMARY TARGET:

FULL_STOP_HOURS ≈ 0.

==================================================
26. MOTOR UPTIME
================

Criar:

MOTOR_UPTIME_RATIO =
time with >=1 productive queue
/
total simulation time.

Também:

CAPITAL_WEIGHTED_UPTIME =
integral productive capital / total capital-time.

Esse segundo indicador é essencial.

Uma fila de US$1 funcionando enquanto US$100.000 estão presos não significa uptime real de 100%.

==================================================
27. CAPITAL-WEIGHTED PRODUCTIVITY
=================================

Reportar:

PRODUCTIVE_CAPITAL_HOURS

LOCKED_CAPITAL_HOURS

IDLE_CAPITAL_HOURS

RESERVE_ACTIVE_HOURS

CORE_RESERVE_IDLE_HOURS.

Objetivo:

maximizar:

PRODUCTIVE_CAPITAL_HOURS.

==================================================
28. REALISTIC EXECUTION REQUIRED
================================

Manter as lições do Binance Reality:

PRICE_TOUCH != FILL.

Modelar:

* queue ahead;
* latency;
* aggressor side;
* order activation;
* full/partial fill;
* Binance quantity rules;
* spread;
* execution slippage;
* release execution;
* capacity.

Compounding não pode ignorar isso.

==================================================
29. CAPACITY
============

Cada fila usa seu capital atribuído atual.

Se seu tamanho crescer a ponto de prejudicar fill:

não resetar para US$100.

Registrar:

QUEUE_CAPACITY_PRESSURE.

O allocation engine pode distribuir capital entre:

Q1
Q2
Q3

para reduzir impacto.

==================================================
30. SAME PAIR FIRST
===================

Nesta versão:

PAIR=USDCUSDT.

Não adicionar segunda paridade.

Primeiro descobrir até onde:

3 Operating Queues
+
1 Active Reserve Queue

conseguem utilizar capital na mesma paridade.

==================================================
31. FUTURE PAIR EXPANSION
=========================

Somente depois, se capacity exigir:

segunda paridade.

Não implementar agora.

==================================================
32. PROFIT FLOW
===============

Operating Queue profitable cycle:

NET_PROFIT=P

10% P
→ Recovery Reserve

90% P
→ Operating Capital.

Active Reserve profitable cycle:

100% do profit líquido

→ Recovery Reserve.

Não retirar profit da Reserve Queue para Operating nesta versão.

==================================================
33. RESERVE RELEASE COST
========================

Todas as releases pagas pela Recovery Reserve devem ser contabilizadas.

Reportar:

RESERVE_FUNDING_FROM_OPERATING

RESERVE_PROFIT_FROM_ACTIVE_QUEUE

RESERVE_CONSUMPTION

RESERVE_NET_CHANGE.

==================================================
34. RESERVE SELF-SUSTAINABILITY
===============================

Criar:

RESERVE_SELF_SUSTAINABILITY_RATIO =

(
operating profit contributions
+
active reserve profits
)
/
release consumption.

Desejável:

> 1.

Muito desejável:

> > 1.

==================================================
35. RECOVERY TIME
=================

Para cada release registrar:

RELEASE_COST

RELEASE_TIMESTAMP

RESERVE_BEFORE

RESERVE_AFTER

RECOVERY_TO_PRE_RELEASE_RESERVE_TIMESTAMP

RECOVERY_DURATION.

Criar:

P50_RESERVE_RECOVERY_TIME

P90

P99

MAX.

==================================================
36. COMPOUNDING CURVES
======================

Gerar:

OPERATING_BANK_CURVE

RECOVERY_RESERVE_CURVE

TOTAL_EQUITY_CURVE

QUEUE_1_CAPITAL_CURVE

QUEUE_2_CAPITAL_CURVE

QUEUE_3_CAPITAL_CURVE

ACTIVE_RESERVE_CAPITAL_CURVE.

==================================================
37. DAY CHECKPOINTS
===================

Reportar economicamente:

DAY_1

DAY_7

DAY_30

DAY_90

FINAL.

Cada checkpoint:

Operating Capital

Reserve

Reserve Ratio

Total Equity

Total Net Profit

Active Queues

Cycles

Motor Uptime

Capital Weighted Uptime

Zero Days

Max Hold

Release Spend.

==================================================
38. PRIMARY SUCCESS CONDITIONS
==============================

A nova estratégia deve buscar simultaneamente:

MOTOR_UPTIME >= 99%

FULL_STOP_DAYS = 0

ZERO_CYCLE_DAYS as close to 0 as possible

MAX_OPERATING_HOLD <=24h

RESERVE never zero

OPERATING capital non-decreasing from release coverage

TOTAL_EQUITY growth positive

RESERVE_SELF_SUSTAINABILITY_RATIO >1

real execution fills valid.

Não considerar resultado aprovado apenas por PnL.

==================================================
39. OVERTRADING PROTECTION
==========================

Não confundir:

machine never stop

com:

trade at any cost.

Uma fila pode permanecer FLAT se:

não existir oportunidade com expected net edge positivo.

Não fabricar trade negativo só para aumentar uptime.

O objetivo é:

MAXIMUM POSITIVE-EXPECTANCY PRODUCTIVITY.

==================================================
40. SELF-COMPETITION
====================

Com múltiplas filas na mesma paridade:

modelar nossa própria competição por queue/depth.

Q1/Q2/Q3/Q4 não podem assumir que cada uma tem acesso independente ao mesmo volume.

Shared market liquidity deve ser consumida consistentemente.

==================================================
41. RESERVE PRIORITY
====================

Se houver simultaneamente:

Active Reserve trade

e

necessidade de emergency release,

prioridade:

PROTECT OPERATING ENGINE.

Se necessário:

cancel Active Reserve order

ou

não renovar Active Reserve position

para preservar liquidez da reserve.

==================================================
42. NÃO USAR CORE RESERVE PARA COMPOUNDING NORMAL
=================================================

Hard invariant:

CORE_RESERVE
!=
NORMAL_OPERATING_CAPITAL.

Somente Active Reserve pode operar.

==================================================
43. TESTES OBRIGATÓRIOS
=======================

Adicionar testes para:

* 3 operating queues independent ledgers;
* fourth Active Reserve queue;
* max 50% reserve active;
* core reserve preservation;
* 10% profit funding;
* 90% operating compounding;
* Active Reserve profit stays in reserve;
* reserve never zero;
* release restores operating queue;
* simultaneous queue fills;
* shared depth consumption;
* self-competition;
* partial fills;
* 24h lock;
* queue-specific recovery;
* motor full-stop metric;
* capital-weighted uptime;
* reserve recovery-time accounting.

==================================================
44. PREREGISTRATION
===================

Antes do replay:

criar:

docs/microstructure/<NEW_MODEL>_CONTINUOUS_MULTI_QUEUE_PREREGISTRATION.md

e:

docs/microstructure/<NEW_MODEL>_MODEL_SPEC.json.

Congelar:

* number of queues;
* allocation policy;
* reserve funding;
* reserve active fraction;
* core reserve rule;
* release rules;
* lock thresholds;
* execution profiles;
* market-capacity accounting;
* success gates.

==================================================
45. REVIEW
==========

Usar reasoning forte para revisar:

* causal allocation;
* reserve safety;
* multi-queue self-competition;
* compounding;
* queue capacity;
* reserve growth;
* release sustainability;
* 24h hard lock;
* possibility of pathological overtrading.

QUALITY_FIRST=ON.

==================================================
46. EXECUTION AUTHORIZATION
===========================

Após:

preregistration
+
implementation
+
tests
+
independent review PASS,

iniciar automaticamente o primeiro Reality replay.

EXECUTION_AUTHORIZED=YES.

==================================================
47. GITHUB JOURNAL
==================

GitHub continua sendo memória canônica.

Criar:

docs/research/<NEW_MODEL>_JOURNAL.md

reports/usdcusdt/<NEW_MODEL>-scoreboard.json

reports/usdcusdt/<NEW_MODEL>-report.md.

Atualizar:

docs/research/CURRENT_STATE.md.

==================================================
48. CURRENT STATE DEVE MOSTRAR
==============================

ACTIVE_MODEL=

PAIR=USDCUSDT

OPERATING_QUEUES_ACTIVE=

ACTIVE_RESERVE_QUEUE=
YES/NO

OPERATING_CAPITAL=

RECOVERY_RESERVE=

RESERVE_RATIO=

ACTIVE_RESERVE_CAPITAL=

CORE_RESERVE_CAPITAL=

TOTAL_EQUITY=

CYCLES=

MOTOR_UPTIME=

CAPITAL_WEIGHTED_UPTIME=

FULL_STOP_HOURS=

ZERO_DAYS=

MAX_HOLD=

RELEASES=

RESERVE_RECOVERY_TIME_P50=

VERDICT=.

==================================================
49. NÃO CONTINUAR RUN INCOMPATÍVEL
==================================

Qualquer run atualmente ativo que use:

FIXED_NOTIONAL_100

2% reserve funding

single queue B10 architecture

ou outra política superseded

deve ser:

preservado,
journaled,
parado.

Classificar:

SUPERSEDED_BY_OWNER_MULTI_QUEUE_STRATEGY.

==================================================
50. OWNER PHILOSOPHY
====================

A filosofia do sistema é:

DINHEIRO PARADO É CAPITAL IMPRODUTIVO.

A reserve existe para proteger produção.

Ela deve crescer.

Ela pode trabalhar parcialmente.

Operating profit aumenta banca.

Banca maior aumenta capacidade produtiva.

Reserve maior aumenta resistência e liberdade de recovery.

Múltiplas filas impedem que uma posição ruim desligue toda a máquina.

==================================================
51. FINAL ARCHITECTURE
======================

OPERATING CAPITAL
↓
Q1 + Q2 + Q3
↓
net profit
↓
90% compounding
+
10% Recovery Reserve
↓
Reserve cresce
↓
50% máximo pode alimentar Q4
↓
Q4 profit volta integralmente para reserve
↓
reserve maior
↓
recovery capacity maior
↓
less capital lock
↓
higher motor uptime
↓
more cycles
↓
more compounding.

==================================================
52. HARD LIMITS
===============

MAX_QUEUES_PER_PAIR=4

MAX_OPERATING_QUEUES=3

MAX_ACTIVE_RESERVE_QUEUES=1

MAX_ACTIVE_RESERVE_SHARE=50%

MIN_RESERVE_TARGET=10% of Operating Capital

RESERVE_NEVER_ZERO=YES

MAX_OPERATING_LOCK=24h

FIXED_NOTIONAL_PRIMARY=FORBIDDEN

COMPOUNDING=MANDATORY.

==================================================
53. PRIMEIRO RETORNO
====================

Não retornar só status técnico.

Entregar:

OLD_RUN_STOPPED=

NEW_MODEL=

MODEL_REGISTERED=

CAPITAL_MODE=

OPERATING_INITIAL=

RESERVE_INITIAL=

RESERVE_TARGET_RATIO=

OPERATING_PROFIT_TO_RESERVE=

ACTIVE_RESERVE_MAX_SHARE=

MAX_OPERATING_QUEUES=

MAX_RESERVE_QUEUES=

MAX_TOTAL_QUEUES=

MAX_LOCK=

ALLOCATION_POLICY=

RELEASE_POLICY=

PREREGISTRATION_STATUS=

IMPLEMENTATION_STATUS=

TEST_STATUS=

REVIEW_STATUS=

NEW_RUN_STATUS=

NEW_RUN_ID=

COMMIT=

HEAD_EQUALS_ORIGIN_MAIN=.

==================================================
REGRA FINAL
===========

THE MACHINE MUST KEEP WORKING.

Não preservar capital ocioso por estética.

Não consumir reserve irresponsavelmente.

Não permitir reserve zero.

Não permitir uma posição única desligar todo o motor.

Compound automatically.

Build reserve automatically.

Use reserve intelligently.

Allow reserve surplus to work.

Up to:

3 operating queues

*

1 active-reserve queue

within USDCUSDT.

MOTOR_UPTIME_IS_THE_PRIMARY_OBJECTIVE=YES.

CAPITAL_WEIGHTED_UPTIME_IS_PRIMARY_METRIC=YES.

SELF_SUSTAINING_RESERVE=YES.

CONTINUOUS_COMPOUNDING=YES.
