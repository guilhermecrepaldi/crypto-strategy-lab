# M016 — first day-2 deadline: read-only prefix autopsy

STATUS=PARTIAL_DIAGNOSTIC_NOT_NEW_REPLAY
EXECUTION_SOURCE=44d75f9183aa052be20734fac0f244bc4ba238bd
MODEL=M016; ENVELOPE=PRICE_PRIORITY; LOGICAL_DAY=2; SOURCE_DAY=2025-02-01

## Finding

The first day-2 deadline was blocked by the **10bps loss cap**, not the reserve
floor or available observed depth. At the deadline's available book prefix,
selling the actual99 USDC inventory would have yielded99.0198 USDT before fees,
against cost99.1881: loss0.1683 USDT, or16.8120245833155bps of restored operating
bank100.10692. The configured cap was0.10010692; reserve above the floor was7.49208.

The best bid was1.0002 with19,013,235 USDC displayed. Reconciliation of the carried
day-1 consumption budget, seam clamp and day-2 native deltas left13,707,359 USDC
available there. All99 units fit at that one price; no deeper level or synthetic
liquidity was necessary for this **conditional depth-cost calculation**.

This was not an executed release. It does not prove that an order submitted under
a different budget would fill exactly at the deadline: cancellation, activation,
the next captured event, unknown venue conditions and the unchanged fee-zero
assumption remain relevant. The book was10.502ms old at the deadline. No orders,
fills, selection decisions, treasury transfers or economic replay were generated
by this diagnostic; runtime sources and the running campaign were untouched.

A20bps budget would cover this particular prefix cost. This does **not** select
the next configuration, prove its optimality or cover other deadlines. Wait for
the full M016 trajectory and other episodes before preregistering a second case.
Changing funding or initial reserve does not remove this episode's loss-cap veto.

## Exact event provenance

| Field | Value |
|---|---|
| First partial BUY / entry, logical us |1735776010349574|
| Deadline, logical us |1735783210349574|
| Deadline, source us |1738375210349574|
| Deadline, source UTC |2025-02-01T02:00:10.349574Z|
| Preparation signal, logical us |1735783206810997|
| First protected block, logical us |1735783207990523|
| Violation record, logical us |1735783210349575|
| Available book capture, source us |1738375210339072|
| Available book capture, logical us |1735783210339072|
| Available book exchange upper bound, source us |1738375210337999|
| Native update ID |1255530829|
| Native physical capture ordinal within source day |71884|
| Reconciled valid BOOK batches through cutoff |48908|

Actual BUY fills, all at1.00190, order2578, zero base commission:

| Native trade ID |Quantity USDC|Logical fill us|
|---|---:|---:|
|222252977|5|1735776010349574|
|222252978|28|1735776010470022|
|222252979|5|1735776010696549|
|222252980|5|1735776011986737|
|222252981|56|1735776012073849|

The checked audit prefix contains no IOC consumption between the day-2 seam and
this deadline. Consequently, its intraday budget reconciliation needs native
quantity changes and the carried checkpoint, not hypothetical additional fills.

## Immutable bindings

- Source manifest: `data/manifests/usdcusdt-tardis-free-l2.json`, SHA256
  `1c564f88935a7c694d2f15cd4c9a8710013a19095f4eaece32529b22e7ba7fa2`.
- Artifact base: `artifacts/usdcusdt/l2-monthly-samples/M016/SYNTHETIC_CONSECUTIVE_12D/PRICE_PRIORITY`.
- `daily/01-engine-state.json` file SHA256:
  `8aa89e414001caacd088faf447a099bd364c9935392a807290e476746ac56369`.
- Embedded day-1 state SHA256:
  `aee083f6a216e4c02190df2a2e171bb688d432d728f64009b451cdd97cf93de0`.
- `execution-audit.jsonl` **prefix only**: first998960 lines /241230461 bytes,
  ending at this entry's DEADLINE_VIOLATION. Prefix SHA256:
  `3ff3485937fd719976fac5217f848bccf2e00d9aa3b0c27fb5f44994b114be02`.
  Later appended bytes are outside this diagnostic and do not change that binding.

Raw originals are under `data/l2/tardis/binance/usdcusdt/2025-02-01/raw/`.
Only offsets0–120 minutes were read; the final slice stops at the cutoff event.
The bound manifest specifies their exact file sizes and paths.

