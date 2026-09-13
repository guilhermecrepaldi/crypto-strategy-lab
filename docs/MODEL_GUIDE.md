# Guia dos modelos M001–M035

Este guia é uma leitura humana da linhagem experimental. A autoridade numérica continua sendo o
registry, os model specs, os journals e os resultados hash-bound. `EVALUATED` ou `PASS` de auditoria
não significa estratégia lucrativa ou pronta para live.

## M001–M010 — seleção serial e primeira disciplina causal

| Modelo | Hipótese/mudança principal | Estado resumido |
|---|---|---|
| M001 | Referência estática: um tick, lookback de 24h e sem reseleção. | Superado antes da execução pela correção da regra histórica de tick. |
| M002 | Reseleção horária somente quando flat. | Superado junto com a premissa de tick do M001. |
| M003 | Reseleção causal a cada minuto (`ALWAYS_BEST`). | Superado pelo M007, que preserva a ideia com tick corrigido. |
| M004 | Política anti-thrashing com espera, confirmação, vantagem e cooldown. | Superado; a versão comparável tornou-se M008. |
| M005 | Baseline estático com tick causalmente observado e anúncio oficial. | Avaliado como diagnóstico de price path; não prova fills físicos. |
| M006 | M005 com reseleção horária. | Execução interrompida/superada após mudança de protocolo. |
| M007 | M006 com seleção a cada minuto; champion histórico da linha serial. | Avaliado, mas somente como evidência de desenvolvimento/price path; operador permanece `SHADOW_ONLY`. |
| M008 | M007 com política stay-until-bad para reduzir trocas. | Rejeitado por não preservar suficientemente o objetivo frente ao M007. |
| M009 | M007 com histerese simples de 10% para trocar candidato. | Rejeitado. |
| M010 | M007 com decisão de liberação de capital em holds longos. | Inconclusivo; o diagnóstico congelado encontrou zero releases elegíveis. |

## M011–M018 — reserva, recuperação e prazo de exposição

| Modelo | Hipótese/mudança principal | Estado resumido |
|---|---|---|
| M011 | Recuperação dinâmica financiada por reserva, com tiers de confiança e controle passivo pareado. | Criado, depois substituído pela direção OWNER seguinte antes de resultado canônico. |
| M012 | Compounding com funding de 5%, target dinâmico e obrigação de desbloqueio em 24h. | Superado antes do replay econômico. |
| M013 | Até três filas operacionais e uma fila de reserva, compartilhando liquidez e capital. | Invalidado tecnicamente por reenvio de BUY obsoleta; evidência parcial preservada. |
| M014 | Reconstrução do B10 F2.5 com banca 100+10 e funding de 10%. | Inconclusivo; frequência ficou muito abaixo da meta e a fila ainda era sintética. |
| M015 | Clearance de fila inferido somente por trade-through compatível e volume próprio limitado. | Inconclusivo; melhorou realismo, mas não demonstrou a frequência requerida. |
| M016 | Deadline de 2h e budget agregado de release de 10 bps. | Rejeitado: perdas defensivas não foram recuperadas e objetivos de hold/sustentabilidade falharam. |
| M017 | Budget defensivo de 20 bps, mantendo o H1 normal. | Inconclusivo após redução de escopo pelo OWNER; prefixo de um dia preservado. |
| M018 | Admissão BUY passiva em `min(LOW, ask-tick)`, mantendo o HIGH original. | Rejeitado: removeu rejeições de entrada, mas reduziu ciclos e retorno frente ao controle. |

## M019–M025 — ladders, bandas e fila física

