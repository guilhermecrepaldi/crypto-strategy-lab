# M036 — diagnóstico causal S0 de alcançabilidade da entrada

Status: `DRAFT_NOT_CONSUMED`. Este arquivo descreve uma hipótese de desenvolvimento,
mas **não autoriza execução**. A autoridade ativa continua sendo
`docs/research/CURRENT_STATE.md`, que declara a próxima janela como não autorizada
depois da campanha M035 V2 consumida.

## Linhagem e escopo técnico

O parent é `M035_PARALLEL_PAIR_CAPITAL_MANAGER`. M035 V2 é a motivação empírica:
nos níveis de compra admitidos, não houve alcance por fluxo agressor vendedor enquanto
as ordens eram executáveis. M036 não reproduz a grade/hotline de dois pares de M035,
nem reivindica as métricas de M035 no motor atual. É uma hipótese nova de livro único
que adapta somente o motor causal S0 existente para `USDCUSDT`, com níveis fixos e
uma fita L2 + trades individualizados que ainda precisa ser pré-selecionada e congelada.

O adaptador declara explicitamente a semântica do motor legado: seu campo interno
`usdc` é o caixa em `USDT` (quote) e `fdusd` é o inventário em `USDC` (base). Nenhum
relatório M036 deve apresentar esses nomes internos como os ativos base/quote corretos.

## Hipótese congelável após autorização

Em uma nova janela selecionada antes de qualquer inspeção econômica, o nível passivo
de compra `1.0000 USDT/USDC` pode ser alcançado no envelope de fila L2 por trades
individuais; um nível de saída `1.0030 USDT/USDC` deixa edge maker modelado
estritamente positivo em cada cenário F0/F1/F2/F5/F10. O runner rejeita a campanha
antes do claim se algum cenário não tiver esse edge. Um ciclo **inferido** com perda,
ou equity terminal modelada abaixo do capital inicial, falha os checks técnicos depois
do claim.

## Medidas que a execução autorizada produziria

- fills e ciclos inferidos somente de snapshot/delta L2 contínuo, cobertura L2
  limitada em toda a janela e trades individuais com IDs nativos contíguos;
- conservação independente de caixa quote, inventário base e capital bloqueado;
- ciclos inferidos negativos, inventário terminal e marcação com livro L2 válido no cutoff;
- `committed_capital_hours_quote`: integral do valor reservado por BUY pendente mais
  custo de inventário preenchido, apenas nas janelas autorizadas;
- fee break-even contrafactual apenas a partir de cenários com ciclos inferidos concluídos.

## Condições antes de qualquer execução

O OWNER precisa publicar uma nova autorização no cabeçalho autoritativo de
`CURRENT_STATE.md`, uma janela UTC exata, a hash final desta spec, uma fita local
pré-selecionada, manifest com hashes das fontes, validação snapshot/delta e binding de
trades individuais, além do commit `main` revisado. Também precisa congelar dois
registros locais e hashados, `fee-record` e `rule-record`, com evidência histórica
`BINANCE_SPOT/USDCUSDT`, intervalo temporal que cubra toda a janela, contexto de tier,
fees por lado e filtros de preço/lote/notional. Como o adaptador S0 legado representa
uma única grade, ele só é elegível quando o `tickSize` e o `stepSize` históricos forem
iguais à sua `step_size`; caso contrário, o run contrafactual é recusado. O status, os
hashes e a janela no `job.yaml` devem então coincidir exatamente com esse estado. M035
não pode ser reexecutado ou ajustado.

Também deve existir cobertura L2 contínua desde a abertura até o cutoff, com cada
intervalo dentro de `max_l2_update_age_seconds`; o runner recusa feed gaps, halt
externos e listas externas de cancelamento porque eles não trazem uma decisão causal
pré-registrada. A fonte de trades deve provar IDs nativos contíguos; uma amostra de
prints não pode consumir fila modelada.

## Limites da afirmação

M036 é desenvolvimento causal local, não OOS, não recomendação, não prova de
rentabilidade e não autorização para SHADOW com transporte de ordens, TESTNET ou LIVE.
O único `evidence_class` admitido é `COUNTERFACTUAL_L2_QUEUE_ENVELOPE`: profundidade
L2 pública fornece no máximo `KNOWN_DISPLAYED_AHEAD_ONLY`, enquanto a prioridade dentro
do nível é `UNKNOWN_TIME_PRIORITY_WITHIN_EXISTING_LEVEL`. Não há ACK, ID de ordem ou
recibo de fill próprio da venue; portanto nenhum resultado pode receber `PASS`
econômico, mesmo se todos os checks técnicos forem aprovados. A fita tampouco prova
ordem de chegada/capture clock ou latência privada histórica; latência zero é hipótese
contrafactual congelada, não uma medição histórica. A ausência de fill, veredito
inconclusivo, falha técnica ou falha pós-claim é evidência preservada e não permite
trocar níveis, janela, fees ou identidade para tentar novamente.

Os cenários F1/F2/F5/F10 são sensibilidades contrafactuais pré-registradas, não uma
afirmação sobre a taxa histórica efetiva, salvo se o `fee-record` as documentar de
forma explícita. O runner rotula essa distinção nos relatórios.
