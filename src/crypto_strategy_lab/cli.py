from __future__ import annotations

import json
import subprocess
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Literal, cast

import typer

from crypto_strategy_lab.analytics.dashboard import (
    resolve_run_report,
    write_dashboard,
    write_learning_dashboard,
)
from crypto_strategy_lab.analytics.divergence import analyze_divergence
from crypto_strategy_lab.analytics.experiments import run_turnover_study
from crypto_strategy_lab.analytics.schemas import ReportProvenance
from crypto_strategy_lab.analytics.walk_forward import WalkForwardPlan
from crypto_strategy_lab.config import Settings
from crypto_strategy_lab.data.binance import (
    download_verified_archive,
    monthly_kline_url,
    parse_kline_archive,
)
from crypto_strategy_lab.data.history import (
    GapPolicy,
    HistoricalCatalogManifest,
    HistoricalDatasetManifest,
    discover_historical_catalog,
    download_history_period,
    ingest_history_period,
    load_normalized_history,
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
from crypto_strategy_lab.microstructure.data import download_archive, manifest_for, parse_archive
from crypto_strategy_lab.microstructure.workflow import (
    audit_trade_levels,
    run_s0_fixture,
    write_artifact,
)
from crypto_strategy_lab.ml.candidate_workflow import run_candidate_strategy
from crypto_strategy_lab.ml.controlled_workflow import (
    run_controlled_training,
    run_controlled_validation,
)
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


@app.command("analyze-divergence")
def analyze_divergence_command(
    manifest: Annotated[Path, typer.Option(exists=True)],
    start: Annotated[str, typer.Option(help="Inclusive UTC date")],
    end: Annotated[str, typer.Option(help="Exclusive UTC date")],
    timeframe: Annotated[str, typer.Option(help="15m, 30m or 1h")] = "15m",
    output: Annotated[Path, typer.Option()] = Path("reports/divergence.json"),
) -> None:
    """Analyze causal divergence and separate post-event diagnostics offline."""
    timeframe_minutes = {"15m": 15, "30m": 30, "1h": 60}.get(timeframe.lower())
    if timeframe_minutes is None:
        raise typer.BadParameter("timeframe must be 15m, 30m or 1h")
    parsed = HistoricalDatasetManifest.model_validate_json(manifest.read_text(encoding="utf-8"))
    if parsed.locked_test_accessed:
        raise typer.BadParameter("LOCKED_TEST is forbidden")
    start_at, end_at = parse_utc_date(start), parse_utc_date(end)
    report = analyze_divergence(
        load_normalized_history(Path(parsed.normalized_path)),
        start=start_at,
        end=end_at,
        timeframe_minutes=timeframe_minutes,
        provenance=ReportProvenance(
            dataset_hash=parsed.dataset_hash,
            period_start=start_at.isoformat(),
            period_end=end_at.isoformat(),
            timeframe=timeframe.lower(),
            symbols=parsed.symbols,
            configuration={
                "strong_move_thresholds": {"15m": "0.005", "1h": "0.01"},
                "lead_lag_periods": [-6, 6],
            },
            seed=None,
            policy="post-event-diagnostic-not-agent-observation",
            execution_costs={key: str(value) for key, value in ExecutionCosts().__dict__.items()},
            code_version=_code_version(),
            partition="TRAIN" if end_at <= parse_utc_date("2022-04-01") else "VALIDATION",
        ),
        costs=ExecutionCosts(),
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    typer.echo(f"Divergence report: {output}")


@app.command("turnover-study")
def turnover_study(
    manifest: Annotated[Path, typer.Option(exists=True)],
    start: Annotated[str, typer.Option()] = "2022-01-01",
    end: Annotated[str, typer.Option()] = "2022-01-31",
    seeds: Annotated[str, typer.Option()] = "11,29",
    timesteps: Annotated[int, typer.Option(min=1)] = 16,
    artifact_dir: Annotated[Path, typer.Option()] = Path("artifacts/turnover-models"),
    output_dir: Annotated[Path, typer.Option()] = Path("reports"),
) -> None:
    """Run the bounded, predefined turnover sensitivity study on TRAIN only."""
    payload = run_turnover_study(
        manifest,
        start=parse_utc_date(start),
        end=parse_utc_date(end),
        seeds=_integers(seeds, label="seed"),
        timesteps=timesteps,
        artifact_dir=artifact_dir,
        output_dir=output_dir,
    )
    typer.echo(f"Completed {len(payload['runs'])} predefined TRAIN runs")
    typer.echo(f"Report: {output_dir / 'turnover-sensitivity.json'}")


@app.command("dashboard")
def dashboard(
    run_id: Annotated[str, typer.Option()],
    output: Annotated[Path, typer.Option()] = Path("reports/dashboard.html"),
    reports_dir: Annotated[Path, typer.Option()] = Path("reports"),
    divergence: Annotated[Path | None, typer.Option()] = None,
) -> None:
    """Generate a deterministic, self-contained offline experiment dashboard."""
    divergence_path = divergence or reports_dir / "divergence.json"
    manifest = write_dashboard(
        resolve_run_report(run_id, reports_dir),
        output,
        divergence_path=divergence_path if divergence_path.exists() else None,
    )
    typer.echo(f"Dashboard: {output} ({manifest.output_sha256})")


@app.command("prepare-walk-forward")
def prepare_walk_forward(
    start: Annotated[str, typer.Option()] = "2022-01-01",
    end: Annotated[str, typer.Option()] = "2022-07-01",
    train_days: Annotated[int, typer.Option(min=1)] = 90,
    validation_days: Annotated[int, typer.Option(min=1)] = 30,
    step_days: Annotated[int, typer.Option(min=1)] = 30,
    output: Annotated[Path, typer.Option()] = Path("reports/walk-forward-plan.json"),
) -> None:
    """Prepare and validate a walk-forward plan without executing any episode."""
    plan = WalkForwardPlan(
        start=parse_utc_date(start),
        end=parse_utc_date(end),
        train_days=train_days,
        validation_days=validation_days,
        step_days=step_days,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(plan.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    typer.echo(f"Prepared only; not executed: {output}")


@app.command("controlled-train")
def controlled_train(
    manifest: Annotated[Path, typer.Option(exists=True)] = Path(
        "data/manifests/experiment-2022H1.json"
    ),
    phase: Annotated[str, typer.Option(help="sanity, development or candidate")] = "sanity",
    artifact_root: Annotated[Path, typer.Option()] = Path("artifacts/controlled-training"),
    output: Annotated[Path | None, typer.Option()] = None,
    max_seconds_per_run: Annotated[int | None, typer.Option(min=1)] = None,
) -> None:
    """Train or idempotently resume the frozen historical curriculum."""
    normalized_phase = phase.lower()
    if normalized_phase not in {"sanity", "development", "candidate"}:
        raise typer.BadParameter("phase must be sanity, development or candidate")
    report = run_controlled_training(
        manifest,
        phase=cast(Literal["sanity", "development", "candidate"], normalized_phase),
        artifact_root=artifact_root,
        output=output or Path(f"reports/controlled-training-{normalized_phase}.json"),
        max_seconds_per_run=max_seconds_per_run,
    )
    completed = sum(item["status"] == "COMPLETED" for item in report.runs)
    typer.echo(f"Completed {completed}/{len(report.runs)} controlled runs")
    for item in report.runs:
        typer.echo(
            f"{item['algorithm']} seed={item['seed']} features={item['feature_variant']} "
            f"config={item['configuration_variant']} steps={item['completed_timesteps']} "
            f"status={item['status']}"
        )


@app.command("learning-dashboard")
def learning_dashboard(
    report: Annotated[Path, typer.Option(exists=True)] = Path(
        "reports/controlled-training-sanity.json"
    ),
    output: Annotated[Path, typer.Option()] = Path("reports/learning-dashboard.html"),
) -> None:
    """Render real training telemetry as one self-contained offline HTML file."""
    digest = write_learning_dashboard(report, output)
    typer.echo(f"Learning dashboard: {output} ({digest})")


@app.command("candidate-strategy-evaluate")
def candidate_strategy_evaluate(
    manifest: Annotated[Path, typer.Option(exists=True)] = Path(
        "data/manifests/experiment-2022H1.json"
    ),
    development_report: Annotated[Path, typer.Option(exists=True)] = Path(
        "reports/controlled-training-development.json"
    ),
    artifact_root: Annotated[Path, typer.Option()] = Path("artifacts/strategy-candidates"),
    output: Annotated[Path, typer.Option()] = Path("reports/strategy-candidate-momentum-24h.json"),
) -> None:
    """Evaluate the frozen strategy candidate on TRAIN only."""
    report = run_candidate_strategy(
        manifest,
        development_report_path=development_report,
        artifact_root=artifact_root,
        output=output,
    )
    typer.echo(
        f"Candidate TRAIN evaluation: {len(report['results'])} runs; "
        f"edge_demonstrated={report['decision']['edge_demonstrated']}"
    )


@app.command("controlled-evaluate")
def controlled_evaluate(
    training_report: Annotated[Path, typer.Option(exists=True)],
    manifest: Annotated[Path, typer.Option(exists=True)] = Path(
        "data/manifests/experiment-2022H1.json"
    ),
    output: Annotated[Path, typer.Option()] = Path("reports/controlled-validation.json"),
) -> None:
    """Open VALIDATION once, only after every frozen training run is complete."""
    report = run_controlled_validation(
        manifest,
        training_report_path=training_report,
        output=output,
    )
    typer.echo(
        f"VALIDATION observed for {len(report.runs)} frozen runs; "
        f"classification={report.gates.classification}"
    )


@app.command("microstructure-download")
def microstructure_download(
    date: Annotated[str, typer.Option(help="UTC day as YYYY-MM-DD")],
    kind: Annotated[Literal["trades", "aggTrades"], typer.Option()] = "aggTrades",
    symbol: Annotated[str, typer.Option()] = "FDUSDUSDC",
    destination: Annotated[Path, typer.Option()] = Path("data/raw/binance-microstructure"),
    manifest_output: Annotated[Path | None, typer.Option()] = None,
) -> None:
    """Download and checksum one public, historical Binance Spot trade archive."""
    normalized = symbol.upper()
    filename = f"{normalized}-{kind}-{date}.zip"
    source_url = f"https://data.binance.vision/data/spot/daily/{kind}/{normalized}/{filename}"
    target = destination / normalized / kind / filename
    downloaded = download_archive(source_url, target)
    events = parse_archive(downloaded, kind)
    manifest = manifest_for(downloaded, events, origin=source_url, period=date)
    output = manifest_output or downloaded.with_suffix(".manifest.json")
    write_artifact(manifest, output)
    typer.echo(f"Archive: {downloaded}")
    typer.echo(f"SHA256: {manifest.sha256}")
    typer.echo(f"Records: {manifest.record_count}")
    typer.echo(f"Manifest: {output}")


@app.command("microstructure-s0-fixture")
def microstructure_s0_fixture(
    fixture: Annotated[Path, typer.Option(exists=True)] = Path("fixtures/microstructure_s0.json"),
    output: Annotated[Path, typer.Option()] = Path("reports/runs/microstructure-s0-fixture.json"),
) -> None:
    """Verify S0 mechanics on an offline scenario with exact expected outcomes."""
    artifact = run_s0_fixture(fixture)
    write_artifact(artifact, output)
    typer.echo(f"Run ID: {artifact.result.run_id}")
    typer.echo(f"Edge: {artifact.result.edge_status}")
    typer.echo(f"Cycles: {artifact.result.metrics['cycle_count']}")
    typer.echo(f"Output: {output}")


@app.command("microstructure-frequency-audit")
def microstructure_frequency_audit(
    archive: Annotated[Path, typer.Option(exists=True)],
    date: Annotated[str, typer.Option(help="UTC day represented by the archive")],
    kind: Annotated[Literal["trades", "aggTrades"], typer.Option()] = "aggTrades",
    symbol: Annotated[str, typer.Option()] = "FDUSDUSDC",
    lower: Annotated[str, typer.Option()] = "0.9988",
    upper: Annotated[str, typer.Option()] = "0.9989",
    output: Annotated[Path, typer.Option()] = Path("reports/runs/fdusdusdc-level-frequency.json"),
) -> None:
    """Measure level recurrence without mislabeling observed price paths as fills."""
    normalized = symbol.upper()
    filename = f"{normalized}-{kind}-{date}.zip"
    source_url = f"https://data.binance.vision/data/spot/daily/{kind}/{normalized}/{filename}"
    audit = audit_trade_levels(
        archive,
        kind=kind,
        source_url=source_url,
        period=date,
        lower=Decimal(lower),
        upper=Decimal(upper),
    )
    write_artifact(audit, output)
    typer.echo(f"Run ID: {audit.run_id}")
    typer.echo(f"Observed lower->upper paths: {audit.completed_observed_paths}")
    typer.echo("Observed paths are fills: NO")
    typer.echo(f"Realistic queue: {audit.realistic_queue_status}")
    typer.echo(f"Output: {output}")


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


def _code_version() -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, check=False, text=True
    )
    return completed.stdout.strip() or "UNKNOWN"


if __name__ == "__main__":
    app()
