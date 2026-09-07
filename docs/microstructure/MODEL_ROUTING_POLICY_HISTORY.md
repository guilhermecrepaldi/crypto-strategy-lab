Status: HISTORICAL_SUPERSEDED_POLICY / SUPERSEDED_BY_OWNER

This records the former OWNER instruction verbatim for provenance. It was superseded by
`OWNER_STRATEGY_OVERRIDE.md`. TOKEN_SAVING_PRIORITY=OFF; QUALITY_FIRST=ON;
CONTEXT_PRESERVATION=ON; SCIENTIFIC_DETAIL_PRESERVATION=ON. Do not execute this historical policy.

---

# PROJECT-WIDE MODEL ROUTING POLICY

# CRYPTO-STRATEGY-LAB

# OBJETIVO: REDUZIR CONSUMO SEM REDUZIR RIGOR CIENTÍFICO

Esta instrução passa a valer para todo o trabalho futuro deste repositório.

O OWNER possui orçamento/uso limitado de modelos premium.

Portanto:

NÃO usar o modelo mais caro simplesmente porque está disponível.

A regra é:

USE THE CHEAPEST MODEL CAPABLE OF COMPLETING THE TASK RELIABLY.

Escalar modelo/raciocínio somente quando existir justificativa objetiva.

==================================================

1. PRINCÍPIO GERAL
   ==================================================

Separar todo trabalho em quatro classes:

A. MECHANICAL
B. ENGINEERING
C. SCIENTIFIC
D. FINAL INDEPENDENT REVIEW

Não utilizar um único modelo caro para todas as classes.

==================================================
2. MECHANICAL — GPT-5.6 LUNA
============================

DEFAULT:

MODEL = GPT-5.6 Luna
EFFORT = Medium

Usar Luna para:

* acompanhar processos Python;
* verificar PID;
* observar checkpoints;
* git status;
* git diff;
* git log;
* HEAD vs origin/main;
* conferir hashes;
* verificar arquivos;
* executar pytest;
* executar Ruff;
* executar mypy;
* executar git diff --check;
* checks de schema;
* checks de existência;
* auditorias mecânicas;
* comparar JSON;
* comparar CSV;
* validar contagens;
* verificar invariants simples;
* atualizar status mecânico;
* gerar tabelas a partir de resultados já calculados;
* documentação factual;
* commit/push depois de gates já definidos;
* monitorar long-running processes.

Luna NÃO deve:

* inventar nova hipótese científica;
* escolher parâmetros econômicos;
* alterar promotion gates;
* decidir entre hipóteses concorrentes;
* interpretar edge;
* promover modelo.

==================================================
3. LONG-RUNNING PYTHON
======================

Regra absoluta:

NÃO gastar Sol/Astra acompanhando Python executar.

Se um replay demora:

10 minutos
30 minutos
1 hora
ou mais,

o trabalho pesado deve permanecer no:

PYTHON / OS PROCESS.

O LLM apenas:

1. inicia;
2. registra identidade;
3. verifica periodicamente;
4. lê checkpoint;
5. reage a erro.

Monitoring:

Luna / Medium.

Não usar High/Ultra para esperar processamento.

==================================================
4. ENGINEERING — GPT-5.6 TERRA
==============================

DEFAULT DE IMPLEMENTAÇÃO:

MODEL = GPT-5.6 Terra
EFFORT = Medium

Usar Terra Medium para:

* implementar features normais;
* escrever funções;
* refactors;
* desenvolver CLI;
* persistência;
* dashboards;
* serialização;
* integração de componentes;
* implementar testes;
* resolver bugs normais;
* melhorar arquitetura;
* performance engineering normal.

==================================================
5. ENGINEERING COMPLEXO — TERRA HIGH
====================================

Escalar:

Terra Medium
→
Terra High

somente quando houver:

* bug não reproduzível facilmente;
* problema Decimal/ledger;
* causalidade complexa;
* race condition;
* concorrência;
* recuperação após crash;
* corrupção de estado;
* inconsistência entre artifacts;
* algoritmo difícil;
* refactor estrutural;
* falha depois de tentativa razoável em Medium.

Não escalar automaticamente por tamanho de arquivo.

==================================================
6. SCIENTIFIC REVIEW — GPT-5.6 SOL
==================================

MODEL = GPT-5.6 Sol
EFFORT = High

Usar somente para trabalho genuinamente científico:

* desenhar hipótese;
* avaliar validade causal;
* preregistration;
* definir search space;
* definir promotion gates;
* avaliar risco de overfit;
* analisar robust region;
* interpretar resultados;
* decidir quais métricas são cientificamente relevantes;
* revisar baseline justo;
* analisar estratégia econômica;
* decidir se novo experimento é justificável.

Sol NÃO deve ficar acompanhando execução mecânica.

Fluxo:

Terra implementa
→
Luna audita mecanicamente
→
Sol revisa ciência.

