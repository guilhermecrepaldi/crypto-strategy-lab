# OWNER DIRECTIVE — GITHUB AS CANONICAL RESEARCH JOURNAL

# B10 / CRYPTO-STRATEGY-LAB

A partir de agora, o GitHub deve funcionar como JORNAL CANÔNICO e CONTÍNUO da pesquisa.

Não usar o chat como memória principal.

Não depender de logs temporários locais para reconstruir o estado.

O estado científico, operacional e econômico relevante deve ser publicado no repositório de forma frequente, legível e auditável.

==================================================

1. PRINCÍPIO CENTRAL
   ==================================================

GITHUB = SOURCE OF TRUTH FOR HANDOFF.

Toda sessão futura deve conseguir responder, apenas lendo o repositório:

* qual estratégia está ativa;
* qual run está ativa;
* qual profile está rodando;
* até que data o replay chegou;
* quantos ciclos foram processados;
* qual PnL parcial;
* qual reserve atual;
* quantos releases ocorreram;
* quais testes passaram;
* quais falhas ocorreram;
* qual foi a última decisão;
* qual o próximo passo.

==================================================
2. ARQUIVOS CANÔNICOS
=====================

Manter obrigatoriamente:

docs/research/CURRENT_STATE.md

docs/research/B10_JOURNAL.md

reports/usdcusdt/B10-reality-scoreboard.json

reports/usdcusdt/B10-reality-report.md

Criar diretórios se não existirem.

==================================================
3. CURRENT_STATE.md
===================

CURRENT_STATE.md deve ser CURTO e representar apenas o estado atual.

Atualizar sempre que houver mudança material.

Formato obrigatório:

# CURRENT STATE

LAST_UPDATED_UTC=

HEAD=

STRATEGY=B10_FROZEN

EXECUTION_PROFILE=

RUN_ID=

RUN_STATUS=

SIMULATION_START=

CURRENT_SIMULATION_TIMESTAMP=

SIMULATION_END=

PROGRESS_PERCENT=

PRICE_PATH_REFERENCE_FULL=3580880

PRICE_PATH_OPPORTUNITIES_SAME_PREFIX=

FULL_FILL_CYCLES=

NET_POSITIVE_CYCLES=

REALITY_RETENTION_SAME_PREFIX=

ZERO_CYCLE_DAYS_SO_FAR=

ACTIVE_DAYS_SO_FAR=

NET_PNL_FIXED_100=

RESERVE_INITIAL=5

RESERVE_FINAL=

RESERVE_MIN=

RELEASES_ATTEMPTED=

RELEASES_FILLED=

RELEASES_BLOCKED=

MAX_HOLD=

LOCK_HOURS=

MAX_DRAWDOWN=

TESTS_PASSED=

TESTS_FAILED=

INDEPENDENT_AUDIT_STATUS=

LAST_ERROR=

CURRENT_VERDICT=

NEXT_ACTION=

BLOCKERS=

==================================================
4. B10_JOURNAL.md
=================

B10_JOURNAL.md é APPEND-ONLY.

NUNCA apagar entradas anteriores.

NUNCA reescrever história.

Cada entrada deve ter:

## YYYY-MM-DDTHH:MM:SSZ

TYPE=
CHECKPOINT / SCENARIO_COMPLETE / ERROR / RECOVERY / AUDIT / DECISION / COMMIT / PROFILE_CHANGE

STRATEGY=

PROFILE=

RUN_ID=

SIM_TIMESTAMP=

PROGRESS=

CYCLES=

NET_POSITIVE_CYCLES=

PNL=

RESERVE=

RELEASES=

ZERO_DAYS=

MAX_HOLD=

LOCK_HOURS=

EVENT=

DECISION=

EVIDENCE_PATHS=

COMMIT=

==================================================
5. FREQUÊNCIA DE ATUALIZAÇÃO
============================

Não fazer commit por cada linha de log.

Atualizar GitHub quando ocorrer qualquer um destes eventos:

A. novo scenario/profile iniciado;
B. scenario/profile concluído;
C. a cada avanço material de replay;
D. a cada novo checkpoint econômico relevante;
E. erro;
F. recovery/restart;
G. mudança de código;
H. auditoria independente;
I. mudança de verdict;
J. decisão científica;
K. alteração de regra;
L. novo blocker.

Para long runs:

publicar checkpoint no mínimo quando houver uma destas condições:

* +5% de progresso do replay;
* +50.000 full-fill cycles;
* +10 releases;
* mudança de dia relevante;
* mudança material de PnL/reserve;
* qualquer anomalia.

Não criar churn absurdo de commits por heartbeat vazio.

==================================================
6. GIT COMMIT POLICY
====================

Cada atualização de journal/state deve usar commit descritivo.

Exemplos:

research: checkpoint B10 profile A at 25pct

research: record B10 profile A 50k fills

research: close B10 profile A

research: record B10 reserve depletion warning

fix: recover B10 replay after checkpoint failure

audit: validate B10 profile A checkpoint

Evitar:

update files

misc

progress

==================================================
7. CHECKPOINT ECONÔMICO
=======================

Não publicar apenas:

RUNNING.

Toda atualização deve trazer números.

Obrigatório:

CURRENT_SIMULATION_TIMESTAMP

PRICE_PATH_OPPORTUNITIES_SAME_PREFIX

FULL_FILL_CYCLES

REALITY_RETENTION_SAME_PREFIX

NET_PNL_FIXED_100

RESERVE_FINAL

RELEASES_FILLED

ZERO_CYCLE_DAYS_SO_FAR

MAX_HOLD

LOCK_HOURS.

Se algum campo ainda não for calculável:

usar:

UNKNOWN

e explicar no journal:

WHY_UNKNOWN=

