import pytest

from packages.astrology import TechniqueResult
from packages.common.provenance import DataGrade
from packages.common.types import SiriusMode
from packages.sirius import (
    EvidenceLayer,
    FeatureObservation,
    Polarity,
    SiriusEngine,
    SiriusRule,
    observation_from_technique,
)


def observation(
    feature_id: str,
    layer: EvidenceLayer,
    polarity: Polarity,
    *,
    explicit: bool = True,
    grade: DataGrade = DataGrade.B,
) -> FeatureObservation:
    return FeatureObservation(
        feature_id=feature_id,
        layer=layer,
        polarity=polarity,
        strength=0.8,
        data_grade=grade,
        data_confidence=0.75,
        hour_robustness=0.9,
        explicit_public_rule=explicit,
        description="testimony",
    )


def test_purist_excludes_inferred_rules_and_keeps_data_quality_separate() -> None:
    observations = [
        observation("coach_cycle", EvidenceLayer.STRUCTURAL, Polarity.FAVORABLE),
        observation("inferred", EvidenceLayer.ANNUAL, Polarity.ADVERSE, explicit=False),
    ]
    assessment = SiriusEngine().evaluate("ARG", observations, SiriusMode.PURIST)
    assert [item.feature_id for item in assessment.favorable] == ["coach_cycle"]
    assert not assessment.adverse
    assert assessment.journey_index.value is not None
    assert assessment.journey_index.status == "descriptive_not_trained"
    assert assessment.data_confidence == 0.75 * 0.85


def test_calibrated_mode_is_available_but_explicitly_untrained() -> None:
    observations = [
        observation("solar_return", EvidenceLayer.ANNUAL, Polarity.FAVORABLE),
        observation("solar_return", EvidenceLayer.ANNUAL, Polarity.ADVERSE),
    ]
    assessment = SiriusEngine().evaluate("ARG", observations, SiriusMode.CALIBRATED)
    assert assessment.contradictions[0]["feature_id"] == "solar_return"
    assert any("no se entrenaron" in warning for warning in assessment.warnings)
    assert assessment.hour_robustness == 0.9


def test_time_dependent_sirius_rule_requires_explicit_true_time_metadata() -> None:
    rule = SiriusRule(
        feature_id="solar_return",
        layer=EvidenceLayer.ANNUAL,
        explicit_public_rule=True,
        requires_known_time=True,
        implementation_status="implemented",
    )
    technique = TechniqueResult("solar_return", {}, {})
    with pytest.raises(ValueError, match="known real time"):
        observation_from_technique(
            rule,
            technique,
            Polarity.NEUTRAL,
            0.0,
            DataGrade.B,
            0.5,
            None,
            ("claim-1",),
        )
    with pytest.raises(ValueError, match="at least one source claim"):
        observation_from_technique(
            rule,
            TechniqueResult("solar_return", {}, {"time_known": True}),
            Polarity.NEUTRAL,
            0.0,
            DataGrade.B,
            0.5,
            None,
            (),
        )
