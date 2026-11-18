from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def _index_value(assessment: Mapping[str, Any], key: str) -> float | None:
    raw_index = assessment.get(key)
    if not isinstance(raw_index, Mapping):
        return None
    value = raw_index.get("value")
    if value is None:
        return None
    return float(value)


def sirius_application_status(
    assessments: Mapping[str, Mapping[str, Any]],
    evidence_audit: Mapping[str, Any],
) -> dict[str, Any]:
    """Describe whether reviewed Sirius evidence can alter relative team strength.

    The match layer uses relative adjustments. A common adjustment shared by every
    team cancels out, so Sirius is only effective when reviewed assessments produce
    at least two distinct confidence-weighted signals.
    """

    effective_signals: dict[str, float] = {}
    nonzero_teams = 0
    for team_id, assessment in assessments.items():
        confidence = float(assessment.get("data_confidence", 0.0) or 0.0)
        journey = _index_value(assessment, "journey_index")
        coronation = _index_value(assessment, "coronation_index")
        signal = (
            ((journey - 50.0) / 50.0 if journey is not None else 0.0)
            + (0.5 * (coronation - 50.0) / 50.0 if coronation is not None else 0.0)
        ) * confidence
        effective_signals[str(team_id)] = signal
        if abs(signal) > 1e-12:
            nonzero_teams += 1

    values = list(effective_signals.values())
    differential = (max(values) - min(values)) if values else 0.0
    effective = differential > 1e-12
    reviewed = int(evidence_audit.get("reviewed_observations", 0) or 0)
    if effective:
        status = "active_reviewed_evidence"
        label = "Sirius experimental activo"
    elif reviewed == 0:
        status = "neutral_no_reviewed_evidence"
        label = "Sirius neutral: sin evidencia revisada"
    else:
        status = "neutral_no_differential_signal"
        label = "Sirius neutral: la evidencia no cambia fuerzas relativas"

    return {
        "status": status,
        "label": label,
        "effective": effective,
        "reviewed_observations": reviewed,
        "pending_observations": int(evidence_audit.get("pending_observations", 0) or 0),
        "teams_with_evidence": int(evidence_audit.get("teams_with_evidence", 0) or 0),
        "teams_with_nonzero_adjustment": nonzero_teams,
    }
