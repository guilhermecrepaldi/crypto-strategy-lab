from datetime import UTC, datetime
from decimal import Decimal

from crypto_strategy_lab.microstructure.models import TradeEvent
from crypto_strategy_lab.microstructure.price_path import PriceHistory, run_campaign
from crypto_strategy_lab.microstructure.reporting import write_backtest_reports


def test_reports_are_complete_self_contained_and_deterministic(tmp_path):
    low = TradeEvent(
        trade_id=1,
        sequence=1,
        timestamp=datetime(2026, 1, 1, 1, tzinfo=UTC),
        price=Decimal("0.9988"),
        quantity=Decimal("10"),
        buyer_is_maker=False,
    )
    high = TradeEvent(
        trade_id=2,
        sequence=2,
        timestamp=datetime(2026, 1, 1, 2, tzinfo=UTC),
        price=Decimal("0.9989"),
        quantity=Decimal("10"),
        buyer_is_maker=True,
    )
    history = PriceHistory(
        relevant_events=(low, high),
        day_last_prices={high.timestamp.date(): (high.timestamp, high.price)},
        first_timestamp=low.timestamp,
        last_timestamp=high.timestamp,
    )
    campaign = run_campaign(
        history,
        dataset_hash="dataset",
        archive_count=1,
        total_records=2,
    )
    markdown = tmp_path / "BACKTEST_REPORT.md"

    outputs = write_backtest_reports(campaign, tmp_path / "reports", markdown_output=markdown)
    first_summary = outputs["summary"].read_bytes()
    write_backtest_reports(campaign, tmp_path / "reports", markdown_output=markdown)

    assert outputs["summary"].read_bytes() == first_summary
    assert "BACKTEST_INCONCLUSIVE" in first_summary.decode()
    assert "Price-path evidence only" in outputs["html"].read_text(encoding="utf-8")
    assert "<svg" in outputs["html"].read_text(encoding="utf-8")
    assert "execution remains `INCONCLUSIVE`" in markdown.read_text(encoding="utf-8")
    assert outputs["periods"].stat().st_size > 0
    assert outputs["cycles"].stat().st_size > 0
