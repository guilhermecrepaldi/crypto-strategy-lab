# OWNER — equilíbrio entre reserva, recuperação e rotação

Autoridade recebida em2026-09-08. Supersede somente proibições anteriores de
estudar sucessores/novas políticas neste escopo. B10/M014/M015 e seus resultados
permanecem imutáveis. Não retomar campanhas antigas nem alterar profiles publicados.

## Objetivo e âmbito

Encontrar uma região robusta para funding do lucro, divisão operacional/reserva,
perda de release, ciclos e tempo de recuperação, alta rotação e crescimento
composto.10/70/80% são exemplos, não valores aprovados como ótimos.
Comparação principal com capital total inicial110 USDT; a divisão pode variar,
sempre explícita. Capital adicional é outro diagnóstico, não vantagem gratuita.
Somente os12 dias sintéticos já autorizados, na ordem publicada. Nenhum dado
posterior, conta, chave, Testnet, live ou nova paridade. Tudo é DEVELOPMENT.

Prioridade: alta frequência de ciclos completos líquidos positivos, capital
produtivo, banca crescente e reserva sem erosão persistente. Preservar metas
500/2000 por dia, reportar também1000. Não confundir ordens, parciais ou releases
com ciclos; uptime de ordem não é produtividade econômica.

## Prazo de posição

Objetivo máximo2h desde o primeiro fill BUY até encerramento efetivo da exposição
negociável; não reiniciar relógio por parcial, cancelamento, reenvio ou faixa.
Enviar saída não comprova fill. Liquidez/custos/latência integrais; qualquer
violação fica explícita. Nunca inventar execução para cumprir prazo.

## Pré-requisitos

Reconciliar código, manifests, checkpoints, ledger, fills e decisões antes de
novos replays. Autópsia por release: perda, duração, motivo/momento, reserva,
impedimentos, custo/liquidez, ciclos posteriores, aportes e perdas sobrepostas.
Separar BUG_TECNICO, RESTRICAO_EXECUCAO, REGRA_ESTRATEGICA,
PERDA_ECONOMICA_LEGITIMA e EVIDENCIA_INSUFICIENTE. Corrigir apenas bugs demonstrados.

Hipótese de execução e hipótese estratégica são distintas. Cada mudança material
recebe identidade; pré-registro, testes, revisão científica independente e
publicação antes de replay. Uma configuração completa por vez; nenhuma mudança
após observar seu resultado. Campanha pequena, limitada e interpretável, sem sweep
massivo. Adaptação causal exige regra congelada usando apenas o prefixo disponível.

## Tesouraria

Para lucro líquido positivo g e funding f:
aporte=f*g; reinvestimento=(1-f)*g.
divida_nova=max(0,divida_anterior+consumo_novo-aporte).
Separar saldo efetivo, dívida, aportes, consumo e excedente após quitação; não
descartar excedentes ou contabilizar o mesmo aporte duas vezes. Medir recuperação
na sequência efetiva; dívida não quitada ao cutoff permanece censurada/aberta.
Perda/(f*lucro_medio) é aproximação, não resultado de replay.

Estados candidatos: NORMAL, RECUPERACAO e PROTECAO. Durante dívida, releases
discricionários podem ser bloqueados; novas entradas exigem capacidade para outra
saída. Bloqueio discricionário não impede saída de prazo. Nova saída com perda
aumenta dívida. Piso, liquidez e prazo incompatíveis devem ser reportados como
conflito, nunca resolvidos esperando indefinidamente ou inventando recursos.

## Resultado e escolha

Cada configuração executa seu próprio compounding sob hipóteses comparáveis.
Redistribuição de lucros dos fills antigos é FROZEN_FILL_ACCOUNTING_ONLY,
nunca substitui replay. Funding não cria lucro; reserva não cria liquidez.
Não afirmar ótimo exato ou crescimento garantido. Mostrar melhor no DEVELOPMENT,
vizinhança robusta, sensibilidade a execução/custos e o que não foi demonstrado.
Se nenhuma configuração atingir as metas, registrar frequência demonstrada,
custo, gargalo e próxima hipótese; não selecionar somente capital ou ciclos.

## Entrega e placar

Comparativo HTML canônico com gráficos, explicações e proveniência. Por
configuração: identidade/status; funding; divisão inicial; política/orçamento de
release; ciclos/dia min/mediana/max e dias abaixo500/1000/2000; distribuição do lucro;
quantidade/custo de releases; recuperação ciclos/tempo mediana/P90/max e censurados;
dívidas sobrepostas/final; funding/consumo; reserva final/min/esgotamentos; banca;
equity marcada, PnL realizado/não realizado e drawdown; esperaBUY/posição;
violações2h; horas em proteção; taxas/slippage e limites da evidência.

Responder primeiro com funding, perda média, recuperação ciclos/tempo, frequência,
banca, reserva e violações2h. Separar software, progresso, economia parcial e final;
TEST_SUITE_PASS != STRATEGY_PASS. Exibir casos ruins, não só médias.
Publicar milestones consistentes no diário GitHub canônico, com fontes e hashes,
seguindo fetch/diffcheck/testes/secrets/tamanho/push normal/verificação remota.
