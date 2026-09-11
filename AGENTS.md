# Crypto Strategy Lab — instruções do repositório

## Autoridade OWNER mais recente — M034 Binance economic eligibility, 2026-09-10

Seguir `docs/microstructure/M034_BINANCE_ECONOMIC_ELIGIBILITY_PRODUCTIVITY.md`
e o prompt oficial refinado do OWNER. M034 é uma camada incremental sobre M032/M033:
execução econômica exclusivamente Binance, com Kraken preservada no código/adapters/
testes/documentos e dormente para alocação econômica. O gate precede produtividade;
fee histórica não provada, custo desconhecido sem bound pré-registrado, dados/safety,
completion ou lock inválidos autorizam zero slots. Capital sem oportunidade permanece
IDLE/AVAILABLE. Safety não multiplica score; P_complete entra uma vez; FIFO pertence
à decisão de troca. Saída negativa exige regra causal pré-registrada e settlement
auditável separado de ciclos positivos. Thresholds exigem provenance e config hash;
calibração não vira OOS. Preservar geometria7 ranks/C1+C2, ledgers/filas por venue,
owned-return e cancel-ACK. Source em revisão; sem thresholds operacionais, universo,
fee histórica selecionada, dataset/janela, runner, registro ou protocolo de replay.
Nenhum replay, conta, Testnet, live, nova venue, leverage, perp, AMM ou yield.

## Autoridade OWNER mais recente — M030 hotline-first, 2026-09-10

Seguir `docs/microstructure/M030_HOTLINE_FIRST_REALLOCATION_OWNER_DIRECTIVE.md` e
o pré-registro M030. M026/M029 são imutáveis. M030 preserva geometria3/2/1, capital,
fila, latência, sizing, returns positivos e mobility8/side, alterando só management:
RETURN>HOT>MID>FAR>old zero-fill. ENTRY sem fill é reclamável pelo mesmo ativo; parcial
ou fill é protegido; saldo libera somente no cancel ACK. Livro causal multi-tick salta
direto ao hotline final e faz uma reconciliação, registrando ticks evitados. Engine
contínuo00–24h sem reset; avaliação primária somente nas horas aleatórias06,12,13 UTC,
seed CSPRNG único13525809254189156280, mask reporting-only. M029 é baseline físico
read-only, sem rerun. Source/testes/revisão Astra/push antes do único run. Normalizado
abaixo do minNotional, não live. Sem reroll, rerun, M031, outro dia, conta/Testnet/live.

O único run M030 usou source publicado `459d023`, processou24h/254.205 trades e
teve seu ledger físico auditado após uma correção somente de relatório, sem replay.
Nas horas aleatórias06,12,13UTC: M029=6 ciclos, M030=13 (+116,67%); cobertura HOT
67,41%→94,28%. O stranded literal caiu100%→59,28% (redução40,72%), abaixo do gate
pré-registrado50%; management falhou. No dia:170 ciclos físicos,509 slot cycles;
equity156,2522→156,3188 (+0,0666; +0,04262%), final51,1088USDT+105USDC. Auditoria
passou, porém M030=`INCONCLUSIVE`, normalizado/não live-executable. Gate consumido;
sem rerun, M031, outro dia, conta, Testnet ou live.

## Autoridade OWNER mais recente — M029 retry técnico M026 por24h, 2026-09-10

Seguir `docs/microstructure/M029_M026_24H_TECHNICAL_RETRY_OWNER_DIRECTIVE.md` e
o pré-registro M029. OWNER respondeu “autorizado” ao pedido exato de retry técnico
corrigido do M026 por24h. Preservar M026/M027/M028. M029 mantém toda economia,
geometria3/2/1, capital, fila, latência, sizing, returns e compounding do M026; a
única correção frente ao M028 é canonicalizar ambos checkpoints via JSON antes da
comparação estrita das03h. Ledger/trades/métricas continuam exatos e o gate ocorre
antes do primeiro evento da extensão. Um run somente, sem reset, tuning, capital
novo, liquidação forçada, M030, outro dia ou live. Publicar source/revisão Astra antes
do run e resultado/auditoria depois. Resultado continua normalizado abaixo do
minNotional e não live-executable.

O único run M029 foi concluído usando source publicado `9dde81b`. O prefixo00–03h
reproduziu M026 exatamente e a auditoria física24h passou. Equity marcada inicial
156.25220000 tornou-se156.3012000000000000: ganho0.0490000000000000, ou
0.03135955845741691956977245760%. Foram98 ciclos físicos (4.0833/h) e289 ciclos
slot-equivalentes (12.0417/h); após03h, somente68 ciclos físicos e+0.0040 de equity.
M029=`INCONCLUSIVE`: normalizado abaixo do minNotional, fee condicional zero, sem
impacto endógeno/rank live e muito abaixo da meta OWNER. Gate consumido; não há
autorização para rerun, outro dia, M030, conta, Testnet ou live.

## Autoridade OWNER mais recente — M028, M026 por um dia, 2026-09-10

