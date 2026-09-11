"""Bounded public-only USDCUSDT calibration; never sends orders or accesses accounts."""

import argparse
from pathlib import Path

from crypto_strategy_lab.microstructure.public_calibration import collect

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seconds", type=int, default=300)
    args = parser.parse_args()
    result = collect(args.output, seconds=args.seconds)
    print({"status": result["status"], "counts": result["counts"], "failure": result["failure"]})
