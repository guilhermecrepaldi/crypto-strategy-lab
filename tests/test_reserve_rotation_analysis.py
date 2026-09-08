"""Report rendering uses explicit frozen-fill labels and includes censoring."""

import json
from decimal import Decimal as D
from pathlib import Path

from crypto_strategy_lab.microstructure.reserve_recovery_diagnostics import analyze_recovery
from scripts.analyze_reserve_rotation import (
    CURRENT_APPROVED_DAYS,
    FUNDING,
    _augment_metrics,
    _checkpoint_run,
    _owner_m016_summary,
    _prefix_positions,
    _prefix_summary,
    _prefix_view,
    build_model_comparison,
    render,
    render_model_comparison,
)


def test_report_exposes_censoring_not_just_recovered_average():
    rows = [
        {"time_us": 1, "release": True, "net_profit": "-.03", "reserve_consumption": ".03"},
        {"time_us": 2, "release": False, "net_profit": ".01", "reserve_consumption": "0"},
    ]
    summary = {
        "RESERVE_CONSUMPTION": ".03",
        "RELEASES": 1,
        "NET_POSITIVE_CYCLES": 1,
        "RESERVE_FINAL": "9.971",
        "TOTAL_EQUITY": "109.98",
    }
    run = {
        "summary": summary,
        "positive_profit_total": ".01",
        "two_hour_violations": 1,
        "daily_positive_cycles": [1] + [0] * 11,
        "positions": [],
        "recovery_sensitivity": {f: analyze_recovery(rows, D(f), 3) for f in FUNDING},
    }
    html = render({"runs": {"CONTROL": run}})
    assert "não é novo replay composto" in html
    assert "Dívida aberta USDT" in html and "0 / 1" in html
    assert "somente dos releases quitados" in html
    assert "Dia 12" in html and "0.02200" in html


def test_m015_m016_comparison_labels_partial_and_defers_debt(tmp_path: Path):
    m015 = tmp_path / "m015"
    (m015 / "daily").mkdir(parents=True)
    (m015 / "summary.json").write_text(
        json.dumps(
            {
                "RUN_STATUS": "PENDING",
                "MODEL_ID": "M015",
                "NET_POSITIVE_CYCLES": 12,
                "RELEASES": 1,
                "TOTAL_EQUITY_FINAL": "110.1",
            }
        ),
        encoding="utf-8",
    )
    (m015 / "daily" / "01.json").write_text(
        json.dumps(
            {
                "DAILY_NET_POSITIVE_CYCLES": 12,
                "TOTAL_EQUITY_FINAL": "110.1",
                "RESERVE_FINAL": "10.1",
            }
        ),
        encoding="utf-8",
    )
    comparison = build_model_comparison(m015, tmp_path / "m016-not-started")
    html = render_model_comparison(comparison)
    assert comparison["models"]["M015"]["status"] == "CHECKPOINT_PARTIAL"
    assert comparison["models"]["M016"]["status"] == "UNAVAILABLE"
    assert "REPORTING_COMPARISON_OF_THREE_SIMULATED_REPLAYS" in html
    assert "THREE_SIMULATED_REPLAYS_FUNDING_REAL_10_PERCENT_SENSITIVITY_DIAGNOSTIC_ONLY" in html
    assert "DEFERRED_UNAVAILABLE" in html
    assert "UNAVAILABLE" in html
    assert "M015" in html and "M016" in html and "M017" in html
    assert "patrimônio final" in html
    assert "Placar completo e definições" in html
    assert html.index("comparison-charts") < html.index("Placar completo e definições")
    assert "replays simulados" in html


def test_recovery_table_denominator_is_debt_cohort_and_shows_no_loss_releases(tmp_path: Path):
    m015 = tmp_path / "m015"
    (m015 / "daily").mkdir(parents=True)
    (m015 / "summary.json").write_text(
        json.dumps({"RUN_STATUS": "PENDING", "MODEL_ID": "M015", "RELEASES": 2}),
        encoding="utf-8",
    )
    (m015 / "daily" / "01.json").write_text(
        json.dumps({"LOGICAL_DAY": 1, "DAILY_NET_POSITIVE_CYCLES": 1}),
        encoding="utf-8",
    )
    comparison = build_model_comparison(m015, tmp_path / "m016-not-started")
    comparison["models"]["M015"]["summary"]["RELEASES"] = 2
    rows = [
        {"time_us": 1, "release": True, "net_profit": "-.03", "reserve_consumption": ".03"},
        {"time_us": 2, "release": True, "net_profit": "0", "reserve_consumption": "0"},
        {"time_us": 3, "release": False, "net_profit": ".1", "reserve_consumption": "0"},
    ]
    comparison["models"]["M015"]["recovery_sensitivity"] = {
        funding: analyze_recovery(rows, D(funding), 4) for funding in FUNDING
    }
    html = render_model_comparison(comparison)
    assert "perdas recuperadas / com dívida" in html
    assert "releases sem perda" in html
    assert "1 / 1" in html
    assert ">1</td>" in html


