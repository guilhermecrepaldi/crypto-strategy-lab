# M032 source-bound independent review — second pass

Reviewer: `gpt-6-astra`

Source: `4376d9320afe0300518738c7581c1e91abb43f7c`

Implementation review: `BLOCK`

Replay readiness: `false`

The second pass confirmed the earlier ledger, ACK race, queue epoch, physical
fragment, manager and data-hash corrections. It retained two P1 findings: a
cancel-pending reservation that had never activated could still fill, and a fee
paid in a third asset reduced equity without reducing cycle PnL. It also found
that a negative final return fill could mutate the ledger before the post-fill
loss check raised.

No replay ran. The next revision requires prior physical activation, converts
external fees into origin-asset PnL using the ledger's frozen marks, and performs
the final-return economic admission gate before applying the fill.
