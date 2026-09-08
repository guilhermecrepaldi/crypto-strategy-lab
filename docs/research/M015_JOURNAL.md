# M015 JOURNAL

## Pré-registro — prioridade de preço condicional

MODEL_ID=M015
MODEL_HASH=4231670b19b1ca5c2b5032b1476b83b3182d1463750ea944da5efb867d81a8fa
STATUS=CREATED
PARENT=M014
EXECUTION_HYPOTHESIS=COUNTERFACTUAL_CONDITIONAL_PRICE_PRIORITY
SPEC=docs/microstructure/M015_MODEL_SPEC.json
PREREG=docs/microstructure/M015_PRICE_PRIORITY_PREREGISTRATION.md
REVIEW=reports/usdcusdt/M015-preflight-independent-review.md
INTERVAL=[2026-01-01,2026-01-08)
MINIMUM_DAILY_POSITIVE_CYCLES=500
ASPIRATIONAL_TARGET=2000
WEEK_2=CONDITIONAL_ON_EACH_DAY_500_AND_AUDIT
COMPOUNDING=100_OPERATING_PLUS_10_RESERVE_FUNDING_10_PERCENT

M014 não é invalidado. Hipótese nova infere clearance de fila por prioridade
de preço somente após ordem ativa e print estritamente além do limite, com
agressor compatível. Fill ao próprio limite, volume limitado e auditoria de TODAS
as inferências. Igualdade permanece fila normal. Não confundir com book observado.

Astra definiu/revisou a hipótese e implementou kernel; Luna adaptou apresentação
delimitada. Python executará. Nada deJan8+ até gate. A continuação exige fonte
econômica preservada e orquestração revisada/publicada conforme pré-registro.
