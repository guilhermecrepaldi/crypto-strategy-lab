# M017 — auditoria independente do primeiro dia

STATUS=PASS_PREFIX_EVIDENCE_NOT_STRATEGY_PASS
REVIEW_DATE=2026-09-08
REVIEWER_MODEL=gpt-6-astra
APPROVED_COMPARISON_DAYS=1
LOGICAL_CUTOFF_EXCLUSIVE_US=1735776000000000
NEW_REPLAY_EXECUTED=false
EXTENSION_AUTHORIZED=false

## Escopo e autoridade

Somente a amostra2025-01-01, relógio lógico2025-01-01T00:00:00Z inclusive até
2025-01-02T00:00:00Z exclusive. Este é o prefixo do run original composto,
PRICE_PRIORITY, inicial100USDT operacionais+10reserva; não uma nova execução.
Aplicada a diretiva OWNER_GATED_REPLAY_WINDOW.md: os artifacts posteriores,
produzidos sob autorização anterior, são preservados e excluídos deste comparativo.
Interrupção OWNER_SCOPE_CHANGE não prova bug nem reprovação econômica de12dias.

M017 executou sua política registrada de2h, funding10%, cap efetivo20bps e
piso2.5. A frase posterior “1hora de espera máxima” aguarda esclarecimento;
este resultado NÃO implementa nem valida uma política de1h.

## Evidência física e método reproduzível

Raiz M017: `artifacts/usdcusdt/l2-monthly-samples/M017/SYNTHETIC_CONSECUTIVE_12D/PRICE_PRIORITY`.
Foram lidos `daily/01.json`, `daily/01-engine-state.json`, manifest e apenas o
prefixo do ledger. A leitura binária para imediatamente antes do primeiro
SYNTHETIC_SAMPLE_SEAM com time_us>=cutoff; nenhuma linha desse seam ou posterior
entra na auditoria/hash. O checkpoint diário grava o seam com book invalidado,
mas conserva a mesma contabilidade e ordens do prefixo anterior.

Esse prefixo contém926760linhas e223289164bytes. Uma view de leitura limitada
a esses bytes foi passada ao `audit_all_fills` canônico, sem criar replay ou
alterar ledger. Resultado PASS_AUTOMATED_ALL_FILLS:28fills,13settlements,1release;
os sete campos financeiros finais do auditor coincidem exatamente com o estado
decodificado. O hash canônico interno do checkpoint também foi recalculado.
O corpo AST do auditor foi comparado ao mesmo método no SHA de execução.
Os14bindings LF do manifest foram verificados contra `git show` desse SHA,
não contra arquivos atuais que podem conter gates posteriores.

| Binding | SHA256 |
| --- | --- |
| Source commit | b5379f6fee40e33334e3d3cc32f14f42d5c0cf85 |
| Model hash | b82a5ef829ca396db0f80885807aa4895ec359db3f10d7e917d6e8be0db65af8 |
| Run hash | 7f55d29131f0e4e8cfdce00594553c48994dbe85ca4262f4a1ddf596fd84585c |
| Manifest físico | 0056d8cfea519fe89489fd337757b838a2756eac8a6937eddf6fc6048f745860 |
| Ledger prefixo1D | e82b8e36afb1a97eae802a160652b713d4918ca54d8a59a08d791f7a9501cfb9 |
| daily/01.json | f72bd75832c5efa70867ebf04ab69abcb7a0420cfa63a77936e93e3c35172f18 |
| daily/01-engine-state.json físico | 85205d5a230869c29baa14bfbf62336922d0ca2bc4bef3b4ad69e18b33ad3b3f |
| Checkpoint hash interno | a64b87d0a40fa04a87b62052d5d8bdfc7bfefc40df24da29d0d1d0c90975da3c |

## Reconciliação financeira e prazo

12ciclos ordinários líquidos positivos produzem0.1188USDT;1release perde0.0198.
Resultado líquido0.099; operacional100.10692+reserva9.99208=equity110.099.
Fees explícitas somam0 no profile maker0/taker0; isto não presume custo zero
em conta real. O auditor verifica fills contra a evidência e o envelope de
execução, não certifica a posição real de fila de uma conta Binance.

Funding total0.01188; consumo0.0198; reserva mínima9.98416>piso2.5.
O release realizado0.0198 usa1.9792945794bps da banca causal100.03564,
abaixo do orçamento20bps=0.20007128. Escrow0.198 também cabe no orçamento
e preserva o piso. Não há consumo/reutilização de depth inválido encontrado
pelo auditor canônico. Release é fill BOOK observado; cancelamento/sinal não
é contabilizado como fill.

Uma coorte de dívida nasceu em0.0198. O funding posterior paga0.00792;
restam0.01188, nenhuma coorte integralmente recuperada (0/1). Funding0.00396
anterior à perda é excedente de reserva, não recuperação retroativa da dívida.
Logo dívida pendente não é simplesmente consumo menos todo funding.

