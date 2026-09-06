# USDCUSDT GPU benchmark

CPU remains canonical. CUDA is selected per workload only when exact results match and end-to-end speedup is at least 2x.

| Workload | Events | Candidates | CPU best | GPU best | Speedup | Peak VRAM | Match | Backend |
|---|---:|---:|---:|---:|---:|---:|---|---|
| TINY_SYNTHETIC | 4 | 18 | 0.000086s | 0.000546s | 0.157x | 2,560 B | PASS | CPU |
| SMALL_HISTORICAL_10000 | 10,000 | 48 | 0.003069s | 0.002079s | 1.476x | 52,736 B | PASS | CPU |
| FULL_HISTORICAL_DAY | 196,022 | 1,914 | 0.072942s | 0.043398s | 1.681x | 1,071,104 B | PASS | CPU |
| MULTI_DAY_SAMPLE | 426,197 | 1,920 | 0.146082s | 0.109787s | 1.331x | 2,187,776 B | PASS | CPU |

Overall equivalence: **PASS**.
Oracle adoption gate: **FAIL**.
Selected mode: **CPU**.

GPU timings include normalization, allocation, host/device transfers, kernels, synchronization and reconstruction of exact event-index results. ZIP parsing and SHA256 remain on CPU and are outside the Oracle-only timing.
