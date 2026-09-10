"""Physically revalidate M031's frozen candidate-date pool without performance reads."""

from __future__ import annotations

import hashlib
import json
from concurrent.futures import ProcessPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

from scripts.validate_tardis_l2_samples import (
    MANIFEST,
    ROOT,
    TRADE_MANIFEST,
    TRADE_MANIFEST_SHA256,
    atomic_json,
    validate_work,
)

CANDIDATES = (
    "2025-02-01",
    "2025-03-01",
    "2025-04-01",
    "2025-06-01",
    "2025-08-01",
)
OUTPUT = Path("reports/usdcusdt/M031-date-pool-preflight.json")


def main() -> None:
    manifest_bytes = (ROOT / MANIFEST).read_bytes()
    manifest = json.loads(manifest_bytes)
    trade_bytes = (ROOT / TRADE_MANIFEST).read_bytes()
    if hashlib.sha256(trade_bytes).hexdigest() != TRADE_MANIFEST_SHA256:
        raise ValueError("M031_CANONICAL_TRADE_MANIFEST_CHANGED")
    if manifest["canonical_trade_manifest_sha256"] != TRADE_MANIFEST_SHA256:
        raise ValueError("M031_L2_MANIFEST_BINDS_ANOTHER_TRADE_SOURCE")
    trade_manifest = json.loads(trade_bytes)
    by_date = {row["date"]: row for row in manifest["dates"]}
    if any(day not in by_date for day in CANDIDATES):
        raise ValueError("M031_CANDIDATE_MISSING_FROM_MANIFEST")
    tasks = [(by_date[day], trade_manifest, False, False) for day in CANDIDATES]
    with ProcessPoolExecutor(max_workers=3) as executor:
        days = list(executor.map(validate_work, tasks))
    invalid = [row["date"] for row in days if row.get("status") != "VALIDATED"]
    payload = {
        "schema": "m031-date-pool-physical-preflight-v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "selection_not_yet_drawn": True,
        "performance_metrics_read": False,
        "candidate_dates": list(CANDIDATES),
        "source_manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "canonical_trade_manifest_sha256": TRADE_MANIFEST_SHA256,
        "workers": 3,
        "days": sorted(days, key=lambda row: row["date"]),
        "status": "PASS_ALL_CANDIDATES_VALIDATED" if not invalid else "FAIL",
        "invalid_dates": invalid,
    }
    atomic_json(ROOT / OUTPUT, payload)
    if invalid:
        raise ValueError(f"M031_DATE_POOL_INVALID:{','.join(invalid)}")
    print(json.dumps({"status": payload["status"], "dates": list(CANDIDATES)}))


if __name__ == "__main__":
    main()
