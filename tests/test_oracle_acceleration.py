from __future__ import annotations

import pytest

from crypto_strategy_lab.microstructure.oracle_acceleration import (
    GPUUnavailableError,
    OracleCandidateResult,
    OracleResult,
    plan_gpu_batches,
    scan_oracle,
    scan_oracle_cpu,
    scan_oracle_gpu,
)

PRICES = [100, 101, 100, 102, 101, 102]
CANDIDATES = [(100, 1), (100, 2), (101, 1)]


def test_cpu_oracle_preserves_non_overlapping_serial_machine() -> None:
    result = scan_oracle_cpu(PRICES, CANDIDATES)

    assert result == OracleResult(
        events=6,
        candidates=(
            OracleCandidateResult(100, 1, 2, (0, 2), (1, 4)),
            OracleCandidateResult(100, 2, 1, (0,), (3,)),
            OracleCandidateResult(101, 1, 2, (1, 4), (3, 5)),
        ),
    )


def test_gpu_memory_plan_reserves_margin_and_pairs_output() -> None:
    plan = plan_gpu_batches(
        event_count=100,
        candidate_count=1_000,
        free_bytes=1_000_000,
        total_bytes=2_000_000,
        safety_margin=0.20,
    )

    assert plan.safety_margin_bytes == 200_000
    assert plan.fixed_bytes == 400
    assert plan.bytes_per_candidate == 820
    assert plan.chunk_size == 975
    assert plan.estimated_peak_bytes <= 800_000


def test_gpu_backend_is_explicit_when_unavailable() -> None:
    cupy = pytest.importorskip("cupy")
    if cupy.cuda.runtime.getDeviceCount() > 0:
        pytest.skip("GPU runtime is available; use equivalence test")
    with pytest.raises(GPUUnavailableError):
        scan_oracle_gpu(PRICES, CANDIDATES)


def test_gpu_matches_cpu_on_golden_sequence() -> None:
    cupy = pytest.importorskip("cupy")
    if cupy.cuda.runtime.getDeviceCount() < 1:
        pytest.skip("CuPy installed without a CUDA device")

    cpu = scan_oracle_cpu(PRICES, CANDIDATES)
    gpu = scan_oracle_gpu(PRICES, CANDIDATES)
    assert cpu == gpu
    assert gpu.backend == "gpu"
    assert gpu.gpu_profile is not None
    assert gpu.gpu_profile.peak_vram_bytes > 0
    assert gpu.gpu_profile.total_seconds >= gpu.gpu_profile.kernel_seconds


def test_auto_backend_falls_back_observably(monkeypatch: pytest.MonkeyPatch) -> None:
    def unavailable() -> None:
        raise GPUUnavailableError("fixture has no CUDA")

    monkeypatch.setattr(
        "crypto_strategy_lab.microstructure.oracle_acceleration._load_cupy",
        unavailable,
    )

    result = scan_oracle(PRICES, CANDIDATES, backend="auto")

    assert result == scan_oracle_cpu(PRICES, CANDIDATES)
    assert result.backend == "cpu"
    assert result.fallback_reason == "GPUUnavailableError: fixture has no CUDA"
