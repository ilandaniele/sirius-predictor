from __future__ import annotations

from datetime import UTC, datetime
from itertools import combinations

from .models import Aspect, AstrologyChart, BodyPosition, ChartRequest, HouseAngles

try:
    import swisseph as swe  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - depends on the Python platform
    swe = None


BODIES = (
    "Sun",
    "Moon",
    "Mercury",
    "Venus",
    "Mars",
    "Jupiter",
    "Saturn",
    "Uranus",
    "Neptune",
    "Pluto",
    "MeanNode",
)
ASPECT_ANGLES = {
    "conjunction": 0.0,
    "sextile": 60.0,
    "square": 90.0,
    "trine": 120.0,
    "opposition": 180.0,
}
DEFAULT_ORBS = {
    "conjunction": 8.0,
    "sextile": 4.0,
    "square": 6.0,
    "trine": 6.0,
    "opposition": 8.0,
}
FALLBACK_ELEMENTS = {
    "Sun": (280.466, 365.256),
    "Moon": (218.316, 27.321661),
    "Mercury": (252.251, 87.969),
    "Venus": (181.980, 224.701),
    "Mars": (355.433, 686.980),
    "Jupiter": (34.351, 4332.589),
    "Saturn": (50.077, 10759.22),
    "Uranus": (314.055, 30685.4),
    "Neptune": (304.348, 60189.0),
    "Pluto": (238.929, 90560.0),
    "MeanNode": (125.045, -6798.38),
}


class EphemerisUnavailable(RuntimeError):
    pass


def angular_distance(left: float, right: float) -> float:
    return abs((left - right + 180.0) % 360.0 - 180.0)


def signed_angular_delta(value: float, target: float) -> float:
    return (value - target + 180.0) % 360.0 - 180.0


def _julian_day(moment: datetime) -> float:
    utc = moment.astimezone(UTC)
    hour = utc.hour + utc.minute / 60.0 + utc.second / 3600.0 + utc.microsecond / 3.6e9
    if swe is not None:
        return float(swe.julday(utc.year, utc.month, utc.day, hour))
    return 2451545.0 + (utc - datetime(2000, 1, 1, 12, tzinfo=UTC)).total_seconds() / 86400


def _fallback_position(name: str, julian_day: float) -> BodyPosition:
    origin, period = FALLBACK_ELEMENTS[name]
    motion = 360.0 / period
    longitude = (origin + motion * (julian_day - 2451545.0)) % 360.0
    return BodyPosition(
        name=name,
        longitude=longitude,
        latitude=0.0,
        distance_au=0.0,
        speed_longitude=motion,
        retrograde=motion < 0,
    )


def _swiss_body_ids() -> dict[str, int]:
    if swe is None:
        return {}
    return {
        "Sun": swe.SUN,
        "Moon": swe.MOON,
        "Mercury": swe.MERCURY,
        "Venus": swe.VENUS,
        "Mars": swe.MARS,
        "Jupiter": swe.JUPITER,
        "Saturn": swe.SATURN,
        "Uranus": swe.URANUS,
        "Neptune": swe.NEPTUNE,
        "Pluto": swe.PLUTO,
        "MeanNode": swe.MEAN_NODE,
    }


def _position(name: str, julian_day: float) -> BodyPosition:
    if swe is None:
        return _fallback_position(name, julian_day)
    calculation = swe.calc_ut(julian_day, _swiss_body_ids()[name], swe.FLG_SPEED)
    # pysweph adds a third, human-readable warning/error field while retaining
    # positions and flags in the first two entries.
    values = calculation[0]
    return BodyPosition(
        name=name,
        longitude=float(values[0] % 360.0),
        latitude=float(values[1]),
        distance_au=float(values[2]),
        speed_longitude=float(values[3]),
        retrograde=bool(values[3] < 0),
    )


def calculate_aspects(
    positions: dict[str, BodyPosition],
    orbs: dict[str, float] | None = None,
) -> list[Aspect]:
    configured_orbs = {**DEFAULT_ORBS, **(orbs or {})}
    results: list[Aspect] = []
    for left_name, right_name in combinations(sorted(positions), 2):
        left, right = positions[left_name], positions[right_name]
        separation = angular_distance(left.longitude, right.longitude)
        for aspect_name, exact_angle in ASPECT_ANGLES.items():
            orb = abs(separation - exact_angle)
            if orb <= configured_orbs[aspect_name]:
                relative_speed = left.speed_longitude - right.speed_longitude
                current_error = signed_angular_delta(left.longitude - right.longitude, exact_angle)
                applying = current_error * relative_speed < 0 if relative_speed else None
                results.append(
                    Aspect(
                        body_a=left_name,
                        body_b=right_name,
                        aspect=aspect_name,
                        angle=exact_angle,
                        orb=orb,
                        applying=applying,
                    )
                )
                break
    return results


def _houses(request: ChartRequest, julian_day: float) -> HouseAngles | None:
    if not request.time_known or request.location is None:
        return None
    if swe is None:
        raise EphemerisUnavailable(
            "ASC/MC/houses require Swiss Ephemeris; no unknown time is imputed"
        )
    raw_cusps, ascmc = swe.houses_ex(
        julian_day,
        request.location.latitude,
        request.location.longitude,
        request.house_system.encode("ascii"),
    )
    # pysweph 2.10.3.4+ follows the C API's 1-based convention and exposes an
    # empty item at index zero; older pyswisseph returned the 12 cusps directly.
    cusps = raw_cusps[1:] if len(raw_cusps) == 13 else raw_cusps
    if len(cusps) != 12:
        raise EphemerisUnavailable("Swiss Ephemeris returned an invalid house cusp count")
    return HouseAngles(
        cusps=tuple(float(value % 360.0) for value in cusps),
        ascendant=float(ascmc[0] % 360.0),
        midheaven=float(ascmc[1] % 360.0),
        armc=float(ascmc[2] % 360.0),
        vertex=float(ascmc[3] % 360.0),
        house_system=request.house_system,
    )


def chart(
    request: ChartRequest,
    bodies: tuple[str, ...] = BODIES,
    orbs: dict[str, float] | None = None,
) -> AstrologyChart:
    unknown = set(bodies) - set(BODIES)
    if unknown:
        raise ValueError(f"unsupported bodies: {sorted(unknown)}")
    julian_day = _julian_day(request.moment)
    positions = {name: _position(name, julian_day) for name in bodies}
    provider, version = ephemeris_identity()
    return AstrologyChart(
        request=request,
        provider=provider,
        ephemeris_version=version,
        julian_day_ut=julian_day,
        positions=positions,
        houses=_houses(request, julian_day),
        aspects=calculate_aspects(positions, orbs),
        parameters={
            "bodies": list(bodies),
            "orbs": {**DEFAULT_ORBS, **(orbs or {})},
            "house_system": request.house_system if request.time_known else None,
            "time_known": request.time_known,
        },
    )


def ephemeris_available() -> bool:
    return swe is not None


def ephemeris_identity() -> tuple[str, str]:
    """Return the calculation provider identity used by content-addressed caches."""

    provider = "Swiss Ephemeris" if swe is not None else "explicit mean-motion fallback"
    return provider, str(getattr(swe, "version", "fallback-v1"))


def body_longitude(name: str, moment: datetime) -> float:
    return _position(name, _julian_day(moment)).longitude
