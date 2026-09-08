# M013 — CONTINUOUS_MULTI_QUEUE_RECOVERY

Pré-registro anterior a qualquer replay econômico M013. Autoridades OWNER:
CONTINUOUS_MULTI_QUEUE_OWNER_DIRECTIVE.md e TWO_STAGE_REPLAY_OWNER_DIRECTIVE.md.
O registry físico confirmou M013 livre; registro/publicação são gates separados.
A especificação executável de política é M013_MODEL_SPEC.json. Alteração material após
congelamento exige decisão explícita de identidade; nenhum ajuste por resultado.

## Hipótese e limites da evidência

Distribuir capital composto entre até três ranges causalmente produtivos pode reduzir
o bloqueio de toda a banca por uma posição. Uma quarta fila usa somente excedente da
reserva sob proteção de caixa. Não há promessa de liquidez, uptime ou crescimento.
M007 é ancestral do contador causal; B10 fornece execução commodity; M012 foi superado
antes de replay econômico e não constitui evidência de rentabilidade desta política.
USDCUSDT, DEVELOPMENT, sem conta, chaves, Testnet/live, LLM por evento ou outra paridade.

Stage 1: [2026-01-01 00:00 UTC, 2026-06-01 00:00 UTC), 151 dias completos.
Stage 2: [2026-06-01 00:00 UTC, 2026-09-05 23:59:59.783644 UTC), somente após
PASS_TO_EXTENSION. Junho–setembro não podem ser atravessados ou agregados no Stage 1.
Seus resultados históricos já foram vistos em B10: SEALED significa selado para esta
execução M013, não um holdout prospectivo jamais observado. Toda conclusão é DEVELOPMENT.

## Capital, composição e tesouraria única

Inicial: operating 100 USDT, reserva 10, equity 110. Nenhum reset a 100 e nenhum saque.
Cada fila operacional recebe capital atual atribuído. Lucro realizado líquido positivo
de lote concluído, inclusive fechamento forçado positivo, destina 10% à reserva e 90%
ao operating. Q4 retém 100% do lucro na reserva. Funding não tem teto.

O = caixa operacional + custo remanescente de inventário + custo do dust, somados
sem duplicar caixa atribuído. R = core líquido + capital comprometido A da Q4.
A inclui caixa reservado a BUY pendente, custo de inventário e dust; caixa livre Q4
retorna ao core. Book capital e equity marcada a bid são métricas distintas.
Transferência interna não cria PnL. Fees BUY em base reduzem quantidade adquirida;
fees SELL reduzem proceeds; alocação proporcional de custo em cada parcial.

Guard = O + soma dos déficits já realizados ainda não liquidados nas filas operacionais.
F = max(0.00000001, 0.001 * Guard). Piso pós-transferência também deve satisfazer
max(0.00000001, 0.001 * O_after). S é soma dos escrows de todas as outras filas.
Orçamento seguro da própria fila = max(0, min(core-S-F, R-2A-S)).
Cada tentativa reserva seu pior déficit total, incluindo perda parcial já realizada.
Após expiração parcial o déficit incorrido permanece reservado até settlement.
Nunca permitir a quatro filas gastar a mesma reserva. Claims concorrentes são serializados.

Admissão Q4: A_total <= max(0,(R-S-0.05O)/2), respeitando também core líquido/piso;
nenhuma nova admissão enquanto houver recuperação operacional pendente. A<=R/2 e
core>=R/2 são invariantes de book. Com A=R/2, qualquer perda operacional L>0 violaria
R-L>=2A. Por isso existe buffer adicional, não apenas a divisão cosmética 50/50.
Inicialmente o orçamento ativo máximo é 2.5 USDT, inferior ao minNotional 5 do perfil:
Q4 começa INACTIVE até poder formar ordem válida; não alegar quatro filas operantes.
Quedas de marcação não são impedidas por uma desigualdade de book: reportar ambas.

O release operacional cobre exatamente o déficit realizado do lote concluído, nunca
min(deficit,reserva). O operating recupera a perda realizada; equity total absorve-a.
Dust menor que step fica como ativo/custo separado, sem despesa nem cobertura fictícia.
Resto >=step sem minNotional permanece preso, podendo violar deadline.
Perdas da Q4 reduzem a reserva, nunca são cobertas pelo operating. Todos os escrows
operacionais e piso continuam protegidos em cada mutação da Q4.

## Alocação causal e ausência de grid

Cadência de decisão 60 segundos. C1 e C24 contam ciclos price-path completos no
prefixo da última hora/24 horas pelo contador canônico; não são fills nem fill probability.
Ranges têm largura de um tick vigente. Edge = HIGH/LOW*(1-maker_fee)^2-1 deve ser
positivo, C1>=1 e C24>=1. Score = min(C24,24*C1)*edge. Ranking decrescente por score,
desempate LOW e HIGH crescentes. Nenhuma estatística futura ou sweep.

