# Crypto Strategy Lab — instruções do repositório

Estas instruções especializam as regras globais para o repositório
`guilhermecrepaldi/crypto-strategy-lab`. Dentro deste diretório, a autoridade canônica é este
projeto; a prioridade global do KNOTEN permanece inalterada fora dele.

## Canônica e continuidade

- Preserve uma única implementação por responsabilidade. Corrija a autoridade existente em vez
  de criar variantes permanentes, worktrees ou pipelines paralelos.
- Antes de mudanças estruturais, confirme diretório, Git root, remote, branch, HEAD, status,
  processos e a identidade experimental afetada.
- Estados físicos, checkpoints e manifests são a autoridade da campanha; relatórios derivados
  devem ser reconciliados com eles.
- Nunca altere silenciosamente uma campanha após observar resultados. Hipóteses novas recebem
  identidade experimental nova.
- Preserve alterações locais e artifacts. Não use reset, checkout, clean ou stash para contornar
  trabalho existente.

## Divisão de responsabilidade

### GPT-6 Astra — autoridade científica

Use explicitamente `gpt-6-astra` para formular hipóteses, definir experimentos e métricas,
projetar ou revisar lógica que muda o significado experimental, investigar perdas e falhas,
distinguir bugs de resultados legítimos, interpretar evidências e decidir o próximo experimento.
Cálculos continuam sendo feitos por código verificável. Não delegue decisões científicas ao
executor econômico.

### GPT-5.6 Luna — execução delimitada

Prefira `gpt-5.6-luna`, quando disponível e adequado, para implementação mecânica já
especificada, comandos e testes definidos, acompanhamento de processos, coleta de logs,
formatação e pequenas correções operacionais. Ele deve devolver fatos verificáveis e não pode
mudar reward, features, hiperparâmetros, partições, critérios de sucesso ou estratégia.

### Python e ferramentas do projeto — execução experimental

Use Python e os comandos existentes para simulações, treinamento PPO/DQN, candles, features,
seeds, checkpoints, replay buffers, métricas, baselines e relatórios. Não chame LLM por candle,
operação, timestep, episódio ou reset. Não crie um harness novo apenas para alternar modelos.

## Ciclo de trabalho

1. Astra define ou revisa a hipótese e o protocolo.
2. Trabalho mecânico delimitado pode ser delegado ao Luna.
3. A implementação é conferida contra a especificação.
4. Python executa a configuração identificada e preservada.
5. Python produz métricas e evidências completas nos artifacts.
6. Astra interpreta resultados e decide o próximo passo.

Use agentes somente quando o bloco for independente e o ganho superar o custo de coordenação.
Informe quais modelos foram realmente usados; não alegue troca de modelo que não ocorreu.

## Segurança experimental

- `VALIDATION` e `LOCKED_TEST` permanecem fechados até seus gates explícitos.
- Não acessar conta Binance, Testnet ou live; não solicitar chaves nem enviar ordens.
- Não fazer push ou deploy sem autorização específica.
- Não iniciar um segundo trainer se existir um trainer canônico ativo.
- Bugs técnicos não são perdas legítimas. Preserve o artifact, invalide somente o escopo
  comprovadamente afetado, corrija com teste e registre a decisão.
- Resultados positivos, negativos, falhas e invalidações devem permanecer rastreáveis aos
  artifacts originais; destaque eventos somente por critérios explícitos e reproduzíveis.
- Todo modelo `Mxxx` executado nesta campanha percorre integralmente o intervalo padronizado de
  `2026-01-01T00:00:00Z` ao cutoff físico congelado. Resultado econômico ruim, ociosidade,
  inferioridade ou posição aberta não autorizam early stop; somente invalidade técnica pode
  interromper e deve ser registrada como `INVALIDATED_TECHNICAL`.
- `HOT`, `COLD`, `FAILURE`, estabilidade, concentração e regimes são análises descritivas
  posteriores ao replay. Não podem alimentar decisões passadas, filtrar meses, fechar posições,
  mudar estratégia ou alterar gates já congelados sem uma nova hipótese pré-registrada.

## Escopo científico ativo

- A única campanha operacional e experimental desta linha de pesquisa é
  `USDCUSDT_EXHAUSTIVE`, no par `USDCUSDT`.
- `FDUSDUSDC` é exclusivamente `LEGACY_EVIDENCE` / `ARCHIVED_EXPERIMENT`: preserve seus
  artifacts existentes, mas não baixe novos dados, não execute scanners ou backtests, não crie
  modelos, não use como controle e não faça novas comparações com ele.
- A estratégia ativa preserva uma banca, um lote, um LOW, um HIGH e um único ciclo serial. Não
  introduza grid, múltiplos lotes, alavancagem, martingale, DCA, RL ou LLM por evento.

## Aceleração GPU opcional

- CPU é o backend canônico. GPU é somente acelerador opcional para scanners e cálculos em lote;
  backend não cria novo `MODEL_ID` e nunca altera decisão científica.
- Mantenha download, ZIP, parsing, SHA256, manifest, persistência, a state machine serial e a
  contabilidade financeira exata na CPU, salvo benchmark específico que demonstre o contrário.
- Use integer ticks para LOW/HIGH e preserve `Decimal`/fixed-point no ledger. Não permita que
  float32 altere seleção, ciclos, eventos, fees, capital ou decisão de promoção.
- CUDA só pode entrar na campanha após fixtures e amostras reais comprovarem
  `CPU_RESULT == GPU_RESULT` e benchmark end-to-end, incluindo transferências, mostrar speedup
  material (limiar inicial de 2x). Falha ou OOM deve cair explicitamente para CPU.
- Não instalar Ollama, LLM local, driver, CUDA Toolkit global, firmware nem mudar BIOS, clock,
  voltagem ou power limit. Dependências Python GPU devem ser opcionais e reproduzíveis.
