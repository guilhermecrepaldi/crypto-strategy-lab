# M032 source-bound independent review — third pass

Reviewer: `gpt-6-astra`

Source: `1be66f139088e47346a4e492546f180b72c92a1b`

Implementation review: `BLOCK`

Replay readiness: `false`

The third pass confirmed that activation, external-fee attribution and pre-mutation
negative-return admission were corrected. One P1 case remained: a fee charged in
the input asset consumed the physical reservation but not the route's remaining
input, leaving an impossible open route with no asset or reservation.

No replay ran. The next revision treats an input-asset fee as part of the leg's
consumed capital and reserves separate origin-PnL conversion only for fees paid in
a third asset.