Seguir `docs/microstructure/M028_M026_24H_EXTENSION_OWNER_DIRECTIVE.md` e o
pré-registro M028. OWNER escolheu manter exatamente a estratégia M026 e autorizou
um único replay contínuo em2025-01-01T00:00Z–2025-01-02T00:00Z. M026/M027 ficam
imutáveis; duração nova exige identidade M028. Não alterar geometria3/2/1, engine,
capital, fila, latência, sizing, returns ou compounding; nenhum reset às03:00. O
prefixo00–03h deve reproduzir ledger e estado econômico M026, normalizando apenas
`end_us`, antes de consumir a extensão. Reportar equity antes/depois, ganho absoluto
e percentual, ganho adicional após03:00, ciclos totais e por hora. Continua
normalizado abaixo do minNotional, não live-executable. Preregister/testar/revisar
com Astra/publicar antes do único run; sem rerun, outro dia, M029 ou live. O único
run M028 foi bloqueado antes do primeiro evento pós-03h: ledger do prefixo idêntico
ao M026. O diagnóstico reproduzido aponta comparação crua de `Decimal`/chaves
inteiras em memória contra strings JSON; o checkpoint rejeitado não foi persistido,
logo não se prova que essa era a única diferença fora do ledger.
M028=`INVALIDATED_TECHNICAL`; não existe resultado24h. O gate está consumido e um
retry corrigido exige nova autorização/identidade.

## Autoridade OWNER mais recente — M027 micro-hot realocation, 2026-09-09

Seguir `docs/microstructure/M027_MICRO_HOT_REALLOCATION_OWNER_DIRECTIVE.md` e o
pré-registro M027. M026 permanece imutável. O A/B autorizado foi executado uma vez
por braço sobre2026-05-01T00:00Z–03:00Z com source publicado `c653292`. CONTROL
preservou15 níveis coarse; TREATMENT trocou somente FAR14/FAR15 por MICRO a
±0.00005,2 colunas de1 slot. Ambos mantiveram60 ordens,140 slots operacionais+16
de mobilidade e passaram capital-match/auditoria. Ambos produziram0 fills e0 ciclos.
Trades ficaram1.00013–1.00015; hotline1.00014; MICRO1.00009/1.00019 não foi tocada.
M027 é `INCONCLUSIVE`, normalizado abaixo do minNotional e não live-executable. Gate
consumido: sem sweep, rerun, outro dia, M028, extensão, conta, Testnet ou live.

## Autoridade OWNER mais recente — M026 dynamic hotline 3/2/1, 2026-09-09

Seguir `docs/microstructure/M026_DYNAMIC_HOTLINE_321_OWNER_DIRECTIVE.md` e o
pré-registro M026. M024 permanece pai imutável; M025 é somente diagnóstico. Um
único replay foi executado em 2025-01-01T00:00Z–03:00Z: 15 níveis por lado,
HOT/MID/FAR com 3/2/1 colunas e 3/2/1 slot units, 60 ordens e 140 slots operacionais,
mais 8 slots reais de mobilidade por ativo. Hotline causal em ticks inteiros; ordens
antigas não movem, não redimensionam e não perdem FIFO/epoch. Promoção requer capital
real, demotion é drain-only. Quantidade whole-USDC usa regra pré-registrada e o banco
inicial físico é derivado, não “156 USDT” presumidos. Gates separados: >=38 ciclos
físicos e >=60 slot-equivalentes em 3h. Fonte/testes/revisão Astra/push antes do run;
resultado/autópsia/revisão/registry/journal/push depois. O resultado foi30 ciclos
físicos (10/h) e90 slot-equivalentes (30/h): gate físico falhou, régua ponderada
passou. M026 é INCONCLUSIVE e não live-executable. Sem rerun, M027, dia2 ou live.

## Autoridade OWNER mais recente — M025 order-size capacity curve, 2026-09-09

Seguir `docs/microstructure/M025_ORDER_SIZE_CAPACITY_OWNER_DIRECTIVE.md` e o
pré-registro M025. M024 e toda sua evidência permanecem imutáveis. M025 executa uma
única campanha no mesmo prefixo `2025-01-01T00:00Z–03:00Z`, com onze cenários
independentes `Q=10,50,100,250,500,750,1000,1500,2000,3000,5000USDC`, cada um uma
vez e em ordem crescente. A única variável é Q; capital escala das reservas físicas,
mas tape, book, trades, fila, latência, manager e fees não escalam. Ciclo exige entrada
Q completa e retorno Q completo positivo. Partiais nunca são ciclos. Growth pool é
medido, mas expansão estrutural fica desabilitada. Knee exige queda adjacente >=20% e
confirmação ortogonal por parcial, full-fill rate ou tempo. Endogenous impact é ausente
e queue rank real é desconhecido. Publicar source/review Astra antes do primeiro evento;
falha técnica após eventos preserva o prefixo e proíbe rerun. Sem M026, dia2 ou live.

## Autoridade OWNER mais recente — M024 triangular pre-aged queue, 2026-09-09

Seguir `docs/microstructure/M024_TRIANGULAR_PRE_AGED_QUEUE_OWNER_DIRECTIVE.md`.
M023 permanece imutável. M024 testa uma única vez o mesmo prefixo L2 de
2025-01-01T00:00Z–03:00Z com50 níveis lógicos por lado,75 BUY+75 SELL entries
normalizadas de1USDC e segunda coluna same-price nos25 níveis mais próximos.
Cada `SIDE+PRICE` usa fila pública/own FIFO segmentada por coorte; não duplicar fila,
trade, capital ou idade. C2 conserva somente prioridade realmente adquirida. Capital
inicial74.9900USDT+75USDC, equity marcada150.1325; sem injeção. Principal reciclado
mantém o pipeline, mas somente lucro de ciclo completo realizado financia nova célula;
USDT não vira USDC contabilmente. Owned returns têm prioridade e permanecem passivos
e lucrativos. Cap físico200. O teste é abaixo do minNotional, não live-executable.
Publicar pré-registro/source/revisão Astra antes do único run; depois publicar resultado
e autópsia. Sem sweep, rerun, M025, extensão, dia2, conta, Testnet ou live.

## Autoridade OWNER mais recente — M020 zonal ping-pong 5h, 2026-09-08