Selecionar até três intervalos fechados estritamente disjuntos, inclusive em relação
a filas ocupadas/Q4: sem limites compartilhados. Distribuir somente caixa de filas
FLAT sem ordens vivas/pendentes proporcionalmente aos scores. Remover candidatos cujo
share arredondado falhe mínimo e redistribuir até conjunto viável. Empates reais podem
produzir shares iguais; não há regra de terços. Nunca mover capital já comprometido.
BUY sem qualquer fill cujo range perde elegibilidade é cancelada na decisão de 60s;
somente ACK libera caixa para nova atribuição. Uma parcial é o mesmo lote, sem DCA.
Q4 escolhe melhor range restante disjunto, exige C1>=2 e orçamento/filters válidos.
MaxQty/maxNotional que impeçam tamanho pretendido geram rejeição explícita, mantendo
caixa; não clipping silencioso, chunks inexistentes ou reset 100. Depth pressure é
reportado separadamente. Capacidade real ilimitada nunca é inferida desta aproximação.

## Urgência e release executável

Idade desde primeiro BUY realmente preenchido; parcial/cancel/retry não reinicia relógio.
Operating: 0–3h NORMAL; 3–6h WATCH; 6–12h recuperação somente se existir outro range
elegível com score atual estritamente maior, com 25% do orçamento seguro; 12–18h cancela
ordem ordinária inclusive BUY parcial e tenta saída com 50%, sem exigir destino;
18h em diante prioridade obrigatória com 100%. Multiplicar essas frações por
g(R/O)=min(1,(R/O)/0.10), monotônica na cobertura, sem aumentar risco arbitrariamente.
Q4 tenta saída protegida aos 3h, limite rígido 6h, perda máxima .001*Guard e limites
globais de tesouraria. Emergência operacional bloqueia renovação e cancela BUY Q4;
inventário Q4 exige venda real para virar caixa, nunca desbloqueio instantâneo.

Preço mínimo IOC arredondado para cima ao tick: max(exchange_min,
(sold_cost + remaining_sellable_cost - sell_net - allowed_total_deficit) /
(sellable_qty*(1-taker_fee))). Se inválido ou sem bid executável, não preencher.
Pior déficit é calculado antes da submissão e coberto por escrow; orçamento pode
impedir saída mesmo no deadline. IOC parcial expira, retry somente em novo epoch de
book e após ACK/expiração. Ordinary SELL pode ganhar corrida de cancelamento e continua
ordinary; release só existe com fill agressivo real. Nenhum timer produz liquidez.
Operating não resolvido aos 24h e Q4 aos 6h registram HARD_LOCK_VIOLATION; contabilizar
tempo excedente, continuar tentativas até fim do estágio, sem early stop econômico.

## Execução compartilhada, pesquisa e decisões de reutilização

ADAPT primitivas canônicas B10 de ativação, filtros, fees, cancelamento e fill;
ADAPT política de custo/dust M012. BUILD somente coordenador multi-fila, tesouraria,
alocação e métricas. Não executar quatro replays independentes sobre o mesmo evento.
ADOPT LIMIT_MAKER e IOC: IOC pode preencher parcialmente e expirar, nunca garante saída.
REJECT price-touch=fill, ordens próprias autofinanciadas, depth/volume multiplicados,
latência privada inventada e garantia de 24h sem contraparte.

Uma fila externa frontal por (side,price), inicializada quando chega a primeira ordem
própria ativa; novas próprias entram FIFO atrás das anteriores. Consumo externo ocorre
uma vez; nível reinicia somente após não haver próprias ativas. Cancelamento remove
somente própria ordem. Novas chegadas/cancelamentos externos são UNKNOWN neste proxy.
Passivo exige preço EXATO do print (sem ampliar o B10 para inferência crossing) e
agressor compatível: buyer_maker=true preenche BUY; false preenche SELL. IDs compostos
queue_id/order_id e sequência global impedem colisões. Um throttle global.

Em cada evento, IOC pronta operacional de maior idade (empate queue_id), depois IOC Q4,
depois passivos FIFO. Soma de TODOS os fills próprios <= quantidade do print; IOC também
consome depth residual único do epoch. Queue-front burn consome restante do print uma
única vez. Este UNIFIED_EVENT_PARTICIPATION_CAP é hipótese conservadora condicional,
não afirmação Binance de que um print represente todo o book. Ordens próprias cruzadas
são adiadas/canceladas com ACK, nunca autofill; modo STP da conta é UNKNOWN.

Perfil único B_REALISTIC_CONSERVATIVE do config SHA
a77e0c67fdff8c618cbfc28fdd3d49d2fa831626560aed7fe1ec27007293537d.
Sem recalibração: queue 2330544 USDC, latency/ACK 1179525us, halfspread .000005,
depth 1144901 USDC, refresh 299570us, fee zero CONDICIONAL. Filtros e tick timeline
do mesmo perfil são preservados. Isto é PARAMETERIZED_FLOW_REFRESH de piloto público,
não L2 histórico nem fee autenticada para todo Jan–May. Não há cenário D certificado.

Fontes primárias e autoridades reutilizadas:

