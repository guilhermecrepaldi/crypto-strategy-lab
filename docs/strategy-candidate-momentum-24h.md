# Candidata: rotação por momentum de 24 horas com barreira de custos

Status: **implementada e avaliada somente em TRAIN; promoção rejeitada**.

Identidade: `779c2fbcd18e729e74128a8bd517f009cdaeac28a4087924a6b94825312eedba`.

## Hipótese

Uma tendência observada em janela maior que o sinal de momentum atual, combinada com decisões
menos frequentes e uma vantagem mínima superior aos custos, pode reduzir trocas instáveis. O
caixa protege a carteira quando a tendência ampla enfraquece. Esta é uma hipótese formulada em
TRAIN, não evidência de generalização ou de vantagem.

## Identidade experimental proposta

- Capital inicial: 100 USDT.
- Universo e ações: `0=USDT`, `1=BTCUSDT`, `2=ETHUSDT`, `3=SHIBUSDT`, `4=BNBUSDT`.
- Uma posição por vez, exposição máxima de 75%, reserva de 25%, sem alavancagem ou martingale.
- Fee `0,001`, spread `0,0002` e slippage `0,0003`, aplicados pelo motor canônico.
- Custo conservador de ida e volta: `c = 2*fee + spread + 2*slippage = 0,0028`.
- Barreira fixa: `h = 2*c = 0,0056`.
- Momentum de 24 horas entre fechamentos, calculado com 289 candles consecutivos de cinco
  minutos (288 intervalos) e endpoints fixos pela grade UTC, todos fechados e disponíveis
  estritamente antes da decisão.
- Decisões às 00h, 04h, 08h, 12h, 16h e 20h UTC; fora desses horários, manter a posição.
- Parâmetros, capital, dataset, custos, versão do código, períodos, seeds e orçamento devem fazer
  parte da identidade antes da primeira execução.

Para cada ativo `i`, no instante `t`, calcular somente com dados disponíveis:

`m_i(t) = close_i(t-) / close_i((t - 24h)-) - 1`.

## Regras executáveis

1. Em caixa, entrar apenas se `m_BTC > h`; escolher o ativo elegível de maior `m_i`, também com
   `m_i > h`. Em empate, escolher o menor índice de ação.
2. Posicionado, manter até uma saída ou troca elegível.
3. Trocar para `j` somente quando `m_BTC > h`, `m_j > h` e `m_j - m_atual > h`.
4. Sair para caixa na próxima decisão se `m_BTC < -h` ou `m_atual < -h`.
5. A faixa `[-h, +h]` não gera uma nova entrada, saída ou troca.
6. Toda solicitação passa por `action_mask` e pelo motor canônico; rejeições preservam a posição
   efetiva e são contabilizadas, sem presumir execução.
7. Para uma decisão em `t`, usar como numerador o fechamento do candle aberto em `t-5m` e como
   denominador o fechamento do candle aberto em `t-24h05m`. Exigir exatamente 289 timestamps
   consecutivos, um candle por timestamp e preços positivos finitos em todos os ativos. Sem essa
   janela completa, com gap, atraso, duplicidade ou preço inválido: bloquear entrada/troca.
   Solicitar caixa apenas quando houver preço executável; nunca preencher, atrasar endpoints ou
   inventar dados.

## Evidência de development usada

Python reconciliou 12/12 identidades, 100.000 passos por identidade e 1.200.000 no total. A
comparação econômica usa o último checkpoint interno comum de 60.000 passos, não presume que o
modelo de 100.000 tenha sido avaliado. Entre as três seeds, as medianas de retorno foram: PPO BASE
`-10,98%`, PPO relativa `-14,01%`, DQN BASE `-21,54%` e DQN relativa `-2,94%`. Os quatro grupos
passam no diagnóstico de sobrevivência e falham no diagnóstico de valor em TRAIN. Isso não é
VALIDATION nem prova de generalização.

Fontes físicas:

- `artifacts/controlled-training/conservative/**/training-state.json`
- `reports/controlled-training-invalidation-20260905.json`
- `reports/controlled-training-development.json`