| Offset minutes |SHA256 of gzip original|
|---:|---|
|0|0564f856572ab720116ee10b161ac6993587880c6afc394e305dfd8e48a1fca1|
|10|7b11a4aa957eaa8f2ae6b3e0d21fdd10307db41595945782ec1534162b03ecfe|
|20|50330213b4e7a25456e8b998a9be372cedf94271b81927d05248d0e3f4ac7d86|
|30|37a17ae030e12ea4bdbf0121ae94d483f89483eb4898de9194911a8f1f7fb208|
|40|e2de40ebd94f473ac584a7109cb9eb77c914f8c3c66074006082fd0a88ef9f1a|
|50|5fa070da1b22ea7f995e81b0c6d636824416db43012abc2076bfe0fb4e5c4df4|
|60|b4969abae7b01481b59229adf7841ab2feeabaf303e4364231f57f4ffc924de5|
|70|c62f7b7094f612fe9181b8f4f4d18ab384b80d57d7f8df7ccf275d135275434e|
|80|64032202ccdb77729220a64f5bb6ce793aa8114979ade4103108e5f3982d0d18|
|90|2a47848e187e19953dfdc3087cf448ceddd6abbf129e071eb0f0ef75b8325c37|
|100|c5eccff525f73989c1b8b1bad67cafe18db2b39c4b696df267837113b6b552b2|
|110|d570396369edc943f0b9b22b92cb514d01a484906807ad93750fdbbd732ab908|
|120|e8e5f516b93613b932b7ac97dd7416b207d1601d2ea75c2a95d8923581c32218|

## Reproduction — data/budget calculation only

Run from repository root with the bound execution-source modules. The following
PowerShell command writes no files and invokes no replay or execution engine.
Native sequence/book interpretation is reused from `iter_native_events`; the
small derived map tracks only available hypothetical IOC quantity using the
already-frozen budget recurrence. It does not implement another native book parser.

```powershell
$reviewCode = @'
import json, hashlib
from pathlib import Path
from decimal import Decimal as D, localcontext
from crypto_strategy_lab.microstructure.tardis_l2 import iter_native_events
from crypto_strategy_lab.microstructure.b10_reality import _decode
from scripts.validate_tardis_l2_samples import raw_lines, ROOT, MANIFEST
from scripts.run_l2_monthly_samples import stitched_mapping

base = ROOT / 'artifacts/usdcusdt/l2-monthly-samples/M016/SYNTHETIC_CONSECUTIVE_12D/PRICE_PRIORITY'
manifest_bytes = (ROOT / MANIFEST).read_bytes()
assert hashlib.sha256(manifest_bytes).hexdigest() == '1c564f88935a7c694d2f15cd4c9a8710013a19095f4eaece32529b22e7ba7fa2'
checkpoint = (base / 'daily/01-engine-state.json').read_bytes()
assert hashlib.sha256(checkpoint).hexdigest() == '8aa89e414001caacd088faf447a099bd364c9935392a807290e476746ac56369'
with (base / 'execution-audit.jsonl').open('rb') as stream:
    assert hashlib.sha256(stream.read(241230461)).hexdigest() == '3ff3485937fd719976fac5217f848bccf2e00d9aa3b0c27fb5f44994b114be02'
mapping = stitched_mapping()[1]
offset = mapping['logical_start_us'] - mapping['source_start_us']
cutoff = 1735783210349574 - offset
item = next(x for x in json.loads(manifest_bytes)['dates'] if x['date'] == '2025-02-01')
slices = [x for x in item['raw_slices'] if x['offset'] <= 120]
for source in slices:
    data = (ROOT / source['local_path']).read_bytes()
    assert len(data) == source['bytes'] and hashlib.sha256(data).hexdigest() == source['sha256']
state = _decode(json.loads(checkpoint)['state'])
displayed, available = dict(state['displayed_bids']), dict(state['bids'])
seen = {D(price) for price in state['bid_consumption_debt']}
first, last, batches = True, None, 0
with localcontext() as context:
    context.prec = 128
    for event in iter_native_events(raw_lines(ROOT, '2025-02-01', slices)):
        if event['local_us'] > cutoff: break
        if event['kind'] != 'BOOK' or not event['sequence_validated']: continue
        batches += 1
        if first:
            now = dict(event['bids'])
            available = {p: min(q, available.get(p,D(0))) if p in seen else q for p,q in now.items()}
            displayed, first = now, False
        else:
            assert not event['is_snapshot'], 'Reconcile any additional snapshot explicitly'
            for side, price, quantity in event['changes']:
                if side != 'bid': continue
                available[price] = max(D(0), min(quantity, available.get(price,D(0)) + quantity - displayed.get(price,D(0))))
                displayed[price] = quantity
        last = event
    assert last['exchange_upper_us'] <= cutoff
    remainder, proceeds, levels = D(99), D(0), []
    for price, quantity in last['bids']:
        budget = available.get(price,D(0))
        take = min(remainder,budget)
        if take:
            proceeds += price*take
            remainder -= take
            levels.append((str(price),str(quantity),str(budget),str(take)))
        if not remainder: break
    loss = D('99.1881') - proceeds
    print(json.dumps({'native_update_id':last['native_update_id'], 'capture_ordinal':last['capture_order'],
        'capture_source_us':last['local_us'], 'age_us':cutoff-last['local_us'], 'batches':batches,
        'levels_price_displayed_available_take':levels, 'unfilled':str(remainder),
        'proceeds_zero_fee':str(proceeds), 'loss_zero_fee':str(loss),
        'loss_bps':str(loss/D('100.10692')*10000)}))
'@
.venv/Scripts/python.exe -c $reviewCode
```

