# M028 — technical invalidation at the M026 prefix gate

`M028_STATUS=INVALIDATED_TECHNICAL`

`24H_RESULT=UNAVAILABLE`

`EVENTS_AFTER_03H_PROCESSED=0`

The only authorized M028 attempt stopped before the first event at or after 03:00
UTC. The full-day result therefore does not exist and no 24-hour return may be
reported.

The economic prefix did reproduce M026: M028's preserved ledger is byte-for-byte
identical to M026's published three-hour ledger. Both contain 43,372 audit rows and
share SHA-256
`7d3fc1e67a41395c353009e829d1288562f8f25eb4554c3f2cf4db9743fd4bb8`.
This proves that fills, cycles and ledgered economic actions through 03:00 did not
diverge.

## Reached economic result

- initial marked equity: `156.25220000 USDT-equivalent`;
- marked equity at 03:00: `156.2972000000000000 USDT-equivalent`;
- marked gain: `0.0450000000000000 USDT-equivalent`;
- marked gain: `0.028799594501709415931423700%`;
- physical cycles: `30`;
- slot-equivalent cycles: `90`.

These are the immutable M026 three-hour values, not a new M028 result.

## Root cause

The prefix verifier compared the live Python checkpoint to the JSON-deserialized
published checkpoint as raw objects. The live state retained `Decimal` values and
integer dictionary keys; JSON restored them as strings. Examples include queue-wait
map keys and `queue_ahead_at_activation`. A source-bound diagnostic reproduced this
representation mismatch while retaining the identical ledger.

The failed process did not persist the rejected in-memory checkpoint. Consequently,
the physical failure artifacts cannot prove that representation differences were
the only non-ledger state differences. This is the strongest reproduced diagnosis,
not a claim of exclusive physical causation.

This is a technical comparator failure, not an economic loss and not evidence that
M026 changed. The fail-closed gate worked as intended: the remaining21 hours were
not executed economically.

## Required correction and gate

The correction is to canonicalize both checkpoint states through the same JSON
representation before semantic equality. M028 cannot be resumed or repeated because
its preregistration authorized one run and states that a prefix mismatch closes it.
A new OWNER-authorized identity is required for a corrected full-day retry.

No replay was performed while diagnosing or finalizing this failure.