Seguir `docs/microstructure/STABLECOIN_ZONAL_PING_PONG_OWNER_DIRECTIVE.md`.
Esta é uma hipótese nova, separada do M019: fixed immutable price bands derivados
descritivamente da ocupação canônica de preços de2025, rolling active window com
alvo4BUY abaixo/4SELL acima, uma sequência econômica por banda e ordens
normalizadas de1USDT. O resultado é explicitamente
`NON_EXECUTABLE_NORMALIZED_THROUGHPUT_DIAGNOSTIC`, pois1USDT viola o minNotional
Spot; somente esse gate pode ser virtualizado conforme o protocolo congelado.
Primeiro e único replay autorizado:2025-01-01T00:00Z–05:00Z exclusive. Nenhum
evento posterior pode chegar à state machine. Capital normalizado total100,
endowment causal aproximadamente50/50, reserva0, release desabilitado, nenhuma
saída negativa, sem liquidação no cutoff. Preregister, testar, revisar, registrar
e publicar o source antes do run; publicar resultado/auditoria depois. Não há
autorização para dia2, safe-min-notional ou tuning. Preservar M019 e anteriores.

## Autoridade OWNER mais recente — adaptive stablecoin ladder,2026-09-08

Seguir `docs/microstructure/ADAPTIVE_STABLECOIN_LADDER_OWNER_DIRECTIVE.md`.
Esta é uma NOVA hipótese: M019 será ADAPTIVE_STABLECOIN_LADDER_V1, exatamente
6BUY+6SELL logical slots sobre USDCUSDT Spot observado L2,100USDT-equivalent
initial marked equity, small safe valid notional, true compounding, inventory
lots/band memory, global capital and liquidity consumption, and profit-only exits.
REALIZED_LOSS_ALLOWED=false; reserve/release/forced timeout/cutoff liquidation
disabled. Underwater/dormant inventory remains marked and visible. First run only
2025-01-01UTC. Day2 is closed unless D1 reaches1000 complete positive cycles with
nondegraded equity and independent audit, then authority must be updated. No live,
Testnet or account access. Preserve B10/M014/M015/M018 and published evidence.
Preregister, test, Astra-review, register and publish exact source before execution.
This section supersedes the unexecuted three-range proposal below.

## Autoridade OWNER mais recente — três faixas sem reserva,2026-09-08

OWNER propôs novo modelo com três faixas de100USDT, sem reserva, comprar baixo
e vender alto, faixas separadas e foco em medir inoperatividade/ciclos. Proposta
registrada em OWNER_GATED_REPLAY_WINDOW.md; não é edição ou retomada de B10/M018.
O capital proposto é300, não110; não apresentar aumento de capital como edge.
OWNER esclareceu: somente1dia e vender em alta somente. Sem saída forçada com
perda;1h é alerta/métrica, não liquidação. Posições abertas permanecem marcadas.
Preparação autorizada; novo replay exige protocolo, identidade, testes, revisão
e publicação. Pergunta sobre90%de cobertura é diagnóstico, não aumento autorizado
do número de lanes, capital ou período; separar price-path de execução L2.
Sem transferência entre faixas ou duplicação de liquidez. Atividade contínua é
hipótese a medir, não garantia. As seções anteriores ficam como proveniência.

## Autoridade OWNER mais recente — progressão1→2→3 e suporte,2026-09-08

Seguir OWNER_GATED_REPLAY_WINDOW.md: primeiro dia somente; ao demonstrar1000
ciclos completos líquidos positivos em CADA dia, com economia/execução/auditoria
válidas, avançar condicionalmente ao segundo e terceiro, mesma estratégia e
estado integral. Depois de três dias aprovados, hipótese de2000/dia retorna ao
primeiro dia com nova identidade e100+10 iniciais. M017 fez12 no dia1; extensão
atualmente bloqueada. OWNER autorizou continuar elaborando com estratégias de
suporte; M018 é o caso isolado de admissão passiva, com registro/revisão/publicação
antes de executar. Não gerar gráficos/HTML: informar ciclos, banca, reserva,total.
A ambiguidade da frase1hora permanece explícita; não relabelar o controle2h.
Esta seção supera a proibição de novo caso e a exigência de nova aprovação manual
para dias2/3 abaixo, exclusivamente quando os novos gates forem demonstrados.

## Autoridade OWNER vigente — somente1dia, ampliação após aprovação,2026-09-08

O OWNER reduziu o escopo12→3→2→1dia. Sua frase “1hora de espera máxima” está
aguardando distinção entre hold simulado e prazo de entrega; não mudar a política
de2h registrada do M017 silenciosamente ou dizer que já foi executada com1h.
Isso NÃO é aprovação de extensão. Seguir
`docs/microstructure/OWNER_GATED_REPLAY_WINDOW.md`. Nenhum replay além
do primeiro dia nem novo caso pode iniciar automaticamente. M017 foi interrompido
por mudança de escopo; preservar o prefixo fechado do dia1 e todos os artifacts já
produzidos sob autorização anterior. O excedente permanece histórico conhecido,
fora do comparativo atual, não é teste ainda não visto. Não modificar a evidência
ou os parâmetros para aparentar que a execução original tinha apenas1dia.
Mesma primeira amostra nos controles; compounding/posição/ordens/timers
preservados no checkpoint, nenhuma liquidação ou reset artificial no cutoff.
Publicar comparação/auditoria do dia1 e aguardar aprovação explícita antes de
ampliar. Esta seção supera os antigos gates automáticos e o horizonte de12dias.

## Autoridade OWNER vigente — equilíbrio reserva/recuperação/rotação,2026-09-08