Arithmetic inputs99USDC, cost99.1881 and bank100.10692 derive from the five BUY
fills and closed day-1 checkpoint listed above, not a new sizing decision.

## ADDENDUM — todos os oito excessos no M016 concluído

ADDENDUM_STATUS=COMPLETE_READONLY_DIAGNOSTIC. A seção de D2 acima permanece
inalterada como evidência publicada do prefixo; seu antigo status PARTIAL
não descreve a situação final. Este complemento usa somente o ledger fechado
e o estado terminal. Nenhum novo replay, reconstrução integral de L2, ajuste
de política ou hipótese M018 foi executado.

### Resultado: sete atrasos curtos e um bloqueio financeiro prolongado

| Lote / BUY | Dia de entrada | Excesso sobre2h (s) | Sinal→fechamento (s) | Perda/consumo USDT | H1 anterior |
|---|---:|---:|---:|---:|---|
|5 / 164|1|0.047867|3.586444|0.0198000000000000|SAME_CANDIDATE|
|14 / 2578|2|424792.190715|424795.729292|0.0792000000000000|LOSS_CAP|
|15 / 2582|7|0.078352|3.616929|0.0198000000000000|NONPOSITIVE_DEFICIT|
|16 / 91188|8|0.154896|3.693473|0.1000000000000000|SAME_CANDIDATE|
|17 / 117252|9|0.335338|3.873915|0|NONPOSITIVE_DEFICIT|
|19 / 117258|10|0.056144|3.594721|0.0100000000000000|NONPOSITIVE_DEFICIT|
|21 / 120008|11|1.113711|4.652288|0.0010000000000000|SAME_CANDIDATE|
|23 / 126954|11|0.096399|3.634976|0.0030000000000000|NONPOSITIVE_DEFICIT|

Lote é o índice1–27 de settlement, não o número de ciclo ordinário. Todos os oito
foram releases; sete tiveram perda e um fechou a zero. Todos são violações reais
da regra estrita de2h, inclusive os atrasos subsegundo. Nenhum grace foi aplicado.

Nos sete casos curtos, a ordem IOC estava programada para ativar em deadline−1us.
Cancelamento, resposta e submissão completaram sua sequência antes do limite.
O fill aconteceu numa observação posterior: atraso de47,867ms a1,113711s além
do deadline. Cada lote teve um único IOC, integralmente preenchido na primeira
RELEASE_BOOK_EVALUATION registrada, sem PROTECTED_EXIT_BLOCKED no lote.
Não houve veto financeiro ou falta de orçamento documentada nesses sete casos.

Classificação suportada: atraso de avaliação/observação após a ativação programada.
Não chamar todos de “milissegundos”: um ultrapassou1s. A fonte exige observação
estritamente posterior à ativação e não inventa um book/evento no relógio exato.
Esta projeção seletiva não mede o intervalo de todas as capturas nem separa
ausência de evento de cada possível inelegibilidade microtemporal. Não afirma
que antecipar a ordem produziria o mesmo preço/fill, nem que aumentar cap elimina
essas sete violações. O preço observado na execução não substitui cotação
desconhecida no instante exato do deadline.

### Identificadores e relógios exatos

