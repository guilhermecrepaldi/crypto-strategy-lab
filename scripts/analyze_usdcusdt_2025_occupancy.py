"""Build the preregistration geometry authority for M020."""

from __future__ import annotations

import argparse
import os
from datetime import UTC, datetime
from pathlib import Path

from crypto_strategy_lab.microstructure.price_occupancy import (
    analyze_price_occupancy,
    load_history_manifest,
    write_occupancy,
)

DEFAULT_MANIFEST = Path("data/manifests/usdcusdt-trades-2025-2026.json")
DEFAULT_OUTPUT = Path("reports/usdcusdt/M020-price-occupancy-2025.json")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--workers", type=int, default=max(1, min(8, os.cpu_count() or 1)))
    args = parser.parse_args()
    manifest = load_history_manifest(args.manifest)
    result = analyze_price_occupancy(
        manifest,
        start=datetime(2025, 1, 1, tzinfo=UTC),
        end_exclusive=datetime(2026, 1, 1, tzinfo=UTC),
        workers=args.workers,
    )
    write_occupancy(args.output, result)
    print(f"OUTPUT={args.output}")
    print(f"RECORDS={result['record_count']}")
    print(f"ANNUAL_LOW={result['annual_low']}")
    print(f"ANNUAL_HIGH={result['annual_high']}")
    for key, interval in result["ranges"].items():
        print(f"{key}_RANGE={interval['low']}..{interval['high']}")


if __name__ == "__main__":
    main()
