"""Preregister the frozen first USDCUSDT model block in the canonical registry."""

from __future__ import annotations

from pathlib import Path

from crypto_strategy_lab.microstructure.serial_replay import preregistered_first_block
from crypto_strategy_lab.ml.model_registry import (
    Hypothesis,
    ModelLineage,
    ModelRegistration,
    ModelRegistry,
    ModelSpec,
    ModelStatus,
)

CAMPAIGN_ID = "USDCUSDT_EXHAUSTION_V1"

_HYPOTHESES = (
    Hypothesis(
        observation="A causal serial reference is required before testing adaptation.",
        hypothesis=(
            "A one-tick pair selected from the preceding 24 hours may retain positive "
            "price-path throughput after it is frozen for the standardized replay."
        ),
        change="Initial STATIC model: one tick, 24-hour lookback and no reselection.",
        expected_effect=(
            "Provide an interpretable lower-complexity reference and expose level migration."
        ),
        reason_for_new_model="Establish the first causal serial benchmark.",
    ),
    Hypothesis(
        observation="A level frozen for the full replay may become stale as activity moves.",
        hypothesis=(
            "Hourly causal reselection with the same 24-hour lookback improves throughput "
            "without changing tick distance."
        ),
        change="Add flat-only PERIODIC_RESELECT at a one-hour decision interval.",
        expected_effect="Recover activity lost to intraday migration without a time stop.",
        reason_for_new_model="Test the smallest scheduled adaptation from M001.",
    ),
    Hypothesis(
        observation="Hourly decisions may react too slowly to rapidly migrating activity.",
        hypothesis=(
            "One-minute ALWAYS_BEST causal decisions raise throughput at the cost of more "
            "reselections."
        ),
        change="Reduce the flat-only selection interval from one hour to one minute.",
        expected_effect="Increase completed cycles while quantifying reselection churn.",
        reason_for_new_model="Measure the upper-frequency causal adaptation reference.",
    ),
    Hypothesis(
        observation="Continuous best-candidate chasing may create unnecessary thrashing.",
        hypothesis=(
            "A stay-until-bad policy can preserve most M003 throughput with materially fewer "
            "changes."
        ),
        change=(
            "Switch only after 30 flat idle minutes, five confirmations, 10% advantage and "
            "a 60-minute cooldown."
        ),
        expected_effect=(
            "Retain at least 90% of cycles and 99% of equity with at most half the reselections."
        ),
        reason_for_new_model="Test the preregistered anti-thrashing mechanism against M003.",
    ),
)


def register_first_block(
    *,
    artifact_root: str | Path = Path("artifacts"),
    report_root: str | Path = Path("reports"),
) -> tuple[ModelRegistration, ...]:
    """Idempotently register M001-M004 without reading any market partition."""
    registry = ModelRegistry(artifact_root=artifact_root, report_root=report_root)
    configurations = preregistered_first_block()
    registrations: list[ModelRegistration] = []
    ancestors: list[str] = []
    for configuration, hypothesis in zip(configurations, _HYPOTHESES, strict=True):
        model_payload = configuration.model_dump(
            mode="json", exclude={"model_id", "parent_model_id"}
        )
        parent = configuration.parent_model_id
        lineage = ModelLineage(
            parent_model_id=parent,
            ancestor_chain=tuple(ancestors),
            change_category="INITIAL" if parent is None else "DECISION_RULE",
            change_summary=hypothesis.change,
            references={
                "campaign_id": CAMPAIGN_ID,
                "journal": "docs/microstructure/USDCUSDT_EXPERIMENT_JOURNAL.md",
            },
        )
        registration = registry.register(
            ModelSpec(
                model_id=configuration.model_id,
                model=model_payload,
                hypothesis=hypothesis,
                lineage=lineage,
                status=ModelStatus.CREATED,
                model_hash=configuration.model_hash,
            )
        )
        registrations.append(registration)
        ancestors.append(configuration.model_id)
    return tuple(registrations)


__all__ = ["CAMPAIGN_ID", "register_first_block"]
