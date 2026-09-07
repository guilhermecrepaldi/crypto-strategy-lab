"""Causal hold-risk diagnostics. Never imported by a strategy or the operator."""

from __future__ import annotations

import gzip
import hashlib
import io
import json
import subprocess
import time
from bisect import bisect_left, bisect_right
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

import numpy as np

from crypto_strategy_lab.domain import canonical_hash
from crypto_strategy_lab.microstructure.capital_release_analysis import (
    audit_legacy_m007_event_projection,
)
from crypto_strategy_lab.microstructure.evolution_diagnostics import load_evaluated_run_evidence
from crypto_strategy_lab.microstructure.hold_risk_quantiles import RollingQuantiles
from crypto_strategy_lab.microstructure.operator import (
    M007_OPERATOR_STRATEGY_HASH,
    frozen_m007_strategy,
)
from crypto_strategy_lab.microstructure.serial_replay import (
    EVENT_ORDER_SCALE,
    USDCUSDT_TICK_CATALOG,
    CandidateTimeline,
    SerialReplayResult,
    SerialTape,
    _datetime_to_micros,
    _event_to_datetime,
    _score,
    _selection_grid,
)
from crypto_strategy_lab.microstructure.tape_cache import TapeCacheManifest, load_tape_cache

D = Decimal
SCALE = EVENT_ORDER_SCALE
HOUR_US = 3_600_000_000
DAY_US = 24 * HOUR_US
HORIZONS = {
    "1m": 60_000_000,
    "5m": 300_000_000,
    "15m": 900_000_000,
    "1h": HOUR_US,
    "6h": 6 * HOUR_US,
    "24h": DAY_US,
}
PROTOCOL_PATH = Path("docs/microstructure/HOLD_RISK_SELECTOR_PROTOCOL.md")
SCHEMA = "hold-risk-selector-diagnostic-v1"
SUPPORT_CACHE = "c5c9ccb6910052cdfce5ad696500b2fb50b0a579a097c81d450de21a3e2b0327"
EXACT_PARENT = Path(
    "artifacts/usdcusdt/models/M010/runs/"
    "5a53ab7dcebbdaf0f4697148c54d3e71b098575b6abc1a3b299c45312a5f4f0c/"
    "M007-technical-reconstruction/completed-replay.json"
)


def _sha(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8"
    )


@contextmanager
def _gzip_writer(path: Path) -> Iterator[io.TextIOWrapper]:
    with (
        path.open("wb") as raw,
        gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0, compresslevel=1) as packed,
        io.TextIOWrapper(packed, encoding="utf-8", newline="\n") as text,
    ):
        yield text


