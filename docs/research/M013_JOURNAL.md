# M013 — CONTINUOUS_MULTI_QUEUE_RECOVERY

## Pré-registro anterior ao replay

MODEL_ID=M013
MODEL_HASH=6a771627bbb820e13f199746c5159100f16cbd0d4c1c91dd0ac6bd500902d57a
MODEL_REGISTERED=YES; registry físico, não ID presumido
TEST_PLAN=TWO_STAGE
STAGE_1=2026-01-01T00:00:00Z..2026-06-01T00:00:00Z exclusive
STAGE_1_CALENDAR_DAYS=151
STAGE_2=2026-06-01T00:00:00Z..2026-09-05T23:59:59.783644Z exclusive
STAGE_2_STATUS=SEALED_NOT_AUTHORIZED_UNLESS_STAGE1_PASS
CAPITAL_MODE=COMPOUNDING
INITIAL_OPERATING=100
INITIAL_RESERVE=10
INITIAL_EQUITY=110
OPERATING_PROFIT_TO_RESERVE=10%
OPERATING_PROFIT_REINVESTED=90%
ACTIVE_RESERVE_PROFIT_TO_RESERVE=100%
MAX_OPERATING_QUEUES=3
MAX_ACTIVE_RESERVE_QUEUES=1
MAX_ACTIVE_RESERVE_SHARE=50%
MAX_OPERATING_LOCK=24h
MAX_ACTIVE_RESERVE_LOCK=6h
OLD_RUN_STOPPED=YES
M012_STATUS=SUPERSEDED_BY_OWNER_MULTI_QUEUE_STRATEGY
M012_ECONOMIC_RESULTS=NONE; stopped before any economic replay/checkpoint
SCIENTIFIC_PREREGISTRATION_REVIEW=PASS
IMPLEMENTATION_STATUS=IN_PROGRESS
IMPLEMENTATION_REVIEW=PENDING
RUN_STATUS=NOT_STARTED
RUN_ID=UNAVAILABLE_UNTIL_PREFLIGHT_PASS_AND_RUN_REGISTRATION
VERDICT=PENDING

### Economia

Nenhum resultado econômico M013 foi produzido. 100+10 são condições iniciais, não
retorno observado. O perfil B é envelope de execução condicional, não L2 histórico.
Q4 inicia inativa: o orçamento seguro inicial de 2.5 USDT é inferior ao mínimo 5.
Reservar até 50% não implica poder executar com 50% desde o primeiro evento.

### Gates congelados

151 dias íntegros; uptime >=99%; uptime ponderado total >=80% e sobre capital
disponível para operar >=95%; full-stop days 0; zero-cycle days <=2; holds operacionais
<=24h/Q4<=6h; nenhuma violação de lock/tesouraria/contabilidade/causalidade/liquidez;
reserva mínima >0; equity bid final >110; PnL realizado líquido >0; sustentabilidade
conservadora >=1, incluindo perdas Q4. Denominador zero é explicitamente indefinido.
Auditoria independente vinculada ao checkpoint: >=100 ordinary, todas as recuperações
e todos os fills Q4. Insuficiência de evidência é INCONCLUSIVE, não falha econômica.

Somente PASS_TO_EXTENSION autoriza junho-setembro, sem reset de capital, posições,
ordens, timers, dust ou liquidez. Não há tuning entre etapas. B10 já observou meses
posteriores: selado para M013 não significa holdout prospectivo nunca visto.

Modelos realmente utilizados: GPT-6 Astra na formulação/revisão/implementação científica;
GPT-5.6 Luna em código de relatório e fixtures mecânicas, sujeitos à revisão Astra.

Autoridades: M013_MODEL_SPEC.json, M013_CONTINUOUS_MULTI_QUEUE_PREREGISTRATION.md,
CONTINUOUS_MULTI_QUEUE_OWNER_DIRECTIVE.md e TWO_STAGE_REPLAY_OWNER_DIRECTIVE.md.

## Runner de duas etapas — preparação apenas

TYPE=SOFTWARE_AND_DATA_PREPARATION
RUNNER_REPORT_TESTS_PASSED=7
RUNNER_REPORT_TESTS_FAILED=0
SOFTWARE_VALIDATION_SCOPE=stage gates, raw ordinal, seven exact boundaries, sealed archive rejection, durable report binding
KERNEL_IMPLEMENTATION_REVIEW=PENDING
ECONOMIC_REPLAY_STARTED=NO