Todos os timestamps abaixo são microssegundos do relógio lógico sintético.
O manifesto mapeia cada dia para sua data original, preservada nos eventos;
não apresentar os dias comprimidos como datas históricas contíguas.

| Lote | First BUY | Deadline | Fechamento | IOC release |
|---|---:|---:|---:|---:|
|5|1735720136091500|1735727336091500|1735727336139367|166|
|14|1735776010349574|1735783210349574|1736208002540289|2580|
|15|1736253909061248|1736261109061248|1736261109139600|2584|
|16|1736377661164284|1736384861164284|1736384861319180|91190|
|17|1736441317104188|1736448517104188|1736448517439526|117254|
|19|1736543163183119|1736550363183119|1736550363239263|117260|
|21|1736568094025599|1736575294025599|1736575295139310|120010|
|23|1736588800841439|1736596000841439|1736596000937838|126956|

O sinal de cada lote ocorreu deadline−3538577us. Nos sete curtos:
cancelamento efetivo=sinal+1179525us; ack=sinal+2359050us;
submissão=sinal+2359051us; ativação nominal=deadline−1us.
DEADLINE_VIOLATION foi registrado em deadline+1us nos oito lotes.
O atraso de fill após ativação nominal é, portanto, excesso+1us nos sete curtos.

### Lote14/D2: cap, seams e desbloqueio

O único lote longo permaneceu119,997830754167h desde a primeira BUY, excedendo2h
em424792,190715s. Os onze PROTECTED_EXIT_BLOCKED de toda a campanha pertencem
a ele: seis registros LOSS_CAP intercalados com cinco NO_LIQUIDITY.

| Transição | Relógio lógico us |
|---|---:|
| Primeiro LOSS_CAP |1735783207990523|
| Seam, NO_LIQUIDITY |1735862400000000|
| Retorno a LOSS_CAP |1735862413216064|
| Seam, NO_LIQUIDITY |1735948800000000|
| Retorno a LOSS_CAP |1735948801302055|
| Seam, NO_LIQUIDITY |1736035200000000|
| Retorno a LOSS_CAP |1736035202302083|
| Seam, NO_LIQUIDITY |1736121600000000|
| Retorno a LOSS_CAP |1736121600784423|
| Seam, NO_LIQUIDITY |1736208000000000|
| Retorno a LOSS_CAP |1736208001122713|
| PROTECTED_EXIT_UNBLOCKED e submissãoIOC |1736208001340105|
| Ativação nominalIOC |1736208002519630|
| Fill/settlement |1736208002540289|

NO_LIQUIDITY aqui coincide exatamente com a indisponibilidade inicial de book
nas cinco emendas. Não prova esgotamento real de todo o mercado. Depois do último
retorno do book houve ainda veto de cap; só em seguida ocorreu desbloqueio.
A ordem finalmente admitida levou1,200184s da submissão ao fechamento, sendo
20,659ms após ativação nominal. A perda final0,0792 foi menor que o custo0,1683
reconstruído no deadline D2 porque preço e momento mudaram. Não são estimativas
concorrentes do mesmo fill.

Em todos os seis registros financeiros: restored_bank100,10692,
loss_cap_budget0,10010692, reserve_budget7,49208, protected_price1,0009 e
binding_constraint=LOSS_CAP. O orçamento não aumentou para tornar a saída
possível. O desbloqueio ocorreu com nova evidência; o fill consumiu99USDC a1,0011,
quantidade disponível antes119366 e native_update_id2005937555. O saldo de
reserva cobriu exatamente0,0792, sem tocar o piso2,5.

Os eventos BLOCKED são transições de motivo, não cada avaliação de preço.
O contador terminal677344 avaliações bloqueadas pelo preço/cap não significa
677344 ordens, nem677344 quotes preservadas. Não é possível reconstruir a curva
completa de custo necessário a partir desses onze registros.

### Orçamentos, H1 e o que continua desconhecido

A regra executável10bps permaneceu fixa. Os valores abaixo são cálculo da política
sobre o lot_budget/restored bank dos lotes sem venda parcial anterior, não
novos registros de preço ou custo no deadline:

| Lote(s) | Cap10bps calculado USDT |
|---|---:|
|5|0,10003564|
|14,15,16,17|0,10010692|
|19|0,10011592|
|21|0,10011682|
|23|0,10011772|