def test_owner_m016_headline_formats_derived_counts_and_money() -> None:
    comparison = {
        "models": {
            "M016": {
                "summary": {
                    "REAL_FUNDING_RATE": "0.10",
                    "RELEASE_LOSS_MEAN": "0.0291",
                    "NET_POSITIVE_CYCLES": 19,
                    "DAILY_CYCLES_MIN": 0,
                    "DAILY_CYCLES_MAX": 12,
                    "INITIAL_BANK": "100",
                    "FINAL_BANK": "100.12132",
                    "INITIAL_RESERVE": "10",
                    "RESERVE_FINAL": "9.78068",
                    "HOLD_GT_2H_COUNT": 8,
                    "FINAL_CAPITAL": "109.902",
                },
                "recovery_sensitivity": {"0.10": {"recovered_count": 0, "tranches": [{}] * 7}},
            }
        }
    }
    headline = _owner_m016_summary(comparison)
    assert "funding 10%" in headline
    assert "0.029100 USDT" in headline
    assert "0/7 recuperados, N/T não estimáveis" in headline
    assert f"19 ciclos positivos (0{chr(0x2013)}12/dia)" in headline
    assert "banca 100.000000 → 100.121320 USDT" in headline
    assert "reserva 10.000000 → 9.780680 USDT" in headline
    assert "8 posições >2h" in headline
    assert "equity final 109.902000 USDT" in headline


def test_m017_not_started_is_explicit_and_spec_binding_is_reported(tmp_path: Path) -> None:
    comparison = build_model_comparison(tmp_path / "m015", tmp_path / "m016", tmp_path / "m017")
    assert comparison["models"]["M017"]["status"] == "NOT_STARTED"
    assert comparison["approved_window_days"] == CURRENT_APPROVED_DAYS
    assert "M017 NOT_STARTED" in comparison["comparison_period"]
    assert "M015/M016 12D completos" in comparison["historical_control_period"]
    assert comparison["configuration"]["M017"]["status"] == "VALIDATED_SPEC_REGISTRY"
    assert comparison["configuration"]["M017"]["executable_loss_cap_bps"] == "20"


def test_partial_m017_sets_common_prefix_for_all_models(tmp_path: Path) -> None:
    roots = [tmp_path / model_id for model_id in ("m015", "m016", "m017")]
    for root in roots:
        (root / "daily").mkdir(parents=True)
        (root / "daily" / "01.json").write_text(
            json.dumps({"LOGICAL_DAY": 1, "DAILY_NET_POSITIVE_CYCLES": 2}),
            encoding="utf-8",
        )
    comparison = build_model_comparison(*roots)
    assert comparison["comparison_period"] == f"mesmo prefixo lógico, dias 1{chr(0x2013)}1"
    assert all(
        comparison["models"][model_id]["period_label"]
        == f"dias 1{chr(0x2013)}1 (mesmo prefixo comparável)"
        for model_id in comparison["model_ids"]
    )


def test_owner_gate_does_not_read_m017_beyond_approved_prefix(tmp_path: Path) -> None:
    roots = [tmp_path / model_id for model_id in ("m015", "m016", "m017")]
    for root in roots:
        (root / "daily").mkdir(parents=True)
        for day in (1, 2):
            (root / "daily" / f"{day:02}.json").write_text(
                json.dumps({"LOGICAL_DAY": day, "DAILY_NET_POSITIVE_CYCLES": day}),
                encoding="utf-8",
            )
        for day in (1, 2):
            (root / "daily" / f"{day:02}-engine-state.json").write_text(
                json.dumps({"state": {"settlements": []}}), encoding="utf-8"
            )
    # This must remain unread: the current OWNER gate is read from the directive.
    (roots[2] / "daily" / "03.json").write_text("{invalid json", encoding="utf-8")

    comparison = build_model_comparison(*roots)

    assert comparison["approved_window_days"] == CURRENT_APPROVED_DAYS
    assert comparison["comparison_period"] == (
        f"mesmo prefixo lógico, dias 1{chr(0x2013)}{CURRENT_APPROVED_DAYS}"
    )
    assert comparison["models"]["M017"]["status"] == "M017_OWNER_PAUSED_AFTER_SCOPE"
    assert "OWNER_PAUSED_AFTER_SCOPE" in _owner_m016_summary(comparison)


