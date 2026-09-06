from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from zipfile import ZipFile

from crypto_strategy_lab.microstructure.workflow import audit_trade_levels, run_s0_fixture


def _trade_archive(path: Path) -> Path:
    timestamps = [
        1_725_148_800_000,
        1_725_148_801_000,
        1_725_148_803_000,
        1_725_148_806_000,
    ]
    prices = ["0.9988", "0.9989", "0.9988", "0.9989"]
    rows = [
        f"{index},{price},1,{index},{index},{timestamp},false,true"
        for index, (price, timestamp) in enumerate(zip(prices, timestamps, strict=True), start=1)
    ]
    with ZipFile(path, "w") as archive:
        archive.writestr("FDUSDUSDC-aggTrades-fixture.csv", "\n".join(rows))
    return path


def test_frequency_audit_separates_paths_cycles_durations_and_fee_roles(tmp_path: Path) -> None:
    archive = _trade_archive(tmp_path / "sample.zip")

    audit = audit_trade_levels(
        archive,
        kind="aggTrades",
        source_url="https://data.binance.vision/sample.zip",
        period="fixture",
        lower=Decimal("0.9988"),
        upper=Decimal("0.9989"),
    )

    assert audit.completed_observed_paths == 2
    assert audit.observed_high_to_low_paths == 1
    assert audit.observed_low_high_low_cycles == 1
    assert audit.low_to_high_duration_seconds["p50"] == Decimal("2")
    assert audit.low_high_low_duration_seconds["max"] == Decimal("3")
    assert audit.can_2000_cycles_on_observed_day == "NO_PRICE_PATH_UPPER_BOUND_BELOW_TARGET"
    scenarios = audit.fee_scenarios_quote_pnl_per_100
    assert scenarios["maker_zero_taker_10bps:MAKER->MAKER"] == Decimal("0.0100")
    assert scenarios["maker_zero_taker_10bps:MAKER->TAKER"] < 0


def test_fixture_uses_entire_compounding_lot_without_binary_float() -> None:
    fixture = Path("fixtures/microstructure_s0.json")

    artifact = run_s0_fixture(fixture)

    assert artifact.result.metrics["cycle_count"] == 1
    assert artifact.result.ledger.fdusd == 0
    assert artifact.result.ledger.usdc == Decimal("1000.100120")
    assert artifact.result.orders[0].quantity == Decimal("1001.20")
    assert artifact.result.decisions[0].latest_input_timestamp == datetime(2026, 9, 5, tzinfo=UTC)