==================================================
7. GPT-6 ASTRA — SOMENTE GATE DE ALTO VALOR
===========================================

GPT-6 Astra é recurso premium.

NÃO usar Astra como agente padrão.

NÃO usar Astra para:

* acompanhar processos;
* fazer git status;
* esperar replay;
* rodar pytest;
* corrigir formatting;
* gerar documentação simples;
* comparar hashes;
* revisar cada pequeno patch;
* conferir cada cenário individual;
* repetir análise já realizada por Sol.

Astra só deve ser chamado quando existir uma DECISÃO DE ALTO VALOR.

Exemplos:

A. campanha inteira terminou;

B. existe candidato concreto para promoção;

C. Sol encontrou questão científica ambígua/material;

D. há risco real de conclusão causal incorreta;

E. mudança arquitetural/econômica de grande impacto;

F. revisão independente antes de mudar champion;

G. decisão antes de Testnet/Live.

==================================================
8. ASTRA FINAL REVIEW
=====================

Uso preferencial:

MODEL = GPT-6 Astra
EFFORT = High

UMA revisão consolidada.

Não dezenas de micro-reviews.

Antes de chamar Astra:

preparar um pacote conciso contendo:

* hipótese;
* preregistration;
* configuração;
* baseline;
* resultados;
* gates;
* robustness;
* anomalies;
* auditoria Luna;
* análise Sol;
* arquivos/linhas necessárias;
* hashes.

Astra deve receber:

SUMMARY + PRIMARY ARTIFACTS

e não centenas de milhares de linhas de log bruto.

==================================================
9. PROIBIDO ASTRA MONITOR
=========================

Nunca:

"Astra acompanhará o replay."

Nunca:

"Astra verificará novamente daqui a alguns minutos."

Nunca:

"Astra ficará observando o processo."

Monitoring pertence a:

Luna.

==================================================
10. CONTEXT BUDGET
==================

Evitar sessões gigantes.

Git é a memória canônica.

Após cada milestone:

1. publicar artifact conciso;
2. commit;
3. push;
4. escrever CURRENT_STATE;
5. próxima fase deve ler o CURRENT_STATE e artifacts relevantes.

Não carregar logs completos antigos desnecessariamente.

==================================================
11. LOG COMPACTION
==================

Para long runs:

não alimentar cada linha de progresso aos modelos caros.

Manter arquivo:

RUN_PROGRESS.json

ou equivalente.

Campos suficientes:

RUN_ID
SOURCE_SHA
SCENARIO
START_TIME
CURRENT_STAGE
CHECKPOINTS_COMPLETE
TOTAL_CHECKPOINTS
LAST_TIMESTAMP
CYCLES
RELEASES
ERROR
STATUS.

Luna pode ler esse arquivo.

Sol/Astra recebem somente o resultado consolidado.

==================================================
12. ERROR ESCALATION
====================

Quando ocorrer erro:

LEVEL 1:
Luna identifica classe mecânica.

Se simples:
Luna resolve/verifica.

Se requer código:
→ Terra Medium.

Se Terra Medium não resolver ou for problema crítico:
→ Terra High.

Se a correção alterar significado científico:
→ Sol High.

Somente se ainda houver decisão científica material:
→ Astra High.

==================================================
13. NÃO ESCALAR POR ANSIEDADE
=============================

Não subir modelo simplesmente porque:

* processo está demorando;
* output ficou grande;
* campanha é importante;
* capital teórico é grande;
* OWNER está aguardando.

Escalonamento depende da natureza intelectual da tarefa.

==================================================
14. PRECISION / LEDGER POLICY
=============================

Para Recovery Reserve e microstructure:

bugs de:

Decimal
fees
ledger
reserve
equity
release
rounding
causal event order

devem inicialmente ir para:

Terra High.

Depois da correção:

Luna verifica invariants.

Sol só revisa se a correção alterar:

economic semantics
scientific gates
causality
model behavior.

Astra somente se isso afetar uma decisão final de promoção.

==================================================
15. RECOVERY RESERVE CAMPAIGNS
==============================

Para campanhas Recovery Reserve:

EXECUTOR:
Python.

ENGINEERING OWNER:
Terra Medium/High.

MECHANICAL AUDITOR:
Luna Medium.

SCIENTIFIC REVIEWER:
Sol High.

FINAL INDEPENDENT REVIEWER:
Astra High.

Não inverter essa hierarquia.

==================================================
16. SCENARIO GRID
=================

Ao executar 10, 18, 50 ou 100 cenários:

NÃO chamar Sol/Astra por cenário.

Executar todos.

Luna valida cada checkpoint mecanicamente.

Depois consolidar:

SCENARIO_MATRIX.

Somente então:

Sol analisa a matriz inteira.

Astra entra apenas se existir candidato sério.

==================================================
17. PROMOTION FLOW
==================

Fluxo oficial:

