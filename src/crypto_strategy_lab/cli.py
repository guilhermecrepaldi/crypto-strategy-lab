from __future__ import annotations

import json
import subprocess
from datetime import date as Date
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
from crypto_strategy_lab.microstructure.adaptive import (
    run_adaptive_campaign,
    write_adaptive_reports,
)
from crypto_strategy_lab.microstructure.campaign import register_first_block
from crypto_strategy_lab.microstructure.data import (
    HistoryManifest,
    download_archive,
    download_history_range,
    iter_archive,
    manifest_for,
    parse_archive,
    reconcile_history_manifest,
    slice_history_manifest,
    verify_history_manifest,
)
from crypto_strategy_lab.microstructure.level_scanner import (
    scan_campaign,
    write_scanner_reports,
)
from crypto_strategy_lab.microstructure.price_path import load_price_history, run_campaign
from crypto_strategy_lab.microstructure.price_profile import (
    build_price_profiles,
    write_price_profile_reports,
)
from crypto_strategy_lab.microstructure.replay_workflow import run_full_replay_campaign
from crypto_strategy_lab.microstructure.reporting import (
    write_backtest_reports,
)
from crypto_strategy_lab.microstructure.reporting import (
    write_history_audit as write_microstructure_history_audit,
)
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

DEFAULT_MICROSTRUCTURE_SYMBOL = "USDCUSDT"
DEFAULT_MICROSTRUCTURE_KIND: Literal["trades", "aggTrades"] = "trades"
DEFAULT_MICROSTRUCTURE_MANIFEST = Path(
    f"data/manifests/{DEFAULT_MICROSTRUCTURE_SYMBOL.lower()}-{DEFAULT_MICROSTRUCTURE_KIND}-history.json"
)


def _microstructure_manifest_path(
    symbol: str = DEFAULT_MICROSTRUCTURE_SYMBOL,
    kind: Literal["trades", "aggTrades"] = DEFAULT_MICROSTRUCTURE_KIND,
) -> Path:
    return Path("data/manifests") / f"{symbol.strip().lower()}-{kind}-history.json"


def _microstructure_audit_path(symbol: str, kind: Literal["trades", "aggTrades"]) -> Path:
    return Path("docs/microstructure") / (
        f"{symbol.strip().lower()}-{kind}-historical-data-audit.md"
    )


def _require_active_microstructure_symbol(symbol: str) -> str:
    normalized = symbol.strip().upper()
    if normalized != DEFAULT_MICROSTRUCTURE_SYMBOL:
        raise typer.BadParameter(
            f"the active campaign accepts only {DEFAULT_MICROSTRUCTURE_SYMBOL}; "
            "legacy pairs are archived"
        )
    return normalized


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


@app.command("microstructure-register-models")
def microstructure_register_models(
    artifact_root: Annotated[Path, typer.Option()] = Path("artifacts"),
    report_root: Annotated[Path, typer.Option()] = Path("reports"),
) -> None:
    """Idempotently preregister the frozen USDCUSDT M001-M004 block."""
    registrations = register_first_block(
        artifact_root=artifact_root,
        report_root=report_root,
    )
    typer.echo(
        "Registered: " + ", ".join(f"{item.model_id}={item.model_hash}" for item in registrations)
    )


@app.command("microstructure-full-replay")
def microstructure_full_replay(
    manifest: Annotated[Path, typer.Option(exists=True)],
    artifact_root: Annotated[Path, typer.Option()] = Path("artifacts"),
    report_root: Annotated[Path, typer.Option()] = Path("reports"),
    models: Annotated[str, typer.Option(help="Comma-separated preregistered model IDs")] = (
        "M001,M002,M003,M004"
    ),
) -> None:
    """Run complete DEVELOPMENT replays to the frozen physical cutoff; never economic-stop."""
    model_ids = tuple(item.strip().upper() for item in models.split(",") if item.strip())
    if not model_ids:
        raise typer.BadParameter("at least one preregistered model ID is required")
    records = run_full_replay_campaign(
        manifest,
        artifact_root=artifact_root,
        report_root=report_root,
        model_ids=model_ids,
    )
    for record in records:
        typer.echo(json.dumps(record, sort_keys=True))


