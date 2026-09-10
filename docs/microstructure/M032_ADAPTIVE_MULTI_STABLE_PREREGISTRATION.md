# M032 preregistration — blocked draft

Status: `BLOCKED_PRE_REPLAY_DATA`. This file freezes implemented mechanics but is
not an executable campaign preregistration and does not register M032.

Draft model-spec hash:
`fb35f67e414cce9cb03b0e83824304f9b4286617b679785663e941fca6e11215`.

Reusable architecture source:
`25273367e6d2146a71d0308a423415320e3da8c0`, independently reviewed `PASS`.
This does not close the evidence or integrated-runner gates below.

## Frozen architecture

- maximum initial equity: 200 USD-equivalent;
- at most four selected stablecoins;
- per book/side: HOT ranks 1–3, MID 4–5, FAR 6–7;
- zero, C1 or C1+C2 per rank; one physical SLOT_BASE per column;
- C1 persistent FIFO-value column; C2 opportunity column;
- priority class before deterministic decomposed marginal score;
- one public queue per side+price, followed by own C1 then C2;
- unique global reservation ownership and cancel-ACK release;
- 2–4 asset routes close only on physical fills back to origin;
- no negative realized exit, future data, self-fill, cutoff liquidation or sweep.

Primary future KPIs are net realized PnL per capital-hour, slot-equivalent cycles
per hour and P95 slot turnover. Physical cycles, marked return, fees, utilization,
C1/C2, pair/band/route and blocker metrics remain mandatory and separate.

## Unfrozen because evidence is absent

`STABLECOIN_UNIVERSE=[]`, `BOOKS=[]`, `SLOT_BASE=UNRESOLVED`,
`INITIAL_BANKROLL=UNRESOLVED<=200`, `FEE_PROFILES=[]`,
`ELIGIBLE_DATE_POOL=[]`, `SCORING_WINDOWS=[]`.

No CSPRNG draw is allowed before the common physical data pool exists. M032 may
enter the registry only after these fields, source hashes, model hash and an
independent PASS review are frozen and published. Until then:

`READY_FOR_REPLAY=false`.
