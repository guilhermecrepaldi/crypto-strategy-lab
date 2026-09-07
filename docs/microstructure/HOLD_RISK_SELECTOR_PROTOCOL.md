# Hold-risk selector — protocolo diagnóstico congelado

Status: `PREREGISTERED_DIAGNOSTIC`; identidade de pesquisa `M011`, parent `M007`.
Autoridade científica: revisão GPT-6 Astra antes de anexar desfechos ao snapshot.
Este documento não registra nem autoriza replay M011 por si só. M007 permanece champion.
Escopo: USDCUSDT, DEVELOPMENT integral de 2026-01-01 ao cutoff físico canônico,
PRICE_PATH, capital inicial 100 USDT. Dataset, tick catalog e cenário do M007 são autoridades.

## Unidade, relógio e snapshot

Enumerar todas as decisões de seleção elegíveis do relógio M007 de um minuto, incluindo
decisões flat sem mudança, seleção inicial e quaisquer seleções adicionais realmente
registradas pelo motor. Minutos com inventário aberto são contados separadamente como
`OPEN_NO_SELECTION`, sem inventar oportunidade de troca. Registrar também cada BUY M007
com o identificador da última decisão aplicável; uma decisão pode preceder vários BUYs.
Separar `decision_count`, `entry_count` e `selection_change_count`.

Em decisão T, limite exclusivo é `floor(event / EVENT_ORDER_SCALE) * EVENT_ORDER_SCALE`:
nenhum trade com timestamp igual a T, mesmo com sequência menor, entra nas features.
Sequências distinguem LOW/HIGH históricos com mesmo timestamp; duração usa micros reais,
sem transformar sequence ID em tempo. Tick/elegibilidade seguem evidência disponível
estritamente antes de T. Preservar a seleção M007 histórica e reportar diferença entre
seu score registrado/reconstruído e o score strict-timestamp quando existir.

Universo: candidatos com um exchange tick vigente, LOW/HIGH compatíveis com o grid causal,
LOW observado no prefixo e ciclos24h > 0. Calcular score M007 para todos os elegíveis;
calcular métricas de risco e materializar somente top 10 por M007 score, mais candidato
M007 quando ausente, sem duplicatas. Alternativas e gates de sinal referem-se estritamente
a esse conjunto (no máximo 11 candidatos), sem extrapolar ausência de sinal às outras faixas.
Desempate M007: score, ciclos, menor LOW, menor distância; desempate diagnóstico igual.
O universo não pode ser revelado por visitas futuras a LOW/HIGH.

Persistir snapshot causal e SHA256 antes de ler/juntar desfechos. Manifest inclui hashes
de protocolo, código publicado, tape, catálogo, cenário, parent e intervalo; resultados
prospectivos não existem nesta análise. Anexos futuros são
`RETROSPECTIVE_DIAGNOSTIC_ONLY`, em estrutura separada e ligada pelo hash do snapshot.

## Episódios, janelas e censura

Para cada candidato e janela W em {1h, 4h, 24h, 30d}, começar flat em T-W, reproduzir
LOW -> primeiro HIGH posterior, serialmente e sem sobreposição, com eventos < T.
Cada novo LOW só abre após o HIGH anterior. O último LOW sem HIGH observado é um
episódio `RIGHT_CENSORED` com idade T-entry; não é descartado nem fechado em T.
As janelas são estimadores de entradas novas, não quatro bancas nem replays financeiros.
O reset da borda esquerda é explícito e corresponde à semântica canônica de
`CandidateTimeline.contained_cycles`; nunca usar duração de saída futura armazenada
na timeline. Se a tape não cobrir toda W, marcar janela `PARTIAL_HISTORY` e não
qualificá-la para suporte. Não baixar novos dados por efeito deste protocolo.

1h/4h/24h medem continuidade recente. 30d é janela fixa de risco, necessária para
observar maturação de 24h e mais de um dia; não escolher seu tamanho por resultado.
Para cada W publicar completos, censurados, dias distintos de entrada, idade censurada,
LOW/HIGH event counts, ciclos/hora de parede, último HIGH bem-sucedido e sua idade.

