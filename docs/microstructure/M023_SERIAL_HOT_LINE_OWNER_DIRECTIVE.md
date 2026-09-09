# OWNER directive — M023 serial hot line

RECEIVED_DATE=2026-09-09
MODEL_ID=M023
STATUS=ACTIVE_AUTHORITY

The OWNER authorizes a new strategy experiment with many order opportunities kept
available in a monitored hot-line radar, while only one real exchange order may be
non-terminal or execute at any time.

Exact intent preserved from the conversation:

> “apenas 1 ordem depois da outra, sendo 1 compra, 1 venda. tem q ser alternado,
> nada de 1 venda depois 1 venda.”

> “teremos as ordens disponíveis, mantem a quantidade em disposição, mas apenas 1
> é comprada e uma vendida e de forma sempre em sequencia, nada paralela, [...] não
> pode haver impedimentos da nossa parte”

> “vamos fazer o teste [...] para 3 horas de operação no primeiro dia l2”

The authorized economic window is exactly2025-01-01T00:00:00Z inclusive through
2025-01-01T03:00:00Z exclusive. No extension, second run, Day2, parameter sweep,
live/Testnet/account access or successor is authorized. Expansion requires a later
explicit OWNER approval.

The200 M022 price addresses may remain available as virtual candidates. They are not
exchange orders, reserve no capital, hold no queue position and cannot fill. Exactly
one selected order may be PENDING, ACTIVE or CANCEL_PENDING. Economic fills must
alternate strictly BUY then SELL then BUY. Cancel/repost attempts within the same
unfinished leg do not constitute another economic leg.

The higher-level manager is modeled as two ordered virtual decks:100 BUY cards and
100 SELL cards. A card selected from the middle hot-line region becomes the only armed
real order. When that card fills, its hot-line position is vacated; a free card from
the same deck's outer stack is moved into that position so the opportunity layout
remains ready. The executed price card is recycled to the free edge after its lifecycle
record is preserved. BUY refills prefer the highest-priced free BUY edge card. SELL
refills use the symmetric lowest-priced free SELL edge card. Rotation is a permutation
of virtual price templates: it cannot erase inventory, change the economic side,
reserve capital or create another real order.

The inherited lattice anchor is1.0020. Position and virtual address move together
during the swap: the promoted edge card really occupies the gap; an unfilled cancel or
rejection releases its card without rotating the deck because no card was traded.

This authority changes order management materially and therefore requires M023. It
does not alter or reinterpret M021/M022 results.
