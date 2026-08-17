from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from statistics import fmean, median

from packages.common.types import SiriusMode

from .models import (
    EvidenceLayer,
    FeatureObservation,
    IndexResult,
    Polarity,
    SiriusAssessment,
)

GRADE_FACTOR = {"A": 1.0, "B": 0.85, "C": 0.60, "D": 0.35, "X": 0.20}
JOURNEY_LAYERS = {EvidenceLayer.STRUCTURAL, EvidenceLayer.ANNUAL, EvidenceLayer.TOURNAMENT}
CORONATION_LAYERS = {EvidenceLayer.ANNUAL, EvidenceLayer.TOURNAMENT, EvidenceLayer.MATCH}


def _contradictions(observations: list[FeatureObservation]) -> list[dict[str, object]]:
    grouped: dict[str, set[Polarity]] = defaultdict(set)
    for observation in observations:
        grouped[observation.feature_id].add(observation.polarity)
    return [
        {
            "feature_id": feature_id,
            "polarities": sorted(polarity.value for polarity in polarities),
        }
        for feature_id, polarities in grouped.items()
        if Polarity.FAVORABLE in polarities and Polarity.ADVERSE in polarities
    ]


def _descriptive_index(
    observations: Iterable[FeatureObservation],
    weights: Mapping[str, float],
) -> tuple[IndexResult, list[dict[str, object]]]:
    usable = [item for item in observations if item.polarity != Polarity.NEUTRAL]
    contributions: list[dict[str, object]] = []
    numerator = 0.0
    denominator = 0.0
    for item in usable:
        sign = 1.0 if item.polarity == Polarity.FAVORABLE else -1.0
        weight = float(weights.get(item.feature_id, 1.0))
        reliability = GRADE_FACTOR[item.data_grade.value] * item.data_confidence
        contribution = sign * item.strength * reliability * weight
        numerator += contribution
        denominator += abs(weight) * reliability
        contributions.append(
            {
                "feature_id": item.feature_id,
                "layer": item.layer.value,
                "polarity": item.polarity.value,
                "raw_strength": item.strength,
                "data_reliability": reliability,
                "configured_weight": weight,
                "contribution": contribution,
            }
        )
    if not usable or denominator == 0:
        return IndexResult(None, "insufficient_evidence", len(usable)), contributions
    value = 50.0 + 50.0 * numerator / denominator
    return IndexResult(
        max(0.0, min(100.0, value)), "descriptive_not_trained", len(usable)
    ), contributions


class SiriusEngine:
    """Structured Sirius testimony engine; observations remain visible and auditable."""

    def __init__(
        self,
        calibrated_weights: Mapping[str, float] | None = None,
        calibrated_version: str | None = None,
    ):
        self.calibrated_weights = dict(calibrated_weights or {})
        self.calibrated_version = calibrated_version

    def evaluate(
        self,
        subject_id: str,
        observations: Iterable[FeatureObservation],
        mode: SiriusMode = SiriusMode.PURIST,
    ) -> SiriusAssessment:
        all_observations = list(observations)
        warnings = [
            "Modelo experimental sin validez científica demostrada.",
            "Fuerza descriptiva y calidad de datos se informan por separado.",
        ]
        if mode == SiriusMode.PURIST:
            selected = [item for item in all_observations if item.explicit_public_rule]
            weights: dict[str, float] = {}
        else:
            selected = all_observations
            weights = self.calibrated_weights
            if self.calibrated_version is None:
                warnings.append(
                    "SIRIUS_CALIBRATED usa pesos unitarios: todavía no se entrenaron pesos."
                )

        journey, journey_contributions = _descriptive_index(
            (item for item in selected if item.layer in JOURNEY_LAYERS), weights
        )
        coronation, coronation_contributions = _descriptive_index(
            (item for item in selected if item.layer in CORONATION_LAYERS), weights
        )
        favorable = [item for item in selected if item.polarity == Polarity.FAVORABLE]
        adverse = [item for item in selected if item.polarity == Polarity.ADVERSE]
        neutral = [item for item in selected if item.polarity == Polarity.NEUTRAL]
        confidences = [
            item.data_confidence * GRADE_FACTOR[item.data_grade.value] for item in selected
        ]
        robustness_values = [
            item.hour_robustness for item in selected if item.hour_robustness is not None
        ]
        contradiction_rows = _contradictions(selected)
        explanation = (
            f"{len(favorable)} testimonios favorables, {len(adverse)} adversos y "
            f"{len(neutral)} neutrales. "
            f"La confianza de datos es {fmean(confidences):.1%}. "
            "Los índices son balances descriptivos, no probabilidades ni pesos entrenados."
            if confidences
            else "No hay evidencia suficiente; no se imputaron datos faltantes."
        )
        return SiriusAssessment(
            subject_id=subject_id,
            mode=mode,
            journey_index=journey,
            coronation_index=coronation,
            data_confidence=fmean(confidences) if confidences else 0.0,
            favorable=favorable,
            adverse=adverse,
            neutral=neutral,
            contradictions=contradiction_rows,
            hour_robustness=median(robustness_values) if robustness_values else None,
            explanation=explanation,
            feature_contributions=journey_contributions + coronation_contributions,
            warnings=warnings,
        )