O primeiro BUY do lote liberado ocorre em1735720136091500; a saída final em
1735727336139367. Hold7200047867us=2.000013296388889h:47.867ms além de2h.
Há1DEADLINE_VIOLATION e1HOLD_OVER_2H; o evento de violação ocorre no primeiro
microssegundo posterior ao deadline. Esse atraso permanece violação explícita,
sem arredondá-lo para afirmar cumprimento perfeito. As durações foram
recalculadas do primeiro fill BUY até settlement, sem reset no BUY parcial.

No corte, posição e dust são zero; existe BUY ativa2578,99USDC a1.00190,
sem fill. FLAT não significa ausência de ordem. Não houve liquidação forçada.

## Comparação estrita do mesmo primeiro dia

Controles usam somente seus `daily/01.json` e `daily/01-engine-state.json`,
com hash interno validado. Nenhum resultado integral entra nesta tabela.

| Métrica | M015 | M016 | M017 |
| --- | ---: | ---: | ---: |
| Ciclos ordinários positivos | 12 | 12 | 12 |
| Operacional | 100.10692 | 100.10692 | 100.10692 |
| Reserva | 9.99208 | 9.99208 | 9.99208 |
| Equity | 110.099 | 110.099 | 110.099 |
| Dívida FIFO pendente | 0.01188 | 0.01188 | 0.01188 |
| Hold máximo, horas | 3.0010133033 | 2.0000132964 | 2.0000132964 |
| Posição aberta no corte | não | não | não |
| Tempo com ordem ativa, fração | 0.9967377292 | 0.9640420889 | 0.9640420889 |

Tempo com ordem ativa não é uptime produtivo, garantia de fill ou rentabilidade.
Não há hold aberto censurado nestes três checkpoints. Hashes físicos dos
checkpoints dos controles: M015 `69c1cd35f51cefac4dec43898433620bf657904b32bf6e034ee4485be5f92f26`;
M016 `8aa89e414001caacd088faf447a099bd364c9935392a807290e476746ac56369`.

## Veredito e limite

PASS da integridade e reconciliação deste prefixo, não da estratégia. O cap20bps
não demonstra vantagem financeira sobre M016 neste dia; a mesma perda cabe no
cap10bps.12ciclos estão abaixo da meta500/dia, a reserva caiu e a dívida não foi
quitada. Um dia positivo não demonstra sustentabilidade ou generalização.

Preservar checkpoint prova o estado financeiro/ordens, não a capacidade completa
de retomada do runner, seletor, book e cursor. Nenhum resume foi testado ou
executado. Qualquer ampliação ou nova política exige a autorização OWNER e os
gates aplicáveis; aprovação desta auditoria não abre esse gate.

## Addendum — fechamento da revisão financeira do reporter

REPORTER_REVIEW_STATUS=PASS_CONDITIONAL_REPORTING_ONLY
REPORTER_SHA256_LF=6c58eb32ceea8164b7d9f20d3831c300725dd4d849bff67611f6681af5e47bdf
REPORTER_TEST_SHA256_LF=00cf659aa145fb03b34e8bf9c447a0e69135cff06d0ec134bb268eca8400dd9c

Revisado o delta de `scripts/analyze_reserve_rotation.py` e
`tests/test_reserve_rotation_analysis.py`. O bloqueio anterior foi corrigido:
o ledger agora é lido sequencialmente até o primeiro seam/evento no cutoff,
sem materializar fills posteriores, e o summary global M017 é ignorado no
gate de prefixo. Fixtures com poison após o seam e summary global inválido
passam.24testes de reporter/recuperação, Ruff e diff-check passaram.

`build_model_comparison()` executado somente como análise read-only, sem
render/HTML/replay, com guarda de abertura que proíbe M017 daily>01,
summary global e terminal. M017 abriu somente daily01, checkpoint01,
manifest e ledger limitado pelo código ao cutoff. Os controles históricos
integrais permanecem em bloco separado; as três views comparáveis têm
exatamente1dia e13settlements. Nenhum valor posterior M017 entra na análise.

Asserts Decimal reconciliaram, para cada view:12ciclos positivos,
operacional100.10692, reserva9.99208, equity110.099, dívida0.01188,
excedente pré-perda0.00396 e fees explícitas0. Hold máximo coincide com a
tabela anterior; os três modelos têm1hold>2h, sem posição aberta censurada.
O status M017 é M017_OWNER_PAUSED_AFTER_SCOPE, nunca COMPLETE12D.
Configuração M017 foi validada contra spec/registry/run-manifest: funding10%,
cap20bps, inicial100+10 e piso2.5; não há atribuição de regra1h a esse run.

Este PASS libera somente a integridade do relatório derivado nos bindings
acima. Não aprova estratégia, publicação HTML cancelada, extensão ou novo run.
A autorização posterior para estudar hipóteses e a nova régua1000ciclos/dia
são tratadas pela autoridade corrente; não alteram os resultados nem a
configuração histórica deste primeiro dia M017.
