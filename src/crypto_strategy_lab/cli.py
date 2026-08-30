from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path
from typing import Annotated

import typer

from crypto_strategy_lab.config import Settings
from crypto_strategy_lab.data.binance import (
    download_verified_archive,
    monthly_kline_url,
    parse_kline_archive,
)
from crypto_strategy_lab.data.history import (
    GapPolicy,
    HistoricalCatalogManifest,
    discover_historical_catalog,
    download_history_period,
    ingest_history_period,
    parse_utc_date,
    rank_catalog_by_daily_quote_volume,
    verify_local_archives,
)
from crypto_strategy_lab.data.history_reporting import (
    build_history_audit,
    write_daily_liquidity_audit,
    write_history_audit,
)
from crypto_strategy_lab.db.persistence import persist_download_manifest, persist_result
from crypto_strategy_lab.fixtures import load_fixture
from crypto_strategy_lab.ml.historical_reporting import write_historical_smoke
from crypto_strategy_lab.ml.historical_workflow import run_historical_smoke
from crypto_strategy_lab.ml.persistence import persist_ml_evaluation
from crypto_strategy_lab.ml.reporting import write_ml_reports
from crypto_strategy_lab.ml.workflow import run_short_training, workflow_payload
from crypto_strategy_lab.reporting import write_reports
from crypto_strategy_lab.simulation.engine import SimulationConfig, SimulationEngine
from crypto_strategy_lab.simulation.portfolio import ExecutionCosts

app = typer.Typer(no_args_is_help=True, help="Offline historical crypto strategy lab")


def _symbols(value: str) -> list[str]:
    symbols = sorted({item.strip().upper() for item in value.split(",") if item.strip()})
    if not symbols:
        raise typer.BadParameter("at least one comma-separated symbol is required")
    return symbols


def _integers(value: str, *, label: str) -> tuple[int, ...]:
    try:
        parsed = tuple(int(item.strip()) for item in value.split(",") if item.strip())
    except ValueError as error:
        raise typer.BadParameter(f"{label} must be comma-separated integers") from error
    if not parsed:
        raise typer.BadParameter(f"at least one {label} value is required")
    return parsed


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


@app.command("history-download")
def history_download(
    symbols: Annotated[str, typer.Option(help="Comma-separated historical candidate symbols")],
    start: Annotated[str, typer.Option(help="Inclusive UTC date, YYYY-MM-DD")],
    end: Annotated[str, typer.Option(help="Exclusive UTC date, YYYY-MM-DD")],
    destination: Annotated[Path, typer.Option()] = Path("data/raw/binance"),
    allow_unavailable: Annotated[
        bool, typer.Option(help="Record historical 404s instead of treating them as success")
    ] = False,
    interval: Annotated[str, typer.Option(help="5m canonical data or 1d ranking data")] = "5m",
    max_workers: Annotated[int, typer.Option(min=1, max=64)] = 8,
) -> None:
    """Download official monthly Spot archives with published checksums."""
    batch = download_history_period(
        _symbols(symbols),
        start=parse_utc_date(start),
        end=parse_utc_date(end),
        destination=destination,
        allow_unavailable=allow_unavailable,
        interval=interval,
        max_workers=max_workers,
    )
    batch_path = destination / "download-batch.json"
    batch_path.write_text(
        json.dumps(
            {
                "verified": [
                    {
                        **item.__dict__,
                        "local_path": str(item.local_path),
                        "ingested_at": item.ingested_at.isoformat(),
                    }
                    for item in batch.verified
                ],
                "unavailable_urls": batch.unavailable_urls,
            },
            indent=2,
            sort_keys=True,
            default=str,
        )
        + "\n",
        encoding="utf-8",
    )
    typer.echo(
        f"Verified {len(batch.verified)} archives; unavailable={len(batch.unavailable_urls)}"
    )
    typer.echo(f"Batch manifest: {batch_path}")


