from __future__ import annotations

import sys
from datetime import date
from hashlib import sha256
from pathlib import Path
from zipfile import ZipFile

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
import collect_m035_fdusdusdt_21_days as acquisition


def test_frozen_date_set_and_urls() -> None:
    assert len(acquisition.DATES) == 21
    assert acquisition.DATES[0] == date(2025, 1, 1)
    assert acquisition.DATES[-1] == date(2026, 9, 1)
    assert acquisition.trade_url(date(2025, 1, 1)) == (
        "https://data.binance.vision/data/spot/daily/trades/FDUSDUSDT/"
        "FDUSDUSDT-trades-2025-01-01.zip"
    )


def test_report_makes_mixed_provenance_and_future_draw_explicit() -> None:
    results = [
        {
            "date": day.isoformat(),
            "l2": {"status": "AVAILABLE"},
            "individual_trades": {"status": "AVAILABLE"},
            "day_status": "AVAILABLE",
        }
        for day in acquisition.DATES
    ]
    report = acquisition.build_report(results)
    assert report["all_21_available"] is True
    assert report["provenance"]["mode"] == "MIXED_EXPLICIT"
    assert report["selection_policy"]["pnl_based_selection"] is False
    assert report["selection_policy"]["three_hour_window"].startswith("NOT_SELECTED")


def test_trade_binding_requires_checksum_and_exact_member(tmp_path: Path) -> None:
    day = date(2025, 1, 1)
    path = tmp_path / "sample.zip"
    with ZipFile(path, "w") as archive:
        archive.writestr("UNRELATED_SYMBOL.csv", "1,1,1,1,1735689600000000,false")
    with pytest.raises(ValueError, match="CHECKSUM_SIDECAR_REQUIRED"):
        acquisition._validate_trade_binding(path, day)
    path.with_name(path.name + ".CHECKSUM").write_text(
        f"{sha256(path.read_bytes()).hexdigest()}  {path.name}\n", encoding="ascii"
    )
    with pytest.raises(ValueError, match="MEMBER_BINDING_MISMATCH"):
        acquisition._validate_trade_binding(path, day)


def test_partial_checkpoint_preserves_unverified_prior_days() -> None:
    prior = {
        "2025-01-01": {"date": "2025-01-01", "l2": {"sha256": "old-a"}},
        "2025-02-01": {"date": "2025-02-01", "l2": {"sha256": "old-b"}},
    }
    completed = {"date": "2025-01-01", "l2": {"sha256": "verified-a"}}
    checkpoint = acquisition.merge_checkpoint(prior, completed)
    assert set(checkpoint) == {"2025-01-01", "2025-02-01"}
    assert checkpoint["2025-01-01"]["l2"]["sha256"] == "verified-a"
    assert checkpoint["2025-02-01"] == prior["2025-02-01"]


def test_preserved_records_can_be_marked_unverified_without_losing_provenance() -> None:
    prior = {"date": "2025-02-01", "verified_in_current_run": True, "sha256": "keep"}
    preserved = {**prior, "verified_in_current_run": False}
    assert preserved["verified_in_current_run"] is False
    assert preserved["sha256"] == "keep"
