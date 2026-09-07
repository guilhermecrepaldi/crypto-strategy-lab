# M007 — state machine contratual

`STATE_MACHINE_READY=YES` significa **estados e topologia formalizados/testados**, não runtime
shadow pronto. `OperatorState` e `OPERATOR_TRANSITIONS` em `microstructure/operator.py` são a
autoridade executável dessa topologia imutável. Não executam transições, IO ou ordens. Uma aresta
permitida é condição necessária, nunca evidência suficiente para avançar. Os guards abaixo
precisam ser implementados/testados nos gates posteriores.

| Estado | Significado e saídas nominais condicionadas |
| --- | --- |
| BOOT | Nenhuma ação econômica. Validar contrato e seguir RECONCILING. |
| RECONCILING | Restaurar estado comprovado: FLAT, BUY_INTENT, BUY_WORKING, BUY_PARTIAL, LONG, SELL_WORKING, SELL_PARTIAL ou CYCLE_COMPLETE. Jamais inferir FLAT de ausência de arquivo. |
| FLAT | Sem inventário nem ordem ambígua. Seleção causal; intenção única leva a BUY_INTENT. |
| BUY_INTENT | Identidade persistida, ainda sem execução comprovada. BUY_WORKING após aceitação; FLAT somente se nunca submetida ou rejeição/encerramento comprovado sem execução. |
| BUY_WORKING | BUY pendente. BUY_PARTIAL após aquisição parcial; LONG após BUY terminal reconciliada; FLAT somente encerramento confirmado com zero aquisição. |
| BUY_PARTIAL | Inventário positivo; congelar faixa, impedir novo lote. Outros fills preservam estado; LONG somente quando BUY terminal e saldo/resíduo reconciliados. |
| LONG | BUY resolvida, inventário positivo. Preparar intenção única de SELL no HIGH original; SELL_WORKING após aceitação. |
| SELL_WORKING | SELL pendente. SELL_PARTIAL após execução parcial; CYCLE_COMPLETE após saída integral reconciliada; LONG após rejeição/cancelamento confirmado com inventário restante. |
| SELL_PARTIAL | Ainda inventariado. Outros fills preservam estado; CYCLE_COMPLETE somente saída reconciliada; LONG após encerramento confirmado com resíduo. |
| CYCLE_COMPLETE | Persistir conclusão idempotente e custos, sem ordens/resíduos pendentes; FLAT. Acionar seleção pós-saída canônica sem duplicá-la no restart. |
| DISCONNECTED | Congelar ações, conservar subestado econômico e cursor; RECOVERING. |
| RECOVERING | Reconstruir continuidade e estado; RECONCILING, nunca FLAT diretamente. |
| HALTED | Bloqueio de segurança; posição preservada. RECOVERING só após análise explícita, nunca por timer. |
| ERROR | Falha técnica registrada; HALTED ou RECOVERING após análise explícita. |

Estados operacionais de RECONCILING até CYCLE_COMPLETE podem ir a DISCONNECTED, HALTED ou ERROR.
BOOT pode ir a HALTED/ERROR. DISCONNECTED pode ir a HALTED/ERROR; RECOVERING pode retornar a
DISCONNECTED ou ir a HALTED/ERROR. Nenhuma dessas transições cancela, vende ou zera inventário.

## Guards que não podem ser inferidos da topologia

- Inventário positivo, inclusive partial, proíbe reseleção e outro lote. Ordens pendentes ou
  incertas também impedem criar outra intenção; não assumir cancelamento depois de timeout.
- Quantidades/fills/custos pertencem ao ledger, não ao nome do estado. Conservar esse subestado
  em DISCONNECTED/RECOVERING/HALTED/ERROR. Hash divergente, sequência sem continuidade ou ledger
  inconsistente impede retorno a qualquer estado econômico operacional.
- Em SHADOW, BUY/SELL working/partial são espaços de estado de uma simulação explicitamente
  identificada, nunca uma ordem real. Não fabricar partial fills quando só há price-touch.
  A trajetória price-path simples pode ir de working a long/complete apenas como evento
  **teórico**, sem emitir fill confirmado. Ledger teórico e real nunca se fundem.
- Cancelamento de BUY pendente, parcial terminal, dust e repricing operacional não estão
  definidos por M007. Até políticas explícitas e evidência reconciliada: manter bloqueio,
  não completar artificialmente, trocar alvo ou forçar saída por tempo.
- Um ciclo não pode ser contado duas vezes. Completion, cursor, cash/inventory e seleção
  pós-saída precisam de gravação atômica/idempotente no runtime futuro.
- Reiniciar em FLAT exige prova de saldo e ausência de intenção/ordem pendente. Reiniciar com
  posição conserva faixa/ciclo/capital da sessão. Só sessão realmente nova inicia em 100 USDT.
- Modo continua SHADOW_ONLY; todas as tentativas de envio de ordem são negadas, mesmo se a
  topologia contiver um caminho de BUY_INTENT a BUY_WORKING.

Os testes atuais verificam enumeração, topologia imutável e ausência de arestas de inventário
ou recovery diretamente para FLAT. Testes de crash, rede, exchange e fills pertencem a etapas
futuras. Esta especificação não declara nenhum desses testes como realizado.