Seguir `docs/microstructure/RESERVE_ROTATION_OWNER_DIRECTIVE.md`. OWNER autorizou
autópsia e campanha pequena pré-registrada para funding, divisão da banca110,
orçamento de release e dívida de recuperação, com objetivo de exposição<=2h.
Não presumir80% ótimo. Preservar B10/M014/M015, profiles e resultados publicados;
novas políticas materiais exigem identidade, testes/revisão/publicação antes do run.
Somente os12 dias sintéticos já aprovados; mesmas restrições de conta/dados/live.
Prazo de saída tem prioridade sobre bloqueio discricionário; conflitos com piso e
liquidez devem ser explícitos, não fills inventados. Diagnóstico sobre fills fixos
não é replay composto. Esta seção supera congelamento de pesquisa de sucessores,
não autoriza modificar os modelos históricos ou ampliar dados.

## Autoridade OWNER vigente — 12 dias L2 consecutivos sintéticos

OWNER substituiu os resets independentes por sequência artificial com estratégia
e compounding preservados. Executar exatamente os12 dias já aprovados: Jan/Fev/Mar/
Abr/Jun/Ago2025 e Jan/Fev/Mar/Abr/Mai/Jul2026, sempre dia1 UTC. Uma inicialização
operacional100 + reserva10 por envelope; carregar banca, posições, ordens e timers.
Seguir `docs/microstructure/L2_CONSECUTIVE_STRESS_OWNER_DIRECTIVE.md` e
`docs/microstructure/L2_MONTHLY_SAMPLE_PROTOCOL.md`.
Não apresentar a concatenação como histórico contínuo real, inventar fills nos
saltos, incluir datas ainda em preparo ou ler Jan8–14 reais. Publicar source/review
antes da execução. M015/estratégia e profiles continuam congelados. Esta seção
supera INDEPENDENT_24H e resets diários da diretiva anterior, não seus gates de dados.

## Autoridade OWNER vigente — bateria mensal L2 histórico gratuito

Seguir `docs/microstructure/L2_MONTHLY_SAMPLE_OWNER_DIRECTIVE.md`: pesquisar,
baixar, validar e executar todas as 21 amostras acessíveis de primeiro dia mensal,
2025-01-01 a 2026-09-01, dentro do histórico canônico USDCUSDT. Cada dia/envelope
é independente, FLAT, operacional100 + reserva10, compounding somente intradia,
funding10% de lucro positivo. Separar2025 calibração de2026 avaliação.
Preservar estratégia vigente conferida no CURRENT_STATE/registry; mudança de
evidência de execução tem identidade própria, não edição de modelo congelado.
Dois envelopes pré-registrados: CONSERVATIVE_QUEUE e PRICE_PRIORITY com L2
observado. Não afirmar posição exata de fila; não duplicar liquidez/trades.
Validar snapshots, sequência nativa, captura, gaps e book; CSV sem U/u não
prova continuidade local. Dados inválidos/inacessíveis são explícitos e não
impedem verificar os demais. Não exigir500 para executar outros dias válidos.
Publicar manifest, journal e placar leve no GitHub; originais imutáveis locais.
Autorização inclui fontes públicas gratuitas, não chaves/contas/compras/live.
Esta bateria NÃO autoriza Jan8–14 contínuo nem composição entre meses.
Retornar placar de dados/commit antes da simulação e iniciar válidos automaticamente.

## Autoridade OWNER vigente — mínimo500/dia e segunda semana condicional

O OWNER autorizou estudar bugs e otimizar a estratégia até obter pelo menos500
ciclos ordinários completos líquidos positivos em CADA dia de1–7janeiro, mantendo
meta2.000/dia. Ao atingir o mínimo auditado, executar8–14janeiro com mesmo modelo,
configuração e estado financeiro/ordens preservados; esta aprovação é condicional
e vale somente para a segunda semana. Nenhum dado posterior antes desse gate.
Hipóteses mudadas exigem novo registro; não modificar M014 já concluído. Não contar
releases/parciais nem reduzir fila/custos ou criar liquidez para obter o número.
O pedido de persistência não prova que o mínimo seja fisicamente alcançável.
Journal deve registrar também falhas e restrições; publicar marcos consistentes.
Esta seção supera proibições anteriores de estudar um sucessor e autorização
separada da segunda semana SOMENTE quando500/dia for demonstrado e auditado.

## Autoridade OWNER vigente — resgate B10 F2.5 e meta 2.000/dia

O OWNER reabriu explicitamente o estudo/otimização do RRV2_H1_B10_F2.5
da identidade097abdab. Meta agora2.000 ciclos completos líquidos positivos por
dia, somente1–7janeiro inicialmente; cada extensão exige aprovação específica.
Consultar M014_MODEL_SPEC.json e M014_B10_RESERVE_PREREGISTRATION.md.
Primeiro reconstruir B10 H1/F2.5/M007 com a reserva OWNER100+10 e funding10%,
compounding, usando ledger/fills reais simulados. M013 não é o pai automático.
Uma fila serial isola essa reconstrução; não importar seletor/urgência6h do M013.
Qualquer otimização posterior de admissão precisa da autópsia e de identidade nova;
não mudar configuração no meio da semana para alcançar a meta.
Preservar B10 antigo, M012 e M013. Reabertura não autoriza retomar gauntlet antigo,
fazer sweep, acessar conta ou processar a segunda semana sem aprovação.

## Autoridade OWNER vigente — SEMANA A SEMANA, 2026-09-07

