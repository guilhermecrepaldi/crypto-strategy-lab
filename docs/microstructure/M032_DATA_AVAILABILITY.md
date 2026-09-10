# M032 data availability and acquisition gate

The reproducible audit is `scripts/audit_m032_data_availability.py`; its output is
`reports/usdcusdt/M032-data-availability.json`.

Only `USDCUSDT` has locally validated physical L2 plus canonical trades, covering
12 currently passing monthly samples. The audit now verifies both physical files
against the L2 and canonical trade SHA-256 values bound in each passing validation,
instead of trusting flags alone. `FDUSDUSDC` has an extensive canonical
`aggTrades` archive, but no local L2; the other candidate books also have no
validated local L2. Trades or candles cannot establish public FIFO.

Tardis documents Binance historical order-book data and downloadable first-day
samples in its [Binance dataset documentation](https://docs.tardis.dev/historical-data-details/binance).
At this audit, public download attempts for additional candidate books were not
usable without an access path. The local `agent-reach` research command was also
unavailable, so official web endpoints were used directly and no social or code
search result was treated as evidence.

Acquisition pipeline, once authorized/access-enabled:

1. fetch native/normalized incremental L2 and corresponding trades per candidate
   book without credentials to any trading account;
2. preserve immutable archives and SHA-256 provenance locally;
3. bridge snapshot/deltas and validate ordering, coverage and trade binding;
4. validate temporal symbol filters and fees independently;
5. intersect only dates passing every book gate;
6. freeze universe, books, slot base, bankroll and CSPRNG windows before replay.

Current result: `MULTI_BOOK_L2_INTERSECTION_EMPTY`. No draw was made and no replay
was executed.
