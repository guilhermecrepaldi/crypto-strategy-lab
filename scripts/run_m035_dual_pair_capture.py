"""Run the published-source M035 dual-pair public evidence capture."""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

from crypto_strategy_lab.microstructure.m035_dual_pair_capture import (
    CAPTURE_SYMBOLS,
    DualPairForwardCapture,
    M035CaptureError,
)
from crypto_strategy_lab.microstructure.public_market import (
    PublicMarketClient,
    connect_market_stream,
)

ROOT = Path(__file__).resolve().parents[1]
SOURCE_PATHS = (
    "scripts/run_m035_dual_pair_capture.py",
    "src/crypto_strategy_lab/microstructure/m035_dual_pair_capture.py",
    "src/crypto_strategy_lab/microstructure/public_market.py",
    "src/crypto_strategy_lab/microstructure/public_calibration.py",
    "pyproject.toml",
    "uv.lock",
)


def git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=ROOT, check=True, capture_output=True, text=True
    ).stdout.strip()


def verify_published_source(source_sha: str) -> None:
    head = git("rev-parse", "HEAD")
    remote = git("rev-parse", "origin/main")
    if source_sha != head or head != remote:
        raise M035CaptureError("M035_CAPTURE_SOURCE_NOT_PUBLISHED")
    if git("status", "--porcelain", "--", *SOURCE_PATHS):
        raise M035CaptureError("M035_CAPTURE_SOURCE_DIRTY")


def main() -> None:
    parser = argparse.ArgumentParser(description="Capture simultaneous M035 Binance evidence.")
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    if ROOT not in output.parents:
        raise M035CaptureError("M035_CAPTURE_OUTPUT_MUST_BE_INSIDE_REPOSITORY")
    if output.exists():
        raise M035CaptureError("M035_CAPTURE_OUTPUT_ALREADY_EXISTS")
    verify_published_source(args.source_sha)
    capture = DualPairForwardCapture(
        public_client=PublicMarketClient(),
        stream_factory=lambda symbols: connect_market_stream(
            symbols=symbols,
            depth_interval_ms=100,
            forward_depth=True,
        ),
        source_sha=args.source_sha,
    )
    if tuple(capture.states) != CAPTURE_SYMBOLS:
        raise M035CaptureError("M035_CAPTURE_SYMBOL_STATE_MISMATCH")
    result = capture.run(output)
    if result["status"] != "COMPLETE":
        raise M035CaptureError(str(result["failure"]))


if __name__ == "__main__":
    main()
