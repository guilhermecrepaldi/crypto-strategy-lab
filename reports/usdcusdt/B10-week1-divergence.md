# Primeira semana: onde ocorreu a divergência

Escopo:1–7janeiro2026 UTC. Reconciliação de evidências existentes, antes de M014.

| Dia | B10 F2.5 price-path, ciclos completos | M013 afetado pelo bug |
|---|---:|---:|
| 01/01 | 5.957 | 1 |
| 02/01 | 1.730 | 0 |
| 03/01 | 18.011 | 0 |
| 04/01 | 26.443 | 0 |
| 05/01 | 17.038 | 0 |
| 06/01 | 11.854 | 0 |
| 07/01 | 7.751 | 0 |
| Total | 88.784 | 1 |

Não são resultados comparáveis de execução: B10 é price-path100+5/skim2%, enquanto
M013 é outra estratégia100+10/skim10%, execução condicional e bug técnico confirmado.
Nem o B10 teórico atingiu2.000 em TODOS os dias desta semana (02/01=1.730).
Não inferir frequência diária pela média mensal nem chamar todos os ciclos de
price-path de fills reais. Não inferir PnL executável dos saldos exponenciais.

M013 fecha sem perda financeira realizada: banca100→100.00891, reserva10→10.00099,
equity110→110.0099. Releases0, consumo0, funding0.00099,6dias sem ciclo. Sua
reserva não se esgotou nem bloqueou um release executado; o dinheiro ficou ocioso.
9948 cancelamentos e470070 rejeições no prefixo; TODAS as rejeições observadas têm
motivo LIMIT_MAKER_WOULD_TAKE. Rejeições não são470070 oportunidades independentes.
O padrão cancel→ACK→mesma BUY foi observado; uma regressão sintética reproduziu
o reenvio inelegível e a correção foi publicada antes desta investigação.

Outra divergência: B10 avalia recovery H1 com condições originais de destino;
M013 trocou seleção/alocação e passa a considerar recuperação às6h. Reserva maior
não remove esse atraso e não obriga três faixas disjuntas elegíveis a existirem.
A primeira semana não permite atribuir quantitativamente a queda inteira a cada
componente sem controles. Tampouco demonstra que a reserva foi prejudicial.

Fontes:

- B10: artifacts/usdcusdt/recovery-reserve/097abdab8225038b091cb721bdd36bedb8a636c94bed1c87120adc0c9e10953a/RRV2_H1_B10_F2.5/replay.json.gz;
  streaming dos ciclos encerrados antes de08/01,257555056bytes comprimidos no arquivo.
  Saldos de fechamento por dia não vieram desse extrato; não foram inventados.
- M013: artifacts/usdcusdt/models/M013/reality-primary/capital-checkpoints/DAY_7.json;
  auditprefix203962935bytes SHA2564e8d8510a0d6065451392a8ef862f1a2c2c9484f271809d2f507fba86bd9a08c.
- Preservação/invalidação: M013-technical-stop.json e registry canônico.

Coleta mecânica: GPT-5.6 Luna. Interpretação/desenho: GPT-6 Astra.
Nenhuma conclusão prospectiva ou comprovação de2.000 fills líquidos/dia.