| Modelo | Hipótese/mudança principal | Estado resumido |
|---|---|---|
| M019 | Seis BUY + seis SELL slots, lot memory e saídas apenas positivas. | Rejeitado; capital concentrou em inventário e houve platô prolongado. |
| M020 | Bandas fixas derivadas de 2025, janela ativa e unidades normalizadas de 1 USDC. | Rejeitado com zero fills; bandas não cruzaram o caminho observado. |
| M021 | 100 lanes BUY-first + 100 SELL-first em lattice congelado. | Inconclusivo; 19 ciclos normalizados, sem executabilidade live. |
| M022 | 200 lanes econômicas, no máximo 160 ordens e preempção para owned returns. | Rejeitado; permaneceu com 19 ciclos e muitos retornos bloqueados/rejeitados. |
| M023 | Uma sequência econômica serial com hotline causal e SELL lucrativo como piso. | Inconclusivo; removeu a tempestade self-cross, mas fechou somente quatro ciclos em 3h. |
| M024 | Fila triangular pré-envelhecida, coortes públicas/own FIFO e prioridade de retorno. | Inconclusivo; 35 ciclos normalizados em 3h, abaixo de minNotional live. |
| M025 | Curva de capacidade variando apenas o tamanho Q em onze cenários. | Inconclusivo; mediu sensibilidade de tamanho, sem impacto endógeno/rank live. |

## M026–M031 — hotline dinâmica e produtividade

| Modelo | Hipótese/mudança principal | Estado resumido |
|---|---|---|
| M026 | Grid dinâmico de 15 níveis com geometria HOT/MID/FAR 3/2/1. | 30 ciclos físicos e 90 slot-equivalentes em 3h; gate físico falhou, resultado inconclusivo. |
| M027 | Substitui dois FAR por duas colunas micro-hot no treatment. | Zero fills nos dois braços; inconclusivo. |
| M028 | Extensão intacta do M026 de 3h para 24h. | Invalidado tecnicamente antes da extensão por comparação de checkpoint. |
| M029 | Corrige somente a canonicalização do checkpoint do M028. | 98 ciclos físicos em 24h e +0,03136% marcado; inconclusivo e abaixo de minNotional. |
| M030 | Prioridade `RETURN > HOT > MID > FAR` e reconciliação multi-tick única. | 170 ciclos/dia; melhorou horas avaliadas, mas falhou o gate de redução de stranded capital. |
| M031 | Geometria dinâmica de 10 níveis e core 4×4, comparada ao M030. | Bloqueado antes do replay porque exigia 0,0125 USDT extra e quebrava capital-match. |

## M032–M035 — múltiplos livros, elegibilidade e pares paralelos

| Modelo | Hipótese/mudança principal | Estado resumido |
|---|---|---|
| M032 | Capital manager multi-stable, rotas de 2–4 ativos, sete ranks e ledgers físicos. | Arquitetura revisada; replay bloqueado inicialmente por interseção L2 multi-book vazia. |
| M033 | Generalização multi-venue com Kraken L3/L2 e capital isolado por venue. | Nenhum replay; Kraken foi posteriormente aposentada da linha ativa e permanece apenas como provenance. |
| M034 | Binance-only economic eligibility, produtividade, attribution zero-loss e owner-return. | Forward fail-closed: zero admissões. Backtest diagnóstico: F0 fechou 2 ciclos; demais fees zero. Não é strategy pass. |
| M035 | Dois pair engines simples e isolados compartilhando uma única banca de 200 USDT. | V2 completo: dez cenários, 151.063 eventos cada, zero fills/ciclos/PnL. Paralelo reservou mais capital sem produtividade; acceptance falhou. |

## Onde conferir

- Estado mais recente: [`research/CURRENT_STATE.md`](research/CURRENT_STATE.md)
- Registry append-only: [`../reports/usdcusdt/model-registry.json`](../reports/usdcusdt/model-registry.json)
- Journals M029–M035: arquivos `research/M0xx_JOURNAL.md`
- Specs e diretivas: diretório [`microstructure/`](microstructure/)
- Resultado M035 V2: [`research/M035_RANDOM_3H_V2_RESULT.md`](research/M035_RANDOM_3H_V2_RESULT.md)
