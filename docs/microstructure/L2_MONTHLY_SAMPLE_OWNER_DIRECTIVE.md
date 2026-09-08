# OWNER DIRECTIVE — USDCUSDT HISTORICAL L2 MONTHLY SAMPLE BATTERY

# REPLACE PARAMETERIZED QUEUE WITH OBSERVED L2 WHERE AVAILABLE

O estudo M015 ficou bloqueado porque a fila histórica de janeiro não é conhecida.

Nova direção do OWNER:

pesquisar, baixar, validar e executar a estratégia em TODAS as datas de L2 histórico gratuito acessíveis dentro do dataset canônico do projeto.

Não inventar queue.

Não reduzir queue artificialmente.

Usar L2 observado sempre que disponível.

==================================================

1. AUTORIDADE DE DADOS
   ==================================================

Fonte primária para L2 histórico:

Tardis Binance Spot historical incremental_book_L2 / snapshots.

A documentação Tardis declara que:

* Binance Spot L2 histórico é capturado do WebSocket;
* depth snapshots iniciais são obtidos via REST;
* sequência U/u é validada;
* first day of each month é downloadable without API key;
* row order preserva capture order.

Verificar novamente essas afirmações diretamente na documentação antes do download.

==================================================
2. HORIZONTE CANÔNICO DO PROJETO
================================

O repo possui trades USDCUSDT auditados continuamente entre:

2025-01-01
e
2026-09-05.

Manifest físico:

data/manifests/usdcusdt-trades-2025-2026.json

Não usar datas fora desse universo nesta campanha.

==================================================
3. DATAS CANDIDATAS L2 GRATUITAS
================================

Verificar fisicamente disponibilidade de USDCUSDT incremental_book_L2 para:

2025-01-01
2025-02-01
2025-03-01
2025-04-01
2025-05-01
2025-06-01
2025-07-01
2025-08-01
2025-09-01
2025-10-01
2025-11-01
2025-12-01

2026-01-01
2026-02-01
2026-03-01
2026-04-01
2026-05-01
2026-06-01
2026-07-01
2026-08-01
2026-09-01.

TOTAL_EXPECTED_CANDIDATES=21.

Não assumir disponibilidade apenas pela regra mensal.

Para cada data:

HTTP status
content length
SHA256
gzip integrity
CSV schema
first timestamp
last timestamp
row count

devem ser registrados.

Se alguma não existir:

DATA_STATUS=UNAVAILABLE

e continuar com as demais.

==================================================
4. NÃO PRECISA API KEY PARA SAMPLE
==================================

Para os datasets públicos gratuitos:

não pedir Binance API key.

não pedir Tardis API key.

não usar conta do OWNER.

não comprar nada.

Se endpoint pedir autenticação numa data que deveria ser sample:

registrar exatamente e não contornar.

==================================================
5. DOWNLOAD
===========

Criar:

data/l2/tardis/binance/usdcusdt/YYYY-MM-DD/

Preservar arquivo original imutável.

Nunca modificar CSV original.

Criar manifest:

data/manifests/usdcusdt-tardis-free-l2.json.

Para cada arquivo:

DATE
SOURCE_URL
DOWNLOAD_TIMESTAMP
BYTES
SHA256
ROWS
FIRST_TIMESTAMP
LAST_TIMESTAMP
STATUS.

==================================================
6. VALIDAR L2
=============

Antes de replay:

reconstruir book sequencialmente.

Validar:

snapshot inicial

update IDs

sequence continuity

bid/ask sides

non-crossed book

price ordering

quantity >=0

delete quantity=0 semantics

timestamps

capture order

gaps

disconnects.

Qualquer gap irreparável:

L2_DAY_VALID=false.

Não preencher artificialmente.

==================================================
7. CRUZAR COM TRADES CANÔNICOS
==============================

Para cada data válida:

usar os trades oficiais USDCUSDT do mesmo dia já presentes no repo.

Verificar:

DATE_MATCH

START/END

tick-size authority

trade IDs

timestamps

price grid.

L2 e trades devem permanecer fontes separadas com provenance próprio.

==================================================
8. SEMANA NÃO PODE SER FABRICADA
================================

CRÍTICO:

os primeiros dias dos meses NÃO são contínuos entre si.

Não carregar banca de:

Jan1
para
Feb1.

Não tratar isso como backtest contínuo.

Cada data é:

INDEPENDENT_24H_L2_EXECUTION_EXPERIMENT.

==================================================
9. CONDIÇÃO INICIAL DE CADA DIA
===============================

Para comparação justa:

OPERATING_INITIAL=100 USDT

RESERVE_INITIAL=10 USDT