Publicado comando --prepare-only, que valida apenas dados do prefixo Dec31 warmup
até maio, sem criar run ou executar estratégia. Junho-setembro não é atravessado.
O primeiro replay permanece fail-closed até revisão independente do código concluída.
Correções pré-run em andamento: cancel/ACK da reserva e contabilização de parciais.
Não são resultados econômicos; nenhum parâmetro foi alterado por resultado.

## Prefixo físico preparado e placar mensal

DATA_PREPARATION=COMPLETE
PREPARATION_CODE_COMMIT=afad9795d5eea7ae1f585600a43722d370c6490b
PREFIX_TAPE_HASH=f2eb7e98f50fa731202e371facc7c6dbd5f4dc2c7d1f06451f656d42325e31cf
PREFIX_CACHE_KEY=437eb38f241f8b2d0360e22a59a3a0dbb65c005082259e3e40321751bfdc0d5c
PREFIX_RECORDS_INCLUDING_DEC31_WARMUP=60870538
STAGE_1_RAW_TRADES=60478963
SEALED_FUTURE_SUFFIX_SCANNED=NO
ECONOMIC_REPLAY_STARTED=NO

SHA256s dos 152 arquivos autorizados foram conferidos. O cache prefixado foi gravado
e validado pelas rotinas canônicas. Hash integral anterior é provenance histórica,
não foi rechecado atravessando junho-setembro. A reconciliação raw/timestamp/preço/
ordinal de todos os eventos ainda será feita durante o replay.

Novo pedido OWNER: saldo da banca e ciclos mês a mês. Runner captura fechamentos
de janeiro, fevereiro, março, abril e maio antes do primeiro evento do mês seguinte.
Reporter mostra banca operacional, reserva, patrimônio e ciclos ordinários do mês
(operacionais + Q4), por diferença dos contadores, com releases separados. Não soma
saldos mensais nem projeta mês aberto. Fixtures confirmam fechamento e diferenças.

TEST_SCOPE=M013 kernel/runner/report + M012 regression + frozen B10 execution
TESTS_PASSED=79
TESTS_FAILED=0
TEST_SUITE_PASS_IS_STRATEGY_PASS=NO
IMPLEMENTATION_REVIEW=PENDING

## Revisão final e autorização de início

IMPLEMENTATION_STATUS=COMPLETE
REVIEW_STATUS=PASS_CONDITIONAL_PRE_RUN
SOFTWARE_VALIDATION_ROOT=101 passed; 0 failed
INDEPENDENT_SOFTWARE_VALIDATION=78 passed; 0 failed
NEW_RUN_STATUS=AUTHORIZED_NOT_YET_STARTED
VERDICT=PENDING

Reviewer Astra vinculou SHA256 LF de kernel, runner e reporter e confirmou prefixo,
quatro filas compartilhando print/depth, parciais/escrows, cancel/ACK, dust idle,
24h dentro da etapa e continuidade da fronteira exclusiva. A auditoria do histórico
completo continua necessária para Stage 2. Nenhum teste aprova retorno financeiro.
Próxima ação autorizada: publicar a implementação e iniciar Stage 1 automaticamente.

## M013 checkpoint

TYPE=TWO_STAGE
SOURCE_SCOREBOARD_SHA256=b8a0146c93d4664a7abee2349d11135679d658ca32a163cd56a946d6a4f290dd
| Métrica atual | Valor |
|---|---|
| OPERATING_CAPITAL | 100 |
| RECOVERY_RESERVE | 10 |
| RESERVE_RATIO | 0.1 |
| CORE_RESERVE | 10 |
| ACTIVE_RESERVE_CAPITAL | 0 |
| TOTAL_EQUITY | 110 |
| TOTAL_PROFIT | 0 |
| OPERATING_QUEUES_ACTIVE | 0 |
| RESERVE_QUEUE_ACTIVE | False |
| CYCLES | 0 |
| NET_POSITIVE_CYCLES | 0 |
| MOTOR_UPTIME | UNAVAILABLE |
| CAPITAL_WEIGHTED_UPTIME | UNAVAILABLE |
| FULL_STOP_HOURS | 0 |
| ZERO_CYCLE_DAYS | 0 |
| MAX_HOLD | 0 |
| LOCK_HOURS_GT24 | 0 |
| HARD_LOCK_VIOLATIONS | 0 |
| RELEASE_COUNT | 0 |
| TOTAL_RELEASE_LOSS | 0 |
| RESERVE_CONTRIBUTIONS | 0 |
| ACTIVE_RESERVE_PROFIT | 0 |
| RESERVE_CONSUMPTION | 0 |
| RESERVE_SELF_SUSTAINABILITY_RATIO | UNAVAILABLE |
| CAPACITY_PRESSURE_EVENTS | 0 |
| VERDICT | PENDING |