O OWNER substituiu janeiro inteiro e TWO_STAGE por uma primeira semana somente:
2026-01-01T00:00:00Z inclusive até 2026-01-08T00:00:00Z exclusive.
Consultar `docs/microstructure/WEEKLY_REPLAY_OWNER_DIRECTIVE.md`.
Meta a testar: 1.000 ciclos operacionais completos e líquidos positivos por dia.
Cada extensão de sete dias exige aprovação explícita e específica do OWNER,
mesmo com métricas positivas e auditoria aprovada. Nenhuma extensão automática.
Preservar banca composta, reserva, posições, ordens, filas e timers entre semanas;
não resetar capital, forçar fills/releases nem otimizar parâmetros após resultados.
M013 está parado por bug técnico confirmado de reenvio de BUY obsoleta; seus
artifacts são evidência preservada, não resultado válido da estratégia corrigida.
Não retomar M013 nem usar o antigo runner de cinco meses para a nova semana.
A correção e o protocolo semanal exigem identidade, fonte publicada e revisão
vinculadas antes do novo replay. Preparação não significa semana executada.
Esta seção supera todas as autorizações temporais/automáticas conflitantes abaixo.

## Autoridade OWNER vigente — TWO_STAGE, 2026-09-07

`docs/microstructure/TWO_STAGE_REPLAY_OWNER_DIRECTIVE.md` limita o primeiro replay
multi-queue a 2026-01-01T00:00:00Z inclusive até 2026-06-01T00:00:00Z exclusive
(151 dias). Junho ao cutoff físico de setembro são SEALED_EXTENSION_DATA.
Não carregar/traversar esses trades nem usar suas estatísticas no Stage 1.
Congelar modelo, políticas e gates antes do replay. Somente PASS_TO_EXTENSION
com todos os gates e auditoria aprovada autoriza Stage 2 automaticamente.
Extensão preserva o mesmo modelo/hash, capital composto, reserva, posições,
ordens, dust, timers, liquidez e ledger; nenhum reset nem tuning entre etapas.
FAIL exige autópsia, sem extensão; problema técnico/evidência insuficiente é
INCONCLUSIVE, nunca perda econômica. Checkpoints DAY_1/7/30/60/90/120/FINAL_5_MONTH.
Esta autoridade supera a obrigação histórica de iniciar pelo período completo.

## Autoridade OWNER vigente — M013 continuous multi-queue, 2026-09-07

`docs/microstructure/CONTINUOUS_MULTI_QUEUE_OWNER_DIRECTIVE.md` supera políticas
incompatíveis anteriores. M012 registrado permanece histórico/SUPERSEDED; seu processo
foi parado ainda na preparação do histórico, antes de qualquer replay econômico.
Registry físico confirma M013 como próximo ID livre para CONTINUOUS_MULTI_QUEUE_RECOVERY.
COMPOUNDING: operating inicial100/reserve10/equity110. Lucro operacional10% reserva,
90% reinvestimento; lucro da fila ativa100% reserva; nenhum saque ou reset100.
Até3 filas operacionais independentes e1fila ativa de reserva em USDCUSDT; alocação
causal pré-registrada, ranges distintos quando viáveis, liquidez compartilhada sem
contar volume/depth quatro vezes. Reserva ativa<=50%;core protegido/sobrevivência>0.
Limite24h por fila operacional; medir uptime ponderado pelo capital, fullstop e
sustentabilidade da reserva. Nenhuma segunda paridade, conta privada, Testnet/live.
Pré-registro+implementação+testes+review independente PASS+publicação autorizam primeira
execução automaticamente. Não retomar B10 ou M012 nem alterar suas evidências.

## Autoridade OWNER vigente — supersessão B10 / M012, 2026-09-07

`docs/microstructure/HIGH_UPTIME_RECOVERY_OWNER_DIRECTIVE.md` supera as ordens anteriores
de continuar o gauntlet B10. B10 permanece histórico e reproduzível; a campanha recebe
SUPERSEDED_BY_OWNER_STRATEGY_UPDATE, não FAIL. A já concluído permanece imutável;
B parcial preservado; não iniciar/retomar B, C, B_FEE10 ou D. Automação B10 pausada.
Registry canônico confirmou M001–M011 ocupados; M012 é o sucessor a registrar.
HIGH_UPTIME_DYNAMIC_RECOVERY: operating100 + reserve5, funding5% de lucro líquido
positivo, target5% da banca operacional, piso não-zero pré-registrado, limite24h.
Correção OWNER `docs/microstructure/OWNER_COMPOUNDING_CORRECTION.md`: COMPOUNDING
obrigatório, sizing CURRENT_AVAILABLE_OPERATING_BANK;100 é somente inicialização.
95% do lucro líquido positivo reinvestido,5% reserva; sem saques. FIXED100 somente
AUXILIARY_DIAGNOSTIC_RULER e nunca retorno/projeção da estratégia OWNER.
Primeiro replay COMPOUNDING reality-style explicitamente autorizado somente
após pré-registro, revisão Astra, implementação, testes e auditoria. Nenhuma liquidez ou fill
pode ser inventado para cumprir24h; descumprimento físico é HARD_LOCK_VIOLATION.
Consultar CURRENT_STATE, journal M012 e pré-registro M012; journal B10 append-only.
As seções conflitantes abaixo são evidência histórica, não autoridade para reabrir B10.

## Handoff e placar OWNER — GitHub canônico, 2026-09-07