São pequenos degraus por compounding, não relaxamentos. Somente no lote14 esses
campos de orçamento foram também persistidos como veto explícito. Não houve
binding_constraint=RESERVE_FLOOR em nenhum dos oito episódios. Isso não prova
que reserva/piso jamais limitariam outra trajetória.

Em cada lote houve uma avaliação H1 anterior ao preparo:3 SAME_CANDIDATE,
4 NONPOSITIVE_DEFICIT e1 LOSS_CAP. Os rótulos são os motivos reais do predicate,
não garantias de rentabilidade de uma alternativa. Depois do sinal de deadline
o latch substituiu o veto por oportunidade e preservou cap/floor; o relógio não
conseguiu sobrepor-se à incompatibilidade financeira de D2.

Apenas D2 possui nesta autópsia custo executável reconstruído no prefixo exato
do deadline, com consumo anterior de profundidade reconciliado. Nos outros sete,
conhecemos custo/perda do fill posterior e os eventos do lifecycle; o custo
exato no deadline permanece UNKNOWN. Não há base para estimar “cap necessário”
dos oito com seus preços finais nem para prometer sucesso de20bps.

### Proveniência e reprodução

Mesmo source publicado44d75f9183aa052be20734fac0f244bc4ba238bd.
Ledger fechado3353263655bytes, SHA256
b22abb83aec4fb0988e390f89b6ac0dcc445e483762d272e41105b005cacc873;
estado canônico SHA25651927d16e16c73c73b00cb234ba5ade81f6d57b30b4b4200cb9d7ae314116a35.
O comando abaixo foi executado uma vez, fez uma passagem sequencial com hash,
projetou eventos relevantes e correlacionou27 settlements/primeiras BUYs.
Não escreveu arquivos e não executou o motor. Os eventos anteriores à entrada
incluídos na janela entre settlements são contexto flat, não causas do deadline.

```powershell
@'
import hashlib,json,re
from pathlib import Path
from decimal import Decimal as D
from crypto_strategy_lab.microstructure.b10_reality import _decode
from crypto_strategy_lab.domain import canonical_hash
p=Path("artifacts/usdcusdt/l2-monthly-samples/M016/SYNTHETIC_CONSECUTIVE_12D/PRICE_PRIORITY")
t=json.loads((p/"terminal-engine-state.json").read_bytes())
assert canonical_hash(t["state"])==t["sha256"]
s=_decode(t["state"]); settlements=s["settlements"]
wanted={"FILL","DEADLINE_EXIT_SIGNAL","DEADLINE_VIOLATION","PROTECTED_EXIT_BLOCKED","PROTECTED_EXIT_UNBLOCKED","RELEASE_PREDICATE_EVALUATION","RELEASE_BOOK_EVALUATION","CANCEL_REQUEST","CANCELED","CANCEL_ACK_SCHEDULED","OBSERVED_DEPTH_CONSUMPTION"}
rows=[]; sha=hashlib.sha256(); pat=re.compile(rb'"kind":"([^"]+)"')
for raw in (p/"execution-audit.jsonl").open("rb"):
 sha.update(raw)
 if pat.search(raw).group(1).decode() in wanted: rows.append(json.loads(raw))
assert sha.hexdigest()==json.loads((p/"all-fill-audit.json").read_bytes())["journal"]["sha256"]
lots=[]; previous=1735689600000000
for index,settle in enumerate(settlements,1):
 closure=settle["time_us"]
 buys=[r for r in rows if r["kind"]=="FILL" and r["side"]=="BUY" and previous<r["time_us"]<=closure]
 entry=min(r["time_us"] for r in buys); deadline=entry+7200000000
 if closure>deadline:
  events=[r for r in rows if previous<r.get("time_us",0)<=closure and r["kind"]!="FILL"]
  oid=buys[0]["order_id"]
  release_orders=[{"id":o.order_id,"submitted":o.submitted_us,"active":o.active_us,"price":str(o.price),"status":o.status} for o in s["orders"] if o.release and entry<=o.submitted_us<=closure]
  lots.append({"lot":index,"buy_order":oid,"entry":entry,"deadline":deadline,"closure":closure,
  "hold_hours":str(D(closure-entry)/D(3600000000)),"excess_seconds":str(D(closure-deadline)/D(1000000)),
  "settlement":settle,"release_orders":release_orders,"events":events})
 previous=closure
print(json.dumps({"ledger_sha256":sha.hexdigest(),"lots":lots},indent=2,default=str))
'@ | .venv/Scripts/python.exe -
```
