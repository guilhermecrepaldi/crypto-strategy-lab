# M027 — autópsia do controle micro-hot

## Resultado

M027 concluiu o A/B auditado sem aumento de frequência:

- CONTROL: 0 fills, 0 ciclos físicos e 0 ciclos-slot.
- TREATMENT: 0 fills, 0 ciclos físicos e 0 ciclos-slot.
- MICRO C1/C2: 0 fills e 0 ciclos.
- Delta físico: 0; percentual indefinido porque o controle também foi zero.
- Auditoria independente: PASS nos dois cenários.
- Status científico: `INCONCLUSIVE`; sem promoção.

## O que aconteceu

Os 30.552 trades canônicos permaneceram entre 1,00013 e 1,00015. A hotline
permaneceu em 1,00014 durante as três horas. As novas entradas MICRO estavam em
BUY 1,00009 e SELL 1,00019, portanto nenhuma foi alcançada pela fita. As quatro
ordens MICRO ficaram abertas até o cutoff sem execução parcial.

Todas as 60 ordens de cada cenário foram ativadas. Não houve cancelamento,
rejeição post-only, falta de capital, duplicação de capital ou reutilização de
liquidez. A ausência de alcance dos preços de entrada explica diretamente os
zero fills desta janela. A espera em FIFO público dominou a decomposição
descritiva de tempo-entidade, mas isso não demonstra que uma fila menor teria
produzido fill; por isso o limitador geral permanece não identificado.

## Respostas às perguntas do OWNER

1. A realocação aumentou a frequência? Não neste tape: 0 contra 0.
2. Criou ciclos adicionais ou canibalizou rank1? Nenhum dos dois foi observado;
   MICRO e rank1 produziram zero.
3. Quanto se perdeu retirando FAR14/FAR15? Zero produtividade realizada: essas
   posições do controle também produziram zero, apesar de cerca de 12
   horas-ordem agregadas.
4. C1 e C2 foram produtivas? Não; não receberam sequer fill parcial.
5. A resolução adicional foi mais eficiente? Não há evidência favorável: não
   houve toque exclusivo, execução ou ciclo adicional.

## Capital e limites

O capital inicial e final permaneceu 155,98394000 no CONTROL e 155,98674000 no
TREATMENT. A diferença de 0,0028 USDT-equivalent, ou 0,0017950566%, é
quantização inicial dentro do gate de 0,01%; não é lucro. PnL realizado e não
realizado foram zero.

Três horas sem fills não exercitaram retornos, canibalização, compounding nem
movimentos da hotline. O teste normalizado está abaixo do minNotional e não é
evidência de capacidade live. O PASS da auditoria valida a coerência física e
contábil do replay, não a eficácia da estratégia.

Nenhum rerun, outro dia, M028 ou extensão foi autorizado.
