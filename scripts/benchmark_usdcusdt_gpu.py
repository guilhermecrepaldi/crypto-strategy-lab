"""Reproducible CPU/CUDA equivalence and performance gate for the USDCUSDT Oracle."""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path
from time import perf_counter
from typing import Any

from crypto_strategy_lab.domain import canonical_hash
from crypto_strategy_lab.microstructure.data import iter_archive
from crypto_strategy_lab.microstructure.oracle_acceleration import (
    GPUExecutionProfile,
    OracleResult,
    scan_oracle_cpu,
    scan_oracle_gpu,
)

TICK_SIZE = Decimal("0.00001")
DISTANCES = (1, 2, 3, 4, 5, 10)
SPEEDUP_GATE = 2.0


def _ticks(paths: list[Path]) -> tuple[list[int], list[str]]:
    values: list[int] = []
    days: list[str] = []
    for path in paths:
        for event in iter_archive(path, "trades"):
            scaled = event.price / TICK_SIZE
            if scaled != scaled.to_integral_value():
                raise ValueError(f"off-grid price {event.price} in {path}")
            values.append(int(scaled))
            days.append(event.timestamp.date().isoformat())
    return values, days


def _candidates(prices: list[int]) -> tuple[tuple[int, int], ...]:
    return tuple((low, distance) for low in sorted(set(prices)) for distance in DISTANCES)


def _semantic_payload(result: OracleResult, event_days: list[str]) -> dict[str, Any]:
    daily_totals: dict[str, int] = {}
    total_cycles = 0
    gross_edge_ticks = 0
    for item in result.candidates:
        total_cycles += item.cycles
        gross_edge_ticks += item.cycles * item.distance
        for index in item.exit_indices:
            day = event_days[index]
            daily_totals[day] = daily_totals.get(day, 0) + 1
    return {
        "events": result.events,
        "aggregate_model_metrics": {
            "completed_cycles": total_cycles,
            "gross_edge_ticks": gross_edge_ticks,
            "daily_completed_cycles": daily_totals,
        },
        "candidates": [
            {
                "low_tick": item.low_tick,
                "high_tick": item.low_tick + item.distance,
                "tick_distance": item.distance,
                "cycle_count": item.cycles,
                "entry_indices": item.entry_indices,
                "exit_indices": item.exit_indices,
            }
            for item in result.candidates
        ],
    }


