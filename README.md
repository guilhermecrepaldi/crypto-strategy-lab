# Crypto Strategy Lab

Laboratório offline-first para pesquisa histórica de estratégias Spot. A campanha científica
ativa é `USDCUSDT_EXHAUSTIVE`: um único lote serial compra USDC em um LOW exato, aguarda o HIGH
exato, vende, compõe o capital e repete. O corte anterior de rotação com aprendizado por reforço
permanece preservado como histórico do projeto, mas não participa desta campanha. Não existe
código para autenticar em exchange, usar Testnet ou enviar ordens.

## Garantias do corte vertical

- Toda consulta de mercado passa por `TemporalMarketData` e aplica
  `available_at <= simulated_time`.
- A decisão usa apenas candles já fechados; a execução ocorre na abertura do próximo candle
  de 5 minutos.
- Dinheiro, preços, quantidades e custos usam `Decimal`/`NUMERIC(38,18)`.
- Decisões inválidas tornam-se `HOLD`.
- Ordens, fills, decisões, equity e auditoria possuem tabelas append-only.
- `CryptoRotationEnv` segue o contrato Gymnasium com `Discrete(5)`. Fixtures genéricas mantêm
  ordem lexical estável; o experimento controlado fixa `0=USDT`, `1=BTC`, `2=ETH`, `3=SHIB` e
  `4=BNB` como parte da identidade reproduzível do run.
- Features usam somente candles disponíveis antes do relógio simulado. Estatísticas do
  normalizador só podem ser ajustadas em `TRAIN`.
- Episódios são sorteados por seed somente entre janelas completas, alinhadas e contidas na
  partição temporal.
- PPO é o agente primário; DQN, caixa, buy-and-hold por ativo, momentum causal e política
  aleatória são comparadores, não promessas de retorno.
- CoinMarketCap e notícias são contratos complementares e não participam da fixture.
- O universo de `2022-01-01` foi selecionado causalmente com arquivos oficiais disponíveis
  entre `2021-10-01` e o início do episódio, sem consultar o estado atual da exchange.

## Stack e arquitetura

Python 3.12, Pydantic 2, NumPy, Gymnasium, Stable-Baselines3, PyTorch, SQLAlchemy 2,
Alembic, PostgreSQL 16 + TimescaleDB e Typer.
O projeto é um monólito modular: `data` cuida de ingestão/barreiras temporais, `decision` do
contrato do agente, `simulation` do relógio/carteira/execução, `ml` de partições, features,
ambiente, treino e avaliação, e `db` da persistência.

