# Crypto Strategy Lab

Laboratório offline-first para pesquisa histórica de rotação Spot com aprendizado por
reforço. O corte histórico usa BTCUSDT, ETHUSDT, SHIBUSDT e BNBUSDT mais caixa em USDT, candles
canônicos de 5 minutos e decisões a cada 15 minutos. Não existe código para autenticar em
exchange, usar Testnet ou enviar ordens.

## Garantias do corte vertical

- Toda consulta de mercado passa por `TemporalMarketData` e aplica
  `available_at <= simulated_time`.
- A decisão usa apenas candles já fechados; a execução ocorre na abertura do próximo candle
  de 5 minutos.
- Dinheiro, preços, quantidades e custos usam `Decimal`/`NUMERIC(38,18)`.
- Decisões inválidas tornam-se `HOLD`.
- Ordens, fills, decisões, equity e auditoria possuem tabelas append-only.
- `CryptoRotationEnv` segue o contrato Gymnasium com `Discrete(5)`: USDT e os quatro pares
  em ordem lexical estável.
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

`STOP` interrompe a ingestão ao detectar ausência; `INVALIDATE_EPISODE` registra a cobertura
como inválida sem preencher o candle. Depois da ingestão, verificação, auditoria e simulação
funcionam offline sobre o artefato normalizado e seu manifesto.

Para preparar dados (sem executar o episódio final) com warmup mais dois anos de cobertura:

```powershell
uv run crypto-lab history-download --symbols BTCUSDT,ETHUSDT,SHIBUSDT,BNBUSDT `
  --start 2021-12-01 --end 2024-01-01 --interval 5m --max-workers 16
uv run crypto-lab history-ingest --symbols BTCUSDT,ETHUSDT,SHIBUSDT,BNBUSDT `
  --start 2021-12-01 --end 2024-01-01 `
  --normalized-path data/processed/two-year-ready.jsonl.gz `
  --manifest-path data/manifests/two-year-ready.json --gap-policy STOP
```

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

- O catálogo, ranking causal e dataset oficial cobrem o experimento de dezembro de 2021 a junho
  de 2022; isso não equivale à história completa de mercado ou a dois anos finais.
- CoinMarketCap, notícias e adaptador de LLM real estão indisponíveis nesta entrega.
- O treino de fixture é uma prova funcional curta, não tuning, backtest representativo ou
  evidência de lucratividade. `LOCKED_TEST` permanece fechado e sem resultados observados.
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
