# Crypto Strategy Lab

Fundação offline-first para pesquisa e replay histórico de estratégias Spot. A primeira
entrega usa quatro pares, caixa em USDT, candles canônicos de 5 minutos e decisões a cada
15 minutos. Não existe código para autenticar em exchange, usar Testnet ou enviar ordens.

## Garantias do corte vertical

- Toda consulta de mercado passa por `TemporalMarketData` e aplica
  `available_at <= simulated_time`.
- A decisão usa apenas candles já fechados; a execução ocorre na abertura do próximo candle
  de 5 minutos.
- Dinheiro, preços, quantidades e custos usam `Decimal`/`NUMERIC(38,18)`.
- Decisões inválidas tornam-se `HOLD`.
- Ordens, fills, decisões, equity e auditoria possuem tabelas append-only.
- CoinMarketCap e notícias são contratos complementares e não participam da fixture.
- O universo da fixture é explicitamente provisório. A seleção definitiva de 2022 permanece
  bloqueada até existir evidência histórica suficiente do catálogo Spot.

## Stack e arquitetura

Python 3.12, Pydantic 2, SQLAlchemy 2, Alembic, PostgreSQL 16 + TimescaleDB e Typer.
O projeto é um monólito modular: `data` cuida de ingestão/barreiras temporais, `decision` do
contrato do agente, `simulation` do relógio/carteira/execução e `db` da persistência.

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

Downloads grandes nunca fazem parte dos testes:

```powershell
uv run crypto-lab download-month BTCUSDT 2021 12
uv run crypto-lab validate-archive data/raw/binance/BTCUSDT-5m-2021-12.zip BTCUSDT
```

## Validação

```powershell
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest
$env:CRYPTO_LAB_RUN_DB_TESTS = "1"
uv run pytest -m integration
```

O teste de migrations pressupõe o serviço do Compose. O workflow de CI executa lint, tipos,
testes unitários e migration em banco limpo.

## Limitações deliberadas

- A fixture não é uma seleção historicamente comprovada dos quatro pares de 2022.
- Ainda não há importação integral de 2021/2022, validação contra candles nativos ou catálogo
  histórico confiável; existem contratos e comandos para evoluir essa etapa sem inventar dados.
- CoinMarketCap, notícias e adaptador de LLM real estão indisponíveis nesta entrega.
- Checkpoints do relógio e contratos de estado existem; não há algoritmo de autoaprendizado.
- Métricas avançadas por regime e Monte Carlo são schema futuro, não evidência atual.

## Segurança operacional

O projeto contém apenas leitura HTTP pública de arquivos históricos Binance. Não há campos de
API key, cliente privado, endpoint de ordens, saque, margem, futuros ou operação ao vivo.
