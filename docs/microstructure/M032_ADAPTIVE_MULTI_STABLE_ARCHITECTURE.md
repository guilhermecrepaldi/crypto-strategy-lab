# M032 architecture

## Decision flow

Each causal book update advances one local hotline, the shared queue estimator and
the global ledger. Safety gates first determine whether a new entry is eligible.
The route enumerator then constructs only physically available 2–4 asset cycles.
For every candidate cell or route, the scorer publishes its decomposition:
expected net PnL, completion probability, capital, expected lock, safety,
inventory-risk penalty and lost FIFO value. Priority class is separate from score,
so an economic obligation cannot be displaced by a superficially attractive
entry.

The allocator funds only what the global ledger can reserve. Reclaiming a
zero-fill entry creates a cancel request; the asset becomes free only on causal
ACK. Partial and filled orders remain owned obligations. Each fill moves a real
asset quantity and fee exactly once. A route is a realized cycle only after all
legs close in its origin asset with non-negative realized PnL.

## Reused authorities

- M030 supplies hotline-first priority, direct final-target jumps and ACK-gated
  zero-fill reclamation semantics.
- M024/M026 supply same-price own FIFO and shared public-queue concepts.
- M032 replaces model-specific slot arithmetic with a global multiasset ownership
  ledger, persistent slot identity, causal queue statistics and physical routes.

No M030 result or M031 draft code is mutated.

## Components

- `multi_stable_models.py`: typed slots, temporal rules/fees, route and fill models.
- `multi_stable_ledger.py`: USD-200 gate, unique reservations, asset ownership,
  fill application, reconciliation and slot turnover.
- `multi_stable_queue.py`: one PUBLIC barrier followed by C1 then C2; prefix-only
  compatible-flow estimates and first/full-fill waits.
- `multi_stable_routing.py`: explainable opportunity and route scores, simple
  cycle enumeration and physical route closure.
- `adaptive_multi_stable_manager.py`: 7-rank geometry, safety guards, local
  hotlines, C1/C2 policy and reclaim decisions.
- `multi_stable_data.py`: physical-evidence inventory and common-date gate.

## Known pre-replay limitations

The architecture is a deterministic library, not yet wired to a historical
multi-book event runner. Public-depth increases arriving after C1/C2 activation
need the existing segmented-cohort semantics at integration time; M032 V1 never
places an unprovable later increase ahead of an order. The causal probability
estimator is descriptive, not a deterministic fill rule. Historical rule and fee
profiles remain unresolved until books and dates are eligible.

These limits do not authorize an economic replay.