@app.command("microstructure-download")
def microstructure_download(
    date: Annotated[str | None, typer.Option(help="One UTC day as YYYY-MM-DD")] = None,
    start: Annotated[str | None, typer.Option(help="Inclusive UTC start date")] = None,
    end: Annotated[str | None, typer.Option(help="Inclusive UTC end date")] = None,
    all_available: Annotated[
        bool, typer.Option("--all-available", help="Download every official daily archive")
    ] = False,
    kind: Annotated[Literal["trades", "aggTrades"], typer.Option()] = DEFAULT_MICROSTRUCTURE_KIND,
    symbol: Annotated[str, typer.Option()] = DEFAULT_MICROSTRUCTURE_SYMBOL,
    destination: Annotated[Path, typer.Option()] = Path("data/raw/binance-microstructure"),
    manifest_output: Annotated[Path | None, typer.Option()] = None,
    max_workers: Annotated[int, typer.Option(min=1, max=32)] = 8,
) -> None:
    """Download verified public Binance Spot trade archives, idempotently."""
    normalized = _require_active_microstructure_symbol(symbol)
    if date is None or start is not None or end is not None or all_available:
        if date is not None:
            raise typer.BadParameter("--date cannot be combined with range options")
        if not all_available and (start is None or end is None):
            raise typer.BadParameter("provide --start and --end, or --all-available")
        try:
            start_date = Date.fromisoformat(start) if start else None
            end_date = Date.fromisoformat(end) if end else None
        except ValueError as error:
            raise typer.BadParameter("dates must use YYYY-MM-DD") from error
        history = download_history_range(
            normalized,
            destination / normalized / kind,
            start=start_date,
            end=end_date,
            all_available=all_available,
            kind=kind,
            max_workers=max_workers,
        )
        output = manifest_output or _microstructure_manifest_path(normalized, kind)
        write_artifact(history, output)
        audit_path = write_microstructure_history_audit(
            history, _microstructure_audit_path(normalized, kind)
        )
        typer.echo(
            f"Archives: {len(history.archives)}; records={history.total_records}; "
            f"integrity={history.integrity_status}"
        )
        typer.echo(f"Coverage: {history.first_timestamp} -> {history.last_timestamp}")
        typer.echo(f"Manifest: {output} ({history.dataset_hash})")
        typer.echo(f"Audit: {audit_path}")
        return
    try:
        single_date = Date.fromisoformat(date)
    except ValueError as error:
        raise typer.BadParameter("date must use YYYY-MM-DD") from error
    filename = f"{normalized}-{kind}-{single_date.isoformat()}.zip"
    source_url = f"https://data.binance.vision/data/spot/daily/{kind}/{normalized}/{filename}"
    target = destination / normalized / kind / filename
    downloaded = download_archive(source_url, target)
    events = parse_archive(downloaded, kind)
    manifest = manifest_for(
        downloaded,
        events,
        origin=source_url,
        period=single_date.isoformat(),
        symbol=normalized,
        kind=kind,
    )
    output = manifest_output or downloaded.with_suffix(".manifest.json")
    write_artifact(manifest, output)
    typer.echo(f"Archive: {downloaded}")
    typer.echo(f"SHA256: {manifest.sha256}")
    typer.echo(f"Records: {manifest.record_count}")
    typer.echo(f"Manifest: {output}")


@app.command("microstructure-history-verify")
def microstructure_history_verify(
    manifest: Annotated[Path, typer.Option(exists=True)] = DEFAULT_MICROSTRUCTURE_MANIFEST,
) -> None:
    """Strictly re-verify a consolidated trade history fully offline."""
    parsed = HistoryManifest.model_validate_json(manifest.read_text(encoding="utf-8"))
    verify_history_manifest(parsed)
    typer.echo(
        f"Verified offline: {len(parsed.archives)} archives, {parsed.total_records} records, "
        f"dataset={parsed.dataset_hash}"
    )


@app.command("microstructure-history-reconcile")
def microstructure_history_reconcile(
    manifest: Annotated[Path, typer.Option(exists=True)] = DEFAULT_MICROSTRUCTURE_MANIFEST,
    destination: Annotated[Path, typer.Option()] = Path("data/raw/binance-microstructure"),
    output: Annotated[Path, typer.Option()] = Path(
        "data/manifests/usdcusdt-trades-reconciled-history.json"
    ),
) -> None:
    """Replace incomplete USDCUSDT months with complete official monthly trades archives."""
    daily = HistoryManifest.model_validate_json(manifest.read_text(encoding="utf-8"))
    _require_active_microstructure_symbol(daily.symbol)
    reconciled = reconcile_history_manifest(daily, destination / "USDCUSDT" / "trades")
    write_artifact(reconciled, output)
    typer.echo(
        f"Reconciled: {len(reconciled.archives)} archives; records={reconciled.total_records}; "
        f"integrity={reconciled.integrity_status}"
    )
    typer.echo(f"Manifest: {output} ({reconciled.dataset_hash})")


