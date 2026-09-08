# M015 — autópsia da semana 1

STATUS=COMPLETE_CONDITIONAL_DIAGNOSTIC

DEVELOPMENT: [2026-01-01, 2026-01-08) UTC. Análise Astra sobre snapshot final e prefixo de auditoria verificado; nenhuma nova execução ou leitura Jan8+.

**73 ciclos ordinários positivos, 3 releases; mínimo de 500/dia não atingido em nenhum dia.** Contagens diárias: **3, 2, 13, 14, 19, 15, 7**. Operacional **100,65655**, reserva **9,95405**, equity **110,61060 USDT**. PnL líquido **+0,61060**; fees condicionais zero. Contra M014: **+1 ciclo e +0,00990 USDT**, sem mudança na contagem de releases.

## O que o delta efetivamente fez

Os **sete fills TRADE_THROUGH são todos da mesma BUY, ordem 16539**, a 1,00100, em 2 de janeiro. Prints a 1,00090 preencheram 19+11+8+8+6+20+27 = **99 USDC** ao limite próprio. Apenas o primeiro evento limpou fila positiva, de **965.363 USDC**; os outros seis já encontraram fila zero. Portanto houve **uma ordem beneficiada e uma limpeza não-zero**, não sete oportunidades independentes de ciclo.

Restaram **148 fills exatos**, 3 fills BOOK de release e **16.526 rejeições post-only**, mesma contagem do M014. Fluxos compatíveis exatos: 233.217; sem saldo após fila: 233.069. Holding máximo **17,87319 h**, inventário durante **81,18907 h** e ordem trabalhando durante **167,99709 h**. A prioridade inferida não removeu o gargalo observado de espera serial.

Reserva mínima **9,89605**, muito acima do piso 2,5. Funding **0,07295** contra consumo **0,11890 USDT**; reserva não foi o limitante observado. Melhorar a cobertura financeira não cria contraparte.

## Decisão científica seguinte

**Um seletor causal orientado à execução é hipótese defensável, mas sua capacidade de chegar a 500/dia continua sem evidência.** Os sete fills observados não são limite universal: outra seleção pode posicionar ordens em outras faixas. O antigo limite por fila fixa tampouco prova impossibilidade sob trade-through. Não confundir essas duas ausências de prova com plausibilidade demonstrada.

Candidato único para posterior pré-registro: substituir somente o ranking de novas entradas por **throughput serial executável no prefixo**, mantendo kernel M015, perfil, reserva e release. Métrica candidata: contagem de ciclos virtuais completos líquidos positivos em janela causal de 24 h para cada faixa elegível M007, com as duas pontas, agressor, quantidade, latência, fila, post-only e trade-through do kernel existente; sizing na avaliação explicitamente definido e congelado. Zero ciclo não recebe score positivo; desempate determinístico por score M007 e LOW/HIGH. Isso é feature retrospectiva do prefixo, nunca agenda de fills futuros. Evitar somar taxas marginais de volume como se provassem alternância BUY→SELL.

**Antes de registrar/implementar M016**, um diagnóstico delimitado deve verificar se existem faixas com suporte executável bidirecional além da única BUY beneficiada. Reportar ciclos completos, tempo até fill de cada ponta, rejeições, volume through efetivamente utilizável e censura; não selecionar janelas após observar sucesso nem ajustar Q para cumprir a meta. Os dados brutos existentes permitem investigação condicional; falta L2 histórico para transformar essa hipótese em execução histórica comprovada. Não há autorização neste relatório para novo replay ou extensão.

## Auditoria e proveniência

A revisão independente encontrou falhas no **auditor**, corrigidas antes do PASS final: validação temporal de ativação, vínculo inferência/fill e reconstrução de fila a partir do bruto. Essas correções **não alteraram o kernel econômico nem rerodaram a estratégia**. `independent-audit.json` registra PASS_CONDITIONAL para todos os **73 ciclos, 3 releases e 7 inferências/fills**; não é PASS econômico nem prova de book histórico.

Diretório: `artifacts/usdcusdt/models/M015/reality-primary`.

- Fonte econômica: `d5cdd2822e4a274bf036b9e2ae1de6ed422137f9`.
- Modelo: `4231670b19b1ca5c2b5032b1476b83b3182d1463750ea944da5efb867d81a8fa`.
- Prefixo lido: **60.191.149 bytes**, SHA256 `e398030a75ba07afe1a43c67f7322078500d442b9a225d3201cc396eaa631cc3`.
- Checkpoint SHA256 verificado: `cec57c12ea7c78fece5970f48aea2b706ddfff643c1aba4d829695491d3a3b48`.

**Semana 2 permanece bloqueada pelo mínimo diário não atingido.** Artifacts e fronteira semanal preservados.

## Atualização posterior — diagnóstico de capacidade concluído

A proposta candidata de seletor acima era condicional ao diagnóstico. O resultado
posterior, em `B10-week1-capacity-review.md` e `M015-week1-priority-capacity.json`,
agora descarta500/dia sob o mesmo kernel/perfil mesmo com seleção perfeita:
limites M015179,402,105,109,447,366,302. Um limite ainda mais amplo para ciclos
positivos híbridos maker/taker resulta212,435,107,111,470,382,321. Todos<500.
Não registrar M016 nem executar o seletor proposto com essa meta e ambiente.
Falta evidência histórica bid+ask/fila dos sete dias para fundamentar outro
ambiente; não é impossibilidade universal no mercado. Valores econômicos M015,
auditoria, artifacts e fonte permanecem inalterados.
