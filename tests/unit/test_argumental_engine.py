from datetime import UTC, datetime

from engine.argumental import all_cycle_fortunes, coach_cycle_fortune, score_revolution
from packages.astrology.ephemeris import chart
from packages.astrology.models import (
    Aspect,
    AstrologyChart,
    BodyPosition,
    ChartRequest,
    GeoLocation,
    HouseAngles,
)

MADRID = GeoLocation(40.4168, -3.7038, "Madrid")


def _revolution_with(
    midheaven: float,
    positions: dict[str, tuple[float, bool]],
    aspects: list[Aspect],
) -> AstrologyChart:
    moment = datetime(2030, 1, 1, 12, tzinfo=UTC)
    base = chart(ChartRequest(moment, None, False))
    built = {
        name: BodyPosition(
            name=name,
            longitude=longitude,
            latitude=0.0,
            distance_au=0.0,
            speed_longitude=1.0,
            retrograde=retrograde,
        )
        for name, (longitude, retrograde) in positions.items()
    }
    for name, position in base.positions.items():
        built.setdefault(name, position)
    return AstrologyChart(
        request=ChartRequest(moment, MADRID, True),
        provider=base.provider,
        ephemeris_version=base.ephemeris_version,
        julian_day_ut=base.julian_day_ut,
        positions=built,
        houses=HouseAngles(
            cusps=tuple(float((index * 30 + midheaven - 270) % 360) for index in range(12)),
            ascendant=(midheaven - 270) % 360,
            midheaven=midheaven,
            armc=midheaven,
            vertex=0.0,
            house_system="P",
        ),
        aspects=aspects,
        parameters={**base.parameters, "time_known": True},
    )


def test_score_revolution_rewards_a_dignified_angular_midheaven_ruler() -> None:
    # Midheaven at 5° Leo -> ruler Sun; Sun placed in Leo (domicile) and angular (house 10).
    revolution = _revolution_with(
        midheaven=125.0,
        positions={"Sun": (125.0, False)},
        aspects=[],
    )
    reading = score_revolution(revolution)
    assert reading.midheaven_sign == "Leo"
    assert reading.midheaven_ruler == "Sun"
    assert reading.midheaven_ruler_dignity == "domicile"
    assert reading.midheaven_ruler_house_class == "angular"
    assert reading.fortune_index > 0
    assert reading.adverse_testimonies == ()


def test_score_revolution_penalizes_saturn_square_and_rewards_jupiter_trine() -> None:
    revolution = _revolution_with(
        midheaven=125.0,
        positions={"Sun": (125.0, False)},
        aspects=[
            Aspect("Sun", "Saturn", "square", 90.0, 0.1, True),
            Aspect("Sun", "Jupiter", "trine", 120.0, 0.1, True),
        ],
    )
    reading = score_revolution(revolution)
    assert any("Saturno" in item for item in reading.adverse_testimonies)
    assert any("Júpiter" in item for item in reading.favorable_testimonies)


def test_score_revolution_requires_houses() -> None:
    untimed = chart(ChartRequest(datetime(2030, 1, 1, tzinfo=UTC), None, False))
    try:
        score_revolution(untimed)
    except ValueError as exc:
        assert "known time and location" in str(exc)
    else:
        raise AssertionError("expected ValueError for a chart without houses")


def test_coach_cycle_fortune_is_none_without_a_coach_debut_file() -> None:
    assert coach_cycle_fortune("ZZZ", 2030) is None


def test_coach_cycle_fortune_degrades_explicitly_without_swiss_ephemeris() -> None:
    from packages.astrology import ephemeris as ephemeris_module

    if ephemeris_module.ephemeris_available():
        return  # this repo's default dev env has no swisseph; skip if it ever does
    result = coach_cycle_fortune("ARG", 2030)
    assert result is not None
    assert result.status == "ephemeris_unavailable"
    assert result.fortune_index == 0.0
    assert result.coach_name == "Lionel Scaloni"


def test_all_cycle_fortunes_skips_teams_without_data() -> None:
    results = all_cycle_fortunes(["ARG", "ZZZ"], 2030)
    assert set(results) <= {"ARG"}
