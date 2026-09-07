# M007 — contrato congelado do operador

Status: **Prompt 1 somente**. Especificação e configuração verificáveis; streaming, persistência,
ordens e runtime shadow ainda não implementados. Os passos 2–6 exigem continuação separada.

```text
MODEL=M007
PARENT_MODEL=M006
SYMBOL=USDCUSDT
INITIAL_CAPITAL=100 USDT
LOTS=1
BANKS=1
MODE=SHADOW_ONLY
TRADING_ENABLED=false
M007_OPERATOR_STRATEGY_HASH=2cb6c755cad4b805eb6b79e7b7e04fd271e660f285a8c1d6aca4c643dded934f
SHADOW_RUNTIME_IMPLEMENTED=NO
```

## Autoridade e identidade

A autoridade científica existente é `preregistered_corrected_block()` em
`src/crypto_strategy_lab/microstructure/serial_replay.py`, configuração com `model_id=M007`,
estratégia `ALWAYS_BEST`. O contrato em `microstructure/operator.py` deriva uma cópia validada
dessa autoridade; não contém outro seletor. Base inspecionada:
`e8663a26aecadecd19b9a320390e087860f9c0ca`.

O hash fixado acima é o `SerialModelConfig.model_hash` canônico, não um hash do código,
do dataset, de execução ou do cenário de custos. IDs são excluídos desse hash pela autoridade
existente; o operador verifica separadamente M007/M006, símbolo, banca e modo. Alteração da
configuração deve falhar fechado, não atualizar automaticamente o hash. Runs futuros também
devem registrar SHA do código, identidade da sessão, cenário, dataset/stream e proveniência.

M008/M009 não são utilizados. M010 concluído permanece evidência histórica, sem autorização de
nova execução ou incorporação ao M007. Não existe capital release, stop temporal ou melhoria
estratégica neste contrato.

## Seleção exata LOW/HIGH

1. Em uma decisão no instante `T`, usar somente o prefixo `[T − 1440 minutos, T)`. O evento de
   decisão não entra no ranking. Bootstrap exige 24 horas anteriores completas e validadas,
   como no fluxo canônico `replay_workflow.py`; ausência de histórico não vira janela vazia.
2. Enumerar as faixas elegíveis no grid conhecido causalmente na seleção, distância de **um
   tick de exchange vigente na seleção**. Não consultar metadata futura. A configuração fixa
   `ONE_EXCHANGE_TICK_AT_LEVEL_SELECTION`, `AT_LEVEL_SELECTION`,
   `BINANCE_ANNOUNCEMENT_PLUS_CAUSAL_TRADE_PREFIX`, `OBSERVED_ACCEPTED_GRID` e
   `selected_levels_remain_absolute=True`. Evidência histórica não substitui a futura
   validação de metadata pública; falha dessa evidência bloqueia o operador, não inventa tick.
3. Contar ciclos teóricos completos com o algoritmo canônico `CandidateTimeline.contained_cycles`:
   iniciar FLAT na janela, encontrar LOW exato, depois HIGH exato em evento estritamente
   posterior; a próxima compra exige evento posterior à saída. Sem sobreposição ou ciclo
   carregado de antes da borda esquerda. Preservar a ordem canônica dos eventos, inclusive
   IDs distintos com mesmo timestamp.
4. Para `C > 0` ciclos contidos, calcular `score = C × (HIGH / LOW − 1)`. Escolher a maior
   tupla `(score, C, −LOW, −distância)`: maior score, mais ciclos, LOW menor, distância menor.
   Não adicionar filtro de fees, volume, hold, confirmação ou vantagem mínima ao seletor.
5. Selecionar inicialmente e a cada **60 segundos quando FLAT**, preservando a âncora temporal
   do replay; também reselecionar **imediatamente após cada saída**, excluindo dessa janela o
   evento que acabou de concluir a saída. A próxima compra exige evento posterior à saída.
   Sem faixa elegível, remover o candidato anterior e continuar FLAT.

Não mover LOW/HIGH absolutos enquanto existir inventário. Mudança de tick não arredonda alvo,
não reprifica posição nem libera reseleção. Não encerrar por minutos, dias ou duração do hold.
Risco estrutural impede novas entradas e preserva a posição, sem liquidação automática.

## Inventário, ciclo e autoridade de execução

