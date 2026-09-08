# M014 — autópsia da semana 1

STATUS=COMPLETE_CONDITIONAL_DIAGNOSTIC

Escopo DEVELOPMENT: [2026-01-01, 2026-01-08) UTC. Interpretação Astra; cálculo Python sobre checkpoints duráveis e auditoria hash-bound. Nenhuma mudança ou nova execução.

**72 ciclos ordinários positivos e 3 releases completos.** Ciclos por dia: **3, 1, 13, 14, 19, 15, 7**. Meta de 2.000/dia atingida em **0/7 dias**, apesar do resultado econômico positivo.

- Operacional **100,64764**, reserva **9,95306**, equity **110,60070 USDT**.
- PnL líquido **+0,60070** = lucro ordinário **0,71960** − perdas de release **0,11890 USDT**; fees **zero neste perfil condicional**.
- Funding **0,07196**, reserva mínima **9,89506**, piso **2,5 USDT**.
- Inventário durante **80,89763 h**; holding máximo **17,87319 h**; ordem trabalhando durante **167,99709 das 168 h**.

## Gargalo observado

**Fila:** 233.133 dos 233.280 fluxos agressivos compatíveis não deixaram volume após a fila externa. Os 147 restantes geraram fills passivos; houve mais 3 fills IOC. Fila é aproximação condicional, não book histórico reconstruído.

**Post-only:** 16.526 rejeições LIMIT_MAKER_WOULD_TAKE, todas BUY a 1,00100 e concentradas em 2 de janeiro. Restrição localizada, insuficiente para explicar toda a semana. O contador de latência registrou **41.862 MISSED_BY_LATENCY**. Esses contadores não são uma partição aditiva de oportunidades perdidas.

**Espera serial:** medianas submissão→fill completo BUY **10,985 minutos**, SELL ordinária **10,313 minutos**. A meta serial exige, em média, um ciclo a cada **43,2 segundos**; não se somam as medianas para estimar duração de ciclo. Ordem trabalhando não equivale a throughput produtivo.

**Reserva não vinculante nesta realização:** 3 sinais, 3 releases completos; mínimo muito acima do piso. Funding inferior ao consumo reduziu a reserva em **0,04694 USDT**. Cobertura protege o operacional, mas não apaga perda da equity.

Foram 75 BUY completas, 72 SELL ordinárias completas e 3 releases completos, sem fills parciais próprios. Uma BUY permanece ativa na fronteira, inventário/dust zerados; não houve fechamento artificial.

## Interpretação e hipótese futura não autorizada

A referência histórica fornecida contém **88.784 ciclos price-path**, não oportunidades garantidas de fill. Toque de preço não comprova execução; fills alteram holding e decisões posteriores, além das diferenças financeiras entre identidades. A diferença para 72 não pode ser atribuída integralmente a um mecanismo nem convertida em probabilidade de fill.

Fila/residência serial e admissibilidade passiva são os gargalos sustentados pelos registros. Hipótese candidata: investigar **fluxo executável e admissão causal**, não aumentar o fundo de recuperação. Qualquer alteração exige novo pré-registro/identidade; nenhuma redução artificial de fila/latência foi proposta ou executada.

## Evidência vinculada

Diretório: artifacts/usdcusdt/models/M014/reality-primary. Fonte: 088ebd62af5f3866b83d8c9b825e988a15d7d6c7.

- FINAL_WEEK_1.json SHA256: e482fc83d70062ad8e1e8fc81190f58f4282d946ac84f509cb408c15b5a46b3a.
- Checkpoint SHA256: a866c40028b14a51bf45c863255dbe6c2b6c9f35e77259a6e49d58674808c09e.
- Auditoria: **60.197.011 bytes**, SHA256 verificado 4f9a14a31975a889e71c9dfcb3d93f6d63820c53f710e106e64efc7b75f997cc. Nenhuma leitura além do prefixo.
- independent-audit.json: **PASS_CONDITIONAL**, todos os 72 ciclos e 3 releases auditados. Depth histórico permanece parametrizado; aprovação contábil não aprova estratégia/meta.

Continuidade: **AWAITING_OWNER_APPROVAL**, NEXT_WEEK_AUTHORIZED=false. Nenhum dado de 8 de janeiro em diante utilizado; artifacts originais preservados.
