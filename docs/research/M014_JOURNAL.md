# M014 JOURNAL

## Pré-registro — reconstrução B10 e meta 2.000/dia

MODEL_ID=M014
MODEL_HASH=e612c45b069fef4c5c71cf092f76dadfa314476848e2663d6315693c7b953469
STATUS=CREATED
SCIENTIFIC_PARENT=RRV2_H1_B10_F2.5_097abdab
SPEC=docs/microstructure/M014_MODEL_SPEC.json
PREREG=docs/microstructure/M014_B10_RESERVE_PREREGISTRATION.md
AUTOPSY=reports/usdcusdt/B10-week1-divergence.md
INTERVAL=[2026-01-01T00:00:00Z,2026-01-08T00:00:00Z)
CAPITAL_MODE=COMPOUNDING
INITIAL_OPERATING=100
INITIAL_RESERVE=10
POSITIVE_PROFIT_FUNDING=10%
DAILY_TARGET=2000
NEXT_WEEK_AUTHORIZED=false

Reconstrução pré-registrada recupera M007/B10/H1/F2.5, com tesouraria OWNER.
Não herda seletor ou urgência M013. Primeiro um lote para isolar comportamento;
filas adicionais e filtro post-only não introduzidos neste modelo. Não é retorno
literal do histórico100+5/2%. Fonte de execução será o commit publicado antes do run.
Regressões cobrem compounding/funding/escrow parcial/restore/boundary/sem fill fictício;
revisão independente é gate separado e não comprova2.000 ciclos/dia.
