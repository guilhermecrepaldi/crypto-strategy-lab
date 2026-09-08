# M014 — autópsia científica da primeira semana

STATUS=COMPLETE_CONDITIONAL_DIAGNOSTIC

Escopo: DEVELOPMENT, `[2026-01-01T00:00:00Z, 2026-01-08T00:00:00Z)`. Nenhuma extensão, alteração de parâmetros ou nova execução foi realizada nesta análise. Interpretação: agente Astra; cálculos e reconciliação: Python sobre checkpoints duráveis e o prefixo de auditoria vinculado por hash.

## Resultado

72 ciclos ordinários, todos positivos, e 3 releases completos. Os ciclos por dia foram **3, 1, 13, 14, 19, 15, 7**: **nenhum dos sete dias atingiu 2.000 ciclos**. O resultado econômico positivo não satisfaz a meta de throughput.

| Métrica final | Valor |
|---|---:|
| Capital operacional | 100,64764 USDT |
| Reserva | 9,95306 USDT |
| Equity total | 110,60070 USDT |
| PnL realizado líquido | +0,60070 USDT |
| Lucro dos ciclos ordinários | +0,71960 USDT |
| Perda executada dos releases | 0,11890 USDT |
| Funding da reserva | 0,07196 USDT |
| Reserva mínima | 9,89506 USDT |
| Piso protegido | 2,5 USDT |
| Fees neste perfil condicional | 0 USDT |
| Holding máximo | 17,87319 horas |
| Tempo com inventário | 80,89763 horas |
| Tempo sem inventário | 87,10237 horas |
| Tempo com ordem de trabalho | 167,99709 horas |

O encerramento do intervalo conserva **uma BUY ativa**, embora inventário, dust e escrow estejam zerados. Não houve liquidação artificial na fronteira. A cobertura transfere perdas para a reserva; não elimina a perda da equity. A reserva caiu 0,04694 USDT: funding inferior ao consumo nesta semana.

## Evidência do gargalo

- **Fila:** 233.280 registros de fluxo agressor compatível; 233.133 não deixaram volume para a ordem própria após a fila à frente. Os 147 restantes correspondem aos fills passivos; os outros 3 fills foram IOC de release. A fila externa do perfil é uma aproximação condicional, não reconstrução histórica de book.
- **Admissibilidade post-only:** 16.526 rejeições, todas `LIMIT_MAKER_WOULD_TAKE`, todas BUY a 1,00100 e concentradas em 2 de janeiro. Esse episódio restringiu a admissão naquele dia, mas não explica sozinho o baixo throughput dos demais dias.
- **Latência:** o contador registrou 41.862 `MISSED_BY_LATENCY`. Esse contador, os eventos de fila e as rejeições não constituem uma partição aditiva de oportunidades perdidas.
- **Residência serial:** mediana entre submissão e preenchimento completo de 10,985 minutos para BUY e 10,313 minutos para SELL ordinária; máximos de 614,683 e 1.072,392 minutos, respectivamente. Trabalhar quase 168 horas significa principalmente manter ordens/esperar, não completar ciclos continuamente.
- **Execução própria:** 75 BUY completas, 72 SELL ordinárias completas e 3 SELL de release completas; nenhum preenchimento parcial próprio nesta semana. Das 16.607 BUY submetidas, 16.526 foram rejeitadas, 5 canceladas e 1 permaneceu ativa. Das 75 SELL ordinárias, 3 foram canceladas para recuperação.
- **Reserva não foi o limitante observado:** os 3 sinais de release resultaram em 3 execuções completas; a reserva mínima ficou muito acima do piso. Não há evidência nesta realização de que aumentar a reserva resolveria a espera por contraparte ou a rejeição post-only.

## Por que 88.784 price-path não são 88.784 fills disponíveis

A referência histórica fornecida para os mesmos sete dias contém 88.784 ciclos teóricos price-path, contra 72 ciclos ordinários deste replay. Não é uma comparação contrafactual pareada: tocar LOW/HIGH não comprova preenchimento, e a execução altera entrada, saída, holding e decisões subsequentes. Também existem diferenças explícitas no mecanismo financeiro de reserva/funding. Não se atribuem os 88.712 ciclos de diferença integralmente a uma única causa, nem se interpreta a razão entre contagens como probabilidade de fill.

Os registros sustentam **fila e residência de uma operação serial**, acrescidas do episódio localizado de rejeições, como gargalos observados. Fees zero e ausência de fills parciais significam que esses dois mecanismos não explicam a perda de throughput nesta realização; não significam que sejam irrelevantes em outros perfis.

Hipótese candidata para investigação futura, **não aprovada nem executada**: verificar se a disponibilidade de fluxo executável e a admissão passiva causal, em vez do tamanho da reserva, são a restrição dominante à meta de ciclos. Qualquer mudança de política exigiria novo pré-registro/identidade; não há recomendação de reduzir artificialmente fila ou latência. Uma semana condicional não prova desempenho real ou prospectivo.

## Proveniência e limites

- Run: `45e1add3ed4fc36f34b17a52205f14f808d304932ca117beca3e3877425da121`.
- Modelo: `e612c45b069fef4c5c71cf092f76dadfa314476848e2663d6315693c7b953469`.
- Fonte publicada: `088ebd62af5f3866b83d8c9b825e988a15d7d6c7`.
- Snapshot: `artifacts/usdcusdt/models/M014/reality-primary/capital-checkpoints/FINAL_WEEK_1.json`; SHA256 físico `e482fc83d70062ad8e1e8fc81190f58f4282d946ac84f509cb408c15b5a46b3a`.
- Checkpoint SHA256: `a866c40028b14a51bf45c863255dbe6c2b6c9f35e77259a6e49d58674808c09e`.
- Auditoria lida somente até **60.197.011 bytes**, SHA256 verificado `4f9a14a31975a889e71c9dfcb3d93f6d63820c53f710e106e64efc7b75f997cc`; nenhuma leitura além desse prefixo.
- 2.489.204 trades processados; último timestamp físico `1767830399988448`, estritamente anterior a 8 de janeiro.
- `independent-audit.json` registra `PASS_CONDITIONAL`, 72/72 ciclos ordinários e todos os 3 releases auditados. O suporte bruto valida âncoras e fluxo acumulado; **depth histórico continua parametrizado**. Esse status é de auditoria, não aprovação da estratégia ou da meta econômica.
- O snapshot final conserva seu status de auditoria original; o resultado independente posterior é evidência separada. Nenhum artifact original foi alterado.

Continuidade: `AWAITING_OWNER_APPROVAL`; `NEXT_WEEK_AUTHORIZED=false`. Nenhum dado de 8 de janeiro em diante foi utilizado nesta autópsia.