PYTHON
↓
LUNA MECHANICAL AUDIT
↓
TERRA ENGINEERING RECONCILIATION
↓
SOL SCIENTIFIC REVIEW
↓
ROBUST CANDIDATE EXISTS?

Se NÃO:

STOP.

Não chamar Astra sem necessidade.

Se SIM:

ASTRA FINAL INDEPENDENT REVIEW
↓
OWNER DECISION.

==================================================
18. EFFORT POLICY
=================

Usar:

LOW/INSTANT:
somente tarefas triviais, se disponível e confiável.

MEDIUM:
DEFAULT.

HIGH:
problemas complexos ou ciência.

EXTRA HIGH / ULTRA:
NÃO usar por padrão.

Ultra/Extra High somente mediante:

explicit technical justification

ou

OWNER authorization.

Não usar para replay/monitoramento.

==================================================
19. DEFAULT MODEL
=================

Se não houver razão específica:

DEFAULT_CODE_MODEL =
GPT-5.6 Terra

DEFAULT_CODE_EFFORT =
Medium.

==================================================
20. MECHANICAL SUBAGENT
=======================

Sempre que subagente barato for suficiente:

preferir:

GPT-5.6 Luna / Medium.

Especialmente para:

verification
QA
repo inspection
tests
artifact reconciliation.

==================================================
21. SCIENTIFIC SUBAGENT
=======================

Quando necessário:

GPT-5.6 Sol / High.

Fornecer pergunta científica específica.

Evitar:

"revise tudo".

Preferir:

"Revise causalidade e promotion gates destes artifacts específicos."

==================================================
22. ASTRA CALL BUDGET
=====================

Objetivo:

ZERO ou UMA chamada Astra por milestone científico relevante.

Mais de uma chamada exige justificativa registrada.

Exemplo:

ASTRA_ESCALATION_REASON=
...

Não chamar novamente apenas para confirmar sua própria conclusão anterior.

==================================================
23. MODEL FALLBACK
==================

Se determinado modelo não estiver disponível:

usar o modelo imediatamente inferior capaz de cumprir a função.

Preferência:

Astra
→ Sol
→ Terra
→ Luna

Mas não elevar modelo só porque o inferior está temporariamente indisponível se a tarefa puder esperar dentro da mesma execução.

Nunca falsificar qual modelo realizou a revisão.

Registrar:

REQUESTED_MODEL=
ACTUAL_MODEL=
EFFORT=

==================================================
24. COST-AWARE REVIEW PACKET
============================

Antes de qualquer review Sol/Astra:

gerar arquivo conciso:

SCIENTIFIC_REVIEW_PACKET.md

Contendo apenas:

1. pergunta;
2. hipótese;
3. invariants;
4. baseline;
5. configurações;
6. resultados;
7. gates;
8. falhas;
9. robustez;
10. decisão solicitada;
11. links/paths para evidência detalhada.

Não enviar log operacional completo ao reviewer salvo necessidade específica.

==================================================
25. OWNER OUTPUT
================

Nos reports finais, incluir:

MODEL_USAGE_SUMMARY

com:

LUNA_TASKS=
TERRA_TASKS=
SOL_REVIEWS=
ASTRA_REVIEWS=

ASTRA_ESCALATION_REASONS=

EXTRA_HIGH_OR_ULTRA_USED=
YES/NO

Se YES:
WHY=

Isso serve para auditar consumo.

==================================================
26. CURRENT CRYPTOCHANGE POLICY
===============================

Para os trabalhos atuais:

Recovery Reserve research
M007 shadow
scenario studies
ledger corrections

seguir:

Luna Medium:
monitoramento/auditoria mecânica.

Terra Medium:
implementação normal.

Terra High:
ledger/Decimal/causal bugs difíceis.

Sol High:
preregistration e revisão científica consolidada.

Astra High:
somente revisão independente final quando houver candidato sério.

==================================================
27. NÃO SACRIFICAR QUALIDADE
============================

Esta política NÃO significa:

"sempre usar modelo barato".

Significa:

"usar inteligência cara onde ela altera a qualidade da decisão."

Se Luna/Terra detectarem uma questão que genuinamente exige Sol/Astra:

ESCALAR.

Mas registrar por quê.

==================================================
28. REGRA FINAL
===============

DO NOT SPEND FRONTIER REASONING ON MECHANICAL WAITING.

Python deve calcular.

Luna deve conferir.

Terra deve construir e corrigir.

Sol deve pensar cientificamente.

Astra deve julgar apenas decisões críticas.

Use Medium como default.

Use High quando a complexidade justificar.

Não usar Extra High/Ultra sem necessidade explícita.

Git e artifacts são a memória canônica.

Agrupe revisões.

Evite context bloat.

Proteja o orçamento do OWNER sem reduzir rigor científico.

A partir deste momento:

MODEL_ROUTING_POLICY=ACTIVE.
