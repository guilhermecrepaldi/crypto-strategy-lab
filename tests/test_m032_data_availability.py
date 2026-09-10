from __future__ import annotations

import json
from pathlib import Path

from crypto_strategy_lab.microstructure.multi_stable_data import build_report


def write_validation(root: Path, symbol: str, date: str, *, valid: bool = True) -> None:
    path = root / "data" / "l2" / "tardis" / "binance" / symbol.lower() / date
    path.mkdir(parents=True)
    payload = {
        "L2_DAY_VALID": valid,
        "CSV_ROWS": 10,
        "TRADES": 5,
        "binding": {"normalized_binding_gate": "PASS"},
        "coverage": {"gate": "PASS"},
    }
    (path / "validation.json").write_text(json.dumps(payload), encoding="utf-8")


def test_multi_book_intersection_requires_two_physical_l2_books(tmp_path: Path) -> None:
    write_validation(tmp_path, "USDCUSDT", "2025-01-01")
    report = build_report(tmp_path)
    assert report["MULTI_BOOK_ELIGIBLE_DATE_POOL"] == []
    assert report["DATA_BLOCKER"] == "MULTI_BOOK_L2_INTERSECTION_EMPTY"
    assert report["READY_FOR_REPLAY"] is False


def test_invalid_book_does_not_create_intersection(tmp_path: Path) -> None:
    write_validation(tmp_path, "USDCUSDT", "2025-01-01")
    write_validation(tmp_path, "FDUSDUSDT", "2025-01-01", valid=False)
    report = build_report(tmp_path)
    assert report["BOOKS_WITH_VALIDATED_LOCAL_L2"] == ["USDCUSDT"]


def test_two_valid_books_create_only_exact_date_intersection(tmp_path: Path) -> None:
    write_validation(tmp_path, "USDCUSDT", "2025-01-01")
    write_validation(tmp_path, "USDCUSDT", "2025-02-01")
    write_validation(tmp_path, "FDUSDUSDT", "2025-02-01")
    report = build_report(tmp_path)
    assert report["MULTI_BOOK_ELIGIBLE_DATE_POOL"] == ["2025-02-01"]
    assert report["DATA_BLOCKER"] is None
    # Replay remains gated on historical symbol rules, fees, universe and preregistration.
    assert report["READY_FOR_REPLAY"] is False