Ler primeiro `docs/research/CURRENT_STATE.md`, `docs/research/B10_JOURNAL.md`,
`reports/usdcusdt/B10-reality-scoreboard.json` e os últimos commits.
Autoridade de publicação: `docs/research/GITHUB_RESEARCH_JOURNAL_OWNER_DIRECTIVE.md`.
O diário B10 é append-only. Publicar checkpoints econômicos materiais, inclusive durante
o run, sem depender do chat. Nunca comparar ciclos parciais a3580880 do período inteiro:
usar saídas B10 históricas até o MESMO evento canônico do checkpoint como denominador.
Separar testes de software, progresso, economia parcial e conclusão final. Enquanto
incompleto, `VERDICT=PENDING`; testes aprovados nunca significam estratégia aprovada.
Não interromper/mudar B10, profiles ou parâmetros para alterar desempenho.
Commits de journal/reporting não alteram o SHA de execução já gravado nos checkpoints.
Uma eventual retomada deve preservar esse vínculo; não trocar SHA silenciosamente.

## Autoridade OWNER vigente — B10 Binance Reality Gauntlet, 2026-09-07

`docs/microstructure/B10_REALITY_GAUNTLET_OWNER_DIRECTIVE.md` supera as autoridades
conflitantes abaixo. Único objeto: `B10_FROZEN` / `RRV2_H1_B10_F0`, identity
`097abdab8225038b091cb721bdd36bedb8a636c94bed1c87120adc0c9e10953a`.
Protocolo: `docs/microstructure/B10_REALITY_GAUNTLET_PROTOCOL.md`.

- Não executar M011, comparar/otimizar estratégias ou modificar B10 para salvá-lo.
- Só muda o ambiente de execução, `BINANCE_REALITY_V1`; isso não cria novo Mn.
- Régua principal deste estudo de execução: FIXED_NOTIONAL_100, operating100 + reserve5,
  skim2% de lucro realizado líquido positivo; um lote serial e somente USDCUSDT.
- Pesquisa oficial, coleta pública L2, testes, replays completos condicionados a evidência,
  autópsia de releases e revisão independente estão autorizados. Preservar B10 original.
- Queue, latency e regras históricas desconhecidas devem ser explícitas; touch não é fill.
- Zero acesso a conta, chave privada, Testnet, ordens live ou deploy.
- Atualizações materiais seguem o placar econômico prefix-to-prefix mais recente do OWNER;
  a seção53 anterior é superada pelo formato de progresso/economia do novo journal.

## Autoridade OWNER anterior — preservada como histórico

`docs/microstructure/OWNER_STRATEGY_OVERRIDE.md` supera todas as regras conflitantes abaixo.
O handoff atual é `docs/microstructure/CURRENT_STRATEGY.md`. Regras históricas deste arquivo
permanecem como proveniência, não como autorização para retomar hipóteses superadas.

- QUALITY_FIRST=ON; TOKEN_SAVING_PRIORITY=OFF. A antiga política de roteamento econômico
  está preservada como HISTORICAL_SUPERSEDED_POLICY em MODEL_ROUTING_POLICY_HISTORY.md.
- Cada estratégia materialmente diferente exige um novo Mn no registry existente, incluindo
  mecanismo de reserva, funding, cap, release, parâmetros materiais e semântica de execução.
- M007 é HISTORICAL_BASELINE / SCIENTIFIC_ANCESTOR e permanece SHADOW_MODEL; não é a
  ACTIVE_RESEARCH_STRATEGY. Promoção passada continua evidência imutável no registry.
- Campanhas superadas pelo OWNER podem ser encerradas com checkpoints preservados e status
  SUPERSEDED_BY_OWNER_STRATEGY_UPDATE, nunca FAIL por esse motivo. Nenhum replay econômico
  pode ser encurtado oportunisticamente; regras de domínio/stop exigem pré-registro.
- A primeira entrega atual termina após publicar linhagem, placar histórico e pré-registro
  da nova estratégia. Nenhuma automação antiga pode iniciar a nova campanha.
- Mantenha detalhe científico e placar econômico; use revisores fortes em decisões materiais
  e Python para cálculo. Não use Astra para aguardar processos.
- Permanecem um lote operacional, USDCUSDT, DEVELOPMENT, conta privada/Testnet/Live fechados,
  SHADOW M007 inalterado, capacity/duas bancas/segunda paridade somente roadmap.

Estas instruções especializam as regras globais para o repositório
`guilhermecrepaldi/crypto-strategy-lab`. Dentro deste diretório, a autoridade canônica é este
projeto; a prioridade global do KNOTEN permanece inalterada fora dele.

## Canônica e continuidade

- Preserve uma única implementação por responsabilidade. Corrija a autoridade existente em vez
  de criar variantes permanentes, worktrees ou pipelines paralelos.
- Antes de mudanças estruturais, confirme diretório, Git root, remote, branch, HEAD, status,
  processos e a identidade experimental afetada.
- Estados físicos, checkpoints e manifests são a autoridade da campanha; relatórios derivados
  devem ser reconciliados com eles.
- Nunca altere silenciosamente uma campanha após observar resultados. Hipóteses novas recebem
  identidade experimental nova.
- Preserve alterações locais e artifacts. Não use reset, checkout, clean ou stash para contornar
  trabalho existente.

## Divisão de responsabilidade

### GPT-6 Astra — autoridade científica

Use explicitamente `gpt-6-astra` para formular hipóteses, definir experimentos e métricas,
projetar ou revisar lógica que muda o significado experimental, investigar perdas e falhas,
distinguir bugs de resultados legítimos, interpretar evidências e decidir o próximo experimento.
Cálculos continuam sendo feitos por código verificável. Não delegue decisões científicas ao
executor econômico.

### GPT-5.6 Luna — execução delimitada

