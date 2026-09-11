# M034 experimental identity

Status: `DRAFT_NOT_REGISTERED`; `M034_EXPERIMENT_MANIFEST_HASH=null`.

The experiment cannot be registered while material fields are unresolved. The draft
manifest at `reports/usdcusdt/M034-experiment-manifest.json` makes every missing field
explicit instead of generating a misleading master hash.

| Field | Value |
|---|---|
| model_id | `M034_BINANCE_ECONOMIC_ELIGIBILITY_PRODUCTIVITY` |
| experiment_id | `null` |
| source_sha | `420c99e825eea9c28a370b8f3f815bad923c60ce` |
| source_review_status | `PASS_GPT_6_ASTRA_EXACT_420C99E` |
| threshold_config_hash | `null` |
| pair_universe_hash | `b9637e30323b9da4885706b805ef7a482616eaab76224cb2b4e105eb1471d66d` |
| fee_evidence_hash | `ff25c6ff1b31c202f6b6779f1b0832053f0d9d3906df75a12bd1b6b003fa68da` |
| exchange_rules_hash | `ed7b810c5541cdc208ff12f974884d3d3bdba6ad696d6c2124db475e855f73ef` |
| dataset_manifest_hash | `31307132cd9227f6e85d0ac453396d3b679ca0bd9758b9183c77d6c77b81b6fa` |
| calibration_set_hash | `694752eb0f83ce10315e7cfffdb86dea5601c60ea92373d5821dbfb508f814a0` |
| validation_oos_pool_hash | `null` |
| estimator/cost/latency hashes | `null` |
| replay_protocol_hash | `e863fc152549312bc4e5b3e7f1658109d9d2b631c1fdf3d91960d3c3c5f53fe9` |
| window_selection_record | `NOT_SELECTED`, draws `0` |
| initial capital/currency/SLOT_BASE | `null` |

Statement preserved for the future complete identity:

`NO_PARAMETER_WAS_SELECTED_USING_M034_REPLAY_PERFORMANCE=true`

No master manifest hash is generated for an incomplete manifest. When every material
field is complete, registration must write a new immutable experiment ID and hash the
canonical deterministic representation. Any later material change requires a new
identity.

`READY_FOR_REPLAY=false`
`ECONOMIC_REPLAY_RUNS=0`
`STRATEGY_PASS=false`
