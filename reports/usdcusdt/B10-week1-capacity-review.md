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
