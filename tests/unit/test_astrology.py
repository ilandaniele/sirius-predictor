from datetime import UTC, datetime

import pytest

from packages.astrology import (
    AstrologyChart,
    ChartRequest,
    GeoLocation,
    accidental_dignities,
    antiscia,
    arabic_parts,
    birth_time_sensitivity,
    chart,
    demi_lunar,
    essential_dignities,
    fixed_star_contacts,
    harmonic_chart,
    kickoff_time_sensitivity,
    lunar_return,
    primary_directions,
    quarti_lunar,
    solar_return,
)
from packages.astrology.models import HouseAngles

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
    assert all("fall" in row for row in dignities.result.values())


def test_time_dependent_returns_never_use_an_unknown_natal_time() -> None:
    untimed = chart(ChartRequest(datetime(1980, 1, 1, 12, tzinfo=UTC), None, False))
    event = datetime(2030, 6, 1, tzinfo=UTC)
    with pytest.raises(ValueError, match="known real natal time"):
        solar_return(untimed, 2030, MADRID)
    for technique in (lunar_return, demi_lunar, quarti_lunar):
        with pytest.raises(ValueError, match="known real natal time"):
            technique(untimed, event, MADRID)


def test_solar_return_handles_a_leap_day_natal_moment() -> None:
    natal = chart(ChartRequest(datetime(2012, 2, 29, 20, tzinfo=UTC), MADRID, True))
    result = solar_return(natal, 2018, MADRID)  # 2018 is not a leap year
    returned_sun = result.result["chart"]["positions"]["Sun"]["longitude"]
    delta = abs((returned_sun - natal.positions["Sun"].longitude + 180) % 360 - 180)
    assert delta < 0.01


def test_kickoff_sensitivity_and_star_orbs_validate_inputs() -> None:
    request = ChartRequest(datetime(2030, 7, 21, 16, tzinfo=UTC), MADRID, False)
    with pytest.raises(ValueError, match="scheduled base time"):
        kickoff_time_sensitivity(request)
    base = chart(ChartRequest(request.moment, None, False))
    with pytest.raises(ValueError, match="between 0 and 10"):
        fixed_star_contacts(base, [], orb=-1)


def _manual_timed_chart() -> AstrologyChart:
    moment = datetime(2030, 7, 21, 16, tzinfo=UTC)
    untimed = chart(ChartRequest(moment, None, False))
    return AstrologyChart(
        request=ChartRequest(moment, MADRID, True),
        provider=untimed.provider,
        ephemeris_version=untimed.ephemeris_version,
        julian_day_ut=untimed.julian_day_ut,
        positions=untimed.positions,
        houses=HouseAngles(
            cusps=tuple(float(index * 30) for index in range(12)),
            ascendant=0.0,
            midheaven=270.0,
            armc=270.0,
            vertex=180.0,
            house_system="P",
        ),
        aspects=untimed.aspects,
        parameters={**untimed.parameters, "time_known": True},
    )


def test_harmonics_are_descriptive_deterministic_and_unweighted() -> None:
    base = chart(ChartRequest(datetime(2030, 7, 21, 16, tzinfo=UTC), None, False))
    result = harmonic_chart(base, 5)
    expected = (base.positions["Sun"].longitude * 5) % 360
    assert result.result["positions"]["Sun"]["longitude"] == pytest.approx(expected)
    assert result.parameters["houses_used"] is False
    assert result.parameters["weighted"] is False
    with pytest.raises(ValueError, match="positive integer"):
        harmonic_chart(base, 0)


def test_accidental_dignities_and_configurable_parts_require_real_time() -> None:
    timed = _manual_timed_chart()
    dignities = accidental_dignities(timed)
    assert set(dignities.result) == set(timed.positions)
    assert all("house_class" in row for row in dignities.result.values())
    parts = arabic_parts(
        timed,
        {
            "custom_mars_venus": {
                "day": ("Ascendant", "Mars", "Venus"),
                "night": ("Ascendant", "Venus", "Mars"),
            }
        },
    )
    assert {"fortune", "spirit", "victory", "custom_mars_venus"} <= set(parts.result)
    assert parts.parameters["sect"] in {"day", "night"}

    untimed = chart(ChartRequest(datetime(2030, 7, 21, 16, tzinfo=UTC), MADRID, False))
    with pytest.raises(ValueError, match="real known time"):
        accidental_dignities(untimed)
    with pytest.raises(ValueError, match="real known time"):
        arabic_parts(untimed)
