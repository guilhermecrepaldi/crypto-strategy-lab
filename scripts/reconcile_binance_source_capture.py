"""Archive reader evidence only for official pages returning empty HTTP bodies."""

import hashlib
import json
import urllib.request
from datetime import UTC, datetime
from pathlib import Path


def reconcile(authority: Path) -> None:
    old = authority.read_bytes()
    manifest = json.loads(old)
    base = Path("artifacts/binance/official-sources/20260907-b10-reader")
    base.mkdir(parents=True, exist_ok=True)
    for entry in manifest["sources"]:
        if entry.get("size_bytes", 0) > 0:
            continue
        entry["content_validation"] = "UNAVAILABLE_EMPTY_HTTP_BODY"
        url = "https://r.jina.ai/" + entry["url"]
        record = {
            "reader_url": url,
            "official_source_url": entry["url"],
            "retrieved_at": datetime.now(UTC).isoformat(),
            "evidence_class": "OFFICIAL_SOURCE_VIA_READER_NOT_ORIGINAL_BYTES",
        }
        path = base / (Path(entry.get("path", "unknown")).stem + ".txt")
        if path.exists():
            raise ValueError("Preserve existing reader capture; choose explicit new capture")
        try:
            with urllib.request.urlopen(url, timeout=30) as response:
                raw = response.read()
            path.write_bytes(raw)
            record.update(
                path=str(path),
                sha256=hashlib.sha256(raw).hexdigest(),
                size_bytes=len(raw),
                content_validation="REQUIRES_SEMANTIC_REVIEW",
            )
        except Exception as exc:
            record.update(status="FETCH_FAILED", error=str(exc))
        entry["reader_capture"] = record
    manifest["previous_derived_authority_sha256"] = hashlib.sha256(old).hexdigest()
    manifest["reader_reconciliation_at"] = datetime.now(UTC).isoformat()
    (base / "previous-authority.json").write_bytes(old)
    authority.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(
        [
            (x["url"], x.get("reader_capture", {}).get("size_bytes"))
            for x in manifest["sources"]
            if x.get("reader_capture")
        ]
    )


if __name__ == "__main__":
    reconcile(Path("artifacts/binance/usdcusdt-execution-rules.json"))
