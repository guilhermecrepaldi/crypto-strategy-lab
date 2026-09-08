# M015 — prioridade de preço condicional

Pré-registro anterior a qualquer resultado M015. OWNER autoriza estudar/adaptar
até mínimo500 ciclos líquidos positivos em CADA dia e meta2.000, seguido de mais
uma semana quando o mínimo for auditado. Não reduzir perfil para fabricar sucesso.

## Observação, hipótese e delta único

M014 fez72 ciclos/3releases, positivo0,60070 USDT; reserva não vinculante. A fila
sintética fixa2330544 por ordem impede500/dia pelo volume necessário nos sete dias,
mesmo ignorando preços e latência. Esse perfil não observa a fila histórica.

Hipótese: um print de agressor compatível estritamente além do limite de uma
ordem que JÁ estava ativa fornece sinal condicional de prioridade de preço. Inferir
que a fila proxy daquele limite foi vencida pode representar execuções omitidas
pela semântica conservadora. Isso NÃO mede cancelamentos ou prova book histórico.

Único delta M014→M015: ordinária ACTIVE com avaliação de ativação estritamente
anterior ao print, sem cancelamento efetivo, book válido, lado compatível, e
BUY print<limite ou SELL print>limite, pode ter fila zerada por INFERÊNCIA explícita.
Fill no próprio limite, não no preço mais favorável do print; quantidade<=rawqty
e<=restante próprio. Não reutilizar fluxo. Igualdade preserva consumo normal deQ.
Nenhum preenchimento em timer, ordem pendente/rejeitada ou lado incompatível.
Cancelamento pendente permite fill somente antes de efetivar; reposição recebeQ.
Parcial da mesma ordem conserva a prioridade inferida. Estado completo restaurável.

Registrar evento específico, Qantes, rawid, rawprice, rawqty, limite, ativação
observada e hipótese. O print pequeno NÃO é registrado como consumo observado de
milhões: separar clearance inferido do volume que suporta a quantidade própria.

## Invariantes preservadas

M007 seleção/histerese/reseleção; B10 H1/F2.5; um lote serial;100+10 iniciais;
funding10%positivo, compounding, piso2.5 e déficitreal coberto exatamente; releases
protegidos/escrows, filtros, latência, fees e valores do perfilB inalterados.
Sem filtro novo de admissão, sweep, timeout, lookahead ou múltiplas filas.
M014 permanece evidência válida da hipótese anterior, não bug retroativo.

## Protocolo e validação

Primeiro [Jan1,Jan8) UTC,2.489.204 trades, warmupDec31 separado. Congelar spec,
registro, fonte publicada e review independente antes de executar. Completar os
sete dias mesmo se economicamente ruim. Novo modelo não herda capital finalM014.

Testes: ambos os lados; igualdade; agressor errado; ativação pelo mesmo print;
cancelamento/ACK; parcial; reposição; restart; ledger; quantidade compartilhada;
prefixo estrito e nenhuma leitura Jan8+. Auditoria independente de TODO ledger e
100 primeiros ciclos (ou todos se menos), TODOS os releases e TODOS os fills
TRADE_THROUGH/inferências, sem confundi-los com observações do book.

Reportar por dia ciclos positivos, banca/reserva/equity, releases e perdas,
fees, minreserva, funding/consumo, holding/drawdown, fills exatos versus inferidos,
rejeições e latência. SoftwarePASS != estratégiaPASS; hipótese condicional não
certifica execução Binance real ou lucro prospectivo.

## Gate segunda semana

Somente >=500 ciclos ordinários completos líquidos positivos EM CADA dia, auditoria
PASS condicional e invariantes íntegras liberam [Jan8,Jan15), autorização OWNER já
concedida. Soma3500 não substitui o critério diário; releases não contam.
Manter mesmo modelo/configuração e estado, sem reset/fechamento artificial. Nenhum
Jan8+ antes do gate. Fonte econômica deve permanecer byte-idêntica à primeira semana;
uma implementação de continuação no orquestrador pode ser acrescentada depois do
gate, desde que revisada, publicada e com SHA anterior e SHA de continuação explícitos.
Falta dessa validação bloqueia somente continuação; não fingir que já foi implementada.

Reprovar o gate não autoriza adaptar política no mesmo run. Autópsia antes de nova
identidade, sem transformar a hipótese de clearance em fato só porque elevou ciclos.
Esta execução testa viabilidade condicional, não pressupõe500/dia alcançável.