| Mês fechado | Banca operacional USDT | Reserva USDT | Patrimônio USDT | Ciclos do mês | Releases |
|---|---:|---:|---:|---:|---:|
| Nenhum mês concluído | — | — | — | — | — |

Ciclos do mês = ciclos ordinários completos operacionais + Q4, sem somar releases. Saldos de fechamento, sem reset; mês ainda aberto não é projetado. Valores visuais arredondados; JSON preserva precisão integral.

VERDICT=PENDING

## M013 checkpoint

TYPE=TWO_STAGE
SOURCE_SCOREBOARD_SHA256=818e82872448d147c616b6b40f9773f5138961e46125ee231642888a12049120
| Métrica atual | Valor |
|---|---|
| OPERATING_CAPITAL | 100.00891 |
| RECOVERY_RESERVE | 10.00099 |
| RESERVE_RATIO | 0.100001 |
| CORE_RESERVE | 10.00099 |
| ACTIVE_RESERVE_CAPITAL | 0 |
| TOTAL_EQUITY | 110.0099 |
| TOTAL_PROFIT | 0.0099 |
| OPERATING_QUEUES_ACTIVE | 0 |
| RESERVE_QUEUE_ACTIVE | False |
| CYCLES | 1 |
| NET_POSITIVE_CYCLES | 1 |
| MOTOR_UPTIME | 0.030578 |
| CAPITAL_WEIGHTED_UPTIME | 0.027796 |
| FULL_STOP_HOURS | 69.830263 |
| ZERO_CYCLE_DAYS | 2 |
| MAX_HOLD | 0.385392 |
| LOCK_HOURS_GT24 | 0 |
| HARD_LOCK_VIOLATIONS | 0 |
| RELEASE_COUNT | 0 |
| TOTAL_RELEASE_LOSS | 0 |
| RESERVE_CONTRIBUTIONS | 0.00099 |
| ACTIVE_RESERVE_PROFIT | 0 |
| RESERVE_CONSUMPTION | 0 |
| RESERVE_SELF_SUSTAINABILITY_RATIO | UNAVAILABLE |
| CAPACITY_PRESSURE_EVENTS | 0 |
| VERDICT | PENDING |

| Mês fechado | Banca operacional USDT | Reserva USDT | Patrimônio USDT | Ciclos do mês | Releases |
|---|---:|---:|---:|---:|---:|
| Nenhum mês concluído | — | — | — | — | — |

Ciclos do mês = ciclos ordinários completos operacionais + Q4, sem somar releases. Saldos de fechamento, sem reset; mês ainda aberto não é projetado. Valores visuais arredondados; JSON preserva precisão integral.

VERDICT=PENDING

## M013 checkpoint

TYPE=TWO_STAGE
SOURCE_SCOREBOARD_SHA256=a56d8c5d7fa49e13ec6974bcb66ce13e6ffc9d085a5f2c5322da692e5f4fbd0f
| Métrica atual | Valor |
|---|---|
| OPERATING_CAPITAL | 100.00891 |
| RECOVERY_RESERVE | 10.00099 |
| RESERVE_RATIO | 0.100001 |
| CORE_RESERVE | 10.00099 |
| ACTIVE_RESERVE_CAPITAL | 0 |
| TOTAL_EQUITY | 110.0099 |
| TOTAL_PROFIT | 0.0099 |
| OPERATING_QUEUES_ACTIVE | 0 |
| RESERVE_QUEUE_ACTIVE | False |
| CYCLES | 1 |
| NET_POSITIVE_CYCLES | 1 |
| MOTOR_UPTIME | 0.016155 |
| CAPITAL_WEIGHTED_UPTIME | 0.014685 |
| FULL_STOP_HOURS | 134.142967 |
| ZERO_CYCLE_DAYS | 4 |
| MAX_HOLD | 0.385392 |
| LOCK_HOURS_GT24 | 0 |
| HARD_LOCK_VIOLATIONS | 0 |
| RELEASE_COUNT | 0 |
| TOTAL_RELEASE_LOSS | 0 |
| RESERVE_CONTRIBUTIONS | 0.00099 |
| ACTIVE_RESERVE_PROFIT | 0 |
| RESERVE_CONSUMPTION | 0 |
| RESERVE_SELF_SUSTAINABILITY_RATIO | UNAVAILABLE |
| CAPACITY_PRESSURE_EVENTS | 0 |
| VERDICT | PENDING |