`CAPITAL_HOURS_CONSUMED_W = sum((observed_exit_or_T - entry)/3600)`.
`CYCLES_PER_CAPITAL_HOUR_W = completed_W / capital_hours_W`.
`PRICE_PATH_EDGE_PER_CAPITAL_HOUR_W = (HIGH-LOW)/LOW * cycles_per_capital_hour_W`.
Unidade da última: retorno bruto por hora de capital; multiplicar por 100 produz
USDT/h na régua fixa100. Não multiplicar throughput duas vezes. Capital-hours zero
produz `UNKNOWN`, não infinito nem epsilon escolhido. `NET_EDGE` permanece UNKNOWN.

Para h em {1m,5m,15m,1h,6h,24h}, coorte madura contém **todas** as entradas da janela
com entry < T-h, inclusive as ainda abertas. A desigualdade estrita evita declarar
falha sem observar um HIGH exatamente em T quando entry+h=T. Entrada recente concluída antes de h
também fica fora: incluí-la causaria seleção por desfecho. `n_h` é a coorte madura;
`s_h` conta as que fecharam em duração <= h. `CLOSURE_RATE_h=s_h/n_h`;
`LOCK_RISK_h=(n_h-s_h+1)/(n_h+2)` é regularização Laplace, não probabilidade calibrada
nem intervalo de confiança. Uma censura com idade >=h é falha conhecida nesse horizonte;
censuras com idade <=h seguem explícitas, sem classificação. `LONG_LOCK_h` significa >h.

Suporte de risco30d: >=30 episódios completos, >=3 dias UTC distintos com entradas e
>=30 entradas maduras por horizonte utilizado. Taxas brutas e denominadores podem ser
exibidos abaixo do gate com `supported=false`; qualquer ranking exige suporte.
Risco insuficiente é `UNKNOWN`. Quantis empíricos completos p50/p75/p90/p95 exigem
>=30 completos e são rotulados `COMPLETED_ONLY`, acompanhados de censored_share.
Não apresentá-los como quantis da distribuição incondicional; não entram no ranking.

`EXPECTED_CYCLES_BEFORE_LOCK_h = s_h / (n_h-s_h)` no mesmo conjunto maduro:
estimativa descritiva de sucessos rápidos por episódio >h. Zero falhas resulta
`UNBOUNDED_IN_SAMPLE`, jamais promessa de segurança; publicar numerador/denominador.
Não interpretar a razão como independência comprovada ou previsão de calendário.

## Regra causal de alternativa e score previamente fixado

Usar métricas30d para risco e métricas24h para produtividade. A e P designam
alternativa e candidato M007 no mesmo snapshot. Ambos precisam de suporte completo
nos horizontes 1h/6h/24h, janela24h completa e capital-hours24h positivos.

Alternativa qualificada exige simultaneamente:

- A != P e elegibilidade M007 no instante T;
- risco24h(A) <= 0.75 * risco24h(P);
- risco1h(A) <= risco1h(P) e risco6h(A) <= risco6h(P);
- edge_per_capital_hour24h(A) >= 0.80 * edge_per_capital_hour24h(P);
- ciclos24h(A) >= 0.80 * ciclos24h(P), ciclos1h(A) > 0;
- score(A) > score(P).

Fórmula candidata, congelada antes do diagnóstico, sem ML:

`R = (min(1, 24*C1/C24) + min(1, 6*C4/C24))/2`

`SCORE = EDGE_PER_CAPITAL_HOUR24 * CLOSURE_RATE_1H_30D * R /
         (1 + LOCK_RISK_1H_30D + 6*LOCK_RISK_6H_30D + 24*LOCK_RISK_24H_30D)`.

C24>0; falta de suporte torna score `UNKNOWN`. Pesos 1/6/24 são os horizontes
em horas, visando cauda; recência tem pesos iguais, limitada em 1 para não premiar
explosão isolada. Retenção80% dá margem diagnóstica sem descartar throughput.
Diferença25% de risco exige separação prática; não alegar significância estatística.
Não retunar nenhum número após observar desfechos ou capital final.

## Anexo retrospectivo e decisão de sinal

Por BUY M007, herdar classificação causal da última decisão real, nunca reclassificar
alternativa usando seu futuro. Anexar duração observada, censura terminal, flags >1h,
>6h, >24h e ciclos efetivamente concluídos nos próximos 1h/6h/24h apenas quando o
cutoff cobrir o horizonte inteiro. Contrafactual de alternativa, se calculado, permanece
descritivo separado e não entra em classificação, seleção nem autorização.

