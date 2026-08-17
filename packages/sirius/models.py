from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any

from packages.common.provenance import DataGrade
from packages.common.types import SiriusMode


class EvidenceLayer(StrEnum):
    STRUCTURAL = "structural"
    ANNUAL = "annual"
    TOURNAMENT = "tournament"
    MATCH = "match"


class Polarity(StrEnum):
    FAVORABLE = "favorable"
    ADVERSE = "adverse"
    NEUTRAL = "neutral"


@dataclass(frozen=True, slots=True)
class FeatureObservation:
    feature_id: str
    layer: EvidenceLayer
    polarity: Polarity
    strength: float
    data_grade: DataGrade
    data_confidence: float
    hour_robustness: float | None
    explicit_public_rule: bool
    description: str
    parameters: dict[str, Any] = field(default_factory=dict)
    source_claim_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not 0 <= self.strength <= 1:
            raise ValueError("strength must be in [0, 1]")
        if not 0 <= self.data_confidence <= 1:
            raise ValueError("data_confidence must be in [0, 1]")
        if self.hour_robustness is not None and not 0 <= self.hour_robustness <= 1:
            raise ValueError("hour_robustness must be in [0, 1]")


@dataclass(frozen=True, slots=True)
class IndexResult:
    value: float | None
    status: str
    evidence_count: int


@dataclass(slots=True)
class SiriusAssessment:
    subject_id: str
    mode: SiriusMode
    journey_index: IndexResult
    coronation_index: IndexResult
    data_confidence: float
    favorable: list[FeatureObservation]
    adverse: list[FeatureObservation]
    neutral: list[FeatureObservation]
    contradictions: list[dict[str, Any]]
    hour_robustness: float | None
    explanation: str
    feature_contributions: list[dict[str, Any]]
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
