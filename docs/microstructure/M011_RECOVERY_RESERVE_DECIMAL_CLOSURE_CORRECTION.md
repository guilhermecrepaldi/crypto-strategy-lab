# M011 recovery reserve — Decimal closure correction

Status: `INVALIDATED_TECHNICAL` for the first v2 attempt. No M011 was registered.

## Observed failure

The source-bound v2 attempt from commit `d024746e` failed closed during the independent ledger
audit of scenario `RRV2_H1_B5_F0`. The first exact mismatch was release event
`7249832558710554624` (`2026-02-01T20:44:12.028944Z`): the runtime recorded reserve transfer
`4873796105270716866.2672440`, while reconstruction from the serialized closure required
`4873796105270716866.2672460`.

The difference was a spurious `0.0000020` buy fee. The position had quantity
`12184490263176792165668.11`, LOW `1.00120`, and a zero configured fee. Release deficit and cash
mutation already used the ledger's Decimal128 context, but the closure's derived buy fee was
calculated after leaving that context. Default Decimal28 multiplication rounded the acquisition
cost before subtraction.

## Correction and scope

The canonical recovery runtime now derives the release closure buy fee inside the same
Decimal128 ledger context. A regression test reproduces the physical magnitude and proves that a
zero acquisition fee remains exactly zero.

The failed scenario is invalid, not a loss. The two earlier completed checkpoints from the same
attempt are preserved but excluded from scientific comparison because the corrected source must
produce a new hashed identity and rerun the whole preregistered grid uniformly. No result or
checkpoint crosses identities.
