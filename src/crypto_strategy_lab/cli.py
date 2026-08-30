from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from crypto_strategy_lab.config import Settings
from crypto_strategy_lab.data.binance import (
    download_verified_archive,
    monthly_kline_url,
    parse_kline_archive,
)
from crypto_strategy_lab.db.persistence import persist_download_manifest, persist_result
from crypto_strategy_lab.fixtures import load_fixture
from crypto_strategy_lab.reporting import write_reports
from crypto_strategy_lab.simulation.engine import SimulationConfig, SimulationEngine
from crypto_strategy_lab.simulation.portfolio import ExecutionCosts

app = typer.Typer(no_args_is_help=True, help="Offline historical crypto strategy lab")


@app.command("simulate-fixture")
def simulate_fixture(
    fixture: Annotated[Path, typer.Option(exists=True)] = Path("fixtures/short_market.json"),
    persist: Annotated[bool, typer.Option(help="Persist append-only events to PostgreSQL")] = True,
    database_url: Annotated[str | None, typer.Option(envvar="CRYPTO_LAB_DATABASE_URL")] = None,
    output_dir: Annotated[Path | None, typer.Option()] = None,
) -> None:
    """Run the small, offline and deterministic vertical slice."""
    settings = Settings()
    candles, provider, _manifest = load_fixture(fixture)
    config = SimulationConfig(
        initial_capital=settings.initial_capital,
        max_exposure=settings.max_exposure,
        reserve_ratio=settings.reserve_ratio,
        costs=ExecutionCosts(
            fee_rate=settings.fee_rate,
            spread_rate=settings.spread_rate,
            slippage_rate=settings.slippage_rate,
        ),
    )
    result = SimulationEngine(candles, provider, config).run()
    json_path, markdown_path = write_reports(result, output_dir or settings.report_dir)
    if persist:
        inserted = persist_result(database_url or settings.database_url, result)
        typer.echo(
            "Database: persisted" if inserted else "Database: deterministic run already exists"
        )
    typer.echo(f"Run ID: {result.run_id}")
    typer.echo(f"JSON: {json_path}")
    typer.echo(f"Markdown: {markdown_path}")


@app.command("download-month")
def download_month(
    symbol: str,
    year: int,
    month: int,
    destination: Annotated[Path, typer.Option()] = Path("data/raw/binance"),
    persist_manifest: Annotated[
        bool, typer.Option(help="Persist the verified dataset manifest")
    ] = True,
    database_url: Annotated[str | None, typer.Option(envvar="CRYPTO_LAB_DATABASE_URL")] = None,
) -> None:
    """Explicitly download and checksum-verify one official 5m monthly archive."""
    url = monthly_kline_url(symbol, year, month)
    manifest = download_verified_archive(url, destination)
    if persist_manifest:
        settings = Settings()
        inserted = persist_download_manifest(database_url or settings.database_url, manifest)
        typer.echo("Manifest: persisted" if inserted else "Manifest: already exists")
    typer.echo(f"Verified {manifest.local_path} ({manifest.sha256})")


@app.command("validate-archive")
def validate_archive(path: Path, symbol: str) -> None:
    """Parse and validate a previously downloaded Binance archive."""
    candles = parse_kline_archive(path, symbol)
    typer.echo(f"Validated {len(candles)} candles for {symbol.upper()}")


if __name__ == "__main__":
    app()
