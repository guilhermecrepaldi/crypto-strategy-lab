# M033 L3 → L2 ablation protocol

Use one immutable Kraken L3 capture and its matching trades. Do not compare
different periods.

1. Validate raw hash, normalized hash, symbol, time bounds, checksums/gaps and
   reconnects. Any unresolved gap invalidates the interval.
2. Replay native L3 individual orders in published arrival order. Same-time
   priority ambiguity is conservative against our order.
3. Deterministically aggregate the same L3 state into price-level quantities.
4. Replay that aggregate through the unchanged conservative M032 L2 queue model.
5. Keep policy, capital, geometry, rules, fees and latency fixed.

Per candidate order compare public order count/quantity ahead, fill/no-fill,
first/full-fill time, slot turnover, cycles/hour and P95 capital lock. Report L3
and L2 independently. The ablation quantifies observable representation error;
L3 remains incomplete about hidden iceberg quantity and exchange internals.

No economic ablation is authorized until an immutable non-gapped L3 interval is
available and the OWNER authorizes its frozen evaluation window.