Arquivos oficiais da Binance são baixados de `data.binance.vision` com o `.CHECKSUM`
correspondente. O parser aceita épocas em milissegundos e microssegundos. Essa decisão segue
a [documentação oficial do arquivo público](https://github.com/binance/binance-public-data/blob/master/README.md),
que também documenta a mudança de Spot para microssegundos a partir de 2025.
O Compose fixa o digest validado da imagem (PostgreSQL 16.15 / TimescaleDB 2.29.2), evitando
que uma atualização silenciosa de `latest-pg16` altere o ambiente reproduzível.

## Fluxo reproduzível

Requisitos: Docker e `uv`.

```powershell
uv sync --all-groups
docker compose up -d --wait
uv run alembic upgrade head
uv run crypto-lab simulate-fixture
```

A execução grava relatórios JSON e Markdown em `reports/` e persiste o run imutável no banco.
Rodar a mesma fixture/política/seed produz o mesmo `run_id`; a segunda persistência é ignorada.

Sem banco, é possível validar somente o engine e os relatórios:

```powershell
uv run crypto-lab simulate-fixture --no-persist
```

O acelerador CUDA é opcional e não altera a estratégia nem o ledger. Para reproduzir o gate da
RTX 5060 com três arquivos oficiais já ingeridos:

```powershell
uv sync --extra gpu
uv run python scripts/benchmark_usdcusdt_gpu.py `
  data/raw/binance-microstructure/USDCUSDT/trades/USDCUSDT-trades-2021-05-19.zip `
  data/raw/binance-microstructure/USDCUSDT/trades/USDCUSDT-trades-2021-05-20.zip `
  data/raw/binance-microstructure/USDCUSDT/trades/USDCUSDT-trades-2021-05-21.zip
```

CPU/GPU produziram hashes semânticos idênticos, mas nenhum workload atingiu o gate de 2x; por
isso o Oracle permanece em CPU. Download, ZIP, hashing, manifests e finanças exatas nunca foram
movidos para GPU.

O corte ML curto treina em uma fixture e avalia em outra cronologicamente separada:

```powershell
uv run crypto-lab rl-train --algorithm PPO --timesteps 64 --seed 42
uv run crypto-lab rl-evaluate --algorithm PPO --timesteps 64 --seed 42
uv run crypto-lab rl-train --algorithm DQN --timesteps 64 --seed 42 --no-persist
```

O segundo comando reutiliza o checkpoint imutável identificado por algoritmo, dataset,
partição, hiperparâmetros e seed. Artefatos ficam em `artifacts/models/`; relatórios incluem
ações, componentes da recompensa, equity, hashes, partição e declarações explícitas de que o
teste bloqueado e trading ao vivo não foram usados.

Downloads grandes nunca fazem parte dos testes:

```powershell
uv run crypto-lab download-month BTCUSDT 2021 12
uv run crypto-lab validate-archive data/raw/binance/BTCUSDT-5m-2021-12.zip BTCUSDT
```

## Dados históricos oficiais e seleção causal

O catálogo histórico consulta apenas diretórios e checksums arquivados no bucket público da
Binance. Ele nunca usa `exchangeInfo` atual como prova de existência passada. A elegibilidade
exclui stablecoins, tokens alavancados, símbolos não suportados e séries sem cobertura integral.
O ranking soma `quote asset volume` exclusivamente no intervalo anterior ao episódio.

Fluxo reproduzível para `2022-01-01`:

```powershell
uv run crypto-lab history-catalog --effective-at 2022-01-01 --lookback-days 92 `
  --output data/catalog/historical-catalog-2022-01-01.json

$catalog = Get-Content data/catalog/historical-catalog-2022-01-01.json -Raw | ConvertFrom-Json
$symbols = ($catalog.entries.symbol) -join ','
uv run crypto-lab history-download --symbols $symbols --start 2021-10-01 `
  --end 2022-01-01 --interval 1d --max-workers 32
uv run crypto-lab history-rank `
  --catalog data/catalog/historical-catalog-2022-01-01.json

uv run crypto-lab history-download --symbols BTCUSDT,ETHUSDT,SHIBUSDT,BNBUSDT `
  --start 2021-12-01 --end 2022-07-01 --interval 5m --max-workers 16
uv run crypto-lab history-verify --symbols BTCUSDT,ETHUSDT,SHIBUSDT,BNBUSDT `
  --start 2021-12-01 --end 2022-07-01
uv run crypto-lab history-ingest --symbols BTCUSDT,ETHUSDT,SHIBUSDT,BNBUSDT `
  --start 2021-12-01 --end 2022-07-01 `
  --normalized-path data/processed/experiment-2022H1.jsonl.gz `
  --manifest-path data/manifests/experiment-2022H1.json --gap-policy STOP
uv run crypto-lab history-smoke --manifest data/manifests/experiment-2022H1.json `
  --train-start 2022-01-01 --validation-start 2022-04-01 `
  --validation-end 2022-07-01 --durations 30,90 --seeds 11,29 --timesteps 16
```

Diagnóstico de turnover, divergência e dashboard offline do gate atual:

```powershell
uv run crypto-lab turnover-study --manifest data/manifests/experiment-2022H1.json `
  --start 2022-01-01 --end 2022-01-31 --seeds 11,29 --timesteps 16
uv run crypto-lab analyze-divergence --manifest data/manifests/experiment-2022H1.json `
  --start 2022-01-01 --end 2022-04-01 --timeframe 15m `
  --output reports/divergence.json
uv run crypto-lab dashboard --run-id f38da96c5c12d578 `
  --output reports/dashboard.html
uv run crypto-lab prepare-walk-forward --start 2022-01-01 --end 2022-07-01 `
  --train-days 90 --validation-days 30 --step-days 30
```

O estudo usa somente `TRAIN`, cenários e seeds predefinidos e reporta todos os resultados.
Os controles versionados incluem penalidade de turnover/rotação, permanência mínima, cooldown,
edge causal acima dos custos, notional mínimo, action masking e conversão de alocação repetida
em `HOLD`. O contrafactual sem custos repete as ações efetivamente executadas. PPO permanece
marcado como smoke insuficientemente treinado. O plano walk-forward é apenas validado e salvo;
não existe executor longo neste gate.

O dashboard é um único HTML autocontido: CSS, JavaScript, dados e gráficos são embutidos, sem
CDN, servidor de aplicação ou acesso à internet. `reports/dashboard-original.html` preserva o
diagnóstico sem controles e `reports/dashboard.html` mostra a configuração com cooldown.

## Treinamento controlado

O currículo canônico usa episódios causais de 30, 60 e 90 dias. Atualização e comparação de
features ocorrem somente em `TRAIN`: `2022-01-01` a `2022-03-31`. O intervalo interno
`2022-03-02` a `2022-03-31` fica fora da atualização até o checkpoint de 60 mil passos; depois
da escolha feita nesse holdout, o estágio de estabilidade pode usar todo o `TRAIN`, sem nova
seleção. O normalizador é ajustado no segmento de atualização de `TRAIN`, nunca em
`VALIDATION`.

```powershell
# sanity: PPO/DQN, seed 42, 10 mil passos e ablação curta
uv run crypto-lab controlled-train --phase sanity `
  --artifact-root artifacts/controlled-training `
  --output reports/controlled-training-sanity.json

# development: PPO/DQN, seeds 11/29/42, 100 mil passos, duas features
uv run crypto-lab controlled-train --phase development `
  --artifact-root artifacts/controlled-training `
  --output reports/controlled-training-development.json

# dashboard real, autocontido e offline
uv run crypto-lab learning-dashboard `
  --report reports/controlled-training-development.json `
  --output reports/learning-dashboard.html

# candidata determinística, somente em TRAIN, após development 12/12
uv run crypto-lab candidate-strategy-evaluate `
  --manifest data/manifests/experiment-2022H1.json `
  --development-report reports/controlled-training-development.json `
  --artifact-root artifacts/strategy-candidates `
  --output reports/strategy-candidate-momentum-24h.json
```

Os comandos são idempotentes: cada identidade retoma `latest.zip`, replay buffer do DQN,
estado dos RNGs e métricas locais. `--max-seconds-per-run` permite uma execução limitada sem
alterar silenciosamente o orçamento solicitado. O candidate de 300 mil passos rejeita um
development incompleto. `controlled-evaluate` também falha fechado até todos os runs estarem
congelados; somente então pode observar `VALIDATION` de `2022-04-01` a `2022-06-30` uma vez para
essa versão. O `LOCKED_TEST` não participa desse fluxo.

`STOP` interrompe a ingestão ao detectar ausência; `INVALIDATE_EPISODE` registra a cobertura
como inválida sem preencher o candle. Depois da ingestão, verificação, auditoria e simulação
funcionam offline sobre o artefato normalizado e seu manifesto.

A primeira candidata auditável usa momentum de 24 horas com barreira fixa de custos e decisões a
cada quatro horas. Em três janelas mensais TRAIN não sobrepostas, ela sobreviveu, mas teve retorno
mediano de `-2,56%`, abaixo de caixa (`0%`) e do melhor baseline, buy-and-hold de ETH (`+8,48%`).
Sua promoção foi rejeitada sem ajuste retrospectivo. Regras, identidade, resultados e próximo
diagnóstico estão em `docs/strategy-candidate-momentum-24h.md`.

Para preparar dados (sem executar o episódio final) com warmup mais dois anos de cobertura:

```powershell
uv run crypto-lab history-download --symbols BTCUSDT,ETHUSDT,SHIBUSDT,BNBUSDT `
  --start 2021-12-01 --end 2024-01-01 --interval 5m --max-workers 16
uv run crypto-lab history-ingest --symbols BTCUSDT,ETHUSDT,SHIBUSDT,BNBUSDT `
  --start 2021-12-01 --end 2024-01-01 `
  --normalized-path data/processed/two-year-ready.jsonl.gz `
  --manifest-path data/manifests/two-year-ready.json --gap-policy STOP
```

## Campanha serial USDC/USDT

`USDCUSDT` é o único par operacional e experimental da linha atual. A identidade é fixa: uma
banca, um lote, um LOW, um HIGH e um ciclo serial. Não existe timeout ou stop temporal; uma
posição aberta continua aguardando HIGH. Mudança estrutural apenas bloqueia novas entradas e não
autoriza liquidação automática.

M001-M004 foram preservados como pré-registros superados antes de qualquer replay: eles tratavam
o tick como constante, enquanto a Binance reduziu oficialmente o tick de USDCUSDT de `0.0001`
para `0.00001` em `2026-04-14T05:00:00Z`. M005 é o baseline estático corrigido e já foi avaliado;
M006 é o próximo challenger autorizado, com reseleção horária somente quando flat. M007 e M008
foram registrados antes do gate evolutivo e não estão automaticamente autorizados. Todo replay
reinicia com 100 USDT em `2026-01-01T00:00:00Z` e usa o mesmo cutoff físico. O intervalo inteiro é
DEVELOPMENT; `VALIDATION` e `LOCKED_TEST` permanecem fechados.

```powershell
# dados oficiais; a campanha ativa usa somente 2025-2026
uv run crypto-lab microstructure-download --symbol USDCUSDT --kind trades `
  --start 2025-01-01 --end 2026-09-05 --max-workers 4 `
  --manifest-output data/manifests/usdcusdt-trades-2025-2026.json

# verificação completamente offline antes de qualquer experimento
uv run crypto-lab microstructure-history-verify `
  --manifest data/manifests/usdcusdt-trades-2025-2026.json

# pré-processamento único e idempotente do tape validado
uv run crypto-lab microstructure-build-tape `
  --manifest data/manifests/usdcusdt-trades-2025-2026.json `
  --artifact-root artifacts

# um modelo explicitamente autorizado por vez; sempre seguido por autópsia
uv run crypto-lab microstructure-full-replay `
  --manifest data/manifests/usdcusdt-trades-2025-2026.json `
  --artifact-root artifacts --report-root reports --models M006
```

O downloader é incremental, idempotente e valida o `.CHECKSUM` oficial. Gaps não são preenchidos.
Datas sem archive podem ser classificadas como período sem trades somente quando os IDs oficiais
antes e depois são consecutivos; ausências não comprovadas mantêm o manifesto `INVALID`. O replay
vai de `2026-01-01` ao cutoff físico completo, sem early stop econômico. Price paths nunca são
chamados de fills; fila, capacidade, partial fills e execução real continuam `INCONCLUSIVE` sem
evidência L2/shadow.

O catálogo de filtros usa somente 2025-2026 e registra fonte, classe de evidência e hash. Até o
primeiro preço fino observado causalmente, `0.0001` é uma hipótese histórica explícita compatível
com os trades; depois desse evento, `0.00001` é uma grade observadamente aceita, e `05:00 UTC` é
somente o limite de conclusão publicado pela Binance. LOW e HIGH ficam absolutos depois de
selecionados: mudança posterior da grade não altera posição aberta, não arredonda alvo e não
provoca reseleção implícita.

Cada sucessor nasce da autópsia do modelo anterior: observação, hipótese causal, uma mudança
interpretável, efeito esperado e risco são registrados antes da execução. O resultado do mesmo
período pode orientar a próxima hipótese porque ele é declarado DEVELOPMENT, mas nenhuma decisão
no evento `T` pode consultar dados posteriores a `T`. Registro `CREATED` não equivale a autorização
científica.

O trabalho anterior FDUSDUSDC é `LEGACY_EVIDENCE` / `ARCHIVED_EXPERIMENT`. Seus arquivos são
preservados para explicar a origem da hipótese, mas nenhum novo download, scanner, backtest,
modelo, controle ou comparação FDUSD faz parte da campanha ativa.

O protocolo e a memória científica estão em `docs/microstructure/`. A auditoria de GPU fica em
`reports/usdcusdt/`: CPU é o backend canônico; CUDA só pode ser selecionado após equivalência exata
CPU/GPU e speedup end-to-end de pelo menos 2x.

## Validação

```powershell
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest -m "not integration"
$env:CRYPTO_LAB_RUN_DB_TESTS = "1"
uv run pytest -m integration
```

O teste de migrations pressupõe o serviço do Compose. O workflow de CI executa lint, tipos,
testes unitários e migration em banco limpo.

## Limitações deliberadas

- A campanha USDCUSDT usa somente 2025-2026. Archives anteriores já obtidos são preservados, mas
  ficam fora da computação ativa. O intervalo histórico sem arquivos diários tem IDs limítrofes
  consecutivos e é registrado explicitamente como período sem trades, não como dado inventado.
- CoinMarketCap, notícias e adaptador de LLM real estão indisponíveis nesta entrega.
- Sanity e development controlados ainda não constituem evidência de lucratividade. Somente
  uma política congelada que generalize cronologicamente em `VALIDATION`, entre seeds e após
  custos pode avançar o gate de valor. `LOCKED_TEST` permanece fechado e sem resultados.
- O catálogo integral usa arquivos 5m para provar presença histórica e arquivos 1d oficiais
  para um ranking compacto de toda a população; os quatro selecionados são novamente validados
  em 5m antes do experimento.
- O runner histórico permanece intencionalmente limitado a 30/90 dias. A preparação de dois
  anos é suportada, mas a execução longa e otimizações de memória são o próximo gate.
- O walk-forward está somente preparado em manifesto. Currículo longo, robustez por regime,
  Monte Carlo e mil simulações permanecem gates futuros e não rodam no CI.
- Nenhum resultado histórico libera automaticamente shadow mode, paper trading ou capital real.

## Gates futuros

1. executar walk-forward curto predefinido e robustez por regime sem abrir `LOCKED_TEST`;
2. shadow mode sem ordens;
3. paper trading por período suficiente;
4. revisão humana de risco, chaves, permissões e kill switch;
5. capital mínimo com limites rígidos, somente após autorização separada.

## Segurança operacional

O projeto contém apenas leitura HTTP pública de arquivos históricos Binance. Não há campos de
API key, cliente privado, endpoint de ordens, saque, margem, futuros ou operação ao vivo.