def test_prefix_positions_stops_before_post_gate_seam_and_poison(tmp_path: Path) -> None:
    ledger = tmp_path / "execution-audit.jsonl"
    ledger.write_text(
        "\n".join(
            (
                json.dumps({"kind": "SYNTHETIC_SAMPLE_SEAM", "time_us": 0}),
                json.dumps({"kind": "FILL", "side": "BUY", "time_us": 100}),
                json.dumps({"kind": "SYNTHETIC_SAMPLE_SEAM", "time_us": 200}),
                json.dumps({"kind": "FILL", "side": "BUY", "time_us": 250, "poison": True}),
                "{poison is beyond the approved prefix",
            )
        ),
        encoding="utf-8",
    )

    positions = _prefix_positions(
        tmp_path,
        [{"time_us": 150, "release": False}],
        cutoff_us=200,
    )

    assert len(positions) == 1
    assert positions[0]["entry_us"] == 100


def test_owner_paused_prefix_ignores_global_summary(tmp_path: Path) -> None:
    (tmp_path / "daily").mkdir(parents=True)
    (tmp_path / "daily" / "01.json").write_text(
        json.dumps({"LOGICAL_DAY": 1, "DAILY_NET_POSITIVE_CYCLES": 1}),
        encoding="utf-8",
    )
    (tmp_path / "daily" / "01-engine-state.json").write_text(
        json.dumps({"state": {"settlements": []}}), encoding="utf-8"
    )
    (tmp_path / "summary.json").write_text("{global summary is outside the gate", encoding="utf-8")

    result = _checkpoint_run(
        tmp_path,
        "M017_PRICE_PRIORITY",
        max_day=CURRENT_APPROVED_DAYS,
    )

    assert result["status"] == "M017_OWNER_PAUSED_AFTER_SCOPE"
    assert result["error"] == "OWNER_SCOPE_LIMIT"


def test_complete_summary_without_terminal_state_is_not_passed_as_complete(tmp_path: Path) -> None:
    root = tmp_path / "m017"
    root.mkdir()
    (root / "summary.json").write_text(
        json.dumps({"RUN_STATUS": "COMPLETE", "MODEL_ID": "M017"}),
        encoding="utf-8",
    )
    result = _checkpoint_run(root, "M017_PRICE_PRIORITY")
    assert result["status"] == "NO_COMPLETE_BOUND_STATE"
    assert result["debt_states"] == "NO_COMPLETE_BOUND_STATE"


def test_comparison_does_not_invent_recovery_average_when_none_are_paid(tmp_path: Path):
    root = tmp_path / "pending"
    (root / "daily").mkdir(parents=True)
    (root / "summary.json").write_text(
        json.dumps({"RUN_STATUS": "PENDING", "MODEL_ID": "M016", "RELEASES": 3}),
        encoding="utf-8",
    )
    comparison = build_model_comparison(tmp_path / "missing-m015", root)
    html = render_model_comparison(comparison)
    assert "M015 dívida aberta" in html
    assert "M016 dívida aberta" in html
    assert html.count("UNAVAILABLE") >= len(FUNDING)
    assert "mediana ciclos / h" in html


def test_partial_checkpoint_without_summary_uses_last_daily_and_engine_state(tmp_path: Path):
    root = tmp_path / "partial"
    (root / "daily").mkdir(parents=True)
    (root / "daily" / "01.json").write_text(
        json.dumps(
            {
                "LOGICAL_DAY": 1,
                "DAILY_NET_POSITIVE_CYCLES": 1,
                "CUMULATIVE_NET_POSITIVE_CYCLES": 1,
                "CUMULATIVE_NET_PNL": "0.0099",
                "TOTAL_EQUITY_FINAL": "110.0099",
                "RESERVE_FINAL": "10.00099",
                "OPERATING_FINAL": "99.00891",
            }
        ),
        encoding="utf-8",
    )
    (root / "daily" / "01-engine-state.json").write_text(
        json.dumps(
            {
                "state": {
                    "cash": "100.00891",
                    "cost": "1",
                    "dust_cost": "0",
                    "reserve": "10.00099",
                    "reserve_min": "10",
                    "reserve_funding": "0.00099",
                    "settlements": [
                        {
                            "time_us": 1,
                            "release": False,
                            "net_profit": "0.0099",
                            "reserve_consumption": "0",
                            "realized_fees_quote": "0",
                        }
                    ],
                }
            }
        ),
        encoding="utf-8",
    )
    (root / "run-manifest.json").write_text(
        json.dumps({"source_day_mapping": [{"logical_start_us": 0}]}),
        encoding="utf-8",
    )
    result = _checkpoint_run(root, "M016_PRICE_PRIORITY")
    assert result["status"] == "CHECKPOINT_PARTIAL"
    assert result["closed_day"] == 1
    assert result["summary"]["TOTAL_EQUITY_FINAL"] == "110.0099"
    assert result["summary"]["OPERATING_FINAL"] == "99.00891"
    assert result["summary"]["OPERATING_BANK"] == "101.00891"
    assert result["summary"]["PERIOD_LABEL"] == f"dias 1{chr(0x2013)}1"
    assert result["debt_states"] == "AVAILABLE_PREFIX_ACCOUNTING_POLICY_DEFERRED"
    assert result["recovery_sensitivity"]["0.80"]["ordinary_positive_cycle_count"] == 1


