"""Motor Sirius estructurado, experimental y separado del baseline futbolístico."""

from .engine import SiriusEngine
from .models import EvidenceLayer, FeatureObservation, IndexResult, Polarity, SiriusAssessment
from .registry import SiriusRule, load_rule_registry, observation_from_technique

__all__ = [
    "EvidenceLayer",
    "FeatureObservation",
    "IndexResult",
    "Polarity",
    "SiriusAssessment",
    "SiriusEngine",
    "SiriusRule",
    "load_rule_registry",
    "observation_from_technique",
]
