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

## Follow-up reserve snapshot correction

The next source-bound attempt at commit `10e5b20` and identity
`88a08fad8436e7f6519342713457db12ede727bb01809bab3d38ca51e79ab65c` proved that the closure
fee correction crossed the former failing event. Its independent final audit then failed closed
at release event `7250076418897391616` (`2026-02-02T13:16:28.207371Z`) because the recorded
`reserve_after` had separately been derived under Decimal28. The authoritative reserve mutation,
cash restoration, deficit, and `reserve_before` were all exact.

The audit reconstructed `1104232714470864415585.685494520`; the record contained the rounded
`1104232714470864415585.685495`. The runtime now computes the post-release reserve once under
Decimal128 and uses that exact value for the floor gate, serialized evidence, and state mutation.
The large-notional regression also asserts byte-equivalent decimal values between the record and
runtime state.

This second attempt is likewise `INVALIDATED_TECHNICAL`. Its two completed checkpoints are
preserved but excluded, and the corrected source requires a third fresh identity for all 18
scenarios.

## Follow-up open-position result correction

The third attempt at commit `8831f6a` and identity
`6dd59fd69597bae4f1f9b391e24ee8f56812487ca1bd3d69bbae3069a55f84c6` crossed and exactly
reconciled all 99 release transfers in `RRV2_H1_B5_F0`. Its final audit then found that `_result`
derived the buy fee of the still-open position outside the configured ledger context. With
quantity `416179260311448223601828427.25` and LOW `0.99983`, the zero fee was serialized as
`0.0173675` under Decimal28 rather than `0E-7` under Decimal128.

The checkpoint reconstruction itself exactly matched final cash `0.003306024` and reserve
`7554208085363787848576692.382940276`; only the derived result field was wrong. `_result` now
uses its existing `ledger_precision` contract for `open_buy_fee_quote`, and a regression covers
the physical open position. This third attempt is `INVALIDATED_TECHNICAL`, its two completed
checkpoints remain preserved and excluded, and the full grid must restart under a fourth identity.