def _measure(
    prices: list[int],
    event_days: list[str],
    candidates: tuple[tuple[int, int], ...],
    repeats: int,
) -> dict[str, Any]:
    cpu_times: list[float] = []
    gpu_times: list[float] = []
    cpu_result: OracleResult | None = None
    gpu_result: OracleResult | None = None
    best_profile: GPUExecutionProfile | None = None
    best_gpu = float("inf")
    for _ in range(repeats):
        started = perf_counter()
        current_cpu = scan_oracle_cpu(prices, candidates)
        cpu_times.append(perf_counter() - started)
        cpu_result = current_cpu
    for _ in range(repeats):
        started = perf_counter()
        current_gpu = scan_oracle_gpu(prices, candidates)
        elapsed = perf_counter() - started
        gpu_times.append(elapsed)
        gpu_result = current_gpu
        if elapsed < best_gpu:
            best_gpu = elapsed
            best_profile = current_gpu.gpu_profile
    if cpu_result is None or gpu_result is None or best_profile is None:
        raise RuntimeError("benchmark requires at least one repeat")
    cpu_payload = _semantic_payload(cpu_result, event_days)
    gpu_payload = _semantic_payload(gpu_result, event_days)
    cpu_best = min(cpu_times)
    gpu_best = min(gpu_times)
    speedup = cpu_best / gpu_best
    return {
        "events": len(prices),
        "candidates": len(candidates),
        "cpu_seconds": cpu_times,
        "gpu_seconds": gpu_times,
        "cpu_best_seconds": cpu_best,
        "gpu_best_seconds": gpu_best,
        "speedup": speedup,
        "result_match": cpu_payload == gpu_payload,
        "cpu_result_hash": canonical_hash(cpu_payload),
        "gpu_result_hash": canonical_hash(gpu_payload),
        "gpu_profile_best": asdict(best_profile),
        "selected_backend": "CUDA" if speedup >= SPEEDUP_GATE else "CPU",
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _markdown(payload: dict[str, Any]) -> str:
    rows = [
        "# USDCUSDT GPU benchmark",
        "",
        "CPU remains canonical. CUDA is selected per workload only when exact results match and "
        "end-to-end speedup is at least 2x.",
        "",
        "| Workload | Events | Candidates | CPU best | GPU best | Speedup | "
        "Peak VRAM | Match | Backend |",
        "|---|---:|---:|---:|---:|---:|---:|---|---|",
    ]
    for name, result in payload["workloads"].items():
        profile = result["gpu_profile_best"]
        rows.append(
            f"| {name} | {result['events']:,} | {result['candidates']:,} | "
            f"{result['cpu_best_seconds']:.6f}s | {result['gpu_best_seconds']:.6f}s | "
            f"{result['speedup']:.3f}x | {profile['peak_vram_bytes']:,} B | "
            f"{'PASS' if result['result_match'] else 'FAIL'} | {result['selected_backend']} |"
        )
    rows.extend(
        [
            "",
            f"Overall equivalence: **{payload['cpu_gpu_equivalence']}**.",
            f"Oracle adoption gate: **{payload['oracle_gate']}**.",
            f"Selected mode: **{payload['selected_mode']}**.",
            "",
            "GPU timings include normalization, allocation, host/device transfers, kernels, "
            "synchronization and reconstruction of exact event-index results. ZIP parsing and "
            "SHA256 remain on CPU and are outside the Oracle-only timing.",
            "",
        ]
    )
    return "\n".join(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("archives", nargs="+", type=Path)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument(
        "--output-json", type=Path, default=Path("reports/usdcusdt/gpu-benchmark.json")
    )
    parser.add_argument("--output-md", type=Path, default=Path("reports/usdcusdt/gpu-benchmark.md"))
    args = parser.parse_args()
    if len(args.archives) < 2:
        parser.error("provide at least two official daily archives")
    if args.repeats < 1:
        parser.error("--repeats must be positive")
    for archive in args.archives:
        if not archive.is_file():
            parser.error(f"archive does not exist: {archive}")

    warmup_prices = [100_000, 100_001, 100_000, 100_002]
    warmup_candidates = ((100_000, 1), (100_000, 2))
    warmup_started = perf_counter()
    warmup_match = scan_oracle_cpu(warmup_prices, warmup_candidates) == scan_oracle_gpu(
        warmup_prices, warmup_candidates
    )
    warmup_seconds = perf_counter() - warmup_started

    first_day = _ticks([args.archives[0]])
    multi_day = _ticks(args.archives)
    datasets = {
        "TINY_SYNTHETIC": (warmup_prices, ["2026-01-01"] * len(warmup_prices)),
        "SMALL_HISTORICAL_10000": (first_day[0][:10_000], first_day[1][:10_000]),
        "FULL_HISTORICAL_DAY": first_day,
        "MULTI_DAY_SAMPLE": multi_day,
    }
    workloads = {
        name: _measure(prices, event_days, _candidates(prices), args.repeats)
        for name, (prices, event_days) in datasets.items()
    }
    all_match = warmup_match and all(item["result_match"] for item in workloads.values())
    selected = {item["selected_backend"] for item in workloads.values()}
    selected_mode = "HYBRID" if "CUDA" in selected else "CPU"
    payload = {
        "schema_version": "usdcusdt-gpu-benchmark-v2",
        "tick_size": str(TICK_SIZE),
        "distances_ticks": DISTANCES,
        "speedup_acceptance_threshold": SPEEDUP_GATE,
        "warmup_seconds": warmup_seconds,
        "warmup_match": warmup_match,
        "archives": [{"path": str(path), "sha256": _sha256(path)} for path in args.archives],
        "workloads": workloads,
        "cpu_gpu_equivalence": "PASS" if all_match else "FAIL",
        "selected_mode": selected_mode if all_match else "CPU",
        "oracle_gate": (
            "PASS"
            if all_match
            and all(
                workloads[name]["speedup"] >= SPEEDUP_GATE
                for name in ("FULL_HISTORICAL_DAY", "MULTI_DAY_SAMPLE")
            )
            else "FAIL"
        ),
        "next_gpu_workload": "DEFERRED_PENDING_CONCRETE_PROFILED_HOTSPOT",
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_md.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    args.output_md.write_text(_markdown(payload), encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