==================================================
8. SEPARAR SOFTWARE TESTS DE STRATEGY RESULTS
=============================================

Nunca misturar:

“93 tests passed”

com:

“B10 passou”.

No CURRENT_STATE:

SOFTWARE_VALIDATION=

STRATEGY_RESULT=

separados.

Exemplo:

SOFTWARE_VALIDATION=PASS

STRATEGY_RESULT=PENDING.

==================================================
9. SCOREBOARD JSON
==================

B10-reality-scoreboard.json deve ser machine-readable e conter:

{
"strategy": "B10_FROZEN",
"run_id": "...",
"profile": "...",
"status": "...",
"updated_at": "...",
"simulation_timestamp": "...",
"progress_percent": ...,
"price_path_reference_full": 3580880,
"price_path_opportunities_same_prefix": ...,
"full_fill_cycles": ...,
"net_positive_cycles": ...,
"reality_retention_same_prefix": ...,
"net_pnl_fixed_100": ...,
"gross_pnl_fixed_100": ...,
"fees_paid": ...,
"slippage_cost": ...,
"reserve_initial": 5,
"reserve_contributions": ...,
"reserve_consumption": ...,
"reserve_final": ...,
"reserve_min": ...,
"release_attempted": ...,
"release_filled": ...,
"release_blocked": ...,
"zero_cycle_days_so_far": ...,
"active_days_so_far": ...,
"max_hold": ...,
"lock_hours": ...,
"max_drawdown": ...,
"software_tests": {...},
"independent_audit": {...},
"verdict": "..."
}

==================================================
10. REPORT MD
=============

B10-reality-report.md deve ser humano-legível.

Começar sempre com:

# B10 REALITY — CURRENT SCOREBOARD

e tabela:

| Metric                   | Value |
| ------------------------ | ----: |
| Profile                  |       |
| Progress                 |       |
| Simulation date          |       |
| Price-path opportunities |       |
| Full fill cycles         |       |
| Reality retention        |       |
| Net positive cycles      |       |
| Net PnL US$100           |       |
| Reserve final            |       |
| Releases                 |       |
| Zero days                |       |
| Max hold                 |       |
| Lock hours               |       |
| Drawdown                 |       |
| Verdict                  |       |

Depois:

## What changed since previous checkpoint

## Current interpretation

## Technical validation

## Known unknowns

## Next action

==================================================
11. HISTÓRICO NÃO DEVE SUMIR
============================

Quando um valor mudar:

não apagar a história no journal.

CURRENT_STATE mostra o valor novo.

JOURNAL preserva o antigo.

Isso permite reconstruir:

como o run evoluiu no tempo.

==================================================
12. ERROS
=========

Se houver erro:

antes de corrigir, registrar no journal:

ERROR_TYPE=

ERROR_TIMESTAMP=

LAST_VALID_CHECKPOINT=

EFFECT_ON_SCIENCE=

RUN_VALID=
YES/NO/UNKNOWN

Depois da correção:

RECOVERY_ACTION=

RESUMED_FROM=

CODE_COMMIT=

REPLAY_INVALIDATED=
YES/NO.

==================================================
13. NÃO INVENTAR SUCESSO
========================

Se Git não contém resultado:

não dizer que contém.

Se resultado é local e ainda não publicado:

marcar:

LOCAL_ONLY_UNPUBLISHED.

Antes de encerrar milestone:

push.

==================================================
14. PUSH
========

Após checkpoint relevante:

git status
git diff --check
testes necessários
commit
push

e verificar:

HEAD == origin/main.

Se push falhar:

registrar:

PUSH_STATUS=FAILED

e não fingir que o journal remoto está atualizado.

==================================================
15. HANDOFF
===========

Ao iniciar nova sessão/agente:

primeiro ler:

docs/research/CURRENT_STATE.md

docs/research/B10_JOURNAL.md

reports/usdcusdt/B10-reality-scoreboard.json

e os últimos commits.

Não reconstruir estado pelo chat se Git estiver atualizado.

==================================================
16. B10 REALITY CURRENT CAMPAIGN
================================

Aplicar imediatamente à campanha:

STRATEGY=B10_FROZEN

EXECUTION_PROFILE=BINANCE_REALITY_V1.

Não alterar estratégia.

Não reiniciar sem necessidade.

Não perder o run atual.

==================================================
17. PRIMEIRA ATUALIZAÇÃO AGORA
==============================

Antes de continuar silenciosamente:

1. inspecionar run ativo;
2. calcular placar atual;
3. atualizar CURRENT_STATE;
4. append B10_JOURNAL;
5. atualizar scoreboard JSON;
6. atualizar report MD;
7. commit;
8. push;
9. verificar HEAD==origin/main.

Retornar ao OWNER:

CURRENT_SIMULATION_TIMESTAMP=

PROGRESS_PERCENT=

FULL_FILL_CYCLES=

NET_POSITIVE_CYCLES=

REALITY_RETENTION_SAME_PREFIX=

NET_PNL_FIXED_100=

RESERVE_FINAL=

RELEASES_FILLED=

ZERO_DAYS=

MAX_HOLD=

LOCK_HOURS=

VERDICT=

COMMIT=

HEAD_EQUALS_ORIGIN_MAIN=

==================================================
18. REGRA FINAL
===============

GitHub deve permitir responder:

“Onde o B10 está agora?”

sem depender da memória do chat.

CODE + JOURNAL + SCOREBOARD + ARTIFACTS

formam a autoridade canônica.

GITHUB_RESEARCH_JOURNAL=ACTIVE.

APPEND_ONLY_HISTORY=ON.

CURRENT_STATE_ALWAYS_FRESH=ON.

ECONOMIC_SCOREBOARD_REQUIRED=ON.

PUSH_AFTER_MATERIAL_CHECKPOINT=ON.
