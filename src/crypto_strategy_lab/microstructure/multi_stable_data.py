"""Physical evidence inventory for M032; never infer L2 from trades or candles."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

CANDIDATE_BOOKS = (
    "USDCUSDT",
    "FDUSDUSDT",
    "FDUSDUSDC",
    "USD1USDT",
    "USD1USDC",
    "TUSDUSDT",
    "USDPUSDT",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def valid_l2_dates(root: Path, symbol: str) -> list[dict[str, str | int]]:
    symbol_root = root / "data" / "l2" / "tardis" / "binance" / symbol.lower()
    rows: list[dict[str, str | int]] = []
    if not symbol_root.is_dir():
        return rows
    for validation_path in sorted(symbol_root.glob("*/validation.json")):
        payload = json.loads(validation_path.read_text(encoding="utf-8"))
        binding = payload.get("binding", {})
        coverage = payload.get("coverage", {})
        input_binding = payload.get("input_binding", {})
        date = validation_path.parent.name
        l2_path = validation_path.parent / "incremental_book_L2.csv.gz"
        trade_path = (
            root
            / "data"
            / "raw"
            / "binance-microstructure"
            / symbol.upper()
            / "trades"
            / f"{symbol.upper()}-trades-{date}.zip"
        )
        l2_hash = sha256(l2_path) if l2_path.is_file() else None
        trade_hash = sha256(trade_path) if trade_path.is_file() else None
        if not (
            payload.get("L2_DAY_VALID") is True
            and binding.get("normalized_binding_gate") == "PASS"
            and coverage.get("gate") == "PASS"
            and l2_hash == input_binding.get("csv_sha256")
            and trade_hash == input_binding.get("canonical_archive_sha256")
        ):
            continue
        assert l2_hash is not None and trade_hash is not None
        rows.append(
            {
                "date": date,
                "validation_sha256": sha256(validation_path),
                "l2_sha256": l2_hash,
                "trade_archive_sha256": trade_hash,
                "l2_rows": int(payload.get("CSV_ROWS", 0)),
                "trades": int(payload.get("TRADES", 0)),
            }
        )
    return rows


def build_report(root: Path) -> dict[str, object]:
    books = {symbol: valid_l2_dates(root, symbol) for symbol in CANDIDATE_BOOKS}
    books_with_l2 = [symbol for symbol, dates in books.items() if dates]
    date_sets = [{row["date"] for row in books[symbol]} for symbol in books_with_l2]
    multi_book_intersection = sorted(set.intersection(*date_sets)) if len(date_sets) >= 2 else []
    return {
        "MODEL": "M032_ADAPTIVE_MULTI_STABLE_CAPITAL_MANAGER_V1",
        "AUDIT_KIND": "PHYSICAL_L2_AND_CANONICAL_TRADES_ONLY",
        "CANDIDATE_BOOKS": list(CANDIDATE_BOOKS),
        "BOOKS_WITH_VALIDATED_LOCAL_L2": books_with_l2,
        "BOOK_EVIDENCE": books,
        "MULTI_BOOK_ELIGIBLE_DATE_POOL": multi_book_intersection,
        "STABLECOINS_SELECTED_FOR_REPLAY": [],
        "BOOKS_SELECTED_FOR_REPLAY": [],
        "SCORING_WINDOWS": [],
        "SLOT_BASE": "UNRESOLVED_UNTIL_HISTORICAL_RULES_FOR_SELECTED_BOOKS",
        "DATA_BLOCKER": (
            "MULTI_BOOK_L2_INTERSECTION_EMPTY" if not multi_book_intersection else None
        ),
        "READY_FOR_REPLAY": False,
        "PROHIBITED_SUBSTITUTIONS": [
            "OHLC_AS_L2",
            "AGGTRADES_AS_PUBLIC_QUEUE",
            "CURRENT_EXCHANGE_INFO_AS_UNPROVEN_HISTORICAL_RULES",
        ],
    }


__all__ = ["CANDIDATE_BOOKS", "build_report", "sha256", "valid_l2_dates"]