@app.command("microstructure-history-slice")
def microstructure_history_slice(
    manifest: Annotated[Path, typer.Option(exists=True)] = DEFAULT_MICROSTRUCTURE_MANIFEST,
    start: Annotated[str, typer.Option(help="Inclusive UTC start date")] = "2025-12-31",
    end: Annotated[str, typer.Option(help="Inclusive UTC end date")] = "2026-09-05",
    output: Annotated[Path, typer.Option()] = Path(
        "data/manifests/usdcusdt-trades-development-2026.json"
    ),
) -> None:
    """Create an offline sub-manifest without redownloading or inventing missing dates."""
    parsed = HistoryManifest.model_validate_json(manifest.read_text(encoding="utf-8"))
    _require_active_microstructure_symbol(parsed.symbol)
    try:
        start_date = Date.fromisoformat(start)
        end_date = Date.fromisoformat(end)
    except ValueError as error:
        raise typer.BadParameter("dates must use YYYY-MM-DD") from error
    subset = slice_history_manifest(parsed, start=start_date, end=end_date)
    write_artifact(subset, output)
    typer.echo(
        f"Slice: {subset.requested_start} -> {subset.requested_end}; "
        f"integrity={subset.integrity_status}; dataset={subset.dataset_hash}"
    )
    typer.echo(f"Manifest: {output}")


@app.command("microstructure-price-profile")
def microstructure_price_profile(
    manifest: Annotated[Path, typer.Option(exists=True)] = DEFAULT_MICROSTRUCTURE_MANIFEST,
    output_dir: Annotated[Path, typer.Option()] = Path("reports/usdcusdt"),
) -> None:
    """Build exact daily-to-historical price profiles from a valid local manifest."""
    parsed = HistoryManifest.model_validate_json(manifest.read_text(encoding="utf-8"))
    _require_active_microstructure_symbol(parsed.symbol)
    verify_history_manifest(parsed)
    events = (
        event
        for archive in parsed.archives
        for event in iter_archive(Path(archive.local_path), parsed.kind)
    )
    rows, summaries = build_price_profiles(
        events,
        symbol=parsed.symbol,
        source_kind=parsed.kind,
    )
    paths = write_price_profile_reports(rows, summaries, output_dir)
    typer.echo(f"Price profile rows: {len(rows)}")
    typer.echo(f"Period summaries: {len(summaries)}")
    typer.echo(f"Profiles: {paths['profiles']}")
    typer.echo(f"Summaries: {paths['summaries_json']}")


@app.command("microstructure-backtest")
def microstructure_backtest(
    manifest: Annotated[Path, typer.Option(exists=True)] = DEFAULT_MICROSTRUCTURE_MANIFEST,
    output_dir: Annotated[Path, typer.Option()] = Path("reports/microstructure"),
    lower: Annotated[str, typer.Option()] = "0.9988",
    upper: Annotated[str, typer.Option()] = "0.9989",
    step_size: Annotated[str, typer.Option()] = "0.01",
    min_quantity: Annotated[str, typer.Option()] = "0.01",
    min_notional: Annotated[str, typer.Option()] = "5",
) -> None:
    """Run the frozen continuous price-path backtest; this does not claim fills."""
    parsed = HistoryManifest.model_validate_json(manifest.read_text(encoding="utf-8"))
    _require_active_microstructure_symbol(parsed.symbol)
    verify_history_manifest(parsed)
    archives = [Path(item.local_path) for item in parsed.archives]
    low, high = Decimal(lower), Decimal(upper)
    history, total = load_price_history(
        archives,
        kind=parsed.kind,
        lower=low,
        upper=high,
    )
    campaign = run_campaign(
        history,
        dataset_hash=parsed.dataset_hash,
        archive_count=len(parsed.archives),
        total_records=total,
        lower=low,
        upper=high,
        step_size=Decimal(step_size),
        min_quantity=Decimal(min_quantity),
        min_notional=Decimal(min_notional),
    )
    outputs = write_backtest_reports(campaign, output_dir)
    typer.echo(f"Run ID: {campaign.run_id}")
    typer.echo(f"Classification: {campaign.backtest_classification}")
    typer.echo("Execution evidence: INCONCLUSIVE (bulk trades contain no queue position)")
    typer.echo(f"Summary: {outputs['summary']}")
    typer.echo(f"HTML: {outputs['html']}")


