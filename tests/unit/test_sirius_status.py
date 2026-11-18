from packages.sirius import sirius_application_status


def _assessment(journey: float | None, coronation: float | None, confidence: float) -> dict:
    return {
        "journey_index": {"value": journey},
        "coronation_index": {"value": coronation},
        "data_confidence": confidence,
    }


def test_sirius_is_explicitly_neutral_without_reviewed_evidence() -> None:
    status = sirius_application_status(
        {"ARG": _assessment(None, None, 0.0)},
        {"reviewed_observations": 0, "teams_with_evidence": 0},
    )
    assert status["effective"] is False
    assert status["status"] == "neutral_no_reviewed_evidence"
    assert status["teams_with_nonzero_adjustment"] == 0


def test_sirius_is_active_only_with_differential_reviewed_signal() -> None:
    status = sirius_application_status(
        {
            "ARG": _assessment(70.0, 60.0, 0.8),
            "ESP": _assessment(45.0, 50.0, 0.7),
        },
        {"reviewed_observations": 2, "teams_with_evidence": 2},
    )
    assert status["effective"] is True
    assert status["status"] == "active_reviewed_evidence"
    assert status["teams_with_nonzero_adjustment"] == 2
