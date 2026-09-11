from __future__ import annotations

import argparse
import hashlib
import subprocess
from pathlib import Path

from crypto_strategy_lab.microstructure.m034_forward_paper import (
    CANONICAL_SYMBOLS,
    ForwardDiagnosticError,
    ForwardPaperDiagnosticRunner,
    claim_identity,
    default_public_client,
    load_config,
)
from crypto_strategy_lab.microstructure.public_market import connect_market_stream

ROOT = Path(__file__).resolve().parents[1]
SOURCE_PATHS = (
    "scripts/run_m034_forward_diagnostic.py",
    "src/crypto_strategy_lab/microstructure",
    "pyproject.toml",
    "uv.lock",
)


def git(*args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def verify_published_source(source_sha: str) -> None:
    head = git("rev-parse", "HEAD")
    remote = git("rev-parse", "origin/main")
    if head != remote:
        raise ForwardDiagnosticError("M034_FORWARD_HEAD_NOT_PUBLISHED")
    if git("merge-base", "--is-ancestor", source_sha, head):
        raise ForwardDiagnosticError("M034_FORWARD_SOURCE_NOT_ANCESTOR")
    dirty = git("status", "--porcelain", "--", *SOURCE_PATHS)
    changed = git("diff", "--name-only", source_sha, "--", *SOURCE_PATHS)
    if dirty or changed:
        raise ForwardDiagnosticError("M034_FORWARD_REVIEWED_SOURCE_CHANGED")


def verify_artifact(path_value: str, expected_sha256: str, *, label: str) -> None:
    artifact = (ROOT / path_value).resolve()
    if ROOT not in artifact.parents or not artifact.is_file():
        raise ForwardDiagnosticError(f"M034_FORWARD_{label}_ARTIFACT_MISSING")
    actual = hashlib.sha256(artifact.read_bytes()).hexdigest()
    if actual != expected_sha256:
        raise ForwardDiagnosticError(f"M034_FORWARD_{label}_HASH_MISMATCH")
    relative = artifact.relative_to(ROOT).as_posix()
    if git("status", "--porcelain", "--", relative):
        raise ForwardDiagnosticError(f"M034_FORWARD_{label}_NOT_FROZEN")
    try:
        tracked = git("ls-files", "--error-unmatch", "--", relative)
    except subprocess.CalledProcessError as exc:
        raise ForwardDiagnosticError(f"M034_FORWARD_{label}_NOT_PUBLISHED") from exc
    if tracked != relative:
        raise ForwardDiagnosticError(f"M034_FORWARD_{label}_NOT_PUBLISHED")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the one-shot M034 Binance forward paper diagnostic."
    )
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config_path = args.config.resolve()
    output_path = args.output.resolve()
    if ROOT not in config_path.parents:
        raise ForwardDiagnosticError("M034_FORWARD_CONFIG_MUST_BE_INSIDE_REPOSITORY")
    if ROOT not in output_path.parents:
        raise ForwardDiagnosticError("M034_FORWARD_OUTPUT_MUST_BE_INSIDE_REPOSITORY")
    if output_path.exists():
        raise ForwardDiagnosticError("M034_FORWARD_OUTPUT_ALREADY_EXISTS")
    config = load_config(config_path)
    verify_published_source(config.source_sha)
    verify_artifact(
        config_path.relative_to(ROOT).as_posix(),
        hashlib.sha256(config_path.read_bytes()).hexdigest(),
        label="CONFIGURATION",
    )
    verify_artifact(
        config.source_review_artifact,
        config.source_review_sha256,
        label="SOURCE_REVIEW",
    )
    verify_artifact(
        config.fee_evidence_artifact,
        config.fee_evidence_sha256,
        label="FEE_EVIDENCE",
    )
    claim_artifact = claim_identity(config, output_path, root=ROOT)
    runner = ForwardPaperDiagnosticRunner(
        config=config,
        public_client=default_public_client(),
        stream_factory=lambda symbols: connect_market_stream(
            symbols=symbols,
            depth_interval_ms=1000,
            forward_depth=True,
        ),
        claim_artifact=claim_artifact,
    )
    if tuple(CANONICAL_SYMBOLS) != tuple(runner.states) and runner.states:
        raise ForwardDiagnosticError("M034_FORWARD_PREEXISTING_RUNTIME_STATE")
    result = runner.run(output_path)
    if result["status"] != "COMPLETE":
        raise ForwardDiagnosticError(str(result["failure"]))


if __name__ == "__main__":
    main()
