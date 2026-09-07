"""Run published B10 execution profiles offline; no exchange/account API imports."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import time
from bisect import bisect_left
from dataclasses import fields
from datetime import datetime
from decimal import Decimal
from itertools import pairwise
from pathlib import Path

from crypto_strategy_lab.microstructure.b10_reality import (
    B10RealityReplay,
    BookEnvelope,
    ExecutionProfile,
    SymbolRules,
    Trade,
)
from crypto_strategy_lab.microstructure.data import HistoryManifest, iter_history
from crypto_strategy_lab.microstructure.evolution_diagnostics import load_evaluated_run_evidence
from crypto_strategy_lab.microstructure.operator import frozen_m007_strategy
from crypto_strategy_lab.microstructure.recovery_reserve import (
    RecoveryReserveRuntime,
    ReserveConfig,
)
from crypto_strategy_lab.microstructure.recovery_reserve_study import (
    file_sha,
    published_sha,
    write_json,
)
from crypto_strategy_lab.microstructure.serial_replay import (
    EVENT_ORDER_SCALE,
    USDCUSDT_TICK_CATALOG,
    SerialScenarioConfig,
    _datetime_to_micros,
)

D = Decimal


class AuditJournal:
    """Durable JSONL trace with hash-bound rollback to the last checkpoint."""

    def __init__(self, path: Path, saved: dict | None = None):
        path.parent.mkdir(parents=True, exist_ok=True)
        if saved is None and path.exists() and path.stat().st_size:
            raise ValueError("AUDIT_EXISTS_WITHOUT_CHECKPOINT")
        self.stream = path.open("r+b" if path.exists() else "w+b")
        self.hasher = hashlib.sha256()
        self.offset = 0
        if saved is not None:
            remaining = int(saved["bytes"])
            while remaining:
                block = self.stream.read(min(1 << 20, remaining))
                if not block:
                    raise ValueError("AUDIT_PREFIX_TRUNCATED")
                self.hasher.update(block)
                self.offset += len(block)
                remaining -= len(block)
            if self.hasher.hexdigest() != saved["sha256"]:
                raise ValueError("AUDIT_PREFIX_HASH_MISMATCH")
            # Only unpublished bytes after the atomic checkpoint are replayed.
            self.stream.truncate(self.offset)

    def drain(self, engine):
        for row in engine.audit:
            encoded = (
                json.dumps(row, sort_keys=True, default=str, separators=(",", ":")) + "\n"
            ).encode()
            self.stream.write(encoded)
            self.hasher.update(encoded)
            self.offset += len(encoded)
        engine.audit.clear()

    def durable(self):
        self.stream.flush()
        os.fsync(self.stream.fileno())
        return {"bytes": self.offset, "sha256": self.hasher.hexdigest()}

    def close(self):
        self.stream.close()


def typed(cls, values):
    converted = dict(values)
    for field in fields(cls):
        if field.name in converted and field.type == "Decimal":
            converted[field.name] = D(converted[field.name])
    for name in ("buy_bounds", "sell_bounds"):
        if converted.get(name) is not None:
            converted[name] = tuple(D(value) for value in converted[name])
    return cls(**converted)


def run(config_path: Path, output: Path, profile_name: str | None = None) -> dict:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    if config.get("execution_authorized") is not True:
        raise ValueError("PUBLISHED_EXECUTION_CONFIG_GATE_CLOSED")
    if (
        config.get("b10_artifact_identity")
        != "097abdab8225038b091cb721bdd36bedb8a636c94bed1c87120adc0c9e10953a"
    ):
        raise ValueError("B10_FROZEN_ARTIFACT_MISMATCH")
    sha = published_sha()
    relative = config_path.resolve().relative_to(Path.cwd().resolve()).as_posix()
    published_config = subprocess.check_output(["git", "show", f"HEAD:{relative}"])
    if published_config.replace(b"\r\n", b"\n") != config_path.read_bytes().replace(b"\r\n", b"\n"):
        raise ValueError("EXECUTION_PROFILE_NOT_PUBLISHED")
    for source in (
        "src/crypto_strategy_lab/microstructure/b10_reality.py",
        "scripts/run_b10_reality.py",
    ):
        if subprocess.check_output(["git", "show", f"HEAD:{source}"]).replace(
            b"\r\n", b"\n"
        ) != Path(source).read_bytes().replace(b"\r\n", b"\n"):
            raise ValueError("EXECUTION_SOURCE_NOT_PUBLISHED")
    for name in ("physical_archive_audit", "calibration_manifest", "official_rule_manifest"):
        if name not in config or file_sha(Path(config[name])) != config.get(name + "_sha256"):
            raise ValueError(f"PINNED_INPUT_HASH_MISMATCH:{name}")
    physical_audit = json.loads(Path(config["physical_archive_audit"]).read_text(encoding="utf-8"))
    aggregate = physical_audit["fresh_aggregate"]
    expected_archives = physical_audit["archive_count"]
    if not physical_audit["coverage_exact"] or any(
        aggregate[key] != expected_archives
        for key in (
            "existing_count",
            "manifest_hash_match_count",
            "manifest_size_match_count",
            "sidecar_hash_match_count",
            "zip_test_ok_count",
        )
    ):
        raise ValueError("PHYSICAL_ARCHIVE_AUDIT_INCOMPLETE")
    manifest_path = Path(config["history_manifest"])
    if file_sha(manifest_path) != config["history_manifest_sha256"]:
        raise ValueError("HISTORY_MANIFEST_HASH_MISMATCH")
    history = HistoryManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
    if (
        history.symbol != "USDCUSDT"
        or history.kind != "trades"
        or history.integrity_status != "VALID"
    ):
        raise ValueError("VALID_USDCUSDT_RAW_TRADES_REQUIRED")
    start, end = (
        datetime.fromisoformat(config["start"]),
        datetime.fromisoformat(config["end_exclusive"]),
    )
    start_us, end_us = _datetime_to_micros(start), _datetime_to_micros(end)
    if (
        start.isoformat() != "2026-01-01T00:00:00+00:00"
        or end.isoformat() != "2026-09-05T23:59:59.783644+00:00"
    ):
        raise ValueError("FROZEN_B10_INTERVAL_MISMATCH")
    print("B10_REALITY_LOADING_CANONICAL_PRICE_TAPE", flush=True)
    evidence = load_evaluated_run_evidence("M007")
    if history.dataset_hash != evidence.tape_manifest.dataset_hash:
        raise ValueError("CANONICAL_DATASET_MISMATCH")
    tape, parent, catalog = evidence.tape, frozen_m007_strategy(), USDCUSDT_TICK_CATALOG
    if tape.tape_hash != "505fd6c31b010eac4e8da2d7e290137bb455d475b95409ac306d1ded7be55b6c":
        raise ValueError("FROZEN_B10_TAPE_HASH_MISMATCH")
    if parent.model_hash != "2cb6c755cad4b805eb6b79e7b7e04fd271e660f285a8c1d6aca4c643dded934f":
        raise ValueError("FROZEN_B10_SELECTOR_HASH_MISMATCH")
    catalog.validate_interval(start, end)
    begin = bisect_left(tape.events, start_us * EVENT_ORDER_SCALE)
    stop = bisect_left(tape.events, end_us * EVENT_ORDER_SCALE)
    if stop <= begin:
        raise ValueError("EMPTY_FROZEN_INTERVAL")
    expected_last_us = int(tape.events[stop - 1]) // EVENT_ORDER_SCALE
    scenario = SerialScenarioConfig(
        scenario_id="PRICE_PATH_HISTORICAL_TICK_ZERO_FEE_V2",
        tick_size=tape.tick_size,
        historical_tick_catalog_hash=catalog.catalog_hash,
        historical_tick_source_url=catalog.source_url,
        historical_tick_policy="CAUSAL_OBSERVED_GRID_THEN_OFFICIAL_COMPLETION_BOUND",
    )
    if scenario.scenario_hash != "db714e7a45aa53ed4e8d961cfcbd2dc3b99392153723967f468b93d952f37ae8":
        raise ValueError("FROZEN_B10_THEORETICAL_SCENARIO_MISMATCH")
    timelines = tape.timelines(catalog.absolute_distances(parent.distances))
    periods = [
        (int(row["start_us"]), int(row["end_us"]), typed(SymbolRules, row["rule"]))
        for row in config["rules"]
    ]
    if not periods or periods[0][0] > start_us or periods[-1][1] < end_us:
        raise ValueError("RULE_TIMELINE_DOES_NOT_COVER_INTERVAL")
    if any(left[1] != right[0] for left, right in pairwise(periods)):
        raise ValueError("RULE_TIMELINE_GAP_OR_OVERLAP")

    def rules_at(timestamp):
        for first, last, rules in periods:
            if first <= timestamp < last:
                return rules
        raise ValueError("NO_RULE_FOR_EVENT")

    results = {}
    for item in config["profiles"]:
        profile = typed(ExecutionProfile, item["profile"])
        if profile_name is not None and profile.name != profile_name:
            continue
        envelope = typed(BookEnvelope, item["envelope"])
        runtime = RecoveryReserveRuntime(
            ReserveConfig(D("0.02"), 1, D(10)), parent, scenario, tape, timelines, catalog
        )
        identity = {
            "published_config_sha": sha,
            "profile_config_sha256": file_sha(config_path),
            "data_manifest_sha256": file_sha(manifest_path),
            "expected_last_trade_us": expected_last_us,
            "expected_trade_count": stop - begin,
            "b10_artifact_identity": config["b10_artifact_identity"],
            "start": start.isoformat(),
            "end_exclusive": end.isoformat(),
        }
        replay = B10RealityReplay(
            runtime,
            profile,
            rules_at,
            envelope,
            start_us=start_us,
            end_us=end_us,
            identity=identity,
        )
        folder = output / profile.name
        checkpoint = folder / "checkpoint.json"
        saved = None
        if checkpoint.exists():
            saved = json.loads(checkpoint.read_text(encoding="utf-8"))
            replay.restore(saved["replay"])
        journal = AuditJournal(folder / "execution-audit.jsonl", saved["audit"] if saved else None)
        if replay.completed:
            result = replay.finish()
            audit_binding = journal.durable()
            journal.close()
            write_json(folder / "scoreboard.json", result)
            write_json(folder / "audit-manifest.json", audit_binding)
            write_json(folder / "release-signals.json", replay.release_signals)
            results[profile.name] = result
            continue
        checkpoint_at = time.monotonic()
        progress_at = checkpoint_at
        previous_id = None
        for event in iter_history(history, start=start, end_exclusive=end):
            stamp = _datetime_to_micros(event.timestamp)
            if (
                replay.execution.last_trade is not None
                and (stamp, event.trade_id) <= replay.execution.last_trade
            ):
                continue
            if previous_id is not None and event.trade_id != previous_id + 1:
                raise ValueError("UNDECLARED_RAW_TRADE_ID_GAP")
            previous_id = event.trade_id
            tape_index = begin + replay.processed_trades
            canonical_event = int(tape.events[tape_index])
            if (
                canonical_event // EVENT_ORDER_SCALE != stamp
                or D(int(tape.price_ticks[tape_index])) * tape.tick_size != event.price
            ):
                raise ValueError("RAW_FLOW_CANONICAL_PRICE_TAPE_MISMATCH")
            replay.step(
                Trade(
                    stamp,
                    event.trade_id,
                    event.price,
                    event.quantity,
                    event.buyer_is_maker,
                    canonical_event,
                )
            )
            journal.drain(replay.execution)
            if time.monotonic() - checkpoint_at >= 300:
                audit_binding = journal.durable()
                write_json(checkpoint, {"replay": replay.checkpoint(), "audit": audit_binding})
                checkpoint_at = time.monotonic()
            if time.monotonic() - progress_at >= 30:
                print(
                    json.dumps(
                        {
                            "profile": profile.name,
                            "trades": replay.processed_trades,
                            "last_us": replay.last_us,
                            "counts": dict(replay.execution.counts),
                        }
                    ),
                    flush=True,
                )
                progress_at = time.monotonic()
        result = replay.finish()
        audit_binding = journal.durable()
        write_json(checkpoint, {"replay": replay.checkpoint(), "audit": audit_binding})
        journal.close()
        write_json(folder / "scoreboard.json", result)
        write_json(folder / "audit-manifest.json", audit_binding)
        write_json(folder / "release-signals.json", replay.release_signals)
        results[profile.name] = result
    if not results:
        raise ValueError("NO_MATCHING_PROFILE")
    write_json(output / "scoreboard.json", results)
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--profile")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    with (args.output / "b10-reality.lock").open("a+b") as lock:
        if lock.tell() == 0:
            lock.write(b"0")
            lock.flush()
        lock.seek(0)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        print(json.dumps(run(args.config, args.output, args.profile), indent=2))
