# M028 post-failure independent scientific review

Reviewer: `gpt-6-astra`

Status: `PASS_WITH_DIAGNOSTIC_LIMITATION`

Scope: source-bound read-only review; no historical event replay and no file edits.

## Findings

1. The runner compares the live Python checkpoint directly with a JSON-deserialized
   checkpoint after normalizing only `end_us`. A `Decimal`/integer-key versus string
   representation defect is therefore compatible with the failure and was reproduced
   diagnostically. Because the failed process did not persist its rejected checkpoint,
   the physical artifacts cannot prove that these were the only state differences.
2. The M026 and M028 prefix ledgers match byte-for-byte:43,372 rows,29,538 trades,
   78 fills and30 cycles. Both have SHA-256
   `7d3fc1e67a41395c353009e829d1288562f8f25eb4554c3f2cf4db9743fd4bb8`.
3. No event at or after03:00 was delivered to the economic engine. The last ledger
   timestamp is `1735700399070509`, before cutoff `1735700400000000`. The full-day
   data were loaded and the iterator reached the triggering event, but no economic
   extension event was processed.
4. `INVALIDATED_TECHNICAL` is appropriate. This is neither an economic loss nor a
   strategy rejection. Current authority forbids automatic rerun or resume.
5. No24-hour result exists. Values156.2522→156.2972 and+0.0287996% are the immutable
   three-hour M026 reference and must remain distinct from null24-hour fields.

The finalizer only reads and registers preserved evidence; it does not invoke the
historical replay engine.