O relatório agregado final coincide com os estados físicos. Seus baselines internos são: caixa
`0%`, buy-and-hold ETH `+8,48%`, BTC `+1,71%`, BNB `+3,44%`, SHIB `-1,83%` e momentum simples
`-36,44%`.

## Implementação e avaliação

A autoridade da política é `CostAwareMomentum24hPolicy` em
`src/crypto_strategy_lab/ml/policies.py`; a execução reproduzível fica em
`src/crypto_strategy_lab/ml/candidate_workflow.py` e na CLI
`candidate-strategy-evaluate`. A normalização foi ajustada apenas em dezembro de 2021, antes de
todas as janelas avaliadas, embora a política não use a observação normalizada para decidir.

Foram executadas três janelas TRAIN de 30 dias sem sobreposição e três seeds por política. Como as
políticas são determinísticas, repetições por seed não são evidências independentes. Uma janela de
90 dias sobreposta foi executada somente como sensibilidade e excluída dos gates.

| Período | Retorno | Custos | Turnover | Drawdown | USDT | Operações |
|---|---:|---:|---:|---:|---:|---:|
| 01/jan–31/jan | -10,63% | 1,78 | 13,46 | 12,99% | 71,67% | 17 |
| 31/jan–02/mar | +9,92% | 1,83 | 12,75 | 14,75% | 64,44% | 15 |
| 02/mar–01/abr | -2,56% | 2,02 | 14,98 | 10,59% | 63,33% | 17 |
| 90 dias (sensibilidade) | -3,47% | 5,53 | 41,96 | 16,27% | 67,04% | 49 |

Nas janelas primárias, a mediana foi `-2,56%`, contra `0%` em caixa e `+8,48%` no melhor baseline
não-caixa, buy-and-hold de ETH. Nenhuma janela superou 40%. Não houve ruína, falha de execução,
solicitação rejeitada ou sinal indisponível. Os 84 artifacts comprimidos tiveram seus SHA-256
reconciliados com `reports/strategy-candidate-momentum-24h.json`.

A candidata reduziu custos medianos em aproximadamente 94,8% e turnover em 96,1% frente ao
momentum simples, sustentando a hipótese operacional de reduzir trocas. A perda da primeira janela
excede amplamente os custos, portanto taxas não explicam sozinhas o resultado. Não há contrafactual
suficiente para atribuir causalmente a perda a um ativo ou a permanecer em caixa.

## Decisão científica

O Astra decidiu rejeitar a promoção desta identidade: houve sobrevivência, mas não vantagem. A
mediana das diferenças pareadas contra ETH foi `-3,60` pontos percentuais. Menos operações e
ausência de ruína não compensam retorno inferior a caixa e ao melhor baseline. Os parâmetros não
serão ajustados retrospectivamente para resgatar a hipótese.

## Limitações conhecidas

- A campanha de development usa 80 USDT e suas avaliações internas chegam a 60.000 passos; a
  candidata de 100 USDT possui identidade separada.
- Há somente três janelas primárias, temporalmente adjacentes, e as repetições determinísticas por
  seed não aumentam a amostra independente.
- Os estados atuais guardam resumos, mas não trajetórias completas; hashes não permitem reconstruir
  eventos de development. A candidata preserva suas trajetórias completas em artifacts fora do Git.
- Condições prováveis de falha: mercado lateral, reversões rápidas, quebra do filtro BTC para
  altcoins e tendências menores que a barreira de custos.

## Próximo experimento

Antes de formular outra estratégia, criar uma identidade nova,
`MOMENTUM24H_FAILURE_ATTRIBUTION_V1`, para análise diagnóstica congelada das trajetórias já
existentes. Segmentar todas as posições entre entrada e saída, inclusive a posição terminal, e
decompor PnL de preço, custos, duração, ativo e decisões mascaradas verificáveis. Registrar critérios
de atribuição antes da análise; não ajustar horizonte, barreira ou filtro nesta identidade.
