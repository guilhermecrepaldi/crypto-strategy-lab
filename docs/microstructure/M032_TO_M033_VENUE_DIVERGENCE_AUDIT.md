# M032 → M033 venue divergence audit

Source audited: reviewed M032 commit `25273367e6d2146a71d0308a423415320e3da8c0`.
Historical M032 files were not modified.

| Component | Finding | Class | M033 disposition |
|---|---|---|---|
| `SymbolRule` | keyed only by symbol | VENUE_COUPLED | `VenueSymbolRule.book: BookKey` |
| `FeeProfile` | keyed only by symbol | VENUE_COUPLED | `VenueFeeProfile.book: BookKey` |
| `StablecoinEvidence` | includes `binance_operational_score` in intrinsic safety | SEMANTIC_CONFLICT | split `AssetSafetyEvidence` and `VenueOperationalEvidence` |
| `EconomicSlot.book` | string symbol; venue absent | REFACTOR_REQUIRED | M033 physical wrappers use `BookKey`; M032 type retained for reproducibility |
| `RouteLeg` | symbol only | SEMANTIC_CONFLICT | `VenueRouteLeg.book`; mixed-venue route rejected |
| `RouteCandidate/Progress` | no venue boundary | REFACTOR_REQUIRED | route derives one immutable venue |
| `PhysicalFill` | symbol only | SEMANTIC_CONFLICT | `VenuePhysicalFill` requires fill venue = book venue |
| `BookState` | symbol only | VENUE_COUPLED | M033 book state key is `BookKey` |
| `CausalQueueEstimator` | groups keyed by string book; IDs global per instance | VENUE_COUPLED | one unchanged L2 estimator per `BookKey` |
| `SlotLedger` | global asset buckets, 200 cap | SEMANTIC_CONFLICT | one M032-compatible ledger per venue; aggregate reporting only |
| `AdaptiveCapitalOrderManager` | books/rules keyed by symbol | VENUE_COUPLED | M033 supervisor supplies venue-local manager state |
| `AdaptiveColumnAllocator` | venue-neutral scoring | MATCH | reused economic semantics |
| `multi_stable_data.py` | Binance-specific paths and symbols | VENUE_COUPLED | separate multi-venue physical evidence inventory |

The refactor is additive because changing the reviewed M032 source would destroy
its exact provenance. M033 is the only venue-aware authority; it composes the
unchanged M032 economic ledger within each venue instead of creating separate
Binance/Kraken strategies.
