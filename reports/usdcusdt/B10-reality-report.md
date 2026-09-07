# B10 REALITY — CURRENT SCOREBOARD

| Metric | Value |
| --- | ---: |
| Profile | A_OBSERVED_BEST_SUPPORTED |
| Progress | 86.5445% |
| Simulation date | 2026-08-03T15:07:39.740126+00:00 |
| Price-path opportunities | 3470174 |
| Full fill cycles | 2458 |
| Reality retention | 0.070832% |
| Net positive cycles | 2458 |
| Net PnL US$100 | 22.412000 |
| Reserve final | 4.581038 |
| Releases | 41 |
| Zero days | 101 |
| Max hold | 2411.42 h |
| Lock hours | 2429.94 h |
| Drawdown | 1.696157% |
| Verdict | PENDING |

Percentuais apresentados na tabela; JSON mantém frações exatas. Dias zerados/ativos incluem apenas dias UTC completos; ciclos do dia parcial: 0.

## What changed since previous checkpoint

Horário simulado anterior: 2026-08-03T15:07:39.740126+00:00.
full_fill_cycles: 2458 → 2458.
net_positive_cycles: 2458 → 2458.
net_pnl_fixed_100: 22.412000 → 22.412000.
reserve_final: 4.581038 → 4.581038.
release_filled: 41 → 41.

## Current interpretation

Sob pressão (under pressure): retenção da posição excede 24h; a produtividade é comparada à referência no mesmo prefixo. Veredito: PENDING; nenhuma promoção. A retenção mede produtividade, não um subconjunto identificado dos ciclos originais.
PnL líquido realizado 22.412000 exclui marcação do inventário não vendido e transferências internas da reserva.

## Technical validation

Testes: 98 passaram, 0 falharam. Resultado estratégico: PENDING. TEST_SUITE_PASS != STRATEGY_PASS.
Auditoria do perfil A_OBSERVED_BEST_SUPPORTED: PASS_PRELIMINARY_DURABLE_PREFIX_ONLY; cobre este checkpoint: False. Amostra: 100 ciclos ordinários e 13 releases do prefixo anterior de A; não aceita o replay completo nem audita outros perfis.
Checkpoint SHA: `4b1e67daffb05fc721cd159946440e09381cbca49dc7051a5d544b4f6140b0c7`. Código executado: `a91811a853bfc5225ce5a2d13750905b6af74991`.

## Known unknowns

Slippage isolado: UNKNOWN; o modelo condicional incorpora custos nos preços. L2/fila/latência históricos e fees da conta não estão certificados. D_PEG_STRESS permanece NOT_CALIBRATED. Dia parcial censurado; checkpoint não comprova saúde atual do processo.

## Next action

Continuar replay congelado; publicar checkpoints materiais; auditar perfis concluídos.

Estado na geração: LOCAL_ONLY_UNPUBLISHED. O commit que contém o relatório estabelece sua publicação; HEAD abaixo foi observado antes dela, sem autorreferência.
HEAD observado: `a91811a853bfc5225ce5a2d13750905b6af74991`.