@app.command("history-catalog")
def history_catalog(
    effective_at: Annotated[str, typer.Option(help="Episode UTC date, YYYY-MM-DD")],
    lookback_days: Annotated[int, typer.Option(min=1)] = 90,
    output: Annotated[Path, typer.Option()] = Path("data/catalog/historical-catalog.json"),
    max_workers: Annotated[int, typer.Option(min=1, max=64)] = 16,
) -> None:
    """Discover pairs proven by archived files, never by current exchange status."""
    catalog = discover_historical_catalog(
        effective_at=parse_utc_date(effective_at),
        lookback=timedelta(days=lookback_days),
        max_workers=max_workers,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(catalog.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    typer.echo(f"Archive-backed historical pairs: {len(catalog.entries)}")
    typer.echo(f"Catalog: {output} ({catalog.catalog_hash})")


@app.command("history-rank")
def history_rank(
    catalog: Annotated[Path, typer.Option(exists=True)],
    raw_root: Annotated[Path, typer.Option()] = Path("data/raw/binance"),
    output_dir: Annotated[Path, typer.Option()] = Path("reports"),
) -> None:
    """Rank archive-backed pairs with complete historical daily quote volume."""
    parsed = HistoricalCatalogManifest.model_validate_json(catalog.read_text(encoding="utf-8"))
    audit = rank_catalog_by_daily_quote_volume(parsed, raw_root=raw_root)
    json_path, markdown_path = write_daily_liquidity_audit(audit, output_dir)
    typer.echo(f"Selected: {', '.join(audit.selected_symbols)}")
    typer.echo(f"JSON: {json_path}")
    typer.echo(f"Markdown: {markdown_path}")


@app.command("history-verify")
def history_verify(
    symbols: Annotated[str, typer.Option(help="Comma-separated symbols")],
    start: Annotated[str, typer.Option(help="Inclusive UTC date, YYYY-MM-DD")],
    end: Annotated[str, typer.Option(help="Exclusive UTC date, YYYY-MM-DD")],
    raw_root: Annotated[Path, typer.Option()] = Path("data/raw/binance"),
) -> None:
    """Offline-verify checksums and parse every requested archive."""
    evidence = verify_local_archives(
        _symbols(symbols),
        start=parse_utc_date(start),
        end=parse_utc_date(end),
        raw_root=raw_root,
    )
    candle_count = sum(item.candle_count for item in evidence)
    typer.echo(f"Verified {len(evidence)} archives and {candle_count} candles")


@app.command("history-ingest")
def history_ingest(
    symbols: Annotated[str, typer.Option(help="Comma-separated symbols")],
    start: Annotated[str, typer.Option(help="Inclusive UTC date, YYYY-MM-DD")],
    end: Annotated[str, typer.Option(help="Exclusive UTC date, YYYY-MM-DD")],
    raw_root: Annotated[Path, typer.Option()] = Path("data/raw/binance"),
    normalized_path: Annotated[Path, typer.Option()] = Path("data/processed/history.jsonl.gz"),
    manifest_path: Annotated[Path, typer.Option()] = Path("data/manifests/history.json"),
    gap_policy: Annotated[str, typer.Option(help="STOP or INVALIDATE_EPISODE")] = "STOP",
) -> None:
    """Normalize verified archives into one deterministic, offline dataset."""
    try:
        policy = GapPolicy(gap_policy.upper())
    except ValueError as error:
        raise typer.BadParameter("gap-policy must be STOP or INVALIDATE_EPISODE") from error
    manifest = ingest_history_period(
        _symbols(symbols),
        start=parse_utc_date(start),
        end=parse_utc_date(end),
        raw_root=raw_root,
        normalized_path=normalized_path,
        manifest_path=manifest_path,
        gap_policy=policy,
    )
    typer.echo(
        f"Ingested {manifest.candle_count} candles; gaps="
        f"{sum(item.missing_count for item in manifest.coverage)}"
    )
    typer.echo(f"Dataset: {normalized_path}")
    typer.echo(f"Manifest: {manifest_path} ({manifest.dataset_hash})")


@app.command("history-audit")
def history_audit(
    manifest: Annotated[Path, typer.Option(exists=True)],
    episode_start: Annotated[str, typer.Option(help="Episode UTC date, YYYY-MM-DD")],
    lookback_days: Annotated[int, typer.Option(min=1)] = 90,
    output_dir: Annotated[Path, typer.Option()] = Path("reports"),
) -> None:
    """Prove historical eligibility and causal liquidity ranking before an episode."""
    payload = build_history_audit(
        manifest,
        episode_start=parse_utc_date(episode_start),
        lookback_days=lookback_days,
    )
    json_path, markdown_path = write_history_audit(payload, output_dir)
    typer.echo(f"Selected: {', '.join(payload['selection']['selected_symbols'])}")
    typer.echo(f"JSON: {json_path}")
    typer.echo(f"Markdown: {markdown_path}")


@app.command("history-smoke")
def history_smoke(
    manifest: Annotated[Path, typer.Option(exists=True)],
    train_start: Annotated[str, typer.Option(help="TRAIN start UTC date")],
    validation_start: Annotated[str, typer.Option(help="VALIDATION start UTC date")],
    validation_end: Annotated[str, typer.Option(help="VALIDATION end-exclusive UTC date")],
    durations: Annotated[str, typer.Option(help="Restricted to comma-separated 30,90")] = "30,90",
    seeds: Annotated[str, typer.Option(help="Predeclared comma-separated seeds")] = "11,29",
    timesteps: Annotated[int, typer.Option(min=1)] = 16,
    artifact_dir: Annotated[Path, typer.Option()] = Path("artifacts/historical-models"),
    output_dir: Annotated[Path, typer.Option()] = Path("reports"),
) -> None:
    """Run bounded TRAIN/VALIDATION comparisons; LOCKED_TEST is forbidden."""
    payload = run_historical_smoke(
        manifest,
        train_start=parse_utc_date(train_start),
        validation_start=parse_utc_date(validation_start),
        validation_end=parse_utc_date(validation_end),
        durations_days=_integers(durations, label="duration"),
        seeds=_integers(seeds, label="seed"),
        total_timesteps=timesteps,
        artifact_dir=artifact_dir,
    )
    json_path, markdown_path = write_historical_smoke(payload, output_dir)
    typer.echo(f"Completed {len(payload['runs'])} policy/seed runs")
    typer.echo(f"JSON: {json_path}")
    typer.echo(f"Markdown: {markdown_path}")


@app.command("rl-train")
def rl_train(
    train_fixture: Annotated[Path, typer.Option(exists=True)] = Path("fixtures/short_market.json"),
    validation_fixture: Annotated[Path, typer.Option(exists=True)] = Path(
        "fixtures/rl_validation_market.json"
    ),
    algorithm: Annotated[str, typer.Option(help="PPO or DQN")] = "PPO",
    timesteps: Annotated[int, typer.Option(min=1)] = 64,
    seed: int = 42,
    artifact_dir: Annotated[Path, typer.Option()] = Path("artifacts/models"),
    output_dir: Annotated[Path, typer.Option()] = Path("reports"),
    persist: Annotated[bool, typer.Option(help="Persist ML events and artifacts metadata")] = True,
    database_url: Annotated[str | None, typer.Option(envvar="CRYPTO_LAB_DATABASE_URL")] = None,
) -> None:
    """Train a short PPO/DQN run and evaluate on a separate fixture."""
    _run_rl_workflow(
        train_fixture=train_fixture,
        validation_fixture=validation_fixture,
        algorithm=algorithm,
        timesteps=timesteps,
        seed=seed,
        artifact_dir=artifact_dir,
        output_dir=output_dir,
        persist=persist,
        database_url=database_url,
        require_existing_checkpoint=False,
    )


@app.command("rl-evaluate")
def rl_evaluate(
    train_fixture: Annotated[Path, typer.Option(exists=True)] = Path("fixtures/short_market.json"),
    validation_fixture: Annotated[Path, typer.Option(exists=True)] = Path(
        "fixtures/rl_validation_market.json"
    ),
    algorithm: Annotated[str, typer.Option(help="PPO or DQN")] = "PPO",
    timesteps: Annotated[int, typer.Option(min=1)] = 64,
    seed: int = 42,
    artifact_dir: Annotated[Path, typer.Option()] = Path("artifacts/models"),
    output_dir: Annotated[Path, typer.Option()] = Path("reports"),
    persist: Annotated[bool, typer.Option(help="Persist evaluation events")] = True,
    database_url: Annotated[str | None, typer.Option(envvar="CRYPTO_LAB_DATABASE_URL")] = None,
) -> None:
    """Evaluate the immutable checkpoint identified by training configuration."""
    _run_rl_workflow(
        train_fixture=train_fixture,
        validation_fixture=validation_fixture,
        algorithm=algorithm,
        timesteps=timesteps,
        seed=seed,
        artifact_dir=artifact_dir,
        output_dir=output_dir,
        persist=persist,
        database_url=database_url,
        require_existing_checkpoint=True,
    )


def _run_rl_workflow(
    *,
    train_fixture: Path,
    validation_fixture: Path,
    algorithm: str,
    timesteps: int,
    seed: int,
    artifact_dir: Path,
    output_dir: Path,
    persist: bool,
    database_url: str | None,
    require_existing_checkpoint: bool,
) -> None:
    if algorithm.upper() not in {"PPO", "DQN"}:
        raise typer.BadParameter("algorithm must be PPO or DQN")
    result = run_short_training(
        train_fixture=train_fixture,
        validation_fixture=validation_fixture,
        artifact_dir=artifact_dir,
        total_timesteps=timesteps,
        seed=seed,
        algorithm=algorithm.upper(),
        require_existing_checkpoint=require_existing_checkpoint,
    )
    json_path, markdown_path = write_ml_reports(workflow_payload(result), output_dir)
    if persist:
        settings = Settings()
        url = database_url or settings.database_url
        run_id, inserted = persist_ml_evaluation(
            url,
            env=result.validation_env,
            normalizer=result.normalizer,
            evaluation=result.evaluation,
            artifact=result.artifact,
        )
        for baseline in result.baselines:
            persist_ml_evaluation(
                url,
                env=result.validation_env,
                normalizer=result.normalizer,
                evaluation=baseline,
                artifact=None,
            )
        typer.echo(f"Database run: {run_id} ({'inserted' if inserted else 'existing'})")
    typer.echo(
        f"Model: {result.artifact.model_id} ({'reused' if result.artifact.reused else 'trained'})"
    )
    typer.echo(f"Checkpoint: {result.artifact.checkpoint_path}")
    typer.echo(f"JSON: {json_path}")
    typer.echo(f"Markdown: {markdown_path}")


if __name__ == "__main__":
    app()
