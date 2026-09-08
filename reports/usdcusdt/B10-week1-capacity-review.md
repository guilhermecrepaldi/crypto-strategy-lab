# B10 — revisão do mínimo500 ciclos/dia

STATUS=VERIFIED_CAPACITY_CONSTRAINT_NOT_STRATEGY_SUCCESS

O novo pedido OWNER autoriza otimização na primeira semana, mínimo500 ciclos
ordinários líquidos positivos em CADA dia e meta2.000, seguido de Jan8–14 somente
quando o mínimo estiver demonstrado/auditado. Nenhuma segunda semana foi lida.

## O que foi revisado

Astra revisou fila, prioridade, cancelamento/ACK, parciais, vínculo ao lote e
contagem de ciclos no kernel publicado do M014. Nenhum bug supressor de500/dia
foi confirmado. Nova ordem recebe nova fila; a mesma ordem mantém prioridade.
Reenvio post-only sem admissão/backoff é ineficiência de política já declarada,
não prova de invalidação do resultado M014. Cancelamentos fora do contador de
submissões são aproximação otimista, não explicação de baixa produtividade.

A documentação oficial confirma que LIMIT_MAKER pode ser rejeitada ao cruzar
o mercado: [Binance Spot, trading endpoints](https://developers.binance.com/docs/binance-spot-api-docs/rest-api/trading-endpoints).
Consulta pública via agent-reach/Jina; nenhuma conta, chave ou ordem utilizada.

## Restrição demonstrada no perfil atual

Fila fixa por nova ordem: Q=2.330.544 USDC. Após no máximo um ciclo trazido da
fronteira diária, cada ciclo serial BUY integral→SELL integral exige uma nova
ordem em cada lado, consumindo Q de fluxo compatível antes do próprio fill.

Limite superior necessário por dia:

`1 + floor(min(volume buyer-maker, volume seller-maker) / Q)`.

O +1 concede gratuitamente um ciclo iniciado antes do dia, inclusive fila já
consumida e posição parcial. Ignorar tamanho próprio, preço, tempo, lucro e
latência torna o limite deliberadamente otimista. Cancelamentos/parciais só
podem acrescentar filas; releases não contam como ciclos ordinários.

| Janeiro | Ciclos observados M014 | Limite otimista do perfil |
|---|---:|---:|
| 01 | 3 | 144 |
| 02 | 1 | 376 |
| 03 | 13 | 103 |
| 04 | 14 | 107 |
| 05 | 19 | 428 |
| 06 | 15 | 354 |
| 07 | 7 | 288 |

**500/dia é incompatível com esse perfil maker/maker em todos os sete dias.**
Isso não é prova de impossibilidade universal na Binance: Q é uma hipótese
parametrizada por piloto público posterior, não observação histórica da fila.
Também não prova que os limites da tabela sejam alcançáveis. O B10 price-path
não tinha essa restrição, portanto seus ciclos não são prova de execução.

Coleta inicial: Luna. Prova/revisão: Astra. Implementação verificável: Python no
auditor canônico, sem novo simulador. Foram reconfirmados SHA de manifest e sete
ZIPs e a continuidade dos2.489.204 IDs/timestamps, sem Jan8+.

Reprodução:

```powershell
.venv/Scripts/python.exe -m scripts.audit_b10_reality --config artifacts/binance/b10-reality-profiles.json --capacity-week1 --output reports/usdcusdt/B10-week1-passive-capacity.json
```

Os hashes e volumes completos estão em B10-week1-passive-capacity.json.

## Decisão científica e limite de escopo

Não registrar um seletor como solução plausível para500 neste perfil: mesmo
seleção perfeita não vence a restrição necessária. Não executar sweep ou reduzir
fila/fees/latência artificialmente para fabricar aprovação. M014 e seus resultados
permanecem intactos, não invalidados por esta análise.

Uma política híbrida/agressiva ou outra hipótese de prioridade seria novo estudo
de execução, não simples otimização do seletor. Precisa suporte de liquidez,
incluindo ask para compras, custos e identidade/pré-registro próprios. Os dados
atuais não certificam profundidade histórica de ambos os lados. Revisão de
alternativas de execução em andamento; nenhuma alteração aplicada no replay.

RESULTADO_ECONOMICO_NOVO=NONE
MINIMUM_500_ATTAINED=false
WEEK_2_GATE=NOT_SATISFIED
OBJECTIVE_COMPLETE=false

## M015 — diagnóstico adicional concluído em 2026-09-08

Esta seção sucede a investigação pendente acima, sem invalidar M014/M015.
O auditor canônico revalidou os mesmos sete ZIPs, 2.489.204 trades, IDs e tempo
ordenados, preços no grid e tick constante. Em TODOS os eventos o BBO inferido
tem spread de exatamente um tick. Não houve leitura de Jan8+.

| Janeiro | M015 ciclos positivos | Quedas bid | Subidas ask | Limite M015 | Limite híbrido |
|---|---:|---:|---:|---:|---:|
| 01 | 3 | 35 | 33 | 179 | 212 |
| 02 | 2 | 33 | 26 | 402 | 435 |
| 03 | 13 | 2 | 2 | 105 | 107 |
| 04 | 14 | 2 | 2 | 109 | 111 |
| 05 | 19 | 23 | 19 | 447 | 470 |
| 06 | 15 | 12 | 16 | 366 | 382 |
| 07 | 7 | 14 | 19 | 302 | 321 |

Estes são limites NECESSÁRIOS otimistas, não resultados alcançáveis ou fills.
Para M015, com Q=2.330.544:

`N <= 1 + min(floor(Vbuy/Q) + bid_down, floor(Vsell/Q) + ask_up)`.

Cada perna precisa consumir Q ou ter prioridade liberada por uma passagem
estrita de preço. Com spread de um tick e ordem admitida passivamente, essa
passagem exige movimento do quote desde a âncora que admitiu a ordem. Intervalos
das pernas homólogas de ciclos seriais não se sobrepõem; não reutilizam mudanças.
Ativação por timer usa o último quote bruto como âncora, sem criar outra mudança.
O +1 concede um ciclo inteiro trazido da fronteira, inclusive prioridade e
inventário. A passagem do último quote do dia anterior ao primeiro é contada.

Mesmo permitindo novas políticas maker/taker, um limite mais amplo é:

`N_positive <= 1 + floor(min(Vbuy,Vsell)/Q) + bid_down + ask_up`.

Um ciclo que contém mudança de quote consome ao menos uma mudança, não
reutilizável em outro ciclo serial. Sem mudança, lucro ESTRITAMENTE positivo
exige quantidade passiva positiva nas DUAS pontas: somente maker BUY/taker SELL
ou taker BUY/maker SELL rende no máximo zero; somente takers perde spread.
Cada ponta passiva exige Q; trade-through não surge sem mudança dentro do ciclo.
O spread constante faz bid_down+ask_up contar todas as mudanças. O limite ignora
tamanho próprio, latência, slippage e custos não negativos. Lucro positivo é
premissa essencial, NÃO uma condição ignorada. Rebates, prioridade entre ciclos,
múltiplos lotes e volume reutilizado estão fora da prova e da estratégia atual.

**Ambos os limites ficam abaixo de500 em TODOS os dias.** Não implementar M016
como seletor ou híbrido sob essas mesmas premissas para perseguir500: a restrição
é anterior à seleção. Reserva maior não cria contraparte nem prioridade de fila.
Isto é impossibilidade dentro do proxy congelado, NÃO na Binance real. A fila
proxy vem de calibração posterior; quotes inferidos não são livro histórico.

Reprodução, sem replay econômico:

```powershell
.venv/Scripts/python.exe scripts/audit_b10_reality.py --config artifacts/binance/b10-reality-profiles.json --priority-capacity-week1 --output reports/usdcusdt/M015-week1-priority-capacity.json
```

Coleta/implementação delimitada: GPT-5.6 Luna. Prova/revisão científica:
GPT-6 Astra. Python faz os cálculos. Validação do delta:34 testes, zero falhas,
Ruff aprovado. TEST_SUITE_PASS != STRATEGY_PASS.

## Evidência necessária para outra hipótese

Inventário local reconfirmado: existem trades de janeiro e captura pública de
setembro, mas não snapshots/deltas sequenciados de janeiro. O manifest da captura
20260907-b10-joint declara historical_l2=NOT_MEASURED e queue_ahead=UNKNOWN.

Consulta pública via agent-reach/Jina e metadados do provedor: a
[Tardis documenta L2 Binance e amostras do primeiro dia de cada mês](https://docs.tardis.dev/historical-data-details/binance).
O [catálogo público](https://api.tardis.dev/v1/exchanges/binance) lista USDCUSDT,
incremental_book_L2, desde2019-11-07 até2026-09-08. Isso é cobertura declarada,
não certificação de integridade dos sete dias.

Verificação GET somente de cabeçalhos: Jan1 retornou200, Content-Length11392252;
Jan2 retornou401, explicando que sem acesso só o primeiro dia mensal é livre.
HEAD retornava404 inclusive para Jan1; não interpretá-lo como ausência de dados.
Nenhum payload de mercado baixado, compra, chave, conta, ordem ou Jan8+ acessado.

A amostra Jan1 sozinha não resolve o gate de sete dias. Próxima ação necessária:
OWNER disponibilizar snapshots/deltas bid+ask históricos de1–7janeiro e sua
proveniência, ou acesso autorizado a uma fonte que os forneça. Validar continuidade,
gaps/recovery, regras e custos antes de pré-registrar outro ambiente. Mesmo L2
não revela a posição exata de uma ordem hipotética na fila. Não substituir
janeiro por coleta prospectiva nem reduzir Q por conveniência.

RESEARCH_STATUS=BLOCKED_REQUIRED_HISTORICAL_EXECUTION_EVIDENCE
M016_REGISTERED=false
MINIMUM_500_ATTAINED=false
WEEK_2_GATE=false
OBJECTIVE_COMPLETE=false