`DEAD_CAPITAL_HOURS = sum(hold observado)`; coincide com horas de inventário aberto
por haver uma banca serial. Publicar também `HOURS_POSITION_OLDER_THAN_h=sum(max(hold-h,0))`.
`AVOIDABLE_LOCK_OPPORTUNITIES_h` conta BUYs com hold observado >h e alternativa
qualificada no snapshot da decisão. Reportar também decisões únicas correspondentes.
`ESTIMATED_AVOIDABLE_CAPITAL_HOURS` soma hold observado desses BUYs >24h;
`ESTIMATED_AVOIDABLE_EXCESS_24H` soma max(hold-24h,0) dos mesmos. São exposição
potencialmente endereçável, **não horas recuperadas causalmente demonstradas**.
Incluir censura terminal se já excede h; não estimar duração após cutoff.

`HOLD_RISK_SIGNAL_FOUND=YES` somente se >=3 BUYs >24h com alternativa qualificada,
em >=2 meses UTC distintos de entrada, e excess24h endereçável >=10% do total M007.
Exigir cobertura de risco conhecida para P (30d completos, 30 episódios completos,
3 dias e 30 maduros em cada horizonte1h/6h/24h) e pelo menos uma alternativa top10
com os mesmos suportes em >=80% dos BUYs >24h. O denominador inclui todos os BUYs
M007 >24h, inclusive terminal censurado já >24h e casos sem suporte; não removê-los.
Sem essa cobertura: INCONCLUSIVE. Com cobertura e sem os demais
gates: NO. São gates de interpretabilidade DEVELOPMENT, não teste prospectivo.
Discriminadores são diferenças assinadas das features preregistradas nos grupos
>1h/6h/24h versus <=h, com suporte/cobertura, sem busca de novos cutpoints.

Somente sinal YES permite revisão Astra autorizar registro M011. Nenhum artifact
`models/M011` antes dessa decisão. Score acima é candidato preregistrado; autorização
de replay requer spec/config/hypothesis/lineage completos e commit/push pré-run.

## Gates M011 condicionais, congelados antes de qualquer resultado M011

Única mudança permitida: ranking. Preservar clock1m, flat-only, one tick, one lot,
one bank, LOW/HIGH fixos aberto, ausência de release/timeout/stop. UNKNOWN conserva
ranking M007 (fallback científico explícito de suporte, sem inventar segurança).
Replay integral, mesmo cutoff/tape/scenario, initial100 e contabilidade canônica.

Promoção científica exige todos: ciclos >=90% M007; horas>24h <=75%; inventory-open
share <=90% da share M007; zero days <=M007; fixed100 PnL >=95% M007; capital final
>=90% M007; max drawdown percentual <=M007 +1 ponto percentual; em >=75% dos meses
UTC com ciclos M007>0 preservar >=80% dos ciclos do mês. Reportar meses sem ciclos
separadamente. Comparação e autópsia completas são obrigatórias mesmo com falha.
Promoção científica jamais altera SHADOW: nova autorização explícita OWNER é necessária.

## Implementação e verificação

ADAPT: loader validado de evidência M007, tape NumPy imutável e episódios
`CandidateTimeline` existentes. BUILD: consultas de janelas/censura e quantis móveis
exatos (Fenwick), somente para análise offline; não há outro engine de estratégia.
ADOPT: definição de censura à direita descrita na
[documentação SciPy](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.ecdf.html).
Não há nova dependência nem código externo copiado. As taxas de coorte madura aqui
não são estimadores Kaplan–Meier nem probabilidades calibradas.

O ledger original é lido para reconstruir o relógio, estado e seleção efetivamente
observados. Durações/desfechos não entram nas features; somente o segundo passe,
depois do selo de arquivo/snapshots, anexa outcomes. O campo
`parent_event_order_score` é contexto `LEGACY_EVENT_ORDER_CONTEXT_ONLY_NOT_A_FEATURE`:
ele não participa do ranking strict-timestamp ou da qualificação de alternativas.

Antes do diagnóstico: `uv run pytest`; `uv run ruff check --exclude public_market.py .`;
`uv run ruff format --check --exclude public_market.py .`;
`uv run mypy --strict --exclude public_market.py`; `git diff --check`.
A exclusão local preserva o arquivo não versionado/inacabado do Prompt 2, que tem
erros próprios de estilo e import `websockets.sync.client` ainda não instalado.
Não há exclusão permanente na configuração do projeto ou supressão de erros da pesquisa.
Não interpretar esses comandos como validação do transporte shadow.
