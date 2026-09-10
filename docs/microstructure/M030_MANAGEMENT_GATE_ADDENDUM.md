# M030 — addendum pré-run do gate de gerenciamento

Status: `FROZEN_BEFORE_ECONOMIC_REPLAY`

Este addendum remove a ambiguidade da palavra “materialmente” na diretiva M030. Ele
não muda a estratégia, as janelas, a fita, a geometria ou a execução.

O comparativo de gerenciamento usa exclusivamente as três horas aleatórias já
pré-registradas e a mesma reconstrução de reservas de ordens `ENTRY` para M029 e
M030.

- Melhora material de cobertura HOT: M030 deve superar M029 em pelo menos 5 pontos
  percentuais na cobertura HOT ponderada pelo tempo.
- Redução material de capital reaproveitável parado enquanto HOT está incompleta:
  M030 deve reduzir a porcentagem de tempo em pelo menos 50% relativamente a M029,
  ou eliminá-la. Se M029 for zero, M030 também deve permanecer em zero.
- `MANAGEMENT_SUCCESS_PASS` exige simultaneamente as duas condições acima e auditoria
  mecânica aprovada.

As métricas de 24 horas continuam diagnósticas. Elas não substituem o recorte causal
primário das três horas aleatórias.
