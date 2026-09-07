"""Capture official source bytes and public observations; never private endpoints."""

from __future__ import annotations

import argparse
import hashlib
import json
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

from crypto_strategy_lab.microstructure.public_market import PublicMarketClient

SOURCES = {
    "web-socket-streams.md": "https://raw.githubusercontent.com/binance/binance-spot-api-docs/master/web-socket-streams.md",
    "rest-api.md": "https://raw.githubusercontent.com/binance/binance-spot-api-docs/master/rest-api.md",
    "filters.md": "https://raw.githubusercontent.com/binance/binance-spot-api-docs/master/filters.md",
    "CHANGELOG.md": "https://raw.githubusercontent.com/binance/binance-spot-api-docs/master/CHANGELOG.md",
    "commission_faq.md": "https://raw.githubusercontent.com/binance/binance-spot-api-docs/master/faqs/commission_faq.md",
    "order_count_decrement.md": "https://raw.githubusercontent.com/binance/binance-spot-api-docs/master/faqs/order_count_decrement.md",
    "order_amend_keep_priority.md": "https://raw.githubusercontent.com/binance/binance-spot-api-docs/master/faqs/order_amend_keep_priority.md",
    "price_range_execution_rules.md": "https://raw.githubusercontent.com/binance/binance-spot-api-docs/master/faqs/price_range_execution_rules.md",
    "public-data-readme.md": "https://raw.githubusercontent.com/binance/binance-public-data/master/README.md",
    "tick-announcement.html": "https://www.binance.com/en/support/announcement/detail/1f1ee792db2d445eb967aa09f6c05138",
    "fee-table.html": "https://www.binance.com/en/fee/trading",
    "march-zero-fee.html": "https://www.binance.com/lo-LA/support/announcement/detail/4c2852795e0a49a0bf72cd83714f743b",
    "summer-zero-fee.html": "https://www.binance.com/en/support/announcement/detail/a6f02526afd1466ab72fe29af4c84c67",
}


def capture(output: Path) -> dict:
    output.mkdir(parents=True, exist_ok=False)
    records = []
    for name, url in SOURCES.items():
        entry = {
            "url": url,
            "retrieved_at": datetime.now(UTC).isoformat(),
            "evidence_class": "OFFICIAL_RULE",
            "historical_applicability": "SEE_RULE_TIMELINE",
        }
        try:
            with urllib.request.urlopen(url, timeout=25) as response:
                content = response.read()
                entry.update(
                    status=response.status,
                    final_url=response.url,
                    headers=dict(response.headers),
                    sha256=hashlib.sha256(content).hexdigest(),
                    size_bytes=len(content),
                    path=str(output / name),
                )
            (output / name).write_bytes(content)
            # A successful HTTP response alone is not semantic validation of a WAF/JS page.
            entry["content_validation"] = "REQUIRES_SEMANTIC_REVIEW"
        except (urllib.error.URLError, TimeoutError) as exc:
            entry.update(status="FETCH_FAILED", error=str(exc))
        records.append(entry)
    client = PublicMarketClient()
    observations = []
    for endpoint in ("exchangeInfo", "executionRules", "referencePrice"):
        entry = {
            "endpoint": endpoint,
            "evidence_class": "OBSERVED",
            "historical_application": "UNKNOWN_DO_NOT_BACKPROJECT",
        }
        try:
            payload = client._request_json("/api/v3/" + endpoint, {"symbol": "USDCUSDT"})
            entry.update(payload=payload, receipt=client.last_response)
            body = client.last_response["body"].encode("utf-8")
            path = output / (endpoint + ".json")
            path.write_bytes(body)
            entry.update(sha256=hashlib.sha256(body).hexdigest(), path=str(path))
        except Exception as exc:
            entry.update(status="FETCH_FAILED", error=str(exc))
        observations.append(entry)
    result = {
        "schema": "binance-usdcusdt-execution-authority-v1",
        "strategy": "B10_FROZEN",
        "execution_profile": "BINANCE_REALITY_V1",
        "retrieved_at": datetime.now(UTC).isoformat(),
        "symbol": "USDCUSDT",
        "sources": records,
        "current_observations": observations,
        "fee_evidence": "UNKNOWN_HISTORICAL_EXACT",
        "account_commission": "UNKNOWN_NOT_AUTHORIZED",
        "historical_l2": "NOT_LOCATED_PUBLIC_OFFICIAL",
        "rule_timeline": "reports/usdcusdt/B10-binance-rule-timeline.json",
    }
    (output / "manifest.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Refresh derived authority, preserve previous raw capture and hash",
    )
    args = parser.parse_args()
    result = capture(args.output)
    authority = Path("artifacts/binance/usdcusdt-execution-rules.json")
    if authority.exists():
        if not args.refresh:
            raise SystemExit("Existing authority: use --refresh to preserve prior provenance")
        previous = authority.read_bytes()
        old = json.loads(previous)
        result["supersedes_authority_sha256"] = hashlib.sha256(previous).hexdigest()
        result["previous_capture_manifest"] = str(
            Path(old["sources"][0]["path"]).parent / "manifest.json"
        )
        result["correction"] = (
            "Public executionRules/referencePrice fixed-host mapping to api.binance.com; "
            "data-api.binance.vision returned404. Prior failed observations preserved."
        )
    authority.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(
        {
            "sources": len(result["sources"]),
            "observations": [
                (x["endpoint"], x.get("status", "CAPTURED")) for x in result["current_observations"]
            ],
        }
    )
