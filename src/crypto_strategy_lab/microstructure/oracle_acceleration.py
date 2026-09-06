"""Optional GPU acceleration for the integer-tick price-path oracle.

This module is deliberately separate from the economic scanner.  It evaluates an
explicit candidate list with the same non-overlapping LOW-then-HIGH machine as the
canonical CPU implementation.  CuPy is imported only when the GPU backend is used.
"""

from __future__ import annotations

import importlib
from bisect import bisect_right
from collections.abc import Sequence
from dataclasses import dataclass, field
from time import perf_counter
from typing import Any, Literal

import numpy as np


class GPUUnavailableError(RuntimeError):
    """The optional CuPy/CUDA runtime is not available."""


class GPUExecutionError(RuntimeError):
    """GPU compilation, memory planning, or execution failed."""


Candidate = tuple[int, int]


@dataclass(frozen=True, slots=True)
class OracleCandidateResult:
    """Cycle count and exact event-index pairs for one integer-tick candidate."""

    low_tick: int
    distance: int
    cycles: int
    entry_indices: tuple[int, ...]
    exit_indices: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class OracleResult:
    """Comparable oracle output with non-semantic execution metadata."""

    events: int
    candidates: tuple[OracleCandidateResult, ...]
    backend: Literal["cpu", "gpu"] = field(default="cpu", compare=False)
    gpu_chunk_size: int | None = field(default=None, compare=False)
    fallback_reason: str | None = field(default=None, compare=False)
    gpu_profile: GPUExecutionProfile | None = field(default=None, compare=False)


@dataclass(frozen=True, slots=True)
class GPUExecutionProfile:
    """Wall-clock breakdown and observed device allocation for one call."""

    total_seconds: float
    host_to_device_seconds: float
    kernel_seconds: float
    device_to_host_seconds: float
    allocation_seconds: float
    peak_vram_bytes: int


@dataclass(frozen=True, slots=True)
class GPUMemoryPlan:
    """Conservative candidate batch plan for one GPU invocation."""

    event_count: int
    candidate_count: int
    free_bytes: int
    total_bytes: int
    safety_margin_bytes: int
    fixed_bytes: int
    bytes_per_candidate: int
    chunk_size: int
    estimated_peak_bytes: int


def scan_oracle_cpu(prices: Sequence[int], candidates: Sequence[Candidate]) -> OracleResult:
    """Evaluate explicit integer-tick candidates using the canonical CPU machine."""
    normalized_prices = _normalize_prices(prices)
    normalized_candidates = _normalize_candidates(candidates)
    occurrences = _price_occurrences(normalized_prices)
    results = tuple(
        _scan_candidate_cpu(occurrences, low_tick, distance)
        for low_tick, distance in normalized_candidates
    )
    return OracleResult(
        events=len(normalized_prices),
        candidates=results,
        backend="cpu",
    )


