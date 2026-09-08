# M016 — autópsia de entrada (somente leitura)

STATUS=COMPLETE_DERIVED_DIAGNOSTIC; nenhum replay, alteração de política ou novo
modelo. Ledger fechado, uma passagem sequencial com SHA256 e projeção seletiva.
Fonte executada:44d75f9183aa052be20734fac0f244bc4ba238bd.
Escopo: mesmos12 dias sintéticos encadeados, não continuidade histórica real.

## Achado principal

Os170975 BUY_ZERO_FILL não são todos rejeições:

| Estado terminal da BUY sem fill | Quantidade |
|---|---:|
| REJECTED, motivo explícito LIMIT_MAKER_WOULD_TAKE |170964|
| CANCELED |10|
| ACTIVE no fim, ainda sem fill |1|

Assim99,9935663% das BUYs sem fill foram rejeitadas por post-only na ativação.
Houve171002 BUYs submetidas,27 FILLED e37 ativações de BUY. Uma das dez canceladas
foi cancelada antes de ativar. O ledger inteiro contém170964 REJECTION, todas com
esse único motivo e todas vinculadas às BUYs acima. Não houve evidência de rejeição
por filtro, cobertura desconhecida ou throttle; o contador de rate-limit não
registrou veto. Ausência de fills não deve ser confundida com falta de capital.

A maior sequência contígua de rejeições manteve a mesma BUY1.00100 por43849
ordens (IDs32332–76180), intervalo entre primeira submissão e última ativação
nominal de14,366954326h. Outra manteve1.00120 por29747 ordens
(IDs2585–32331),9,747464086h. Uma terceira manteve1.00013 por27180 ordens,
8,905421300h. São sequências de ordens recusadas antes de ingressar na fila,
não43849 avaliações independentes de uma estratégia nem ciclos.

## Causa demonstrável e limites

No código executado, b10_reality.py:
- _advance, linhas315–322: BUY com limite>=ask observado é recusada como
  LIMIT_MAKER_WOULD_TAKE. É a regra post-only declarada, não fill perdido por fila.
- _submit_next, linhas862–869: enquanto flat, candidata existente gera BUY no
  LOW escolhido; não há ajuste passivo automático do preço.
- _clock, linhas815–826: a seleção periódica cancela BUY quando a candidata muda.
  A rejeição, por si, não muda a candidata.
- _next_clock inclui active_us+1. Após processamento, observed_l2_execution.py
  _after_capture volta a chamar _submit_next; o caminho de _clock também chama.
  A combinação permite reenviar o mesmo limite rejeitado até haver nova candidata
  ou mudança suficiente no mercado. Cada tentativa paga a latência simulada.

Essas funções pertencem à autoridade canônica. Os caminhos atuais podem conter
preparação M017; para reproduzir a interpretação usar git show do SHA acima,
não assumir que HEAD é a fonte do M016.

Os dez cancelamentos BUY efetivos foram solicitados em fronteiras exatas de minuto;
a próxima ordem tem preço diferente em todos os dez. Isso é consistente com troca
de candidata periódica, e não com timeout de posição. O ledger não persiste a
justificativa textual por cancelamento nem toda comparação de score do seletor:
não é possível atribuir retrospectivamente cada decisão a uma desigualdade
específica só por esses eventos. O resumo informa23 range_switches.

Conclusão: incompatibilidade causal entre LOW selecionado e admissão post-only,
com repetição de preço sem condição de nova evidência, é um gargalo comprovado.
A rejeição está de acordo com o contrato de execução. Não foi demonstrada
invalidação técnica do replay: transformar LOW, reprecificar ou alterar a reação
à rejeição mudaria uma hipótese e requer definição/revisão próprias. Nenhuma
dessas mudanças foi implementada ou proposta como M018 nesta autópsia.

## Tempo parado: não confundir contagem com duração

Reconstruindo primeira BUY preenchida e settlement de cada um dos27 lotes,
mais prefixo/sufixo flat, obtêm-se145,005973328611h, iguais ao resumo.
Maiores intervalos flat:32,3755624122h;25,4982694744h;21,1001588208h.

