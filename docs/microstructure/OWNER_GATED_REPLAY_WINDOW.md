# OWNER — primeiro dia e progressão condicional de mil ciclos por dia

RECEIVED_DATE=2026-09-08
AUTHORITY=“Simule em 3 dias, caso eu aproveite, aumenta”; correção seguinte “Aprove”.
INTERMEDIATE_OVERRIDE=“2 dias.”
LATEST_OVERRIDE=“1 dia simulador, 1 hora de espera max”.
ONE_HOUR_MEANING=HOLD_ALERT_ONLY; OWNER_SELL_HIGH_ONLY_SUPERSEDES_FORCED_EXIT
INTERPRETATION=“caso eu aprove”; não é aprovação já concedida para ampliar.
APPROVED_COMPARISON_DAYS=1
EXTENSION_AUTHORIZED=false
NEW_REPLAY_AUTHORIZED_NOW=false
AUTHORIZED_MODEL=NONE_PENDING_THREE_RANGE_PROTOCOL

## Latest proposal — three independent ranges, no reserve

OWNER_PROPOSED_STRATEGY=THREE_DISJOINT_RANGES_NO_RESERVE
PROPOSAL_STATUS=EXIT_RULE_CONFIRMED; PREPARATION; NOT_REGISTERED_OR_EXECUTED
PROPOSED_INITIAL_CAPITAL=300_USDT; THREE_ALLOCATIONS_OF_100
PROPOSED_INITIAL_RESERVE=0
OWNER_EXIT_RULE=SELL_AT_HIGH_ONLY_WITH_POSITIVE_NET_PROFIT; NO_FORCED_LOSS
OWNER_LATEST_WINDOW=ONE_DAY_ONLY; NO_AUTOMATIC_EXTENSION
OWNER_COVERAGE_QUESTION=HOW_MANY_RANGES_COVER_90_PERCENT_OF_CYCLES

The new OWNER proposal supersedes reserve-based strategy design for the next
case, not immutable historical runs. Preserve the first-day data gate. No new
replay may begin before preregistration, identity, tests, independent review and
publication. The OWNER resolved exit policy with "Vender em alta somente" and
confirmed "Fazer1dia somente". No loss budget is approved. Hold beyond1h must be
reported; no forced exit, no artificial profitable fill or cutoff liquidation.
Capital/inventory/order ownership remains separate per range; all lanes share
realistic market-liquidity consumption. Proposed interpretation: price intervals
do not overlap and each lane compounds its own gains, with no cash transfers.
These details must be explicit in the eventual frozen protocol.

Measure completed positive cycles per lane and total, final marked equity,
unrealized losses, BUY/SELL waiting, longest interval without a completed cycle,
and time with zero/one/two/three eligible working lanes. A working order is not
evidence of realized economic productivity. Never infer fills from chart touches
or choose historical ranges using future highs/lows. If fewer than three causal
ranges qualify, record unavailable lanes rather than manufacture opportunities.
Any paired strategy comparison must account for the new300 initial capital;
the historical100+10 control is not a capital-matched experiment. No promise of
continuous operation,1000 cycles/day or forced profitable exit within1h.
The question about90% coverage authorizes a first-day descriptive calculation,
not a massive strategy sweep. State the denominator and deduplicate shared
opportunities. Retrospective coverage is not prospective selection or actual
L2 fills; it cannot silently set the new strategy's ranges from future events.
Do not increase funded lanes beyond three or read another day on this question.

## Preserved M018 execution authority and earlier progression

CURRENT_CASE_STATUS=M018_COMPLETE_9_POSITIVE_CYCLES; EXTENSION_GATE_FAILED
M018 já completou o primeiro dia. Não repetir o run nem iniciar dia2:9<1000.
A autorização true foi publicada antes do run em65b7fe6; esta atualização é
pós-execução, não altera o vínculo histórico. Nova hipótese precisa dos próprios
registro, revisão e publicação; a pesquisa de suporte continua autorizada.

LATEST_CONTINUATION=Continue, use as estratégias de suporte para novas elaborações.
CONDITIONAL_MAX_STAGE_DAYS=3
MINIMUM_POSITIVE_CYCLES_EACH_DAY=1000

A instrução posterior autoriza dia2 quando dia1 atingir1000 ciclos completos
líquidos positivos auditados, e dia3 quando dia2 também atingir1000, mantendo
mesma estratégia e todo o estado. O limite atualmente liberado continua1dia:
M017 demonstrou12, não1000. EXTENSION_AUTHORIZED=false descreve o gate atual,
não revoga a autorização condicional futura. Exigir também sustentabilidade
econômica, execução e auditoria; não esconder dia fraco numa média acumulada.
Após três dias aprovados, nova hipótese para2000/dia retorna ao dia1 e capital
inicial100+10. Não modificar modelo durante replay nem reinicializar numa extensão.
O runner atual recusa extensão até haver continuação completa auditada.
M018 pode executar somente após registro, testes, revisão independente e publicação.
Usar mecanismos de suporte isolados; não juntar indicadores ou enfraquecer fila.

A ordem mais recente reduz o horizonte anterior. O replay M017 já havia ultrapassado
o limite novo sob a autorização anterior. Seu processo foi interrompido assim
que a nova ordem foi recebida; a interrupção é OWNER_SCOPE_CHANGE, não bug técnico
nem reprovação econômica do período completo. Não apagar ou renomear o run antigo
para fingir que originalmente foi um replay de1dia. Não há liquidação forçada.

Usar agora somente checkpoint fechado do dia1 de M015/M016/M017 para a
comparação principal. É a primeira amostra da sequência existente:2025-01-01.
Relógio lógico:2025-01-01T00:00:00Z inclusive até2025-01-02T00:00:00Z exclusive.
Não é uma semana histórica contínua, nem dados prospectivos. Os dias posteriores
já conhecidos não voltam a ser holdout; ficam separados como evidência histórica.

Preservar 100USDT operacionais+10reserva iniciais, compounding próprio por modelo,
custos e hipóteses de execução identificadas. M017 conserva a configuração original
registrada e seu SHA publicado; o relatório de1dia é um prefixo auditado, não uma
nova configuração executada ou resultado integral de12dias.

No corte, posições, ordens, reserva, dívida e timers permanecem como estavam.
Posição ainda aberta é marcada e censurada, não encerrada ficticiamente.
O checkpoint de engine não prova, sozinho, capacidade de retomar todo o runner:
uma futura extensão deverá verificar também seletor, book, fluxo, cursor e
relógios, ou reconstruir deterministicamente o prefixo e provar equivalência,
sem sobrescrever artifacts. Nada disso autoriza a extensão antes do OWNER.

O OWNER cancelou gráficos/HTML. Entregar ciclos positivos, banca operacional,
reserva e patrimônio total, identificando período e status. Manter auditoria e
diário GitHub; testes de software não aprovam a estratégia. A frase “1hora”
continua pendente de esclarecimento; o caso isolado de admissão conserva2h e
deve declarar isso, sem alegar validação de uma política de1h.