def scan_oracle_gpu(
    prices: Sequence[int],
    candidates: Sequence[Candidate],
    *,
    device_id: int = 0,
    safety_margin: float = 0.20,
) -> OracleResult:
    """Evaluate explicit candidates with CuPy RawKernels.

    The first kernel counts serial cycles per candidate.  A second kernel writes the
    exact entry/exit event indices, making CPU/GPU equivalence directly auditable.
    This function raises explicitly on missing runtime, planning failure, OOM, or
    kernel failure; callers wanting recoverable CPU fallback should use
    :func:`scan_oracle` with ``backend="auto"``.
    """
    total_started = perf_counter()
    cp = _load_cupy()
    normalized_prices = _normalize_prices(prices)
    normalized_candidates = _normalize_candidates(candidates)
    if not normalized_candidates:
        return OracleResult(events=len(normalized_prices), candidates=(), backend="gpu")
    try:
        with cp.cuda.Device(device_id):
            free_bytes, total_bytes = (int(value) for value in cp.cuda.Device().mem_info)
            pool = cp.get_default_memory_pool()
            baseline_pool_bytes = int(pool.used_bytes())
            plan = plan_gpu_batches(
                len(normalized_prices),
                len(normalized_candidates),
                free_bytes,
                total_bytes,
                safety_margin=safety_margin,
            )
            h2d_started = perf_counter()
            prices_gpu = cp.asarray(normalized_prices, dtype=cp.int32)
            cp.cuda.Stream.null.synchronize()
            host_to_device_seconds = perf_counter() - h2d_started
            peak_vram_bytes = max(0, int(pool.used_bytes()) - baseline_pool_bytes)
            count_kernel, pairs_kernel = _kernels(cp)
            result_rows: list[OracleCandidateResult] = []
            kernel_seconds = 0.0
            device_to_host_seconds = 0.0
            allocation_seconds = 0.0
            for start in range(0, len(normalized_candidates), plan.chunk_size):
                chunk = normalized_candidates[start : start + plan.chunk_size]
                rows, measurements = _scan_gpu_chunk(
                    cp,
                    count_kernel,
                    pairs_kernel,
                    prices_gpu,
                    chunk,
                    baseline_pool_bytes=baseline_pool_bytes,
                )
                result_rows.extend(rows)
                host_to_device_seconds += measurements["host_to_device_seconds"]
                kernel_seconds += measurements["kernel_seconds"]
                device_to_host_seconds += measurements["device_to_host_seconds"]
                allocation_seconds += measurements["allocation_seconds"]
                peak_vram_bytes = max(peak_vram_bytes, int(measurements["peak_vram_bytes"]))
            cp.cuda.Stream.null.synchronize()
            total_seconds = perf_counter() - total_started
            return OracleResult(
                events=len(normalized_prices),
                candidates=tuple(result_rows),
                backend="gpu",
                gpu_chunk_size=plan.chunk_size,
                gpu_profile=GPUExecutionProfile(
                    total_seconds=total_seconds,
                    host_to_device_seconds=host_to_device_seconds,
                    kernel_seconds=kernel_seconds,
                    device_to_host_seconds=device_to_host_seconds,
                    allocation_seconds=allocation_seconds,
                    peak_vram_bytes=peak_vram_bytes,
                ),
            )
    except GPUExecutionError:
        raise
    except (MemoryError, RuntimeError) as exc:
        raise GPUExecutionError(f"GPU execution failed: {exc}") from exc


def scan_oracle(
    prices: Sequence[int],
    candidates: Sequence[Candidate],
    *,
    backend: Literal["cpu", "gpu", "auto"] = "cpu",
    device_id: int = 0,
    safety_margin: float = 0.20,
) -> OracleResult:
    """Run the oracle with explicit backend policy and observable fallback."""
    if backend == "cpu":
        return scan_oracle_cpu(prices, candidates)
    if backend == "gpu":
        return scan_oracle_gpu(
            prices,
            candidates,
            device_id=device_id,
            safety_margin=safety_margin,
        )
    try:
        return scan_oracle_gpu(
            prices,
            candidates,
            device_id=device_id,
            safety_margin=safety_margin,
        )
    except (GPUUnavailableError, GPUExecutionError) as exc:
        cpu = scan_oracle_cpu(prices, candidates)
        return OracleResult(
            events=cpu.events,
            candidates=cpu.candidates,
            backend="cpu",
            fallback_reason=f"{type(exc).__name__}: {exc}",
        )


def plan_gpu_batches(
    event_count: int,
    candidate_count: int,
    free_bytes: int,
    total_bytes: int,
    *,
    safety_margin: float = 0.20,
) -> GPUMemoryPlan:
    """Estimate a conservative candidate chunk size including pair output memory."""
    if event_count < 0 or candidate_count < 0:
        raise ValueError("event_count and candidate_count must be non-negative")
    if free_bytes < 0 or total_bytes < 0:
        raise ValueError("GPU memory values must be non-negative")
    if not 0 <= safety_margin < 1:
        raise ValueError("safety_margin must be in [0, 1)")
    if candidate_count == 0:
        return GPUMemoryPlan(
            event_count,
            candidate_count,
            free_bytes,
            total_bytes,
            int(free_bytes * safety_margin),
            event_count * np.dtype(np.int32).itemsize,
            20 + event_count * 8,
            0,
            event_count * np.dtype(np.int32).itemsize,
        )
    fixed_bytes = event_count * np.dtype(np.int32).itemsize
    # Candidate pair (8), count (4), int64 offset (8), and two int32 pair indices
    # for each event (8 * event_count) are retained for each candidate batch.
    bytes_per_candidate = 20 + event_count * 8
    safety_margin_bytes = int(free_bytes * safety_margin)
    budget = free_bytes - safety_margin_bytes
    available_for_candidates = budget - fixed_bytes
    chunk_size = available_for_candidates // bytes_per_candidate
    if chunk_size < 1:
        raise GPUExecutionError(
            "GPU memory plan cannot fit one candidate with the requested safety margin"
        )
    chunk_size = min(candidate_count, chunk_size)
    return GPUMemoryPlan(
        event_count=event_count,
        candidate_count=candidate_count,
        free_bytes=free_bytes,
        total_bytes=total_bytes,
        safety_margin_bytes=safety_margin_bytes,
        fixed_bytes=fixed_bytes,
        bytes_per_candidate=bytes_per_candidate,
        chunk_size=chunk_size,
        estimated_peak_bytes=fixed_bytes + chunk_size * bytes_per_candidate,
    )


