# M034 threshold pre-registration

Status: `INCOMPLETE_OWNER_VALUE_REQUIRED`; `THRESHOLD_CONFIG_HASH=null`.

This document uses the exact canonical source names. No value was selected from a
future M034 replay, a cycle target, a monthly-return aspiration or convenience.

| Name | Value | Unit | Status | Required objective authority |
|---|---:|---|---|---|
| `MIN_COMPLETION_PROBABILITY` | `null` | ratio | `OWNER_VALUE_REQUIRED` | owner preregistration or frozen calibration estimate |
| `MAX_EXPECTED_LOCK_TIME` | `null` | seconds | `OWNER_VALUE_REQUIRED` | owner preregistration or censoring-aware frozen calibration |
| `RISK_BUFFER` | `null` | bps | `OWNER_VALUE_REQUIRED` | explicit safety/economic derivation without double charging |
| `MAX_INVENTORY_EXPOSURE` | `null` | USD | `OWNER_VALUE_REQUIRED` | physical capital/risk authority |
| `PEG_DEVIATION_THRESHOLD` | `null` | ratio | `OWNER_VALUE_REQUIRED` | temporal safety authority or frozen calibration |
| `MIN_NET_EDGE` | `null` | bps | `OWNER_VALUE_REQUIRED` | owner economic rule or objective external rule |
| `TAIL_RISK_BOUND` | `null` | USD | `OWNER_VALUE_REQUIRED` | explicit tail population and derivation |
| `MAX_SPREAD` | `null` | bps | `OWNER_VALUE_REQUIRED` | frozen calibration or safety bound |
| `MIN_DEPTH` | `null` | USD | `OWNER_VALUE_REQUIRED` | frozen book-depth calibration and capital basis |
| `MIN_COMPATIBLE_FLOW` | `null` | asset/second | `OWNER_VALUE_REQUIRED` | frozen compatible-flow calibration |

Required provenance fields remain unset for every row: `source_type`,
`source_reference`, `derivation_method`, `calibration_dataset_hash`, `effective_from`
and `frozen_at`. Values from synthetic tests are not eligible.

`UnknownCostPolicy=UNRESOLVED`. Therefore the conditional thresholds
`UNKNOWN_EXECUTION_COST_BOUND` and `UNKNOWN_ADVERSE_SELECTION_BOUND` are not registered.
If the owner selects `CONSERVATIVE_BOUND`, both become mandatory with the same provenance
fields; they cannot be filled merely because a number seems conservative.

The deterministic threshold hash is generated only after all mandatory rows are
complete and validated by the source registry. Until then:

`THRESHOLD_CONFIG_HASH=null`
`CONFIGURATION_HASH=null`
`READY_FOR_REPLAY=false`