@dataclass
class EpisodeIndex:
    """Indexed canonical fresh-window episodes; never expose future exit durations."""

    timeline: CandidateTimeline

    def __post_init__(self) -> None:
        self.entries = np.asarray(self.timeline.cycle_entries, dtype=np.int64)
        self.exits = np.asarray(self.timeline.cycle_exits, dtype=np.int64)
        self.entry_us = self.entries // SCALE
        self.exit_us = self.exits // SCALE
        self.duration_us = self.exit_us - self.entry_us
        self.duration_sum = np.r_[np.int64(0), np.cumsum(self.duration_us)]
        days = self.entry_us // DAY_US
        self.day_changes = np.r_[np.int64(0), np.cumsum(np.r_[False, days[1:] != days[:-1]])]
        self.success_prefix = {
            name: np.r_[np.int64(0), np.cumsum(self.duration_us <= horizon)]
            for name, horizon in HORIZONS.items()
        }
        self.quantiles = RollingQuantiles(self.duration_us)

    def window(
        self, end: int, hours: int, *, coverage_start: int, quantiles: bool = False
    ) -> dict[str, Any]:
        if end % SCALE:
            raise ValueError("STRICT_TIMESTAMP_PREFIX_REQUIRED")
        start = end - hours * HOUR_US * SCALE
        t_us = end // SCALE
        lo = int(np.searchsorted(self.entries, start))
        hi = int(np.searchsorted(self.exits, end))
        lo = min(lo, hi)
        # Fresh left boundary may use a LOW inside a globally crossing cycle.
        cross_entry: int | None = None
        cross_exit: int | None = None
        original_lo = int(np.searchsorted(self.entries, start))
        first_low = bisect_left(self.timeline.low_events, start)
        if original_lo > 0 and first_low < len(self.timeline.low_events):
            prior_exit = int(self.exits[original_lo - 1])
            low = int(self.timeline.low_events[first_low])
            if start <= prior_exit < end and low < prior_exit:
                cross_entry, cross_exit = low // SCALE, prior_exit // SCALE
        # Prefix-completed exits alone determine the pending LOW. Future HIGH is never used.
        after = max(start - 1, int(self.exits[hi - 1]) if hi else start - 1)
        pending_index = bisect_right(self.timeline.low_events, after)
        pending: int | None = None
        if pending_index < len(self.timeline.low_events):
            candidate = int(self.timeline.low_events[pending_index])
            if candidate < end:
                pending = candidate // SCALE
        n_complete = hi - lo + int(cross_entry is not None)
        censored = int(pending is not None)
        total = n_complete + censored
        cross_duration = (
            cross_exit - cross_entry if cross_exit is not None and cross_entry is not None else None
        )
        occupied_us = int(self.duration_sum[hi] - self.duration_sum[lo])
        occupied_us += cross_duration or 0
        occupied_us += t_us - pending if pending is not None else 0
        day_count = int(self.day_changes[hi] - self.day_changes[lo + 1]) + 1 if hi > lo else 0
        known_days: set[int] = set()
        if hi > lo:
            known_days.update(
                (int(self.entry_us[lo]) // DAY_US, int(self.entry_us[hi - 1]) // DAY_US)
            )
        for entry in (cross_entry, pending):
            if entry is not None and entry // DAY_US not in known_days:
                known_days.add(entry // DAY_US)
                day_count += 1
        complete_history = start >= coverage_start
        base_support = complete_history and n_complete >= 30 and day_count >= 3
        closure: dict[str, Any] = {}
        for name, horizon in HORIZONS.items():
            mature_end = min(hi, int(np.searchsorted(self.entry_us, t_us - horizon)))
            mature_end = max(lo, mature_end)
            n = mature_end - lo
            successes = int(self.success_prefix[name][mature_end] - self.success_prefix[name][lo])
            if cross_entry is not None and cross_entry < t_us - horizon:
                n += 1
                successes += int(cross_duration is not None and cross_duration <= horizon)
            if pending is not None and pending < t_us - horizon:
                n += 1
            failures = n - successes
            closure[name] = {
                "mature_entries": n,
                "successes": successes,
                "failures": failures,
                "closure_rate": str(D(successes) / n) if n else None,
                "lock_risk": str(D(failures + 1) / (n + 2)) if n else None,
                "supported": base_support and n >= 30,
                "expected_cycles_before_lock": str(D(successes) / failures) if failures else None,
                "cycles_before_lock_status": (
                    "UNKNOWN" if not n else "ESTIMATE" if failures else "UNBOUNDED_IN_SAMPLE"
                ),
            }
        last_exit = int(self.exit_us[hi - 1]) if hi > lo else cross_exit
        result = {
            "history": "COMPLETE" if complete_history else "PARTIAL_HISTORY",
            "completed_entries": n_complete,
            "right_censored_entries": censored,
            "entry_days": day_count,
            "censored_share": str(D(censored) / total) if total else None,
            "censored_age_seconds": str(D(t_us - pending) / 1_000_000)
            if pending is not None
            else None,
            "capital_hours_consumed": str(D(occupied_us) / HOUR_US),
            "cycles_per_capital_hour": str(D(n_complete) * HOUR_US / occupied_us)
            if occupied_us
            else None,
            "cycles_per_wall_hour": str(D(n_complete) / hours),
            "last_successful_closure_us": last_exit,
            "last_successful_closure_age_seconds": str(D(t_us - last_exit) / 1_000_000)
            if last_exit is not None
            else None,
            "low_events": bisect_left(self.timeline.low_events, end) - first_low,
            "high_events": bisect_left(self.timeline.high_events, end)
            - bisect_left(self.timeline.high_events, start),
            "closure": closure,
        }
        if quantiles:
            result["hold_quantiles_completed_only_seconds"] = (
                self.quantiles.quantiles(lo, hi, extra=cross_duration)
                if n_complete >= 30
                else {name: None for name in ("p50", "p75", "p90", "p95")}
            )
        return result


def candidate_features(
    index: EpisodeIndex, end: int, coverage_start: int, quantum: Decimal
) -> dict[str, Any]:
    low, distance = index.timeline.low_tick, index.timeline.distance
    edge = D(low + distance) / D(low) - 1
    windows = {
        name: index.window(end, hours, coverage_start=coverage_start, quantiles=name == "30d")
        for name, hours in (("1h", 1), ("4h", 4), ("24h", 24), ("30d", 720))
    }
    for window in windows.values():
        productivity = window["cycles_per_capital_hour"]
        window["price_path_edge_per_capital_hour"] = (
            str(edge * D(productivity)) if productivity is not None else None
        )
    c1, c4, c24 = (windows[key]["completed_entries"] for key in ("1h", "4h", "24h"))
    closure = windows["30d"]["closure"]
    known = all(closure[key]["supported"] for key in ("1h", "6h", "24h"))
    epch = windows["24h"]["price_path_edge_per_capital_hour"]
    ready = known and c24 > 0 and epch is not None and windows["24h"]["history"] == "COMPLETE"
    recency = (min(D(1), D(24 * c1) / c24) + min(D(1), D(6 * c4) / c24)) / 2 if c24 else D(0)
    score = None
    if ready:
        denominator = 1 + sum(
            D(closure[key]["lock_risk"]) * weight
            for key, weight in (("1h", 1), ("6h", 6), ("24h", 24))
        )
        score = D(epch) * D(closure["1h"]["closure_rate"]) * recency / denominator
    return {
        "low_tick": low,
        "distance": distance,
        "low": str(low * quantum),
        "high": str((low + distance) * quantum),
        "m007_strict_score": str(edge * c24),
        "windows": windows,
        "risk_status": "KNOWN" if known else "UNKNOWN",
        "recency_quality": str(recency),
        "preregistered_score": str(score) if score is not None else None,
        "net_edge_per_capital_hour": "UNKNOWN_PRICE_PATH_ONLY",
    }


def qualifies(parent: dict[str, Any], alternative: dict[str, Any]) -> bool:
    if parent["preregistered_score"] is None or alternative["preregistered_score"] is None:
        return False
    p, a = parent["windows"], alternative["windows"]
    pr, ar = p["30d"]["closure"], a["30d"]["closure"]
    return (
        (parent["low_tick"], parent["distance"])
        != (alternative["low_tick"], alternative["distance"])
        and D(ar["24h"]["lock_risk"]) <= D("0.75") * D(pr["24h"]["lock_risk"])
        and all(D(ar[key]["lock_risk"]) <= D(pr[key]["lock_risk"]) for key in ("1h", "6h"))
        and D(a["24h"]["price_path_edge_per_capital_hour"])
        >= D("0.80") * D(p["24h"]["price_path_edge_per_capital_hour"])
        and D(a["24h"]["completed_entries"]) >= D("0.80") * p["24h"]["completed_entries"]
        and a["1h"]["completed_entries"] > 0
        and D(alternative["preregistered_score"]) > D(parent["preregistered_score"])
    )


def decision_points(result: SerialReplayResult) -> tuple[list[tuple[int, str]], int]:
    start = _datetime_to_micros(result.start) * SCALE
    end = _datetime_to_micros(result.end_exclusive) * SCALE
    entries = [item.entry_event for item in result.cycles]
    exits = [item.exit_event for item in result.cycles]
    if result.open_entry_event is not None:
        entries.append(result.open_entry_event)
        exits.append(end)
    points = [(start, "INITIAL")]
    blocked = 0
    for event in range(start + 60_000_000 * SCALE, end, 60_000_000 * SCALE):
        previous = bisect_left(entries, event) - 1
        if previous >= 0 and exits[previous] >= event:
            blocked += 1
        else:
            points.append((event, "FLAT_CLOCK"))
    points.extend((cycle.exit_event, "POST_EXIT") for cycle in result.cycles)
    points.sort()
    return points, blocked


def _selected_history(
    result: SerialReplayResult, quantum: Decimal
) -> tuple[list[int], list[tuple[int, int] | None]]:
    def pair(low: Decimal | None, high: Decimal | None) -> tuple[int, int] | None:
        return (
            (int(low / quantum), int((high - low) / quantum))
            if low is not None and high is not None
            else None
        )

    if result.selection_changes:
        first = result.selection_changes[0]
        initial = pair(first.previous_low, first.previous_high)
    elif result.cycles:
        initial = pair(result.cycles[0].low, result.cycles[0].high)
    else:
        initial = pair(result.active_low, result.active_high)
    events = [_datetime_to_micros(result.start) * SCALE]
    selected = [initial]
    for item in result.selection_changes:
        events.append(item.event)
        selected.append(pair(item.selected_low, item.selected_high))
    return events, selected


def seal_snapshots(
    result: SerialReplayResult, tape: SerialTape, coverage_start: int, root: Path
) -> dict[str, Any]:
    config = frozen_m007_strategy()
    print("HOLD_RISK_BUILD_TIMELINES", flush=True)
    timelines = tape.timelines(USDCUSDT_TICK_CATALOG.absolute_distances(config.distances))
    indices: dict[tuple[int, int], EpisodeIndex] = {}
    points, blocked = decision_points(result)
    selection_events, selected = _selected_history(result, tape.tick_size)
    path = root / "causal-snapshots.jsonl.gz"
    begun = time.monotonic()
    feature_cache: dict[tuple[int, int], dict[str, Any]] = {}
    cache_end = -1
    with _gzip_writer(path) as stream:
        for ordinal, (event, kind) in enumerate(points):
            end = event // SCALE * SCALE
            if end != cache_end:
                feature_cache.clear()
                cache_end = end
            _, distances, multiple = _selection_grid(
                config,
                USDCUSDT_TICK_CATALOG,
                end,
                tape.tick_size,
                tape.observed_tick_evidence_event,
            )
            assert distances is not None and multiple is not None
            ranked = []
            for candidate, timeline in timelines.items():
                if (
                    candidate[1] not in distances
                    or candidate[0] % multiple
                    or (candidate[0] + candidate[1]) % multiple
                ):
                    continue
                count = timeline.contained_cycles(end - DAY_US * SCALE, end)
                if count:
                    score = _score(candidate, timelines, config, end - DAY_US * SCALE, end)
                    ranked.append((score, count, -candidate[0], -candidate[1]))
            ranked.sort(reverse=True)
            top = [(-item[2], -item[3]) for item in ranked[:10]]
            parent_key = selected[bisect_right(selection_events, event) - 1]
            materialized = list(top)
            if parent_key is not None and parent_key not in materialized:
                materialized.append(parent_key)
            features = []
            for key in materialized:
                if key not in timelines:
                    raise ValueError("PARENT_CANDIDATE_TIMELINE_MISSING")
                if key not in indices:
                    indices[key] = EpisodeIndex(timelines[key])
                if key not in feature_cache:
                    feature_cache[key] = candidate_features(
                        indices[key], end, coverage_start, tape.tick_size
                    )
                features.append(feature_cache[key])
            parent = next(
                (item for item in features if (item["low_tick"], item["distance"]) == parent_key),
                None,
            )
            alternatives = [
                item
                for item in features
                if (item["low_tick"], item["distance"]) in top and item is not parent
            ]
            qualified = [
                item for item in alternatives if parent is not None and qualifies(parent, item)
            ]
            row = {
                "decision_id": ordinal,
                "decision_event": event,
                "timestamp": _event_to_datetime(event).isoformat(),
                "kind": kind,
                "prefix_end_exclusive": end,
                "parent_candidate": parent_key,
                "parent_event_order_score": str(
                    _score(parent_key, timelines, config, event - DAY_US * SCALE, event)
                ),
                "parent_event_order_score_class": "LEGACY_EVENT_ORDER_CONTEXT_ONLY_NOT_A_FEATURE",
                "eligible_candidates": len(ranked),
                "candidates": features,
                "alternative_available": bool(alternatives),
                "qualified_alternatives": [[x["low_tick"], x["distance"]] for x in qualified],
                "risk_coverage_known": parent is not None
                and parent["risk_status"] == "KNOWN"
                and any(x["risk_status"] == "KNOWN" for x in alternatives),
            }
            row["snapshot_sha256"] = canonical_hash(row)
            stream.write(json.dumps(row, separators=(",", ":")) + "\n")
            if ordinal % 5000 == 0:
                stream.flush()
                print(
                    f"HOLD_RISK_DECISIONS={ordinal}/{len(points)} "
                    f"ELAPSED={time.monotonic() - begun:.1f}",
                    flush=True,
                )
    seal = {
        "file": path.name,
        "sha256": _sha(path),
        "bytes": path.stat().st_size,
        "decision_count": len(points),
        "open_no_selection_minutes": blocked,
        "elapsed_seconds": time.monotonic() - begun,
    }
    _write(root / "causal-seal.json", seal)
    return seal


def attach_outcomes(result: SerialReplayResult, root: Path, seal: dict[str, Any]) -> dict[str, Any]:
    """Only this second pass attaches any hold outcome to the sealed causal snapshots."""
    path = root / seal["file"]
    if _sha(path) != seal["sha256"]:
        raise ValueError("CAUSAL_SNAPSHOT_SEAL_MISMATCH")
    decisions = []
    contexts = []
    alternative_decisions = 0
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            digest = row.pop("snapshot_sha256")
            if canonical_hash(row) != digest:
                raise ValueError("CAUSAL_SNAPSHOT_HASH_MISMATCH")
            decisions.append(row["decision_event"])
            parent = next(
                (
                    item
                    for item in row["candidates"]
                    if [item["low_tick"], item["distance"]] == row["parent_candidate"]
                ),
                None,
            )
            alternative_decisions += int(row["alternative_available"])
            contexts.append(
                {
                    "snapshot_sha256": digest,
                    "decision_id": row["decision_id"],
                    "qualified": bool(row["qualified_alternatives"]),
                    "known": row["risk_coverage_known"],
                    "alternative_available": row["alternative_available"],
                    "discriminators": {
                        **{
                            f"lock_risk_{name}": parent["windows"]["30d"]["closure"][name][
                                "lock_risk"
                            ]
                            for name in ("1h", "6h", "24h")
                        },
                        "censored_share_30d": parent["windows"]["30d"]["censored_share"],
                        "epch24": parent["windows"]["24h"]["price_path_edge_per_capital_hour"],
                        "cycles24": parent["windows"]["24h"]["completed_entries"],
                        "recency_quality": parent["recency_quality"],
                        "hold_p90_completed_only": parent["windows"]["30d"][
                            "hold_quantiles_completed_only_seconds"
                        ]["p90"],
                    }
                    if parent is not None
                    else {},
                }
            )
    entries = [(c.entry_event, c.exit_event, False) for c in result.cycles]
    end = _datetime_to_micros(result.end_exclusive) * SCALE
    if result.open_entry_event is not None:
        entries.append((result.open_entry_event, end, True))
    exits = [c.exit_event for c in result.cycles]
    hours = D(0)
    addressed_hours = D(0)
    total_excess = D(0)
    addressed_excess = D(0)
    long_count = known_count = opportunities = alt_long = 0
    opportunity_months: set[str] = set()
    horizon_totals: dict[str, dict[str, Any]] = {
        key: {"long_entries": 0, "avoidable_opportunities": 0, "excess_hours": D(0)}
        for key in ("1h", "6h", "24h")
    }
    cohorts: dict[str, dict[str, list[Decimal]]] = {
        f"{group}_{key}": {} for key in ("1h", "6h", "24h") for group in ("LONG", "NOT_LONG")
    }
    unique_opportunities: set[int] = set()
    with _gzip_writer(root / "retrospective-outcomes.jsonl.gz") as stream:
        for entry, exit_event, censored in entries:
            ix = bisect_right(decisions, entry) - 1
            if ix < 0:
                raise ValueError("ENTRY_WITHOUT_DECISION")
            context = contexts[ix]
            hold = D(exit_event // SCALE - entry // SCALE) / HOUR_US
            hours += hold
            is_long = hold > 24
            for key, horizon in (("1h", 1), ("6h", 6), ("24h", 24)):
                if hold > horizon:
                    horizon_totals[key]["long_entries"] += 1
                    horizon_totals[key]["avoidable_opportunities"] += int(context["qualified"])
                    horizon_totals[key]["excess_hours"] += hold - horizon
            if is_long:
                long_count += 1
                known_count += int(context["known"])
                alt_long += int(context["alternative_available"])
                total_excess += hold - 24
                if context["qualified"]:
                    opportunities += 1
                    unique_opportunities.add(context["decision_id"])
                    addressed_hours += hold
                    addressed_excess += hold - 24
                    opportunity_months.add(_event_to_datetime(entry).strftime("%Y-%m"))
            for key, horizon in (("1h", 1), ("6h", 6), ("24h", 24)):
                if censored and hold <= horizon:
                    continue  # Unknown future horizon is not a successful short hold.
                group = cohorts[f"{'LONG' if hold > horizon else 'NOT_LONG'}_{key}"]
                for name, value in context["discriminators"].items():
                    if value is not None and context["known"]:
                        group.setdefault(name, []).append(D(value))
            future_counts = {
                key: bisect_left(exits, entry + horizon * HOUR_US * SCALE)
                - bisect_right(exits, entry)
                if entry + horizon * HOUR_US * SCALE <= end
                else None
                for key, horizon in (("1h", 1), ("6h", 6), ("24h", 24))
            }
            row = {
                **context,
                "classification": "RETROSPECTIVE_DIAGNOSTIC_ONLY",
                "entry_event": entry,
                "hold_hours_observed": str(hold),
                "right_censored_at_cutoff": censored,
                "actual_subsequent_m007_cycles": future_counts,
            }
            stream.write(json.dumps(row, separators=(",", ":")) + "\n")
    coverage = D(known_count) / long_count if long_count else D(0)
    addressed_share = addressed_excess / total_excess if total_excess else D(0)
    signal = (
        "INCONCLUSIVE"
        if coverage < D("0.80")
        else (
            "YES"
            if opportunities >= 3 and len(opportunity_months) >= 2 and addressed_share >= D("0.10")
            else "NO"
        )
    )

    def describe(values: list[Decimal]) -> dict[str, Any]:
        values.sort()
        n = len(values)
        median = (values[(n - 1) // 2] + values[n // 2]) / 2 if n else None
        return {"n": n, "median": str(median) if median is not None else None}

    return {
        "M007_DECISIONS_ANALYZED": len(decisions),
        "M007_ENTRIES": len(entries),
        "selection_change_count": len(result.selection_changes),
        "LONG_HOLD_ENTRIES": long_count,
        "ALTERNATIVE_CANDIDATE_AVAILABLE": alt_long,
        "DECISIONS_WITH_ALTERNATIVE": alternative_decisions,
        "AVOIDABLE_LOCK_OPPORTUNITIES": opportunities,
        "unique_opportunity_decisions": len(unique_opportunities),
        "M007_CAPITAL_HOURS": str(hours),
        "ESTIMATED_AVOIDABLE_CAPITAL_HOURS": str(addressed_hours),
        "M007_HOURS_GT24H": str(total_excess),
        "ESTIMATED_AVOIDABLE_EXCESS_24H": str(addressed_excess),
        "known_long_entries": known_count,
        "risk_coverage": str(coverage),
        "addressed_excess_share": str(addressed_share),
        "opportunity_months": sorted(opportunity_months),
        "horizons": horizon_totals,
        "discriminators": {
            name: {key: describe(values) for key, values in group.items()}
            for name, group in cohorts.items()
        },
        "HOLD_RISK_SIGNAL_FOUND": signal,
        "M011_AUTHORIZED": "NO_PENDING_ASTRA_REVIEW" if signal == "YES" else "NO",
        "CURRENT_CHAMPION": "M007",
        "BEST_CAUSAL_DISCRIMINATORS": "PENDING_ASTRA_REVIEW_OF_PREREGISTERED_FEATURES",
        "scope": "TOP10_M007_STRICT_PREFIX_PLUS_PARENT",
        "estimated_avoided_hours_are_realized_savings": False,
    }


def run_diagnostic() -> dict[str, Any]:
    """Offline canonical entry point; never train or replay a model."""
    code_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    protocol_sha = _sha(PROTOCOL_PATH)
    print("HOLD_RISK_VERIFY_M007", flush=True)
    evidence = load_evaluated_run_evidence("M007")
    if evidence.model_hash != M007_OPERATOR_STRATEGY_HASH:
        raise ValueError("PARENT_HASH_MISMATCH")
    raw = json.loads(EXACT_PARENT.read_text(encoding="utf-8"))
    if canonical_hash(raw["result"]) != raw["result_sha256"]:
        raise ValueError("EXACT_PARENT_HASH_MISMATCH")
    parent = SerialReplayResult.model_validate(raw["result"])
    if parent.model_id != "M007" or parent.initial_quote != D(100):
        raise ValueError("PARENT_IDENTITY_OR_CAPITAL_MISMATCH")
    legacy_audit = audit_legacy_m007_event_projection(
        SerialReplayResult.model_validate(evidence.replay), parent
    )
    print("HOLD_RISK_VERIFY_SUPPORT_TAPE", flush=True)
    support_dir = Path("artifacts/usdcusdt/market-tape") / SUPPORT_CACHE
    support_manifest = TapeCacheManifest.model_validate_json(
        (support_dir / "manifest.json").read_text()
    )
    if (
        support_manifest.dataset_hash != evidence.tape_manifest.dataset_hash
        or support_manifest.end_exclusive != parent.end_exclusive
    ):
        raise ValueError("SUPPORT_DATASET_OR_CUTOFF_MISMATCH")
    tape = load_tape_cache(support_dir, tick_catalog=USDCUSDT_TICK_CATALOG)
    # No diagnostic decision can use events older than the first 30-day window.
    view_start = _datetime_to_micros(parent.start) * SCALE - 30 * DAY_US * SCALE
    first = bisect_left(tape.events, view_start)
    tape = SerialTape(
        tick_size=tape.tick_size,
        occurrences={
            price: events[bisect_left(events, view_start) :]
            for price, events in tape.occurrences.items()
        },
        events=tape.events[first:],
        price_ticks=tape.price_ticks[first:],
        last_event=tape.last_event,
        last_price_tick=tape.last_price_tick,
        observed_tick_evidence_event=tape.observed_tick_evidence_event,
        tape_hash=tape.tape_hash,
        tape_cache_key=tape.tape_cache_key,
    )
    identity = {
        "schema": SCHEMA,
        "code_sha": code_sha,
        "protocol_sha256": protocol_sha,
        "model": "M007",
        "model_hash": evidence.model_hash,
        "run_hash": evidence.run_hash,
        "scenario_hash": parent.scenario_hash,
        "initial_capital": "100",
        "currency": "USDT",
        "start": parent.start.isoformat(),
        "end": parent.end_exclusive.isoformat(),
        "dataset_hash": support_manifest.dataset_hash,
        "support_tape_hash": support_manifest.tape_hash,
        "computation_view_start_event": view_start,
        "execution_tape_hash": evidence.tape_manifest.tape_hash,
        "parent_exact_result_hash": raw["result_sha256"],
        "parent_exact_artifact_sha256": _sha(EXACT_PARENT),
    }
    root = Path("artifacts/usdcusdt/hold-risk-diagnostics") / canonical_hash(identity)
    root.mkdir(parents=True, exist_ok=True)
    _write(root / "identity.json", identity)
    _write(root / "parent-event-id-audit.json", legacy_audit)
    seal_path = root / "causal-seal.json"
    if seal_path.exists():
        seal = json.loads(seal_path.read_text())
    else:
        # Incomplete snapshots are not published evidence; rerun uses this identity only.
        seal = seal_snapshots(
            parent, tape, _datetime_to_micros(support_manifest.start) * SCALE, root
        )
    summary = attach_outcomes(parent, root, seal)
    report = {
        "schema": SCHEMA,
        "status": "DIAGNOSTIC_COMPLETE_PENDING_ASTRA_REVIEW",
        "identity": identity,
        "causal_seal": seal,
        **summary,
        "artifact_root": str(root),
        "outcomes_sha256": _sha(root / "retrospective-outcomes.jsonl.gz"),
        "protections": {
            "validation_accessed": False,
            "locked_test_accessed": False,
            "binance_live_accessed": False,
            "testnet_accessed": False,
            "shadow_modified": False,
            "m011_replayed": False,
        },
    }
    _write(root / "summary.json", report)
    _write(Path("reports/usdcusdt/hold-risk-selector-diagnostic.json"), report)
    return report