CAPITAL_MODE=COMPOUNDING_WITHIN_DAY

START_STATE=FLAT.

Durante as 24h:

compounding normal.

90% positive realized net profit
→ Operating

10%
→ Reserve.

No fim do dia:

não carregar estado para próximo mês.

==================================================
10. ESTRATÉGIA
==============

Usar a estratégia OWNER vigente somente após verificar CURRENT_STATE e registry.

Não assumir M015 se já houver modelo posterior.

Se a estratégia mudou materialmente:

usar CURRENT_ACTIVE_RESEARCH_MODEL.

Nunca editar modelo congelado apenas para adaptar loader L2.

Mudança de execution evidence != mudança de strategy.

==================================================
11. L2 EXECUTION
================

Substituir onde possível:

PARAMETERIZED_QUEUE_AHEAD

por:

OBSERVED_BOOK_AHEAD_ESTIMATE.

Ao inserir ordem hipotética:

capturar:

BEST_BID
BEST_ASK
OUR_LIMIT
DISPLAYED_QTY_AT_LEVEL
DISPLAYED_QTY_AHEAD_ESTIMATE
BOOK_DEPTH_1TICK
BOOK_DEPTH_2TICKS
BOOK_DEPTH_5TICKS.

Preservar limitação:

L2 NÃO fornece posição exata da nossa ordem dentro da fila.

Portanto classificar:

KNOWN_DISPLAYED_AHEAD
UNKNOWN_TIME_PRIORITY_WITHIN_EXISTING_LEVEL.

Não afirmar queue rank exato.

==================================================
12. EXECUTION ENVELOPES
=======================

Para cada L2 day, rodar pelo menos:

A. CONSERVATIVE_QUEUE
assumir toda quantidade já exibida no nível antes de nossa ordem como ahead.

B. PRICE_PRIORITY
se preço atravessar estritamente nosso limit após activation, aplicar regra preregistrada correspondente.

C. SENSITIVITY_ONLY_IF_JUSTIFIED
outros envelopes somente se definidos ANTES de resultado.

Não inventar cenário otimista após observar resultado.

==================================================
13. MULTI-QUEUE
===============

Se o modelo OWNER vigente possuir:

Q1
Q2
Q3
Q4 Active Reserve,

o L2 deve ser compartilhado entre TODAS.

Não duplicar liquidez.

Quando uma fila consome volume:

reduzir disponibilidade para as outras conforme ordering causal.

Modelar self-competition.

==================================================
14. MÉTRICAS POR DIA
====================

Para cada data:

DATE=

L2_VALID=

L2_ROWS=

TRADES=

OPERATING_START=100

RESERVE_START=10

OPERATING_FINAL=

RESERVE_FINAL=

TOTAL_EQUITY_FINAL=

NET_PNL=

ORDINARY_CYCLES=

NET_POSITIVE_CYCLES=

CYCLES_PER_HOUR=

FULL_STOP_HOURS=

MOTOR_UPTIME=

CAPITAL_WEIGHTED_UPTIME=

ZERO_CYCLE_DAY=
YES/NO

BUY_ORDERS=

BUY_FULL=

BUY_PARTIAL=

BUY_ZERO_FILL=

SELL_FULL=

SELL_PARTIAL=

SELL_ZERO_FILL=

RELEASES=

RELEASE_LOSS=

MAX_HOLD=

HARD_LOCK_VIOLATIONS=

DISPLAYED_QUEUE_P50=

DISPLAYED_QUEUE_P90=

DISPLAYED_QUEUE_P99=

DEPTH_BEST_P50=

DEPTH_BEST_P90=

SPREAD_P50=

SPREAD_P90=

CAPACITY_PRESSURE=

VERDICT=.

==================================================
15. COMPARAR COM PROXY ANTIGO
=============================

Proxy M015 antigo:

QUEUE_AHEAD≈2,330,544 USDC.

Para cada data calcular:

OBSERVED_DISPLAYED_QUEUE_MEDIAN

OBSERVED_DISPLAYED_QUEUE_P90

OBSERVED_DISPLAYED_QUEUE_P99

e:

OLD_PROXY / OBSERVED_MEDIAN.

Responder:

O PROXY DE 2.33M ERA:

TOO_CONSERVATIVE
REASONABLE
TOO_OPTIMISTIC

para cada regime.

Não misturar isso com queue rank real.

==================================================
16. RESULTADO AGREGADO DOS 21 DIAS
==================================

Criar tabela ordenada por data.

Depois calcular:

VALID_L2_DAYS=

TOTAL_INDEPENDENT_DAYS=

MEDIAN_CYCLES_PER_DAY=

