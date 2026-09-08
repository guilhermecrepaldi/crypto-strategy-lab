# M014 — B10 F2.5 com reserva reforçada

Primeira semana somente · 100 USDT operacionais + 10 de reserva · COMPOUNDING · 10% dos lucros positivos para a reserva.

**72 ciclos completos, 3 releases; patrimônio 110.600700 USDT.** Banca operacional é caixa + custo do inventário; patrimônio marca o inventário ao preço de venda observado. Por isso banca + reserva pode diferir do patrimônio durante uma posição aberta.

| Métrica | Valor |
|---|---|
| SIMULATION_TIMESTAMP | 2026-01-08T00:00:00+00:00 |
| RUN_STATUS | COMPLETE |
| OPERATING_BANK | 100.64764 |
| RESERVE | 9.95306 |
| TOTAL_EQUITY | 110.6007 |
| FULL_FILL_CYCLES | 72 |
| NET_POSITIVE_CYCLES | 72 |
| NET_REALIZED_PNL | 0.6007 |
| TOTAL_FEES_QUOTE | 0 |
| RESERVE_FUNDING | 0.07196 |
| RESERVE_CONSUMPTION | 0.1189 |
| MIN_RESERVE | 9.89506 |
| RELEASE_FILLED | 3 |
| ZERO_CYCLE_DAYS | 0 |
| MAX_HOLD_HOURS | 17.873193 |
| HOLDS_OVER_24H | 0 |
| FLAT_HOURS | 87.102372 |
| HOLDING_HOURS | 80.897628 |
| WORKING_ORDER_HOURS | 167.99709 |
| MAX_DRAWDOWN_PCT | 0.098973 |
| EXTENSION_STATUS | AWAITING_OWNER_APPROVAL |

## Fechamentos diários

| Dia UTC | Banca USDT | Reserva USDT | Patrimônio USDT | Ciclos completos | Positivos | Releases |
|---|---:|---:|---:|---:|---:|---:|
| 2026-01-01 | 100.026730 | 10.002970 | 110.000000 | 3 | 3 | 0 |
| 2026-01-02 | 100.035640 | 9.974260 | 109.930700 | 1 | 1 | 1 |
| 2026-01-03 | 100.152640 | 9.908060 | 110.050700 | 13 | 13 | 1 |
| 2026-01-04 | 100.278640 | 9.912060 | 110.190700 | 14 | 14 | 1 |
| 2026-01-05 | 100.449640 | 9.931060 | 110.340700 | 19 | 19 | 0 |
| 2026-01-06 | 100.584640 | 9.946060 | 110.530700 | 15 | 15 | 0 |
| 2026-01-07 | 100.647640 | 9.953060 | 110.600700 | 7 | 7 | 0 |

Meta de 2.000 ciclos positivos: 0 de 7 dias fechados. Releases não entram na meta.

O resultado é condicional às hipóteses de execução; não é uma operação real. Próxima semana NÃO autorizada, mesmo que a meta seja atingida.

[Diagnóstico dos gargalos e comparação com B10](M014-week1-autopsy.md).

## Curvas de capital

Valores observados no replay condicional; não são projeções.

![Patrimônio total](M014-equity-curve.svg)

![Banca operacional — custo contábil](M014-operating-curve.svg)

![Reserva de recuperação](M014-reserve-curve.svg)

![Orçamento do ciclo](M014-notional-curve.svg)


## Testes do software

{"tests_passed": 107, "tests_failed": 0, "TEST_SUITE_PASS_IS_STRATEGY_PASS": false, "independent_audit_samples": 72}

TEST_SUITE_PASS != STRATEGY_PASS. Auditoria independente do replay: PASS_CONDITIONAL.

## Resultado final

WEEK_COMPLETE_CONDITIONAL; AWAITING_OWNER_APPROVAL. Custos/L2 históricos incompletos; perfil parametrizado condicional, não promessa de crescimento real.
