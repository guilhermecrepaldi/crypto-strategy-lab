# USDCUSDT GPU environment report

Audit timestamp: `2026-09-06T12:56:03-03:00`.

## Detected environment

- GPU: NVIDIA GeForce RTX 5060, 8,151 MiB VRAM.
- Free VRAM at the initial query: 6,610 MiB; a later `nvidia-smi` snapshot showed 1,204 MiB
  used by Windows graphics applications and no project compute process.
- Driver: NVIDIA 610.74, WDDM; CUDA UMD exposed by the driver: 13.3.
- Compute capability reported by `nvidia-smi`: 12.0.
- Python: 3.12.13 in the project `.venv`.
- uv: 0.11.26.
- PyTorch: 2.13.0+cpu; `torch.cuda.is_available()` is false.
- CuPy: 14.2.0 (`cupy-cuda13x`) installed as the optional project extra; CUDA runtime 13.2,
  driver runtime 13.3 and one CUDA device detected. Numba: not installed. ROCm tools: absent.

## Gate state

The CPU remains the canonical backend. The first candidate workload was the exact integer-tick
LOW/HIGH Oracle scan. CuPy was added as a reproducible optional dependency after profiling showed
that repeated Oracle sweeps were the appropriate first GPU candidate. No system component was
changed.

Completed gate:

1. CPU profile on real USDCUSDT data: complete;
2. tiny synthetic, small historical, full-day and multi-day golden datasets: complete;
3. exact CPU/GPU equality for LOW, HIGH, distance, cycle count, event indexes and aggregate daily
   metrics: pass;
4. end-to-end benchmark including transfers, kernels, allocation and peak device allocation:
   complete;
5. measured speedup of at least 2x: fail (best material workload in the frozen report was
   1.681x).

Therefore CUDA is available but not selected for this Oracle workload. The campaign continues on
CPU; the optional backend remains isolated for future workloads that independently pass the same
gate.

Download, ZIP parsing, SHA256, manifests, persistence and the canonical serial ledger remain on
CPU. No driver, Windows, BIOS, global CUDA Toolkit, power, firmware or Ollama change is authorized
or required at this stage.