Dois diagnósticos de relógio, não uma decomposição causal exata:
- Soma das janelas submissão→ativação nominal de BUY intersectadas com flat:
  56,028092791667h. É tempo nominal mínimo de pedidos pendentes, não tempo
  adicional que desapareceria se fossem removidas as rejeições.
- Espera BUY da ativação nominal até primeiro fill/cancelamento/fim, somente
  ordens com ORDER_ACTIVE e intersectada com flat:88,94086405h. A ativação
  efetivamente avaliada dessas37 BUYs ocorreu1us depois da nominal em cada caso.
  Disponibilidade do book nos seams não foi deduzida desse número.

Não somar esses números para afirmar uma partição completa do idle: há tempos
sem ordem, ativação bloqueada, cancelamento/ack e fronteiras de eventos não
classificados aqui. Tampouco confundir ordem ACTIVE com execução garantida.
A BUY final171037 permaneceu ACTIVE, quantidade100, preço1.00070,
fila restante4961347, inventory0. Portanto “fim flat” não significa “sem ordens”.

O cap20 em estudo separado pode liberar uma posição antes; não resolve
automaticamente essas entradas. Métrica de custo de oportunidades perdidas,
melhor preço alternativo ou número de fills que uma reprecificação geraria é
UNKNOWN sem outro experimento pré-registrado. Os fills e custos atuais ficam
imutáveis.

## Proveniência

Diretório:artifacts/usdcusdt/l2-monthly-samples/M016/SYNTHETIC_CONSECUTIVE_12D/PRICE_PRIORITY

- execution-audit.jsonl:3353263655 bytes;
  SHA256 b22abb83aec4fb0988e390f89b6ac0dcc445e483762d272e41105b005cacc873.
- terminal-engine-state.json arquivo:
  09fc393462bf4cb97e9f15f7497ffa060b7202f23c17d339a4997160014a9185.
- Estado serializado canônico:
  51927d16e16c73c73b00cb234ba5ade81f6d57b30b4b4200cb9d7ae314116a35.
- summary.json:
  7bd14b12f153a226cf916a755732502a88d6f6f86c7fc8915a02731ed523d413.
- all-fill-audit.json:
  3375c63275ce6d4fe1c3b83eb467c150783ca448d12246a54b2566f9f62336e9.
- run-manifest.json:
  fe758bb8a65cc694b14672d859855fe20d52a602804eb0a05702c15b44ee7b92.

A passagem verificou o SHA do ledger contra a auditoria,27 settlements e78 FILL.
O hash do estado também foi recalculado. Não foi reexecutada a auditoria econômica
nem reconstruído o book. Valores monetários usam Decimal; timestamps, inteiros.

## Comando reproduzível (PowerShell, raiz do repositório)

O comando abaixo foi executado com sucesso; imprime contagens, intervalos,
exemplos e hashes, sem escrever no ledger ou em qualquer arquivo.

