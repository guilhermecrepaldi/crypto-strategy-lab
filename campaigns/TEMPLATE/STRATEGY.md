# MXXX — hipótese diária de microestrutura Spot

Status: `DRAFT_NOT_CONSUMED`. Copie este diretório para `campaigns/YYYY-MM-DD/`
somente após criar uma nova identidade `Mxxx` e preencher a hipótese antes de
inspecionar o resultado da janela.

## Hipótese

Parent: `Mxxx`.

Descreva uma única mudança interpretável frente ao parent, o gargalo observado que
ela ataca e o efeito mensurável esperado. Não reutilize identidade, janela, fita ou
resultado de uma campanha consumida.

## Medidas obrigatórias

- ciclos inferidos pelo envelope contrafactual L2 + trades individuais, sempre
  separados de recibos de execução da venue;
- capital-hours de reserva BUY pendente mais custo de inventário, inventário e
  conservação exata de capital;
- ciclos inferidos negativos e a regra zero-loss modelada;
- fee break-even somente como métrica, sem alegação live/OOS.

## Congelamento exigido

Antes de autorizar, preencha e congele o hash deste texto, o contrato canônico de
`job.yaml`, o hash da spec, commit `main` revisado, janela UTC, fita local e manifest.
O manifest deve vincular a fita a fontes hashadas, validação de continuidade L2 e
trades individuais contíguos por ID nativo. A cobertura L2 deve permanecer dentro
de `max_l2_update_age_seconds` na abertura, entre updates e no cutoff; gaps,
halt externos e listas de cancelamento externas são recusados. `current_state_binding` precisa usar `MODEL_SPEC_SHA256` no job;
o cabeçalho autoritativo de `CURRENT_STATE.md` deve carregar o hash final real da spec.

Para caminho `AUTHORIZED`, inclua no campo `execution.temporal_provenance` uma fee
record e uma rule record locais, hashadas e `PROVEN_HISTORICAL`, ambas `BINANCE_SPOT`
e `USDCUSDT`, cobrindo integralmente a janela. A primeira precisa provar contexto de
tier, taxas maker/taker e semântica de fee; a segunda, `LIMIT_MAKER`/GTC/post-only e
filtros históricos de preço, lote e notional. O adaptador S0 só aceita o caso em que
tick de preço e step de lote históricos coincidam com sua única `step_size`. Registre
qualquer sweep de fee diferente da taxa provada como sensibilidade contrafactual.
Cada fonte de ambos os records precisa ser um `IMMUTABLE_CAPTURE` local e hashado com
schema `crypto-lab-day-venue-evidence-capture-v1`; o `record_payload` do capture deve
ser semanticamente idêntico ao record que ele sustenta, exceto pela lista de fontes.

Se o engine legado usar nomes de ledger diferentes dos ativos físicos, descreva o
adaptador base/quote explicitamente no texto e na spec. Não copie métricas de um parent
cujo mecanismo não seja o mesmo do engine selecionado.

O único `evidence_class` suportado por este adaptador é
`COUNTERFACTUAL_L2_QUEUE_ENVELOPE`. A ordem só é modelada quando seu preço possui
profundidade L2 observada; isso registra apenas `KNOWN_DISPLAYED_AHEAD_ONLY`, com
`UNKNOWN_TIME_PRIORITY_WITHIN_EXISTING_LEVEL`. Não há ACK, ordem ou fill próprio da
venue. Logo, mesmo com todos os checks técnicos aprovados, o resultado é
`INCONCLUSIVE`, nunca elegibilidade econômica ou `PASS`. A fita também não prova
ordem de chegada/capture clock nem latência privada histórica; latências zero são
hipótese contrafactual congelada, não medida histórica.

## Não é uma alegação

Nada nesta campanha autoriza dados privados, navegador, LLM no loop, TESTNET, LIVE
ou transporte de ordens. Não altere apenas `execution_authorized`: publique primeiro
todas as evidências e a autorização do OWNER, depois gere novos hashes congelados.