- [Binance filters](https://developers.binance.com/docs/binance-spot-api-docs/filters).
- [Tipos e IOC](https://developers.binance.com/docs/binance-spot-api-docs/enums).
- [REST/order semantics](https://raw.githubusercontent.com/binance/binance-spot-api-docs/master/rest-api.md).
- [Raw trades e depth sequencing](https://raw.githubusercontent.com/binance/binance-spot-api-docs/master/web-socket-streams.md).
- [STP FAQ](https://developers.binance.com/docs/binance-spot-api-docs/faqs/stp_faq),
  conferida via agent-reach/Jina: modos reais variam, portanto não presumir modo da conta.
- docs/binance/BINANCE_USDCUSDT_EXECUTION_AUTHORITY.md e timeline B10 preservam
  comissões históricas UNKNOWN, filtros e limitações de observabilidade.

Nenhum código externo copiado/licença nova; regras de matching aproximadas são nossas
hipóteses declaradas, não algo demonstrado pela documentação oficial.

## Métricas, gates e auditoria

Fila produtiva: range causal ainda elegível, ordem válida working/pending ou caixa
apto a entrada; idade operacional <6h/Q4<3h; sem recuperação/capacity block. Espera
válida pode contar; ordem obsoleta ou capital preso não conta. Integrar estados
causalmente entre eventos/timers, sem sobreposição ou exclusão de warmup.
MOTOR_UPTIME é tempo com >=1 fila produtiva / duração inteira. Capital weighted é
integral do book produtivo / integral de O+R. Deployable weighted usa O+A no denominador.
Core é idle explícito: não excluir reserva para inflar métrica principal. Productive,
locked e idle capital-hours particionam exatamente total book capital-hours; registrar
também active-reserve e core-idle sem somá-los novamente à partição.

FULL_STOP_DAYS conta dias UTC com zero duração produtiva; ZERO_CYCLE_DAYS conta dias
UTC sem ordinary operating closure, separando Q4 e forced positive closures. Reportar
fullstop events/minutes/hours, ciclos por fila, holding realizado e idade aberta censurada,
P50/P90/P99/max, taxas, rejects, partials, ordens pendentes, capacidade e equity drawdown.

Gates Stage1: íntegro 151 dias; motor>=99%; capital-weighted>=80%; deployable>=95%;
fullstopdays=0; zerocycledays<=2; operating<=24h; Q4<=6h; hardviolations=0;
reserva>0 sempre; depletion/core/share/coverage violations=0; equity bid final>110;
PnL realizado líquido>0; sustentabilidade>=1; ledger/liquidez/causalidade válidos.
Sustentabilidade conservadora = (contribuições op + lucros positivos Q4) /
(cobertura op + perdas Q4). Mostrar também ratio OWNER com só releases op no
denominador, sem esconder perdas Q4. Denominador zero: ratio UNKNOWN, não infinito;
caso sem consumo passa este gate somente se Q4 net>=0 e demais gates econômicos positivos.
Recuperação da reserva: para cada consumo, primeiro instante em que Rbook volta ao
R anterior; episódios ainda abertos censurados, não duração zero.

Auditoria independente sem helpers contábeis do engine: no mínimo 100 ordinary
closures determinísticos, representação de cada fila que operar, e TODOS os sinais,
tentativas/parciais/fechamentos de recovery e TODOS os fills Q4. Reconciliar raw side,
price, quantity, queue burn, volume compartilhado, depth epoch, latência, claims,
fees, custos, dust, transferências e saldos; sha/prefix de checkpoint e trace obrigatórios.
Testes de software não aprovam economia. Amostra insuficiente, auditoria falha, dados
faltantes ou bug: INCONCLUSIVE antes de gates econômicos. Replay válido e completo com
gate econômico não atendido: FAIL. Todos aprovados: PASS_TO_EXTENSION somente para
o envelope condicional registrado, nunca promessa de execução Binance real.

## Persistência, corte e extensão sem reset

Checkpoints exatos DAY_1/7/30/60/90/120 e FINAL_5_MONTH; sete curvas de capital do spec.
Advance timer-only até boundary não cria fill nem consome primeiro trade posterior.
Não finalizar/cancelar artificialmente posições na fronteira June1. Persistir caixa,
inventário/custo/dust, ordens/latências/ACK, filas externas, depth residual, escrows,
IDs globais, selector rolling state, timers, contadores, curvas e journal prefix.
Stage2 retoma exatamente esse estado/model/hash; não reinicializar reserva/operating,
não retunar, não repetir evento fronteira. Snapshot e decisão de gate vinculam mesmo SHA.

Prefix tape derivado pode usar mmap restrito a timestamps<June1, hashes dos slices e
manifest histórico explicitamente rotulado; reconciliar todos os raw trades Jan–May
com timestamp/preço/ordinal canônico e rehashar somente ZIPs Jan–May. Não revalidar
arrays inteiros futuros para produzir uma alegação de rigor. Prefix hashes físicos são
preflight artifacts a produzir, não números inventados neste documento.

Registry/model hash incorpora spec/prereg LF hashes. Run vincula SHA de código já
publicado, classes reais compiladas, perfil completo, dados/prefix e revisão independente.
Sem PASS pre-run, testes e publicação, execução permanece fechada. Stage1 não aprovado
mantém extensão selada; somente PASS_TO_EXTENSION libera continuação automática.