```powershell
@'
import hashlib, json, re
from pathlib import Path
from collections import Counter
from decimal import Decimal as D
from crypto_strategy_lab.microstructure.b10_reality import _decode
from crypto_strategy_lab.domain import canonical_hash
root=Path("artifacts/usdcusdt/l2-monthly-samples/M016/SYNTHETIC_CONSECUTIVE_12D/PRICE_PRIORITY")
terminal=json.loads((root/"terminal-engine-state.json").read_bytes())
assert canonical_hash(terminal["state"])==terminal["sha256"]
state=_decode(terminal["state"]); orders=state["orders"]
audit=json.loads((root/"all-fill-audit.json").read_bytes())
sha=hashlib.sha256(); kinds=Counter(); reasons=Counter(); rejected={}; active={}; fills={}; cancels={}; samples=[]
pattern=re.compile(rb'"kind":"([^"]+)"')
for raw in (root/"execution-audit.jsonl").open("rb"):
 sha.update(raw); kind=pattern.search(raw).group(1).decode(); kinds[kind]+=1
 if kind not in ("REJECTION","ORDER_ACTIVE","FILL","CANCEL_REQUEST"): continue
 row=json.loads(raw); oid=row.get("order_id")
 if kind=="REJECTION":
  reasons[row["reason"]]+=1
  if oid is not None: rejected[oid]=row["reason"]
  if len(samples)<3: samples.append(row)
 elif kind=="ORDER_ACTIVE": active[oid]=row["time_us"]
 elif kind=="FILL": fills.setdefault(oid,[]).append(row["time_us"])
 else: cancels[oid]=row
assert sha.hexdigest()==audit["journal"]["sha256"]
buys=[o for o in orders if o.side=="BUY"]
classification=Counter((o.status,rejected.get(o.order_id,"NO_REJECTION_EVENT"),str(o.filled)) for o in buys)
start=1735689600000000; end=start+12*86400000000
entries=sorted(min(v) for oid,v in fills.items() if orders[oid-1].side=="BUY")
settlements=state["settlements"]; assert len(entries)==len(settlements)==27
flats=[]; last=start
for entry,settle in zip(entries,settlements):
 flats.append((last,entry)); last=settle["time_us"]
flats.append((last,end))
flat_us=sum(b-a for a,b in flats)
def intersection(a,b):
 return sum(max(0,min(b,y)-max(a,x)) for x,y in flats)
pending_lower=sum(intersection(o.submitted_us,o.active_us) for o in buys)
active_wait=sum(intersection(active[o.order_id], min(fills[o.order_id]) if o.order_id in fills else o.cancel_us if o.cancel_us is not None else end) for o in buys if o.order_id in active)
bursts=[]; current=[]
for o in orders:
 if o.side=="BUY" and rejected.get(o.order_id)=="LIMIT_MAKER_WOULD_TAKE":
  if current and current[-1].price!=o.price: bursts.append(current); current=[]
  current.append(o)
 else:
  if current: bursts.append(current); current=[]
if current: bursts.append(current)
longest=sorted(bursts,key=len,reverse=True)[:8]
out={
"ledger_sha256":sha.hexdigest(),"terminal_state_sha256":terminal["sha256"],
"kind_counts":dict(kinds),"rejection_reasons":dict(reasons),
"buy_status_counts":dict(Counter(o.status for o in buys)),
"zero_buy_status_counts":dict(Counter(o.status for o in buys if o.filled==0)),
"zero_buy_reasons":dict(Counter(rejected.get(o.order_id,"NO_REJECTION_EVENT") for o in buys if o.filled==0)),
"buy_order_count":len(buys),"buy_activations":sum(o.order_id in active for o in buys),
"flat_hours":str(D(flat_us)/D(3600000000)),
"flat_pending_nominal_lower_hours":str(D(pending_lower)/D(3600000000)),
"flat_active_wait_from_nominal_activation_hours":str(D(active_wait)/D(3600000000)),
"cancel_side_status_counts":dict(Counter(orders[oid-1].side+":"+orders[oid-1].status for oid in cancels)),
"longest_rejection_bursts":[{"count":len(b),"price":str(b[0].price),"first_id":b[0].order_id,"last_id":b[-1].order_id,"first_submit":b[0].submitted_us,"last_nominal_active":b[-1].active_us,"span_hours":str(D(b[-1].active_us-b[0].submitted_us)/D(3600000000))} for b in longest],
"longest_flat_intervals":[{"start":a,"end":b,"hours":str(D(b-a)/D(3600000000))} for a,b in sorted(flats,key=lambda p:p[1]-p[0],reverse=True)[:6]],
"rejection_samples":samples,
"zero_canceled_buys":[{"id":o.order_id,"price":str(o.price),"submitted":o.submitted_us,"active":active.get(o.order_id),"canceled":o.cancel_us,"queue_remaining":str(o.queue)} for o in buys if o.filled==0 and o.status=="CANCELED"]
}
print(json.dumps(out,indent=2))
'@ | .venv/Scripts/python.exe -
```
