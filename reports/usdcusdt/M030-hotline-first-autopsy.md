# M030 — hotline-first capital reallocation — autopsy

## Owner scoreboard

```text
MODEL=M030
PERIOD=24H_CONTINUOUS; RANDOM_3H_PRIMARY=06–07,12–13,13–14 UTC

M029_MATCHED_RANDOM_3H_PHYSICAL_CYCLES=6
M030_RANDOM_3H_PHYSICAL_CYCLES=13
PHYSICAL_CYCLE_GAIN=+7 (+116.6666666667%)
FREQUENCY_IMPROVEMENT_PASS=true
STRONG_IMPROVEMENT_20PCT_PASS=true

M030_FULL_DAY_PHYSICAL_CYCLES=170
M030_FULL_DAY_SLOT_CYCLES=509

INITIAL_USDT=78.10400000
INITIAL_USDC=78
INITIAL_MARKED_EQUITY=156.25220000

FINAL_USDT=51.1088000000000000
FINAL_USDC=105.00000000
FINAL_USDC_MARKED_VALUE=105.2100000000000000
FINAL_MARKED_EQUITY=156.3188000000000000
MARKED_GAIN=0.0666000000000000 (+0.0426233999%)

REALIZED_CYCLE_PNL=0.0642000000000000
REALIZED_DISPOSAL_PNL=0.0810014422000000
UNREALIZED_PNL=-0.0144014422000000

AUDIT=PASS_M030_HOTLINE_FIRST_LEDGER_TERMINAL_AND_MASK_AUDIT
VERDICT=INCONCLUSIVE
```

## O que melhorou

Nas três horas sorteadas antes do replay, o M030 fechou 13 ciclos físicos, contra
6 do M029 no mesmo recorte. A taxa passou de 2 para 4,3333 ciclos/h. Os 13 ciclos
vieram da região HOT: 3 BUY-first e 10 SELL-first. As colunas 1/2/3 contribuíram
4/5/4 ciclos, sem concentração exclusiva em uma coluna.

A cobertura HOT ponderada no recorte passou de 67,4125% para 94,2835%, ganho de
26,8711 pontos percentuais e aprovação do gate de cobertura. O manager reclamou
264 ordens zero-fill somente após cancel ACK; não houve cancelamento forçado de
ordem preenchida, saída negativa, reescrita de cost basis ou roubo de capital de
return.

No dia inteiro, o M030 fechou 170 ciclos físicos contra 98 do M029. Esse número é
diagnóstico secundário; não substitui o comparativo primário aleatório.

## Onde não passou

O capital literalmente preso em ordens zero-fill reclamáveis enquanto HOT estava
incompleto caiu de 100% do recorte no M029 para 59,2785% no M030. A redução de
40,7215% ficou abaixo do gate pré-registrado de 50%. Portanto o gate de management
completo falhou, mesmo com a melhora de cobertura e frequência.

O contador bruto inicialmente rotulado como `RECLAIMABLE_CAPITAL_STRANDED` media
uma condição mais ampla: HOT incompleto com qualquer capacidade administrativa
identificada, incluindo capital livre/mobility. Ele marcou 69,0909% nas três horas.
A recuperação de relatório preserva esse valor bruto com nome explícito e usa, no
placar oficial de stranded, a reconstrução literal independente do ledger. Nenhum
evento de mercado foi reexecutado e nenhuma decisão econômica mudou.

No dia, HOT esteve subfinanciado em 73,5410% do tempo; falta verdadeira de capital
existiu em 20,3982%. O estado descritivo dominante por entity-time continuou sendo
`PUBLIC_FIFO_WAIT` (54,8130%), seguido de `CAPITAL_FUNDING_BLOCK` (27,7260%). Isso
indica que a realocação resolveu as promoções administrativas registradas pelo M029,
mas não removeu a combinação de fila pública e disponibilidade física de ativo.

## Interpretação

M030 demonstrou uma melhora material de frequência e de presença da região HOT no
dia de desenvolvimento sorteado. Ainda não demonstrou que a política de gestão está
estruturada: falhou um dos dois gates pré-registrados e permaneceu muito distante da
meta de 1.000 ciclos/dia.

O resultado continua normalizado abaixo do `minNotional`, com fee condicional zero,
book/trades exógenos, posição L3 real e impacto endógeno desconhecidos. Não é um
resultado executável em live e não autoriza M031, rerun ou outro dia.

## Proveniência

- Fonte publicada do run: `459d0237ae9005fd272a91e00de744c21da71435`.
- Run hash físico: `83483b9bfaaeae68f49c23504650a93f7e5701017a7c37a05d416d6095d376ee`.
- Ledger físico: `afc84dea354415eb1bde0b315258cc250d9edeaeef71913ce1b86b63737e3b66`.
- A falha original `M030_AUDIT_RANDOM_STRANDED` permanece preservada; tratava-se de
  inconsistência semântica no relatório pós-run, não de divergência econômica.
