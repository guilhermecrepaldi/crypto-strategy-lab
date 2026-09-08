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
