# LEGACY — stablecoin market research

Status: `LEGACY_EVIDENCE`. This document records how the hypothesis moved from FDUSDUSDC to
USDCUSDT. Any FDUSD comparison or recommendation below is historical context, not an active
experiment or instruction to perform new FDUSD work.

Consulta realizada em **2026-09-06**. Este documento é uma investigação anterior a qualquer
adaptação. Ele não muda `S0_FROZEN_LEVELS-v1`, não cria estratégia, não troca o par e não afirma
execução. Dados atuais vieram somente de endpoints públicos de mercado; nenhuma conta, chave,
Testnet ou ordem foi usada.

## 1. Nossa estratégia atual

O objeto de estudo não é market making convencional. É um autômato serial com uma banca, um
lote e um par: publica compra maker em `LOW`; depois do fill completo, mantém somente a venda em
`HIGH`; só reinveste e reinicia após o fechamento. Não há alavancagem, martingale, DCA, previsão,
grid, segunda banca ou stop temporal. Posição aberta é capital imobilizado, não ociosidade.

A hipótese econômica é que um ganho líquido minúsculo, repetido muitas vezes e composto, possa
ser relevante. O primeiro laboratório usou `FDUSDUSDC 0.9988 -> 0.9989`. O nível mostrou
recorrência, mas também migração no tempo. Por isso `LOW/HIGH` não pode ser eterno. A ideia
`STAY UNTIL BAD` procura preservar uma região enquanto ela funciona e só reavaliá-la quando o
lote estiver livre e houver deterioração confirmada. Isso permanece hipótese, não implementação
autorizada nesta etapa.

## 2. Precedentes e grau de similaridade

Há implementações públicas de stablecoin market making, mas nenhuma evidência encontrada de um
motor com exatamente uma compra, uma venda fixa, uma banca e milhares de ciclos líquidos por
dia. BBGO, GQTC e Hummingbot usam ordens nos dois lados, várias camadas, inventário e/ou
reprecificação. São precedentes úteis de microestrutura, não validações da nossa estratégia.

| Dimensão | Nosso motor | BBGO `scmaker` | GQTC/Columbia GTQB | Hummingbot PMM | hftbacktest |
|---|---|---|---|---|---|
| Ordens simultâneas | uma, em um lado | vários níveis + ajuste | grid + queue-based, dois ativos | dois lados; layers opcionais | depende da estratégia |
| Níveis | um `LOW/HIGH` | até `N+1` por lado | 2 QB + 10 grid por lado no exemplo | um ou vários | não prescreve |
| Centro | faixa congelada no ciclo | BBO, EMA e Bollinger | BBO, reserva e skew | mid/fonte configurável | replay do book |
| Inventário | lote aberto bloqueia novo ciclo | custo médio e exposição | caps e skew | skew, ping-pong, hanging | modelo do usuário |
| Reposição | somente após fechar | cancel/recreate por calendário | sincroniza targets | refresh periódico | latência configurável |
| Fila | ainda não demonstrada | sem FIFO explícita no módulo | modelo probabilístico | exchange em produção | modelos de fila MBP |
| Objetivo | retorno líquido composto | prover liquidez com lucro mínimo | volume ponderado por ROE | spread/inventário | fidelidade de replay |
| Similaridade | referência | baixa | baixa | parcial | infraestrutura útil |

## 3. BBGO `scmaker`