Prefira `gpt-5.6-luna`, quando disponível e adequado, para implementação mecânica já
especificada, comandos e testes definidos, acompanhamento de processos, coleta de logs,
formatação e pequenas correções operacionais. Ele deve devolver fatos verificáveis e não pode
mudar reward, features, hiperparâmetros, partições, critérios de sucesso ou estratégia.

### Python e ferramentas do projeto — execução experimental

Use Python e os comandos existentes para simulações, treinamento PPO/DQN, candles, features,
seeds, checkpoints, replay buffers, métricas, baselines e relatórios. Não chame LLM por candle,
operação, timestep, episódio ou reset. Não crie um harness novo apenas para alternar modelos.

## Ciclo de trabalho

1. Astra define ou revisa a hipótese e o protocolo.
2. Trabalho mecânico delimitado pode ser delegado ao Luna.
3. A implementação é conferida contra a especificação.
4. Python executa a configuração identificada e preservada.
5. Python produz métricas e evidências completas nos artifacts.
6. Astra interpreta resultados e decide o próximo passo.

Use agentes somente quando o bloco for independente e o ganho superar o custo de coordenação.
Informe quais modelos foram realmente usados; não alegue troca de modelo que não ocorreu.

## Evolução dirigida por aprendizado

- Trate todo o intervalo congelado de `2026-01-01` ao cutoff físico como `DEVELOPMENT`; seu
  resultado é score de desenvolvimento, nunca prova prospectiva.
- Execute um único `Mxxx` por vez. Antes de autorizar o sucessor, faça a autópsia física do
  anterior, registre observação, hipótese de causa, mudança proposta, efeito esperado e riscos.
- Cada challenger deve atacar um gargalo observado com uma mudança interpretável. Resultado
  rejeitado não vira pai automático; a linhagem parte do champion vigente e pode ramificar.
- Compare capital final, ciclos, idle, zero days, holding, reseleções, drawdown, estabilidade,
  concentração e taxas. Capital final isolado não autoriza promoção.
- Registros `CREATED` anteriores a este protocolo são somente identidades reservadas. Não são
  autorização científica de execução sem vínculo explícito com a autópsia do pai.
- A cada dez modelos concluídos, pause novas execuções para revisar champion, descobertas,
  hipóteses rejeitadas, risco de overfit, gargalo e direção seguinte.
- Toda decisão no evento `T` usa apenas o prefixo causal até `T`. Análises posteriores podem
  motivar um novo modelo, mas nunca retroagir dentro de um replay.

## Segurança experimental

- `VALIDATION` e `LOCKED_TEST` permanecem fechados até seus gates explícitos.
- Não acessar conta Binance, Testnet ou live; não solicitar chaves nem enviar ordens.
- Não fazer deploy sem autorização específica.
- Não iniciar um segundo trainer se existir um trainer canônico ativo.
- Bugs técnicos não são perdas legítimas. Preserve o artifact, invalide somente o escopo
  comprovadamente afetado, corrija com teste e registre a decisão.
- Resultados positivos, negativos, falhas e invalidações devem permanecer rastreáveis aos
  artifacts originais; destaque eventos somente por critérios explícitos e reproduzíveis.

## Espelho contínuo da campanha no GitHub

- O OWNER autoriza `git push` normal exclusivamente para `origin/main` deste repositório após
  cada milestone consistente da campanha. Não acumule milestones concluídos apenas localmente.
- Antes de uma execução longa baseada em mudanças novas, valide, faça commit e push da
  pré-configuração; registre no run o `GIT_COMMIT_SHA` já publicado. Ao concluir, reconcilie
  registry, journal, decisões e resultados leves, então faça novo commit e push.
- Antes de cada push, execute `git fetch`, confirme que `origin/main` não avançou de forma
  inesperada, rode `git diff --check` e os testes proporcionais ao delta, verifique secrets e
  arquivos grandes. Depois do push, confirme `HEAD == origin/main`.
- Nunca usar force push, reescrever histórico publicado, alterar remote, criar release ou fazer
  deploy por efeito desta autorização. Divergência remota ambígua bloqueia somente o push.
- Não versionar trades históricos brutos, ZIPs, market tapes, caches mmap ou artifacts binários
  grandes. Versionar manifests, hashes, provenance, comandos de reconstrução, configs, código,
  testes, registros e relatórios resumidos.
- Resultados publicados são imutáveis como evidência. Correções exigem novo commit e registro
  explícito; se mudarem significado científico, registrar correção ou invalidação.
- Todo modelo `Mxxx` executado nesta campanha percorre integralmente o intervalo padronizado de
  `2026-01-01T00:00:00Z` ao cutoff físico congelado. Resultado econômico ruim, ociosidade,
  inferioridade ou posição aberta não autorizam early stop; somente invalidade técnica pode
  interromper e deve ser registrada como `INVALIDATED_TECHNICAL`.
- `HOT`, `COLD`, `FAILURE`, estabilidade, concentração e regimes são análises descritivas
  posteriores ao replay. Não podem alimentar decisões passadas, filtrar meses, fechar posições,
  mudar estratégia ou alterar gates já congelados sem uma nova hipótese pré-registrada.

## Escopo científico ativo

- A única campanha operacional e experimental desta linha de pesquisa é
  `USDCUSDT_EXHAUSTIVE`, no par `USDCUSDT`.
- `FDUSDUSDC` é exclusivamente `LEGACY_EVIDENCE` / `ARCHIVED_EXPERIMENT`: preserve seus
  artifacts existentes, mas não baixe novos dados, não execute scanners ou backtests, não crie
  modelos, não use como controle e não faça novas comparações com ele.
- A estratégia ativa preserva uma banca, um lote, um LOW, um HIGH e um único ciclo serial. Não
  introduza grid, múltiplos lotes, alavancagem, martingale, DCA, RL ou LLM por evento.