def _scan_candidate_cpu(
    occurrences: dict[int, list[int]], low_tick: int, distance: int
) -> OracleCandidateResult:
    entries: list[int] = []
    exits: list[int] = []
    lows = occurrences.get(low_tick, [])
    highs = occurrences.get(low_tick + distance, [])
    after = -1
    low_index = high_index = 0
    while low_index < len(lows):
        low_index = bisect_right(lows, after, lo=low_index)
        if low_index >= len(lows):
            break
        entry_index = lows[low_index]
        high_index = bisect_right(highs, entry_index, lo=high_index)
        if high_index >= len(highs):
            break
        exit_index = highs[high_index]
        entries.append(entry_index)
        exits.append(exit_index)
        after = exit_index
        low_index += 1
        high_index += 1
    return OracleCandidateResult(low_tick, distance, len(entries), tuple(entries), tuple(exits))


def _price_occurrences(
    prices: np.ndarray[Any, np.dtype[np.int32]],
) -> dict[int, list[int]]:
    occurrences: dict[int, list[int]] = {}
    for index, price in enumerate(prices):
        occurrences.setdefault(int(price), []).append(index)
    return occurrences


def _scan_gpu_chunk(
    cp: Any,
    count_kernel: Any,
    pairs_kernel: Any,
    prices_gpu: Any,
    candidates: tuple[Candidate, ...],
    *,
    baseline_pool_bytes: int,
) -> tuple[list[OracleCandidateResult], dict[str, float | int]]:
    h2d_started = perf_counter()
    candidate_gpu = cp.asarray(np.asarray(candidates, dtype=np.int32))
    cp.cuda.Stream.null.synchronize()
    host_to_device_seconds = perf_counter() - h2d_started
    candidate_count = len(candidates)
    threads = 256
    blocks = ((candidate_count + threads - 1) // threads,)
    allocation_started = perf_counter()
    counts_gpu = cp.empty(candidate_count, dtype=cp.int32)
    allocation_seconds = perf_counter() - allocation_started
    peak_vram_bytes = max(0, int(cp.get_default_memory_pool().used_bytes()) - baseline_pool_bytes)
    kernel_started = perf_counter()
    count_kernel(
        blocks,
        (threads,),
        (prices_gpu, prices_gpu.size, candidate_gpu, candidate_count, counts_gpu),
    )
    cp.cuda.Stream.null.synchronize()
    kernel_seconds = perf_counter() - kernel_started
    d2h_started = perf_counter()
    counts = np.asarray(cp.asnumpy(counts_gpu), dtype=np.int64)
    device_to_host_seconds = perf_counter() - d2h_started
    offsets = np.zeros(candidate_count, dtype=np.int64)
    if candidate_count > 1:
        offsets[1:] = np.cumsum(counts[:-1])
    total_pairs = int(counts.sum())
    allocation_started = perf_counter()
    pair_gpu = cp.empty((total_pairs, 2), dtype=cp.int32)
    allocation_seconds += perf_counter() - allocation_started
    h2d_started = perf_counter()
    offsets_gpu = cp.asarray(offsets, dtype=cp.int64)
    cp.cuda.Stream.null.synchronize()
    host_to_device_seconds += perf_counter() - h2d_started
    peak_vram_bytes = max(
        peak_vram_bytes,
        int(cp.get_default_memory_pool().used_bytes()) - baseline_pool_bytes,
    )
    kernel_started = perf_counter()
    pairs_kernel(
        blocks,
        (threads,),
        (
            prices_gpu,
            prices_gpu.size,
            candidate_gpu,
            candidate_count,
            offsets_gpu,
            pair_gpu,
        ),
    )
    cp.cuda.Stream.null.synchronize()
    kernel_seconds += perf_counter() - kernel_started
    d2h_started = perf_counter()
    pairs = np.asarray(cp.asnumpy(pair_gpu), dtype=np.int32)
    device_to_host_seconds += perf_counter() - d2h_started
    rows = [
        OracleCandidateResult(
            low_tick=low_tick,
            distance=distance,
            cycles=int(count),
            entry_indices=tuple(int(value) for value in pairs[offset : offset + count, 0]),
            exit_indices=tuple(int(value) for value in pairs[offset : offset + count, 1]),
        )
        for (low_tick, distance), count, offset in zip(candidates, counts, offsets, strict=True)
    ]
    return rows, {
        "host_to_device_seconds": host_to_device_seconds,
        "kernel_seconds": kernel_seconds,
        "device_to_host_seconds": device_to_host_seconds,
        "allocation_seconds": allocation_seconds,
        "peak_vram_bytes": peak_vram_bytes,
    }


def _kernels(cp: Any) -> tuple[Any, Any]:
    try:
        source = r"""
        extern "C" __global__ void count_cycles(
            const int* prices, const long n, const int* candidates,
            const long candidate_count, int* counts
        ) {
            const long candidate = (long)blockDim.x * blockIdx.x + threadIdx.x;
            if (candidate >= candidate_count) return;
            const int low = candidates[2 * candidate];
            const int high = low + candidates[2 * candidate + 1];
            int armed = 0;
            int cycles = 0;
            for (long index = 0; index < n; ++index) {
                const int price = prices[index];
                if (!armed && price == low) {
                    armed = 1;
                } else if (armed && price == high) {
                    ++cycles;
                    armed = 0;
                }
            }
            counts[candidate] = cycles;
        }

        extern "C" __global__ void write_pairs(
            const int* prices, const long n, const int* candidates,
            const long candidate_count, const long long* offsets, int* pairs
        ) {
            const long candidate = (long)blockDim.x * blockIdx.x + threadIdx.x;
            if (candidate >= candidate_count) return;
            const int low = candidates[2 * candidate];
            const int high = low + candidates[2 * candidate + 1];
            int armed = 0;
            int entry = -1;
            long long written = 0;
            for (long index = 0; index < n; ++index) {
                const int price = prices[index];
                if (!armed && price == low) {
                    armed = 1;
                    entry = (int)index;
                } else if (armed && price == high) {
                    const long long output = offsets[candidate] + written;
                    pairs[2 * output] = entry;
                    pairs[2 * output + 1] = (int)index;
                    ++written;
                    armed = 0;
                }
            }
        }
        """
        return cp.RawKernel(source, "count_cycles"), cp.RawKernel(source, "write_pairs")
    except Exception as exc:  # CuPy exposes several backend-specific compile exceptions.
        raise GPUExecutionError(f"GPU kernel compilation failed: {exc}") from exc


def _load_cupy() -> Any:
    try:
        cp = importlib.import_module("cupy")
    except ImportError as exc:
        raise GPUUnavailableError("CuPy is not installed") from exc
    try:
        if cp.cuda.runtime.getDeviceCount() < 1:
            raise GPUUnavailableError("CuPy found no CUDA device")
    except GPUUnavailableError:
        raise
    except Exception as exc:
        raise GPUUnavailableError(f"CUDA device query failed: {exc}") from exc
    return cp


def _normalize_prices(prices: Sequence[int]) -> np.ndarray[Any, np.dtype[np.int32]]:
    values = np.asarray(list(prices), dtype=np.int64)
    if values.size and (
        values.min() < np.iinfo(np.int32).min or values.max() > np.iinfo(np.int32).max
    ):
        raise ValueError("prices must fit int32")
    return values.astype(np.int32, copy=False)


def _normalize_candidates(candidates: Sequence[Candidate]) -> tuple[Candidate, ...]:
    normalized: list[Candidate] = []
    for candidate in candidates:
        if len(candidate) != 2:
            raise ValueError("candidates must contain (low_tick, distance) pairs")
        low_tick, distance = (int(value) for value in candidate)
        if distance <= 0:
            raise ValueError("candidate distance must be positive")
        if not np.iinfo(np.int32).min <= low_tick <= np.iinfo(np.int32).max:
            raise ValueError("candidate low_tick must fit int32")
        if low_tick + distance > np.iinfo(np.int32).max:
            raise ValueError("candidate high_tick must fit int32")
        normalized.append((low_tick, distance))
    return tuple(normalized)