**Fato documentado.** O README chama `scmaker` de estratégia para stablecoins como USDC/USDT.
O exemplo oficial fixa `USDCUSDT` na exchange **MAX**, não Binance, com maker `0%`, taker
`0.025%`, dez layers configuradas, tick de camada `0.0001`, ajuste a cada minuto, renovação de
liquidez a cada hora, EMA 99 x 1h, Bollinger 10 x 1h, exposição máxima e `minProfit=0.01%`.
[Configuração fixa consultada](https://github.com/c9s/bbgo/blob/3c7776aba8291e404caf6107bdf5bcb15d4850d6/config/scmaker.yaml).

O código usa `LIMIT_MAKER`. O nível zero acompanha o BBO; os demais se distribuem ao redor da
EMA e a borda usa a banda. O laço é inclusivo `0..NumOfLiquidityLayers`, portanto dez layers
configuradas podem produzir onze níveis por lado, sujeitos a saldo e filtros. Ordens de ajuste
protegem o preço em relação a custo médio, maker fee e lucro mínimo. A atualização de liquidez
cancela e recria ordens; não há seletor serial equivalente a `IDLE_TRIGGERED`.
[Implementação fixa consultada](https://github.com/c9s/bbgo/blob/3c7776aba8291e404caf6107bdf5bcb15d4850d6/pkg/strategy/scmaker/strategy.go).

**Inferência.** Devemos adotar a separação entre custo, posição, dust, exposição e preço
desejado. Não devemos copiar layers, EMA/Bollinger, cotações bilaterais nem o calendário de
cancelamento. A proteção de custo reduz vendas nominais ruins, mas não garante fill, recuperação
do peg ou lucro líquido. O indicador `Intensity` existe, porém não é consumido na decisão de
cotação observada; não se deve atribuir ao módulo uma política que o código não executa.

## 4. GQTC / Columbia

**Relato primário dos participantes.** O repositório da equipe Moon Shot afirma 3º lugar entre
50 equipes e prêmio de USD 5 mil na Gemini Collegiate Quant Trading Competition de fevereiro a
abril de 2026, executada live com USD 3 mil fornecidos. Um perfil de membro repete a colocação,
mas não foi encontrada publicação do organizador confirmando ranking e prêmio. Esses fatos ficam
classificados como `PARTICIPANT_REPORTED`, não como prova independente.
[Repositório em commit fixo](https://github.com/hk3425-hash/gqtc-market-making/tree/6f9e1d7f81ca5bd3b9847f532f1ceabb48837b17).

O começo usou `USDC/USD` e `USDT/USD` na Gemini, com taxa maker zero. Três semanas antes do fim,
volume de stablecoins deixou de pontuar e a equipe migrou para XRP/BNB/SOL. Logo, o 3º lugar não
prova edge de stablecoins. O objetivo `Volume x (1 + ROE)^2`, somado nos cinco melhores dias,
pode premiar volume mesmo com perda e conflita com nosso retorno líquido composto.

O exemplo reproduzível de stablecoins fixa tick `0.00001`, ordem de USD 100, banca de USD 4 mil,
dois níveis queue-based e dez grid por lado em **dois ativos**. O replay usa
`power_prob_queue_model(2)` e latência constante. Isso ensina a declarar fila, latência e função
objetivo, mas não deve fornecer parâmetros para Binance nem arquitetura para o motor serial.
[Exemplo](https://github.com/hk3425-hash/gqtc-market-making/blob/6f9e1d7f81ca5bd3b9847f532f1ceabb48837b17/mm/gtqb_usdc_usdt.py) e
[algoritmo](https://github.com/hk3425-hash/gqtc-market-making/blob/6f9e1d7f81ca5bd3b9847f532f1ceabb48837b17/mm/mmbt/algorithms/gtqb_algo.py).

Licenças: BBGO declara AGPL-3.0; o repositório GQTC não expunha licença detectável. Esta pesquisa
não reutilizou código.

## 5. Outros projetos e papers

- O Hummingbot PMM possui `order_refresh_tolerance`: mantém ordens se a mudança ficar dentro de
  uma tolerância. É precedente concreto para inação por limiar, não um detector estatístico de
  deterioração. [Documentação](https://hummingbot.org/strategies/v1-strategies/strategy-configs/order-refresh-tolerance/).
- `ping_pong` alterna o lado após fill, mas começa com compra e venda e volta a publicar ambos
  quando equilibra; restart quebra o estado corrente. Não é nosso autômato persistente.
  [Documentação](https://hummingbot.org/strategies/v1-strategies/strategy-configs/ping-pong/).
- `hanging_orders` preserva a contraparte, porém continua criando novos pares e pode cancelar
  por distância ao mid. Não é “um lote preso, nenhum novo lote, alvo imutável”.
  [Documentação](https://hummingbot.org/strategies/v1-strategies/strategy-configs/hanging-orders/).
- Bergault et al. modelam AMM para ativos ligados, incluindo USDC/USDT, com centro de reversão
  móvel. Apoia investigar migração da região, não prova fills em CEX.
  [Paper](https://arxiv.org/abs/2411.08145).
- Huang, Lehalle e Rosenbaum modelam o book por intensidades condicionadas ao estado das filas.
  Apoia exigir L2/fluxo para execução em vez de converter toque em fill.
  [Queue-reactive model](https://arxiv.org/abs/1312.0563).
- Leung et al. estudam entrada/saída repetida com custos em processo mean-reverting. Regiões de
  entrada, saída e espera dão fundamento à inação, mas seus thresholds não calibram este mercado.
  [Paper](https://arxiv.org/abs/1504.04682).
- Lyons e Viswanath-Natraj estudam arbitragem e estabilização. A força que restaura o peg não
  garante que qualquer participante secundário tenha acesso, prioridade ou prazo de recuperação.
  [NBER](https://www.nber.org/papers/w27136).

## 6. Mercados Binance Spot

Snapshot dos endpoints públicos `exchangeInfo`, `ticker/24hr`, `ticker/bookTicker` e `depth`, em
`2026-09-06T14:52:33Z`. A Binance documenta `exchangeInfo` como a fonte atual de regras e os
endpoints de mercado separadamente. [API geral](https://developers.binance.com/docs/binance-spot-api-docs/rest-api/general-endpoints),
[market data](https://developers.binance.com/docs/binance-spot-api-docs/rest-api/market-data-endpoints) e
[filtros](https://developers.binance.com/docs/binance-spot-api-docs/filters).

| Par | Status | Tick | Step | Min notional | Volume quote 24h | Trades 24h | Spread | Histórico diário oficial |
|---|---|---:|---:|---:|---:|---:|---:|---|
| USDCUSDT | TRADING | 0.00001 | 1 | 5 | 2,278,132,056 | 451,681 | 1 tick | 2018-12-15 a 2026-09-05 |
| USD1USDT | TRADING | 0.00001 | 1 | 5 | 140,850,112 | 248,805 | 1 tick | 2025-05-22 a 2026-09-05 |
| USD1USDC | TRADING | 0.0001 | 1 | 5 | 23,904,610 | 36,994 | 1 tick | 2025-11-13 a 2026-09-05 |
| FDUSDUSDT | TRADING | 0.0001 | 1 | 5 | 14,329,119 | 18,861 | 1 tick | 2023-07-26 a 2026-09-05 |
| FDUSDUSDC | TRADING | 0.0001 | 1 | 5 | 4,063,125 | 7,605 | 1 tick | 2024-11-22 a 2026-09-05 |
| TUSDUSDT | TRADING | 0.0001 | 1 | 5 | 198,592 | 334 | 1 tick | 2018-05-31 a 2026-09-05 |
| USDPUSDT | TRADING | 0.0001 | 1 | 5 | 10,919 | 156 | 1 tick | 2021-09-10 a 2026-09-05 |

O histórico é a presença de arquivos `aggTrades` no bucket oficial, não prova de integridade ou
liquidez em cada dia. O repositório público explica o formato, checksums e arquivos disponíveis.
[Binance public data](https://github.com/binance/binance-public-data).

Primeira e última data não demonstram continuidade. Por exemplo, USDCUSDT possui 2,657 arquivos
em um intervalo de 2,822 dias corridos; TUSDUSDT e USDPUSDT também têm diferença de 165 dias. A
origem e distribuição dessas ausências não foram investigadas nesta pesquisa e precisam passar
por manifesto/checksum antes de um experimento.

Outros pares verificados como `TRADING`: `RLUSDUSDT` (USD 21.0 mi/3,245 trades), `UUSDT`
(USD 15.2 mi/23,488), `UUSDC` (USD 3.48 mi/15,365), `XUSDUSDT` (USD 1.80 mi/598) e
`USDEUSDT` (USD 0.62 mi/492). `EURIUSDT` não é USD/USD e foi excluído da comparação principal.
Nenhum superou USDCUSDT em fluxo; moedas mais novas também oferecem menos história de regimes.

## 7. FDUSD/USDC versus USDC/USDT

No mesmo snapshot, USDCUSDT apresentou **59.39 vezes** mais trades e **560.68 vezes** mais
volume quote. No topo do book, tinha 1,498,598 USDC no bid e 4,342,197 no ask, contra 20,631 e
63,544 FDUSD em FDUSDUSDC: aproximadamente **72.64x** e **68.33x** mais quantidade exibida.
São razões nominais: volume quote compara USDT com USDC e profundidade-base compara USDC com
FDUSD, sem conversão para um numerário comum. A proximidade do peg torna a aproximação útil para
triagem, não uma identidade monetária.

Em contrapartida, um tick de USDCUSDT é aproximadamente **0.001% (0.1 bp)**; um tick de
FDUSDUSDC é aproximadamente **0.01001% (1.001 bp)**. Assim, USDCUSDT oferece muito mais fluxo e
profundidade, mas um décimo do edge bruto por tick. Dez ticks de USDCUSDT são necessários para
aproximar a margem bruta de um tick de FDUSDUSDC, mudando a frequência e a posição na fila.

**Conclusão factual:** a hipótese “FDUSD tem tick maior e menos fluxo; USDC tem tick menor e muito
mais fluxo” foi confirmada no snapshot. **Inferência ainda não demonstrada:** esse fluxo produzirá
mais ciclos seriais preenchidos e líquidos. Volume e trade count não medem nossa fila.

## 8. Tick economics

Para `LOW` próximo de 1, sem taxas nem slippage:

| Classe | Distância | Edge bruto | Fee maker simétrica máxima por perna |
|---|---:|---:|---:|
| tick 0.00001 | 1 | ~0.0010% = 0.10 bp | ~0.00050% = 0.05 bp |
| tick 0.00001 | 2 | ~0.0020% = 0.20 bp | ~0.00100% = 0.10 bp |
| tick 0.00001 | 3 | ~0.0030% = 0.30 bp | ~0.00150% = 0.15 bp |
| tick 0.0001 | 1 | ~0.0100% = 1.00 bp | ~0.00500% = 0.50 bp |
| tick 0.0001 | 2 | ~0.0200% = 2.00 bp | ~0.01000% = 1.00 bp |
| tick 0.0001 | 3 | ~0.0300% = 3.00 bp | ~0.01500% = 1.50 bp |

O break-even usa o modelo normalizado `(1-f)^2 * HIGH/LOW = 1`, no qual uma fração igual `f` é
deduzida do ativo recebido em cada perna. A cobrança real pode ocorrer em base, quote ou BNB e
exige contabilidade específica. Se ambas as fees forem cobradas em quote, por exemplo, a relação
normalizada é `(HIGH/LOW) * (1-f)/(1+f)`. A tabela não inclui fila, partial fill, rounding,
rebate, tributação, adverse selection ou oportunidade. Em USDCUSDT de um tick, qualquer custo
round-trip efetivo acima de cerca de 0.1 bp elimina a margem antes dos demais riscos.

## 9. Frequency potential

Dois mil ciclos/dia exigem no mínimo quatro mil fills elegíveis e média inferior a 43.2 segundos
por ciclo completo. Como diagnóstico condicional, `trade_count/2` seria 225,840 para USDCUSDT e
3,802 para FDUSDUSDC **somente** num replay idealizado em que cada perna consome um único trade
e cada par de trades alterna exatamente nos nossos níveis. Não é um teto operacional comprovado:
uma perna pode exigir vários partial fills, e direção, preço, fila e latência reduzem o número.

Classificação atual:

- `USDCUSDT`: **PLAUSIBLE AS PRICE-PATH CANDIDATE**, pois o fluxo observado não elimina a meta
  antes da análise sequencial; execução e lucro continuam desconhecidos.
- `FDUSDUSDC`: **PROVISIONALLY UNLIKELY FOR 2,000 SUSTAINABLE EXECUTED CYCLES/DAY**. O diagnóstico
  condicional é estreito, mas esta pesquisa não constitui estimativa estatística de frequência
  sustentável.
- pares restantes: fluxo, história curta ou granularidade não apresentam combinação superior
  demonstrada.

Não se deve usar a palavra `PLAUSIBLE` como `PROFITABLE` ou `FILLABLE`.

## 10. Fees

`exchangeInfo` não informa a comissão efetiva do usuário. A API documenta comissão em endpoint
`USER_DATA`, que exigiria conta/chave e não foi consultado. A evidência pública oficial mais
recente encontrada, de junho de 2026, listava USDCUSDT, FDUSDUSDC, FDUSDUSDT, USD1USDT,
USD1USDC, TUSDUSDT e USDPUSDT entre pares zero-fee excluídos de uma promoção.
[Anúncio oficial](https://www.binance.com/en/square/post/330080314408769).

Isso não garante taxa futura, disponibilidade regional nem elegibilidade desta conta.

```text
CURRENT_FEE_STATE=PUBLIC_ZERO_FEE_EVIDENCE_AS_OF_2026-06; ACCOUNT_RATE_NOT_QUERIED
FEE_RISK=CRITICAL
```

O próximo experimento deve congelar pelo menos: zero fee documentado, fee efetiva verificável
sem operar quando isso for futuramente autorizado, e cenários de estresse. Uma promoção que
termina pode transformar edge positivo em negativo instantaneamente.

## 11. Queue / execution

`TRADE AT OUR PRICE != OUR ORDER FILLED`. Uma prova de execução requer queue ahead, prioridade,
agressor, partial fills, cancelamentos à frente, latência de envio/ack/cancel e tamanho do lote.
Arquivos bulk de `aggTrades` agregam negócios do mesmo taker, tempo e preço; não preservam nossa
posição hipotética.

O hftbacktest adverte que replay não recebe impacto das ordens simuladas e pressupõe lote pequeno.
Em dados Market-By-Price, posição na fila precisa ser modelada; seu modelo conservador só avança
por trades, enquanto modelos probabilísticos fazem hipóteses sobre cancelamentos.
[Documentação](https://hftbacktest.readthedocs.io/en/latest/order_fill.html).

Práticas a incorporar futuramente ao simulador/shadow engine: L2 sequenciado com snapshots e
deltas; timestamps de evento, recebimento, envio e ack; fila conservadora e probabilística lado a
lado; partial fills; cancel/replace e perda de prioridade; capacidade por lote; resultados
separados em price-path, queue-model e shadow observado.

## 12. `IDLE_TRIGGERED` reselection

Há fundamento técnico para **não** reprecificar a cada ruído: Hummingbot oferece tolerância de
refresh e GQTC preserva ordens cujo preço ainda é desejado. Histerese, confirmação e cooldown são
mecanismos conhecidos para reduzir churn e perda de prioridade.

Nossa ideia difere: a faixa permanece enquanto saudável; nenhuma análise de idle ocorre com
posição; após a compra, `HIGH` não muda por idade; nova faixa só pode ser considerada flat. Isso
preserva a identidade serial, mas cria risco de adverse selection e de depeg. “Sem fill” também
pode significar fila grande, ausência de agressor, preço migrado ou feed ruim. O detector futuro
precisa distinguir causas e nunca converter tempo preso em stop automático.

## 13. Recomendação

**Sim: USDC/USDT merece prioridade como o próximo laboratório comparativo.** A evidência mais
forte não é a popularidade em terceiros; é o snapshot Binance: ~59x mais trades, ~561x mais volume,
~70x mais quantidade no topo, spread de um tick e histórico oficial desde 2018. BBGO e o paper de
pegged assets apenas reforçam que USDC/USDT é uma comparação legítima.

A recomendação não é migrar produção, substituir FDUSDUSDC nem declarar vantagem executável.
USDCUSDT paga por esse fluxo com edge por tick 10x menor; taxas, fila e adverse selection podem
eliminar inteiramente a oportunidade. FDUSDUSDC deve permanecer controle histórico.

## 14. Plano de adaptação — não implementar ainda

1. Registrar nova identidade de experimento pareado, sem alterar S0.
2. Baixar e validar `aggTrades` oficiais de USDCUSDT nas mesmas datas UTC usadas por FDUSDUSDC.
3. Rodar dois laboratórios independentes, cada qual com um par, uma banca, um lote e ciclo serial.
4. Pré-fixar distâncias 1/2/3 ticks, capital, rounding e cenários de fee; não selecionar depois do
   resultado.
5. Comparar preços distintos, mudanças, visitas, alternâncias, ciclos seriais, espera, censura e
   retorno matemático; não chamar toque de fill.
6. Price-path filtra inviabilidade sob hipóteses declaradas e prioriza a etapa seguinte, mas fila
   pode inverter o ranking. A comparação executável deve modelar ambos os pares, preservando
   FDUSDUSDC como controle, com captura prospectiva L2/shadow pareada, latência, partial fills e
   capacidade. Nenhuma ordem real é parte deste plano.
7. Avaliar `IDLE_TRIGGERED` em identidade posterior, contra STATIC e ALWAYS_BEST, preservando
   HIGH do lote aberto e evitando retuning após OOS.

## Decisão final

```text
RECOMMENDED_PRIMARY_PAIR=USDCUSDT_FOR_NEXT_COMPARATIVE_LAB
SECONDARY_PAIR=FDUSDUSDC_AS_PRESERVED_CONTROL
WHY=59.39X_TRADES_560.68X_VOLUME_AND_ABOUT_70X_TOP_DEPTH_WITH_LONGER_HISTORY
EXPECTED_ADVANTAGE=MORE_OPPORTUNITIES_AND_FINER_PRICE_GRID
BIGGEST_RISK=ONE_TICK_EDGE_IS_ONLY_ABOUT_0.1_BP_BEFORE_FEES_QUEUE_AND_ADVERSE_SELECTION
THIRD_PARTY_IDEAS_TO_ADOPT=COST_ACCOUNTING_QUEUE_MODELS_LATENCY_PERSISTENCE_REFRESH_HYSTERESIS
THIRD_PARTY_IDEAS_TO_REJECT=MULTI_LAYER_GRID_TWO_SIDED_INVENTORY_AND_VOLUME_FIRST_OBJECTIVES
OUR_UNIQUE_IDENTITY=ONE_PAIR_ONE_BANK_ONE_LOT_ONE_LOW_ONE_HIGH_SERIAL_STAY_UNTIL_BAD
NEXT_EXPERIMENT=PREREGISTERED_MATCHED_USDCUSDT_VS_FDUSDUSDC_PRICE_PATH_STUDY_THEN_L2_SHADOW
EXECUTABLE_EDGE=NOT_DEMONSTRATED
```

## Proveniência e limitações

- Coleta de mercado: endpoints públicos Binance, snapshot único; valores mudam continuamente.
- Histórico disponível: listagem S3 oficial de arquivos diários, sem download/validação dos novos
  pares nesta tarefa.
- Terceiros: GitHub e documentação oficial em commits/URLs citados; afirmações GQTC sem fonte do
  organizador permanecem relato dos participantes.
- Papers apoiam mecanismos gerais, não calibram este motor.
- Nenhum dado de conta, comissão personalizada, ordem, Testnet, live trading, VALIDATION ou
  `LOCKED_TEST` foi acessado.
