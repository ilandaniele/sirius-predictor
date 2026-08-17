from datetime import UTC, datetime

import pytest

from packages.astrology import (
    ChartRequest,
    GeoLocation,
    antiscia,
    birth_time_sensitivity,
    chart,
    essential_dignities,
    primary_directions,
)

MADRID = GeoLocation(40.4168, -3.7038, "Madrid")


def test_known_j2000_chart_is_deterministic_and_records_provider() -> None:
    request = ChartRequest(datetime(2000, 1, 1, 12, tzinfo=UTC), None, False, label="J2000")
    first = chart(request)
    second = chart(request)
    assert first.to_dict() == second.to_dict()
    assert 279 < first.positions["Sun"].longitude < 282
    assert 210 < first.positions["Moon"].longitude < 230
    assert first.provider in {"Swiss Ephemeris", "explicit mean-motion fallback"}
    assert first.parameters["time_known"] is False


def test_unknown_time_never_calculates_angles_or_houses() -> None:
    request = ChartRequest(datetime(1980, 1, 1, 12, tzinfo=UTC), MADRID, False)
    result = chart(request)
    assert result.houses is None
    assert result.parameters["house_system"] is None
    with pytest.raises(ValueError, match="reliable real birth time"):
        primary_directions(result, datetime(2030, 7, 21, 16, tzinfo=UTC))


def test_birth_time_sensitivity_labels_samples_as_synthetic() -> None:
    result = birth_time_sensitivity(
        datetime(1980, 1, 1, tzinfo=UTC),
        "Europe/Madrid",
        MADRID,
        step_minutes=60,
    )
    assert result.result["sample_count"] == 24
    assert result.parameters["synthetic_times"] is True
    assert "Sun" in result.result["invariant_signs"]


def test_unweighted_techniques_return_testimonies_without_a_score() -> None:
    result = chart(ChartRequest(datetime(2030, 7, 21, 16, tzinfo=UTC), None, False))
    dignities = essential_dignities(result)
    mirrored = antiscia(result)
    assert set(dignities.result) == set(result.positions)
    assert 0 <= mirrored.result["Sun"]["antiscia"] < 360
    assert "score" not in dignities.result
