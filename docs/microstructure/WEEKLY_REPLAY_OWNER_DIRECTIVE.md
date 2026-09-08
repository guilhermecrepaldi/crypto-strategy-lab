# Replay semanal com aprovação humana

Autoridade: mensagens OWNER de 2026-09-07 nesta tarefa.

> vamos refletir 1 semana somente, conseguindo reproduzir os ciclos, usando a reserva, fazendo funcionar, ampliamos a simulação para 2, dando certo, 3, e por ai vai, semana a semana. mas somente mediante minha aprovação

Esta ordem substitui o pedido imediatamente anterior de estudar janeiro inteiro
e a extensão automática do protocolo TWO_STAGE. Não modifica silenciosamente M013.

## Limite e aprovação

- Primeiro bloco: [2026-01-01T00:00:00Z, 2026-01-08T00:00:00Z).
- Segundo bloco proposto: [2026-01-08T00:00:00Z, 2026-01-15T00:00:00Z), não autorizado.
- Terceiro bloco proposto: [2026-01-15T00:00:00Z, 2026-01-22T00:00:00Z), não autorizado.
- Ao fechar qualquer bloco, parar em AWAITING_OWNER_APPROVAL. Nem PASS econômico,
  nem testes/auditoria, nem uma automação autorizam o próximo bloco.
- A aprovação deve identificar a próxima semana e vincular o checkpoint anterior.
  Cada autorização vale somente para o bloco indicado, nunca para todos os seguintes.
- Carregar somente os trades do prefixo autorizado. O warmup causal prévio já
  especificado permanece separado; não usar dados posteriores para decisões passadas.

## Continuidade e correção

Mesma configuração congelada e mesma fonte de execução entre semanas. Preservar
capital composto, reserva, inventário, ordens parciais, prioridade de fila, liquidez,
escrows, dust e timers. A fronteira temporal não é venda forçada nem reset.
Mudança material de política exige nova hipótese/identidade, não continuação disfarçada.

M013 possui erro comprovado: nova BUY de faixa inelegível reaparece após o ACK de
cancelamento antes da próxima seleção. Preservar/invalidate tecnicamente a execução
afetada. Corrigir na implementação canônica e testar antes de congelar o sucessor;
não editar o spec, a revisão histórica ou o ledger M013 para fazê-los parecer corretos.
O próximo ID livre observado foi M014; observação não é registro nem execução.

## Placar e objetivo

Objetivo: pelo menos 1.000 ciclos ordinários operacionais completos, com lucro
líquido positivo, em cada dia UTC. Somar 7.000 ciclos não basta se um dia ficou abaixo.
Comprar/vender integralmente é necessário; tentativas, parciais, releases e ciclos
da reserva ativa são categorias separadas, não infladores da meta operacional.

Reportar por dia: ciclos completos, ciclos líquidos positivos, banca operacional,
reserva e patrimônio; ainda, aportes/consumo da reserva, releases, fees, holding,
ociosidade ponderada pelo capital e violações. Distinguir testes de software,
progresso do replay, economia observada e conclusão da semana.

Usar a reserva somente quando a regra causal congelada autorizar e existir execução
simulada suportada. Não forçar consumo para demonstrar funcionamento. Ausência de
release implica evidência histórica insuficiente dessa função, não aprovação implícita.
Manter 100 USDT operacionais + 10 USDT de reserva na inicialização independente,
compounding e demais regras financeiras vigentes; nenhum parâmetro econômico
foi alterado por esta ordem de horizonte.

## Estado desta entrega

M013 parado; monitor antigo pausado. Correção em teste/revisão antes de qualquer
novo replay. A primeira semana corrigida ainda não foi executada. Protocolo de
identidade e runner semanal precisam ser vinculados/publicados antes da execução.
Não interpretar resultados tecnicamente afetados de M013 como prova de viabilidade
ou impossibilidade de 1.000 ciclos/dia, nem como novos resultados semanais.