| Mês fechado | Banca operacional USDT | Reserva USDT | Patrimônio USDT | Ciclos do mês | Releases |
|---|---:|---:|---:|---:|---:|
| Nenhum mês concluído | — | — | — | — | — |

Ciclos do mês = ciclos ordinários completos operacionais + Q4, sem somar releases. Saldos de fechamento, sem reset; mês ainda aberto não é projetado. Valores visuais arredondados; JSON preserva precisão integral.

VERDICT=PENDING

## M013 checkpoint

TYPE=TWO_STAGE
SOURCE_SCOREBOARD_SHA256=a04d6caff6fc2f8bccc2a667b9d67363be785967d2ded73bd07d9ed28a05406c
| Métrica atual | Valor |
|---|---|
| OPERATING_CAPITAL | 100.10692 |
| RECOVERY_RESERVE | 10.01188 |
| RESERVE_RATIO | 0.100012 |
| CORE_RESERVE | 10.01188 |
| ACTIVE_RESERVE_CAPITAL | 0 |
| TOTAL_EQUITY | 110.1188 |
| TOTAL_PROFIT | 0.1188 |
| OPERATING_QUEUES_ACTIVE | 0 |
| RESERVE_QUEUE_ACTIVE | False |
| CYCLES | 12 |
| NET_POSITIVE_CYCLES | 12 |
| MOTOR_UPTIME | 0.039668 |
| CAPITAL_WEIGHTED_UPTIME | 0.036075 |
| FULL_STOP_HOURS | 265.448073 |
| ZERO_CYCLE_DAYS | 9 |
| MAX_HOLD | 5.177563 |
| LOCK_HOURS_GT24 | 0 |
| HARD_LOCK_VIOLATIONS | 0 |
| RELEASE_COUNT | 0 |
| TOTAL_RELEASE_LOSS | 0 |
| RESERVE_CONTRIBUTIONS | 0.01188 |
| ACTIVE_RESERVE_PROFIT | 0 |
| RESERVE_CONSUMPTION | 0 |
| RESERVE_SELF_SUSTAINABILITY_RATIO | UNAVAILABLE |
| CAPACITY_PRESSURE_EVENTS | 0 |
| VERDICT | PENDING |

| Mês fechado | Banca operacional USDT | Reserva USDT | Patrimônio USDT | Ciclos do mês | Releases |
|---|---:|---:|---:|---:|---:|
| Nenhum mês concluído | — | — | — | — | — |

Ciclos do mês = ciclos ordinários completos operacionais + Q4, sem somar releases. Saldos de fechamento, sem reset; mês ainda aberto não é projetado. Valores visuais arredondados; JSON preserva precisão integral.

VERDICT=PENDING

## Correção técnica e autoridade semanal — 2026-09-07

M013: **INVALIDATED_TECHNICAL / STOPPED**. O status RUNNING nos registros anteriores
é histórico. Após cancelar BUY zero-fill inelegível, o motor podia reenviar a mesma
faixa antes da reseleção. Isso compromete a interpretação econômica do replay.
Nenhuma perda/fill foi reescrita. Originais e prefixos permanecem preservados;
ver [manifest de preservação](../../reports/usdcusdt/M013-technical-stop.json).

Último fechamento físico preservado (janeiro, afetado): **63 ciclos ordinários
positivos + 1 release**, 24 dias sem ciclo, banca100.357840 USDT,
reserva10.012160 USDT, patrimônio110.370000 USDT. Contador bruto64 inclui o release.
Estes valores não são resultado de uma primeira semana corrigida.

OWNER: primeiro bloco somente1–7janeiro UTC; qualquer semana seguinte depende
de aprovação humana específica, mesmo se positiva. Sem reset de banca/reserva/estado.
Correção mínima na canônica revisada por GPT-6 Astra:81 testes independentes
passaram; TEST_SUITE_PASS != STRATEGY_PASS. O novo replay semanal não foi executado.
Fonte original M013 e revisão prévia preservadas no Git; nenhuma promoção de modelo.