## Gate atual — operador M007 congelado

- Atualização OWNER: Prompt 2 autorizado somente para observação pública SHADOW. Sua
  implementação está pendente da escolha temporal reportada (timestamp estrito versus ordem
  de eventos do M007); não alterar seletor congelado silenciosamente.
- Atualização OWNER: RECOVERY_RESERVE tem prioridade histórica; HOLD_RISK_SELECTOR fica
  pausado, com pré-registro e artifacts preservados. M011 ainda livre será registrado somente
  após região robusta e revisão Astra. Seguir `docs/microstructure/RECOVERY_RESERVE_PROTOCOL.md`:
  100 USDT operacionais, 5 segregados, cobertura exata integral e skim somente de lucro positivo.
  A grade limitada de cenários é autorizada exclusivamente para essa hipótese. Comparar equity
  total contra M007 + 5 parados; nenhuma alteração automática do operador/champion.
- Esta atualização supera a limitação histórica ao Prompt 1 e a proibição de estudar M011,
  apenas nesse escopo. Preserve artifacts M010, sem incorporá-lo ao novo seletor.

- O protocolo do milestone anterior limitou aquela entrega ao Prompt 1: especificação M007, contrato
  `SHADOW_ONLY`, state machine, testes, commit e push. Parar após esse milestone.
- A autoridade é o M007 existente, sem melhoria científica ou novo Mxxx. M008/M009 não são
  utilizados; M010 concluído é evidência histórica, sem autorização de nova execução.
- TESTNET e LIVE falham fechado; `TRADING_ENABLED=false`. Market data público pertence somente
  ao Prompt 2. O diagnóstico HOLD_RISK_SELECTOR é offline, sem conexão a mercado ou conta.
- Consultar `docs/live/M007_OPERATOR_SPEC.md`, `LIVE_ARCHITECTURE.md` e `STATE_MACHINE.md`.
  Price-touch não é fill; estados reservados não são capacidades de execução já implementadas.

## Linha histórica de capital release — não reabrir neste gate

- O OWNER reabriu a evolução price-path exclusivamente para investigar `CAPITAL_RELEASE`, com
  parent científico `M007` e problema `LONG_HOLD_CAPITAL_LOCK`. M008 e M009 permanecem
  rejeitados; seus controles não podem entrar silenciosamente no sucessor.
- Capital release não é stop-loss fixo nem timeout. Uma posição só pode ser liberada por uma
  desigualdade econômica causal pré-registrada entre esperar e realizar uma perda controlada,
  reentrar em uma faixa selecionada pelo prefixo e recuperar capital.
- Nenhuma decisão em `T` pode usar HIGH, ciclos, volume, faixa, Oracle, duração restante ou
  resultado posteriores a `T`. Desfechos futuros pertencem somente à autópsia, identificados
  como `RETROSPECTIVE_DIAGNOSTIC_ONLY`.
- Separe sempre `THEORETICAL_RELEASE_LOSS` price-path de `EXECUTABLE_RELEASE_LOSS`. A segunda
  permanece `UNKNOWN` sem evidência histórica de fila, book, spread, slippage e latency.
- Antes de registrar o sucessor, publique o diagnóstico causal do M007 e uma única regra
  interpretável, com fórmulas, suporte mínimo, margem e gates congelados. Não faça sweep de
  loss, hold, horizonte ou janelas.
- O replay autorizado do sucessor começa com 100 USDT, cobre todo o DEVELOPMENT congelado sem
  early stop e reporta, além da composição, uma régua de notional fixo de 100 USDT.

## Régua financeira canônica

- Todo replay principal de um modelo `Mxxx` começa, de forma independente, com exatamente
  `100 USDT` em `2026-01-01T00:00:00Z` ou no primeiro evento causal elegível posterior. O
  capital final do pai nunca é o capital inicial do sucessor.
- O modelo pode reinvestir seus próprios ganhos durante o replay (`COMPOUNDING`), mas cada nova
  identidade volta a 100 USDT. Manifest, registry e scoreboard devem registrar
  `initial_capital=100`, `currency=USDT` e `capital_mode=COMPOUNDING`.
- Qualquer replay principal que tente iniciar com outro valor é inválido e deve falhar fechado
  com `INITIAL_CAPITAL_INVARIANT_VIOLATION`; não corrija o valor silenciosamente.
- `FIXED_NOTIONAL_100` é diagnóstico auxiliar sem compounding. Seus resultados e ledger não
  podem substituir nem ser misturados com o replay principal composto.

## Aceleração GPU opcional

- CPU é o backend canônico. GPU é somente acelerador opcional para scanners e cálculos em lote;
  backend não cria novo `MODEL_ID` e nunca altera decisão científica.
- Mantenha download, ZIP, parsing, SHA256, manifest, persistência, a state machine serial e a
  contabilidade financeira exata na CPU, salvo benchmark específico que demonstre o contrário.
- Use integer ticks para LOW/HIGH e preserve `Decimal`/fixed-point no ledger. Não permita que
  float32 altere seleção, ciclos, eventos, fees, capital ou decisão de promoção.
- CUDA só pode entrar na campanha após fixtures e amostras reais comprovarem
  `CPU_RESULT == GPU_RESULT` e benchmark end-to-end, incluindo transferências, mostrar speedup
  material (limiar inicial de 2x). Falha ou OOM deve cair explicitamente para CPU.
- Não instalar Ollama, LLM local, driver, CUDA Toolkit global, firmware nem mudar BIOS, clock,
  voltagem ou power limit. Dependências Python GPU devem ser opcionais e reproduzíveis.
