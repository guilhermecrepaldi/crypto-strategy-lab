"""Read-only preliminary audit of one atomic checkpoint and its bound journal prefix."""

import argparse
import hashlib
import json
from pathlib import Path

from audit_b10_reality import audit_raw_support, digest, reconstruct, same


def audit_prefix(config_path, folder):
    config_bytes = config_path.read_bytes()
    config = json.loads(config_bytes)
    checkpoint_bytes = (folder / "checkpoint.json").read_bytes()
    checkpoint = json.loads(checkpoint_bytes)
    binding = checkpoint["audit"]
    hasher = hashlib.sha256()
    remaining = binding["bytes"]

    def rows():
        nonlocal remaining
        with (folder / "execution-audit.jsonl").open("rb") as stream:
            while remaining:
                line = stream.readline(remaining)
                if not line or not line.endswith(b"\n"):
                    raise ValueError("INCOMPLETE_CHECKPOINT_PREFIX")
                hasher.update(line)
                remaining -= len(line)
                yield json.loads(line)

    selected = next(p for p in config["profiles"] if p["profile"]["name"] == folder.name)
    ledger = reconstruct(rows(), selected["profile"])
    if hasher.hexdigest() != binding["sha256"]:
        raise ValueError("CHECKPOINT_PREFIX_HASH_MISMATCH")
    state = checkpoint["replay"]["payload"]["execution"]["state"]
    balances = {}
    for independent, stored in {
        "cash": "cash",
        "reserve": "reserve",
        "inventory": "inventory",
        "basis": "cost",
        "dust": "dust",
        "dust_basis": "dust_cost",
        "fees": "fees",
        "funding": "reserve_funding",
        "consumption": "reserve_consumption",
    }.items():
        same(ledger[independent], state[stored], stored)
        balances[independent] = str(ledger[independent])
    ordinary = [s for s in ledger["settlements"] if not s["release"]]
    releases = [s for s in ledger["settlements"] if s["release"]]
    chosen = {oid for s in ordinary[:100] + releases for oid in s["order_ids"]}
    chosen |= {oid for oid, order in ledger["orders"].items() if order["release"]}
    for signal in ledger["signal_records"].values():
        closing = next(
            (s for s in ledger["settlements"] if s["time_us"] >= signal["time_us"]), None
        )
        chosen.update(closing["order_ids"] if closing else ledger["open_cycle_orders"])
    history_path = Path(config["history_manifest"])
    if digest(history_path) != config["history_manifest_sha256"]:
        raise ValueError("HISTORY_MANIFEST_HASH_MISMATCH")
    support = audit_raw_support(
        json.loads(history_path.read_text()),
        ledger["orders"],
        ledger["fills"],
        chosen,
        ledger["release_evaluations"],
        selected["envelope"],
        config["rules"],
    )
    return {
        "status": "PASS_PRELIMINARY_DURABLE_PREFIX_ONLY",
        "completion_acceptance": False,
        "checkpoint_sha256": hashlib.sha256(checkpoint_bytes).hexdigest(),
        "config_sha256": hashlib.sha256(config_bytes).hexdigest(),
        "audit_prefix": binding,
        "balances": balances,
        "ordinary_settlements": len(ordinary),
        "ordinary_raw_sample": min(100, len(ordinary)),
        "release_settlements": len(releases),
        "release_signals": len(ledger["signal_records"]),
        "raw_support": support,
        "limitations": [
            "Only the captured atomic checkpoint prefix is audited.",
            "Complete replay audit remains required; release BOOK support is a conditional "
            "envelope, not historical L2.",
        ],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--profile-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = audit_prefix(args.config, args.profile_dir)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