No replay price-path, posição abre por compra teórica no LOW; fecha por venda teórica no HIGH
posterior. Um ciclo completo exige essa sequência serial; o capital reinvestido é apenas o
produzido dentro da mesma sessão. Posição não fechada no cutoff permanece OPEN, marcada a
mercado, nunca artificialmente vendida.

No futuro SHADOW, esses eventos devem ser explicitamente teóricos: `PRICE_TOUCHED` e
`EXECUTABLE_FILL_UNKNOWN`. Não são fills, ordens enviadas, lucro executável ou evidência de
capacidade. Um ledger teórico não pode alimentar um ledger de execução real como se fosse fill.

Nos modos futuros, qualquer quantidade adquirida e ainda não liquidada, inclusive partial fill,
constitui inventário. Somente confirmações reconciliadas da Binance poderão provar fills reais.
Um ciclo real só completa após compra e venda confirmadas, inventário zerado e contabilização
reconciliada de quantidades e custos; nenhuma ordem pendente ambígua pode liberar novo lote.

M007 price-path não define fila, partial fills, cancel/replace, dust, política de completar BUY
parcial ou cancelamento de BUY ainda pendente. A state machine reserva esses estados, mas
**não inventa essas políticas**. Bloquear nova intenção/reseleção enquanto houver ordem BUY
não resolvida; em qualquer partial inventariado, LOW/HIGH permanecem congelados. Rejeição,
cancelamento e resíduo exigem reconciliação antes de avançar. Escolhas de execução ainda não
definidas são gates futuros, não alterações econômicas silenciosas.

## Capital e recuperação

Sessão nova: exatamente `Decimal("100")` USDT, uma banca independente. Nunca carregar capital
final M007/M010/backtest ou de outra sessão. O replay histórico principal começa em
`2026-01-01T00:00:00Z`, mesmo cutoff/snapshot padronizado; futuro shadow usa o relógio observado,
sem fingir que ocorreu em janeiro. Resultados não são diretamente intercambiáveis.

Restart da **mesma sessão** não é sessão nova: restaurar seu próprio caixa, inventário,
fees acumuladas, ciclo, LOW/HIGH e tick da seleção, cursor/IDs, âncora das decisões, janela
causal, intents e subestado econômico. Não voltar a 100, não herdar outra banca e não recalcular
faixa com informações posteriores à decisão original. O contrato inicial de 100 não é um
validador de equity corrente: ganhos/perdas da sessão pertencem ao ledger.

Antes de retomar: validar integridade, hash, SHA/proveniência, identidade da sessão, continuidade
do stream e reconciliação. Reprocessamento deve ser idempotente por IDs, sem duplicar capital,
ciclos ou intenções. Posição desconhecida, checkpoint incompleto, divergência de hash ou
sequência não reparada: HALTED/ERROR, nunca reset silencioso para FLAT.

Disconnect preserva inventário. BOOT passa por RECONCILING; DISCONNECTED passa por RECOVERING
e RECONCILING. Recuperação de HALTED/ERROR exige análise explícita. Em etapas futuras com ordens,
timeout depois de submit exige consultar identidade da ordem antes de qualquer reenvio;
Binance é autoridade sobre fills. Persistência, single-instance e recovery são requisitos do
Prompt 2 e seguintes, **não capacidades já entregues neste milestone**.

O compounding histórico permanece inalterado. O futuro limite live de 100 USDT é outro gate,
incluindo política explícita para ganhos e capital alocado; não reinterpretar isso como
autorização para ativar live ou alterar o replay agora.

## Gate executável entregue

`M007OperatorSpec()` aceita somente `OperatorMode.SHADOW`, banca inicial Decimal 100 e identidade
fixada. TESTNET, LIVE e `trading_enabled=True` falham fechado. Não há construtor com override
de estratégia. Cópias modificadas de Pydantic não alteram a configuração interna: cada acesso
deriva e revalida a autoridade. `assert_ready()` deve ser chamado em futuras fronteiras de uso;
`authorize_order_submission()` sempre nega. Imutabilidade Python não é isolamento contra código
hostil no mesmo processo; não há cliente de ordens para habilitar neste estágio.

Verificação offline, sem iniciar operador:

```powershell
uv run python -c "from crypto_strategy_lab.microstructure.operator import M007OperatorSpec; print(M007OperatorSpec())"
uv run pytest tests/test_m007_operator.py
```

O contrato de estados está em [STATE_MACHINE.md](STATE_MACHINE.md); limites de implementação e
autoridades estão em [LIVE_ARCHITECTURE.md](LIVE_ARCHITECTURE.md).
