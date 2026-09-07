"""Audit the frozen B10 raw Binance trade archive without parsing trade rows."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import zipfile
from datetime import date, timedelta
from pathlib import Path


def sha256_file(path: Path, chunk_size: int = 8 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sidecar_hash(path: Path) -> tuple[str | None, str | None]:
    sidecar = Path(f"{path}.CHECKSUM")
    if not sidecar.is_file():
        return None, None
    text = sidecar.read_text(encoding="utf-8", errors="replace").strip()
    match = re.match(r"^([0-9a-fA-F]{64})\s+(.+?)\s*$", text)
    if not match:
        return None, text
    return match.group(1).lower(), match.group(2)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--manifest", type=Path, default=Path("data/manifests/usdcusdt-trades-2025-2026.json")
    )
    parser.add_argument(
        "--output", type=Path, default=Path("reports/usdcusdt/B10-data-manifest-audit.json")
    )
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    archives = manifest["archives"]
    rows: list[dict[str, object]] = []
    for entry in archives:
        path = Path(entry["local_path"])
        item: dict[str, object] = {
            "utc_date": entry["utc_date"],
            "path": str(path),
            "manifest_sha256": entry.get("sha256"),
            "manifest_size_bytes": entry.get("size_bytes"),
            "manifest_record_count": entry.get("record_count"),
            "exists": path.is_file(),
        }
        if path.is_file():
            item["actual_size_bytes"] = path.stat().st_size
            item["actual_sha256"] = sha256_file(path)
            item["manifest_hash_match"] = item["actual_sha256"] == item["manifest_sha256"]
            item["manifest_size_match"] = item["actual_size_bytes"] == item["manifest_size_bytes"]
            checksum, checksum_name = sidecar_hash(path)
            item["sidecar_present"] = checksum is not None
            item["sidecar_sha256"] = checksum
            item["sidecar_filename"] = checksum_name
            item["sidecar_hash_match"] = checksum == item["actual_sha256"] if checksum else None
            with zipfile.ZipFile(path) as archive:
                names = archive.namelist()
                item["zip_members"] = names
                item["zip_member_count"] = len(names)
                item["zip_test"] = archive.testzip() is None
        else:
            item.update(
                {
                    "manifest_hash_match": False,
                    "manifest_size_match": False,
                    "sidecar_present": False,
                }
            )
        rows.append(item)

    expected_dates = []
    cursor = date.fromisoformat(manifest["requested_start"])
    end = date.fromisoformat(manifest["requested_end"])
    while cursor <= end:
        expected_dates.append(cursor.isoformat())
        cursor += timedelta(days=1)
    actual_dates = [str(row["utc_date"]) for row in rows]
    output = {
        "schema": "b10-data-manifest-audit-v1",
        "scope": "READ_ONLY_FULL_RAW_ARCHIVE_SHA256_NO_ROW_PARSE",
        "manifest": str(args.manifest),
        "symbol": manifest["symbol"],
        "requested_start": manifest["requested_start"],
        "requested_end": manifest["requested_end"],
        "canonical_physical_cutoff": "2026-09-05",
        "archive_count": len(rows),
        "expected_daily_count": len(expected_dates),
        "coverage_exact": actual_dates == expected_dates,
        "missing_dates_fresh": sorted(set(expected_dates) - set(actual_dates)),
        "unexpected_dates_fresh": sorted(set(actual_dates) - set(expected_dates)),
        "manifest_declared": {
            "dataset_hash": manifest["dataset_hash"],
            "integrity_status": manifest["integrity_status"],
            "total_records": manifest["total_records"],
            "total_size_bytes": manifest["total_size_bytes"],
            "missing_dates": manifest["missing_dates"],
            "cross_archive_gaps": manifest["cross_archive_gaps"],
            "cross_archive_overlaps": manifest["cross_archive_overlaps"],
        },
        "fresh_aggregate": {
            "existing_count": sum(bool(row["exists"]) for row in rows),
            "manifest_hash_match_count": sum(bool(row.get("manifest_hash_match")) for row in rows),
            "manifest_size_match_count": sum(bool(row.get("manifest_size_match")) for row in rows),
            "sidecar_present_count": sum(bool(row.get("sidecar_present")) for row in rows),
            "sidecar_hash_match_count": sum(bool(row.get("sidecar_hash_match")) for row in rows),
            "zip_test_ok_count": sum(bool(row.get("zip_test")) for row in rows),
            "actual_size_bytes": sum(int(row.get("actual_size_bytes", 0)) for row in rows),
            "actual_record_count_not_reparsed": manifest["total_records"],
        },
        "prior_manifest_parse_evidence": {
            "source": str(args.manifest),
            "row_parsing_performed_by_this_script": False,
            "manifest_declared_gaps": manifest["cross_archive_gaps"],
            "manifest_declared_overlaps": manifest["cross_archive_overlaps"],
            "manifest_declared_duplicate_ranges": [
                row["duplicates"] for row in archives if row["duplicates"]
            ],
            "interpretation": (
                "fresh archive bytes/hashes and ZIP integrity are checked; "
                "275M trade rows are not reparsed"
            ),
        },
        "archives": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "output": str(args.output),
                "archives": len(rows),
                "actual_size_bytes": output["fresh_aggregate"]["actual_size_bytes"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
