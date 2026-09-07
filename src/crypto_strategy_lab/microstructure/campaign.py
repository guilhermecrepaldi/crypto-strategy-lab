"""Preregister the frozen first USDCUSDT model block in the canonical registry."""

from __future__ import annotations

from pathlib import Path

from crypto_strategy_lab.microstructure.serial_replay import (
    SerialModelConfig,
    preregistered_corrected_block,
    preregistered_first_block,
)
from crypto_strategy_lab.ml.model_registry import (
    Hypothesis,
    ModelLineage,
    ModelRegistration,
    ModelRegistry,
    ModelSpec,
    ModelStatus,
)

CAMPAIGN_ID = "USDCUSDT_EXHAUSTION_V1"
LEGACY_TICK_ASSUMPTION_REASON = "UNVERIFIED_HISTORICAL_TICK_ASSUMPTION"

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

_CORRECTED_HYPOTHESES = (
    Hypothesis(
        observation=(
            "The first tape pass exposed a historical tick transition before any model ran."
        ),
        hypothesis=(
            "A pair one causally known exchange tick wide, selected from the preceding 24 "
            "hours, may retain positive price-path throughput when frozen."
        ),
        change=(
            "Replace M001's unverified constant-tick assumption with the announcement-bound, "
            "causal observed-grid policy; keep STATIC selection and every economic rule."
        ),
        expected_effect=(
            "Restore admissible historical price levels without using a future grid or changing "
            "the serial benchmark."
        ),
        reason_for_new_model="Correct M001 before execution under a new hashed tick semantics.",
    ),
    Hypothesis(
        observation="M005 can become stale as market activity moves.",
        hypothesis=(
            "Hourly causal reselection with M005's tick-at-selection semantics improves "
            "throughput without changing its distance rule."
        ),
        change="Add flat-only PERIODIC_RESELECT at a one-hour decision interval to M005.",
        expected_effect="Recover intraday level migration relative to M005.",
        reason_for_new_model="Test the smallest scheduled adaptation from M005.",
    ),
    Hypothesis(
        observation="M006 hourly decisions may react too slowly to migrating activity.",
        hypothesis=(
            "One-minute ALWAYS_BEST decisions with the same causal tick policy raise throughput "
            "at the cost of more reselections."
        ),
        change="Reduce M006's flat-only selection interval from one hour to one minute.",
        expected_effect="Increase completed cycles while quantifying reselection churn.",
        reason_for_new_model="Measure the upper-frequency adaptation reference against M006.",
    ),
    Hypothesis(
        observation="M007 may create unnecessary candidate thrashing.",
        hypothesis=(
            "A stay-until-bad policy can preserve most M007 throughput with materially fewer "
            "changes."
        ),
        change=(
            "Relative to M007, switch only after 30 flat idle minutes, five confirmations, 10% "
            "advantage and a 60-minute cooldown."
        ),
        expected_effect=(
            "Retain at least 90% of M007 cycles and 99% of its equity with at most half its "
            "reselections."
        ),
        reason_for_new_model="Test the preregistered anti-thrashing mechanism against M007.",
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
        model_payload = _model_payload(configuration)
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


def register_active_block(
    *,
    artifact_root: str | Path = Path("artifacts"),
    report_root: str | Path = Path("reports"),
) -> tuple[ModelRegistration, ...]:
    """Register corrected M005-M008, then supersede the never-run legacy block."""
    legacy = register_first_block(artifact_root=artifact_root, report_root=report_root)
    registry = ModelRegistry(artifact_root=artifact_root, report_root=report_root)
    legacy_ids = {item.model_id for item in legacy}
    if any(
        event["event_type"] == "RUN_REGISTERED" and event["payload"].get("model_id") in legacy_ids
        for event in registry.journal()
    ):
        raise ValueError("legacy tick-assumption block has a registered run; refusing supersession")
    incompatible = {
        model_id: registry.current_status(model_id)
        for model_id in legacy_ids
        if registry.current_status(model_id) not in {ModelStatus.CREATED, ModelStatus.SUPERSEDED}
    }
    if incompatible:
        raise ValueError(f"legacy tick-assumption block has incompatible states: {incompatible}")
    registrations: list[ModelRegistration] = []
    ancestors: list[str] = []
    for offset, (configuration, hypothesis) in enumerate(
        zip(preregistered_corrected_block(), _CORRECTED_HYPOTHESES, strict=True), start=1
    ):
        model_payload = _model_payload(configuration)
        parent = configuration.parent_model_id
        lineage = ModelLineage(
            parent_model_id=parent,
            ancestor_chain=tuple(ancestors),
            change_category="TECHNICAL_CORRECTION" if parent is None else "DECISION_RULE",
            change_summary=hypothesis.change,
            references={
                "campaign_id": CAMPAIGN_ID,
                "journal": "docs/microstructure/USDCUSDT_EXPERIMENT_JOURNAL.md",
                "supersedes": f"M{offset:03d}",
                "reason": LEGACY_TICK_ASSUMPTION_REASON,
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
    for registration in legacy:
        if registry.current_status(registration.model_id) == ModelStatus.CREATED:
            registry.transition(
                registration.model_id,
                ModelStatus.SUPERSEDED,
                reason=LEGACY_TICK_ASSUMPTION_REASON,
            )
    return tuple(registrations)


def _model_payload(configuration: SerialModelConfig) -> dict[str, object]:
    payload: dict[str, object] = configuration.model_dump(
        mode="json", exclude={"model_id", "parent_model_id"}
    )
    if configuration.capital_release_protocol is None:
        payload.pop("capital_release_protocol")
    if payload.get("distance_semantics") is None:
        for field_name in (
            "distance_semantics",
            "selection_moment",
            "tick_source",
            "tick_evidence_class",
            "selected_levels_remain_absolute",
        ):
            payload.pop(field_name)
    return payload


__all__ = [
    "CAMPAIGN_ID",
    "LEGACY_TICK_ASSUMPTION_REASON",
    "register_active_block",
    "register_first_block",
]