@app.command("microstructure-level-scan")
def microstructure_level_scan(
    manifest: Annotated[Path, typer.Option(exists=True)] = DEFAULT_MICROSTRUCTURE_MANIFEST,
    output_dir: Annotated[Path, typer.Option()] = Path("reports/microstructure"),
) -> None:
    """Run the preregistered daily ORACLE and causal selector campaign offline."""
    parsed = HistoryManifest.model_validate_json(manifest.read_text(encoding="utf-8"))
    _require_active_microstructure_symbol(parsed.symbol)
    if parsed.integrity_status != "VALID":
        raise typer.BadParameter("history manifest must be VALID; run history verification first")
    payload = scan_campaign(parsed)
    outputs = write_scanner_reports(payload, output_dir)
    typer.echo(f"Run ID: {payload['run_id']}")
    typer.echo(f"ORACLE_PATTERN: {payload['oracle_pattern']}")
    typer.echo(f"CAUSAL_SELECTOR: {payload['causal_selector']}")
    typer.echo("EXECUTION: INCONCLUSIVE")
    typer.echo(f"Summary: {outputs['summary']}")
    typer.echo(f"HTML: {outputs['html']}")


@app.command("microstructure-adaptive-scan")
def microstructure_adaptive_scan(
    manifest: Annotated[Path, typer.Option(exists=True)] = DEFAULT_MICROSTRUCTURE_MANIFEST,
    scanner_report: Annotated[Path, typer.Option(exists=True)] = Path(
        "reports/microstructure/daily-level-scanner.json"
    ),
    output_dir: Annotated[Path, typer.Option()] = Path("reports/microstructure"),
) -> None:
    """Evaluate STATIC, ALWAYS_BEST and preregistered IDLE_TRIGGERED offline."""
    parsed = HistoryManifest.model_validate_json(manifest.read_text(encoding="utf-8"))
    _require_active_microstructure_symbol(parsed.symbol)
    scanner = json.loads(scanner_report.read_text(encoding="utf-8"))
    if parsed.integrity_status != "VALID" or scanner.get("dataset_hash") != parsed.dataset_hash:
        raise typer.BadParameter("scanner and VALID history manifest must share one dataset hash")
    payload = run_adaptive_campaign(parsed, scanner)
    outputs = write_adaptive_reports(payload, output_dir)
    typer.echo(f"Run ID: {payload['run_id']}")
    typer.echo(f"ADAPTIVE_PATTERN: {payload['adaptive_pattern']}")
    typer.echo(f"ANTI_THRASHING: {payload['anti_thrashing']}")
    typer.echo("EXECUTION: INCONCLUSIVE")
    typer.echo(f"Summary: {outputs['summary']}")


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
    kind: Annotated[Literal["trades", "aggTrades"], typer.Option()] = DEFAULT_MICROSTRUCTURE_KIND,
    symbol: Annotated[str, typer.Option()] = DEFAULT_MICROSTRUCTURE_SYMBOL,
    lower: Annotated[str, typer.Option()] = "0.9988",
    upper: Annotated[str, typer.Option()] = "0.9989",
    output: Annotated[Path | None, typer.Option()] = None,
) -> None:
    """Measure level recurrence without mislabeling observed price paths as fills."""
    normalized = _require_active_microstructure_symbol(symbol)
    output_path = output or Path("reports/runs") / (
        f"{normalized.lower()}-{kind}-level-frequency.json"
    )
    filename = f"{normalized}-{kind}-{date}.zip"
    source_url = f"https://data.binance.vision/data/spot/daily/{kind}/{normalized}/{filename}"
    audit = audit_trade_levels(
        archive,
        kind=kind,
        source_url=source_url,
        period=date,
        symbol=normalized,
        lower=Decimal(lower),
        upper=Decimal(upper),
    )
    write_artifact(audit, output_path)
    typer.echo(f"Run ID: {audit.run_id}")
    typer.echo(f"Observed lower->upper paths: {audit.completed_observed_paths}")
    typer.echo("Observed paths are fills: NO")
    typer.echo(f"Realistic queue: {audit.realistic_queue_status}")
    typer.echo(f"Output: {output_path}")


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