P10_CYCLES_PER_DAY=

P90_CYCLES_PER_DAY=

MIN_CYCLES_DAY=

MAX_CYCLES_DAY=

DAYS_ABOVE_500_CYCLES=

DAYS_ABOVE_2000_CYCLES=

DAYS_WITH_ZERO_CYCLES=

MEDIAN_MOTOR_UPTIME=

MEDIAN_CAPITAL_WEIGHTED_UPTIME=

MEDIAN_NET_RETURN=

MEDIAN_MAX_HOLD=

HARD_LOCK_VIOLATION_DAYS=.

==================================================
17. NÃO USAR MÉDIA GEOMÉTRICA ENTRE MESES
=========================================

Não calcular:

100 → Jan → Feb → Mar...

porque não há continuidade de L2.

Pode calcular:

ONE-DAY RETURN DISTRIBUTION.

Pode mostrar hipoteticamente:

median one-day return

mas rotular:

CROSS_SECTIONAL_INDEPENDENT_DAY_STATISTIC

e não compounding path.

==================================================
18. 2025 VS 2026
================

Separar:

2025 L2 CALIBRATION DAYS

e:

2026 STRATEGY-EVALUATION DAYS.

2025 ajuda a testar robustez de execução.

2026 é mais diretamente comparável à campanha financeira.

Não misturar os dois silenciosamente.

==================================================
19. SE UMA DATA FOR MUITO MELHOR/PIOR
=====================================

Fazer autópsia:

spread

depth

trade intensity

queue

price moves

fill latency

range activity.

Queremos descobrir:

QUAL REGIME PERMITE MUITOS CICLOS?

e:

QUAL REGIME MATA O MOTOR?

==================================================
20. RESULTADO PRINCIPAL
=======================

Responder ao OWNER principalmente:

COM L2 OBSERVADO,

QUANTOS CICLOS POR DIA O MOTOR CONSEGUIU?

Não esconder isso em relatório técnico.

Mostrar tabela:

DATE | CYCLES | PNL | RESERVE | MAX HOLD | UPTIME | QUEUE P50 | VERDICT.

==================================================
21. GITHUB
==========

GitHub é journal canônico.

Criar:

docs/research/L2_MONTHLY_SAMPLE_JOURNAL.md

reports/usdcusdt/L2-monthly-sample-scoreboard.json

reports/usdcusdt/L2-monthly-sample-report.md

data/manifests/usdcusdt-tardis-free-l2.json.

Commitar:

data manifests/hashes e resultados.

Não necessariamente versionar arquivos L2 gigantes se política do repo proibir.

Nesse caso:

preservar localmente
+
manifest/hash/path/provenance no Git.

==================================================
22. NÃO LER SEMANA 2
====================

A regra OWNER de semana seguinte continua válida.

Esta campanha usa somente datas mensais independentes.

Não interpretar isso como autorização para:

Jan8-14 continuous replay.

==================================================
23. NÃO BLOQUEAR PELO TARGET 500
================================

Executar todos os dias L2 válidos mesmo se primeiro dia der <500.

Queremos a distribuição real entre regimes.

Depois decidir.

==================================================
24. PRIMEIRO RETORNO
====================

Antes de simular, retornar:

L2_CANDIDATE_DATES=

L2_AVAILABLE_FREE=

L2_UNAVAILABLE=

TOTAL_BYTES=

TOTAL_ROWS=

INTEGRITY_PASS=

STRATEGY_MODEL_USED=

REPLAY_MODE=
INDEPENDENT_24H

QUEUE_MODEL=
OBSERVED_L2

COMMIT=

HEAD_EQUALS_ORIGIN_MAIN=.

Depois iniciar automaticamente todos os dias válidos.

==================================================
25. RETORNO FINAL
=================

Retornar tabela completa dos 21 dias e:

VALID_DAYS=

MEDIAN_CYCLES=

BEST_DAY=

WORST_DAY=

DAYS_GE500=

DAYS_GE2000=

MEDIAN_DAILY_RETURN=

MEDIAN_QUEUE=

OLD_2_33M_PROXY_ASSESSMENT=

MAIN_FINDING=

NEXT_RECOMMENDED_TEST=.

==================================================
REGRA FINAL
===========

USE REAL L2 WHEN WE HAVE REAL L2.

DO NOT GUESS QUEUE WHEN OBSERVATION EXISTS.

DO NOT JOIN NONCONTIGUOUS DAYS INTO FAKE COMPOUNDING.

TEST EVERY AVAILABLE FREE L2 DAY.

FIND THE REGIMES WHERE THE MACHINE CAN ACTUALLY RUN.