def test_open_position_uses_manifest_cutoff_even_without_new_settlements(tmp_path: Path):
    root = tmp_path / "open"
    (root / "daily").mkdir(parents=True)
    (root / "daily" / "02.json").write_text(
        json.dumps({"LOGICAL_DAY": 2, "DAILY_NET_POSITIVE_CYCLES": 0, "TOTAL_EQUITY_FINAL": "109"}),
        encoding="utf-8",
    )
    (root / "daily" / "02-engine-state.json").write_text(
        json.dumps(
            {
                "state": {
                    "entry_us": 100,
                    "cash": "100",
                    "cost": "9",
                    "dust_cost": "0",
                    "settlements": [],
                }
            }
        ),
        encoding="utf-8",
    )
    (root / "run-manifest.json").write_text(
        json.dumps(
            {"source_day_mapping": [{"logical_start_us": 0}, {"logical_start_us": 86_400_000_000}]}
        ),
        encoding="utf-8",
    )
    result = _checkpoint_run(root, "M016_PRICE_PRIORITY")
    result = _augment_metrics(result)
    assert result["summary"]["SIMULATION_TIMESTAMP_US"] == 172_800_000_000
    assert result["summary"]["DAILY_CYCLES_MAX"] == 0
    assert result["summary"]["HOLD_GT_2H_COUNT"] == 1
    assert float(result["summary"]["HOLD_GT_2H_EXCESS_HOURS"]) > 45


def test_prefix_fees_include_closed_settlements_and_open_component() -> None:
    summary = _prefix_summary(
        {},
        [],
        {
            "realized_cycle_fees": "0.03",
            "settlements": [
                {"realized_fees_quote": "0.10", "release": False, "time_us": 1, "net_profit": "0"},
                {"realized_fees_quote": "0.10", "release": False, "time_us": 2, "net_profit": "0"},
            ],
        },
        1,
        86_400_000_000,
    )
    assert summary["REALIZED_FEES_QUOTE"] == "0.23"


def test_complete_open_hold_is_counted_once_in_two_hour_metrics() -> None:
    run = {
        "summary": {},
        "positions": [
            {"hold_hours": "1", "open_censored": False},
            {"hold_hours": "1.5", "open_censored": False},
        ],
        "open_hold": {"age_hours": "3", "censored": True},
        "daily": [],
        "settlements": [],
        "recovery_sensitivity": {},
    }
    result = _augment_metrics(run)
    assert result["summary"]["HOLD_GT_2H_COUNT"] == 1
    assert result["summary"]["HOLD_GT_2H_EXCESS_HOURS"] == "1"
    assert result["summary"]["MAX_HOLD_HOURS"] == "3"


def test_prefix_view_does_not_inherit_terminal_open_hold(tmp_path: Path) -> None:
    root = tmp_path / "prefix"
    (root / "daily").mkdir(parents=True)
    (root / "daily" / "01.json").write_text(
        json.dumps({"LOGICAL_DAY": 1, "DAILY_NET_POSITIVE_CYCLES": 0}),
        encoding="utf-8",
    )
    run = {
        "status": "COMPLETE",
        "summary": {},
        "daily": [{"logical_day": 1, "DAILY_NET_POSITIVE_CYCLES": 0}],
        "daily_positive_cycles": [0],
        "daily_equity": [None],
        "daily_reserve": [None],
        "open_hold": {"age_hours": "99", "censored": True},
        "settlements": [{"time_us": 1}],
        "positions": [{"hold_hours": "99"}],
        "recovery_sensitivity": {"0.80": {"tranches": []}},
    }
    view = _prefix_view(run, root, 1)
    assert view["open_hold"] is None
    assert view["settlements"] == []
    assert view["positions"] == []
