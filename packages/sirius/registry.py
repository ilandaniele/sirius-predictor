from __future__ import annotations

from dataclasses import dataclass

import yaml

from packages.astrology.models import TechniqueResult
from packages.common.provenance import DataGrade

from .models import EvidenceLayer, FeatureObservation, Polarity


@dataclass(frozen=True, slots=True)
class SiriusRule:
    feature_id: str
    layer: EvidenceLayer
    explicit_public_rule: bool
    requires_known_time: bool
    implementation_status: str


def load_rule_registry(path: str) -> dict[str, SiriusRule]:
    with open(path, encoding="utf-8") as handle:
        raw = yaml.safe_load(handle)
    return {
        item["id"]: SiriusRule(
            feature_id=item["id"],
            layer=EvidenceLayer(item["layer"]),
            explicit_public_rule=bool(item["explicit_public_rule"]),
            requires_known_time=bool(item.get("requires_known_time", False)),
            implementation_status=str(item["implementation_status"]),
        )
        for item in raw["rules"]
    }


def observation_from_technique(
    rule: SiriusRule,
    technique: TechniqueResult,
    polarity: Polarity,
    strength: float,
    grade: DataGrade,
    confidence: float,
    hour_robustness: float | None,
    source_claim_ids: tuple[str, ...],
) -> FeatureObservation:
    if rule.requires_known_time and technique.parameters.get("time_known") is False:
        raise ValueError(f"{rule.feature_id} requires a known real time")
    return FeatureObservation(
        feature_id=rule.feature_id,
        layer=rule.layer,
        polarity=polarity,
        strength=strength,
        data_grade=grade,
        data_confidence=confidence,
        hour_robustness=hour_robustness,
        explicit_public_rule=rule.explicit_public_rule,
        description=technique.technique,
        parameters={"technique": technique.result, "calculation": technique.parameters},
        source_claim_ids=source_claim_ids,
    )
