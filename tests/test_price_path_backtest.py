from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from zipfile import ZipFile

from crypto_strategy_lab.microstructure.price_path import load_price_history, run_campaign


def _daily_archive(
    root: Path,
    day: date,
    rows: list[tuple[int, str, datetime]],
) -> Path:
    path = root / f"FDUSDUSDC-aggTrades-{day.isoformat()}.zip"
    content = "\n".join(
        f"{trade_id},{price},100,{trade_id},{trade_id},"
        f"{int(timestamp.timestamp() * 1_000_000)},false,true"
        for trade_id, price, timestamp in rows
    )
    with ZipFile(path, "w") as archive:
        archive.writestr(path.with_suffix(".csv").name, content)
    return path


def test_continuous_serial_state_crosses_days_and_censors_terminal_position(
    tmp_path: Path,
) -> None:
    start = date(2026, 1, 1)
    archives: list[Path] = []
    trade_id = 1
    for offset in range(8):
        day = start + timedelta(days=offset)
        rows: list[tuple[int, str, datetime]] = [
            (trade_id, "1.0000", datetime(day.year, day.month, day.day, 12, tzinfo=UTC))
        ]
        trade_id += 1
        if offset == 0:
            rows.append(
                (
                    trade_id,
                    "0.9988",
                    datetime(day.year, day.month, day.day, 23, 59, tzinfo=UTC),
                )
            )
            trade_id += 1
        if offset == 7:
            rows.extend(
                [
                    (
                        trade_id,
                        "0.9989",
                        datetime(day.year, day.month, day.day, 1, tzinfo=UTC),
                    ),
                    (
                        trade_id + 1,
                        "0.9988",
                        datetime(day.year, day.month, day.day, 2, tzinfo=UTC),
                    ),
                ]
            )
            trade_id += 2
        archives.append(_daily_archive(tmp_path, day, rows))

    history, total = load_price_history(
        archives,
        kind="aggTrades",
        lower=Decimal("0.9988"),
        upper=Decimal("0.9989"),
    )
    campaign = run_campaign(
        history,
        dataset_hash="fixture",
        archive_count=len(archives),
        total_records=total,
    )

    maximum = campaign.horizon_results[-1]
    assert maximum.completed_serial_cycles == 1
    assert campaign.cycles[0].holding_seconds == Decimal("522060")
    assert maximum.open_position_at_end is not None
    assert maximum.open_position_at_end.status == "OPEN_AT_DATASET_END"
    assert maximum.open_position_at_end.entry_time.day == 8
    rolling_second = next(
        item for item in campaign.rolling_results if item.label == "ROLLING_7D_2026-01-02"
    )
    assert rolling_second.carried_in_position is True
    assert rolling_second.closed_in_window == 1
    assert rolling_second.carried_out_position is True


def test_capital_scenarios_compound_only_after_complete_cycles(tmp_path: Path) -> None:
    day = date(2026, 1, 1)
    rows = [
        (1, "0.9988", datetime(2026, 1, 1, 1, tzinfo=UTC)),
        (2, "0.9989", datetime(2026, 1, 1, 2, tzinfo=UTC)),
        (3, "0.9988", datetime(2026, 1, 1, 3, tzinfo=UTC)),
        (4, "0.9989", datetime(2026, 1, 1, 4, tzinfo=UTC)),
    ]
    history, total = load_price_history(
        [_daily_archive(tmp_path, day, rows)],
        kind="aggTrades",
        lower=Decimal("0.9988"),
        upper=Decimal("0.9989"),
    )

    first = run_campaign(history, dataset_hash="same", archive_count=1, total_records=total)
    second = run_campaign(history, dataset_hash="same", archive_count=1, total_records=total)
    maximum = first.horizon_results[-1]
    zero_fee = next(
        item
        for item in maximum.capital_outcomes
        if item.initial_capital == 1000 and item.fee_scenario.name == "SCENARIO_ZERO_MAKER"
    )
    stressed = next(
        item
        for item in maximum.capital_outcomes
        if item.initial_capital == 1000 and item.fee_scenario.name == "SCENARIO_STRESS_MAKER_1BP"
    )

    assert zero_fee.completed_cycles == 2
    assert zero_fee.final_capital_compounding > zero_fee.final_capital_fixed_lot
    assert stressed.economic_status == "ECONOMIC_NO_GO_FOR_THIS_FEE_SCENARIO"
    assert first.model_dump(mode="json") == second.model_dump(mode="json")
