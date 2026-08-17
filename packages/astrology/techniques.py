from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timedelta

from .ephemeris import body_longitude, chart, signed_angular_delta
from .models import AstrologyChart, ChartRequest, GeoLocation, TechniqueResult

SIGNS = (
    "Aries",
    "Taurus",
    "Gemini",
    "Cancer",
    "Leo",
    "Virgo",
    "Libra",
    "Scorpio",
    "Sagittarius",
    "Capricorn",
    "Aquarius",
    "Pisces",
)
RULERS = {
    "Aries": "Mars",
    "Taurus": "Venus",
    "Gemini": "Mercury",
    "Cancer": "Moon",
    "Leo": "Sun",
    "Virgo": "Mercury",
    "Libra": "Venus",
    "Scorpio": "Mars",
    "Sagittarius": "Jupiter",
    "Capricorn": "Saturn",
    "Aquarius": "Saturn",
    "Pisces": "Jupiter",
}
EXALTATIONS = {
    "Sun": "Aries",
    "Moon": "Taurus",
    "Mercury": "Virgo",
    "Venus": "Pisces",
    "Mars": "Capricorn",
    "Jupiter": "Cancer",
    "Saturn": "Libra",
}


def sign_name(longitude: float) -> str:
    return SIGNS[int(longitude % 360 // 30)]


def relocalize(base: AstrologyChart, location: GeoLocation) -> AstrologyChart:
    request = ChartRequest(
        moment=base.request.moment,
        location=location,
        time_known=base.request.time_known,
        house_system=base.request.house_system,
        label=f"{base.request.label} relocalized",
    )
    return chart(request, tuple(base.positions), base.parameters.get("orbs"))


def transits(natal: AstrologyChart, event: ChartRequest) -> TechniqueResult:
    current = chart(event, tuple(natal.positions))
    contacts = []
    for transit_name, transit_position in current.positions.items():
        for natal_name, natal_position in natal.positions.items():
            delta = abs(signed_angular_delta(transit_position.longitude, natal_position.longitude))
            for label, exact, orb in (
                ("conjunction", 0, 3),
                ("square", 90, 3),
                ("opposition", 180, 3),
            ):
                if abs(delta - exact) <= orb:
                    contacts.append(
                        {
                            "transit": transit_name,
                            "natal": natal_name,
                            "aspect": label,
                            "orb": abs(delta - exact),
                        }
                    )
    return TechniqueResult(
        technique="transits",
        result={"contacts": contacts, "event_chart": current.to_dict()},
        parameters={"orb": 3.0},
    )


def _find_return(
    body: str,
    target_longitude: float,
    after: datetime,
    nominal_period_days: float,
    fraction: float = 1.0,
) -> datetime:
    target = (target_longitude + 360.0 * fraction) % 360.0
    current = body_longitude(body, after)
    speed = 360.0 / nominal_period_days
    distance = (target - current) % 360.0
    estimate = after + timedelta(days=distance / speed)
    for _ in range(12):
        error = signed_angular_delta(body_longitude(body, estimate), target)
        if abs(error) < 1e-7:
            break
        probe = estimate + timedelta(minutes=30)
        measured_speed = signed_angular_delta(
            body_longitude(body, probe), body_longitude(body, estimate)
        ) / (30 / 1440)
        if abs(measured_speed) < 1e-6:
            measured_speed = speed
        estimate -= timedelta(days=error / measured_speed)
    return estimate


def solar_return(natal: AstrologyChart, year: int, location: GeoLocation) -> TechniqueResult:
    target = natal.positions["Sun"].longitude
    after = natal.request.moment.replace(year=year) - timedelta(days=2)
    moment = _find_return("Sun", target, after, 365.256)
    result_chart = chart(ChartRequest(moment, location, True, label="Solar return"))
    return TechniqueResult(
        technique="solar_return",
        result={"exact_moment": moment.isoformat(), "chart": result_chart.to_dict()},
        parameters={"target_longitude": target, "year": year},
    )


def lunar_return(
    natal: AstrologyChart,
    after: datetime,
    location: GeoLocation,
    fraction: float = 1.0,
) -> TechniqueResult:
    labels = {1.0: "lunar_return", 0.5: "demi_lunar", 0.25: "quarti_lunar"}
    if fraction not in labels:
        raise ValueError("fraction must be 1, 0.5 or 0.25")
    target = (natal.positions["Moon"].longitude + 360.0 * fraction) % 360.0
    moment = _find_return("Moon", natal.positions["Moon"].longitude, after, 27.321661, fraction)
    result_chart = chart(ChartRequest(moment, location, True, label=labels[fraction]))
    return TechniqueResult(
        technique=labels[fraction],
        result={"exact_moment": moment.isoformat(), "chart": result_chart.to_dict()},
        parameters={"target_longitude": target, "fraction": fraction},
    )


def secondary_progressions(natal: AstrologyChart, event_moment: datetime) -> TechniqueResult:
    tropical_years = (event_moment - natal.request.moment).total_seconds() / (365.2422 * 86400)
    progressed_moment = natal.request.moment + timedelta(days=tropical_years)
    progressed = chart(
        ChartRequest(
            progressed_moment,
            natal.request.location,
            natal.request.time_known,
            natal.request.house_system,
            "Secondary progressions",
        ),
        tuple(natal.positions),
    )
    return TechniqueResult(
        technique="secondary_progressions",
        result={"progressed_moment": progressed_moment.isoformat(), "chart": progressed.to_dict()},
        parameters={"key": "one day per tropical year", "age_years": tropical_years},
    )


def primary_directions(natal: AstrologyChart, event_moment: datetime) -> TechniqueResult:
    if not natal.request.time_known or natal.houses is None:
        raise ValueError("primary directions require a reliable real birth time")
    years = (event_moment - natal.request.moment).total_seconds() / (365.2422 * 86400)
    arc = years * 0.98564736
    directed = {
        "ascendant": (natal.houses.ascendant + arc) % 360,
        "midheaven": (natal.houses.midheaven + arc) % 360,
    }
    return TechniqueResult(
        technique="primary_directions",
        result=directed,
        parameters={"key": "Naibod mean solar arc", "years": years, "arc": arc},
        warnings=("Research approximation; direction variant must be preregistered.",),
    )


def proluna(natal: AstrologyChart, event_moment: datetime) -> TechniqueResult:
    result = secondary_progressions(natal, event_moment)
    return TechniqueResult(
        technique="proluna_optional",
        result={"progressed_moon": result.result["chart"]["positions"]["Moon"]},
        parameters={"implementation": "secondary progressed Moon proxy"},
        warnings=("Optional proxy; disabled from SIRIUS_PURIST unless documented.",),
    )


def essential_dignities(astrology_chart: AstrologyChart) -> TechniqueResult:
    results = {}
    for body, position in astrology_chart.positions.items():
        sign = sign_name(position.longitude)
        domicile = RULERS[sign] == body
        exalted = EXALTATIONS.get(body) == sign
        results[body] = {
            "sign": sign,
            "domicile": domicile,
            "exaltation": exalted,
            "detriment": RULERS[SIGNS[(SIGNS.index(sign) + 6) % 12]] == body,
        }
    return TechniqueResult(
        technique="essential_dignities",
        result=results,
        parameters={"zodiac": "tropical", "rulership": "traditional"},
    )


def receptions(astrology_chart: AstrologyChart) -> TechniqueResult:
    body_signs = {
        body: sign_name(position.longitude) for body, position in astrology_chart.positions.items()
    }
    found = []
    for body, sign in body_signs.items():
        ruler = RULERS[sign]
        ruler_sign = body_signs.get(ruler)
        if ruler_sign and RULERS[ruler_sign] == body:
            found.append({"body_a": body, "body_b": ruler, "type": "mutual_domicile"})
    return TechniqueResult(
        technique="receptions",
        result={"receptions": found},
        parameters={"rulership": "traditional"},
    )


def rulers_and_almutens(astrology_chart: AstrologyChart) -> TechniqueResult:
    if astrology_chart.houses is None:
        raise ValueError("house rulers and almutens require a real known time")
    rulers = {
        str(index + 1): RULERS[sign_name(cusp)]
        for index, cusp in enumerate(astrology_chart.houses.cusps)
    }
    return TechniqueResult(
        technique="rulers_almutens",
        result={"house_rulers": rulers, "almuten_variant": "domicile-only"},
        parameters={"rulership": "traditional"},
        warnings=("Full almuten scoring remains configurable and unweighted.",),
    )


def arabic_parts(astrology_chart: AstrologyChart) -> TechniqueResult:
    if astrology_chart.houses is None:
        raise ValueError("Arabic parts require a real known time and houses")
    asc = astrology_chart.houses.ascendant
    sun = astrology_chart.positions["Sun"].longitude
    moon = astrology_chart.positions["Moon"].longitude
    day_chart = astrology_chart.positions["Sun"].longitude < 180
    fortune = (asc + (moon - sun if day_chart else sun - moon)) % 360
    spirit = (asc + (sun - moon if day_chart else moon - sun)) % 360
    jupiter = astrology_chart.positions["Jupiter"].longitude
    victory = (asc + jupiter - spirit) % 360
    return TechniqueResult(
        technique="arabic_parts",
        result={"fortune": fortune, "spirit": spirit, "victory": victory},
        parameters={"day_chart_proxy": day_chart, "formula_set": "configurable-v1"},
    )


def antiscia(astrology_chart: AstrologyChart) -> TechniqueResult:
    return TechniqueResult(
        technique="antiscia",
        result={
            body: {
                "antiscia": (180.0 - position.longitude) % 360,
                "contra_antiscia": (360.0 - position.longitude) % 360,
            }
            for body, position in astrology_chart.positions.items()
        },
        parameters={"axis": "Cancer-Capricorn solstice"},
    )


def fixed_star_contacts(
    astrology_chart: AstrologyChart,
    stars: Iterable[dict[str, float | str]],
    orb: float = 1.0,
) -> TechniqueResult:
    contacts = []
    catalog = list(stars)
    for star in catalog:
        star_longitude = float(star["longitude"])
        for body, position in astrology_chart.positions.items():
            distance = abs(signed_angular_delta(position.longitude, star_longitude))
            if distance <= orb:
                contacts.append({"star": star["name"], "body": body, "orb": distance})
    return TechniqueResult(
        technique="fixed_stars",
        result={"contacts": contacts},
        parameters={"orb": orb, "catalog": catalog},
    )


def kickoff_chart(request: ChartRequest) -> AstrologyChart:
    if not request.time_known:
        raise ValueError("kickoff chart requires an actual scheduled time")
    return chart(request)


def lunations_eclipses_ingresses(
    moments: Iterable[datetime], location: GeoLocation | None = None
) -> TechniqueResult:
    events = []
    previous_sun_sign: str | None = None
    for moment in moments:
        current = chart(ChartRequest(moment, location, True, label="event scan"), ("Sun", "Moon"))
        phase = abs(
            signed_angular_delta(
                current.positions["Moon"].longitude,
                current.positions["Sun"].longitude,
            )
        )
        sun_sign = sign_name(current.positions["Sun"].longitude)
        if phase <= 1.0:
            events.append({"moment": moment.isoformat(), "kind": "new_moon", "phase_orb": phase})
        elif abs(phase - 180) <= 1.0:
            events.append(
                {"moment": moment.isoformat(), "kind": "full_moon", "phase_orb": abs(phase - 180)}
            )
        if previous_sun_sign is not None and previous_sun_sign != sun_sign:
            events.append({"moment": moment.isoformat(), "kind": "solar_ingress", "sign": sun_sign})
        previous_sun_sign = sun_sign
    return TechniqueResult(
        technique="lunations_eclipses_ingresses",
        result={"events": events},
        parameters={"scan_resolution": "caller supplied", "eclipse_status": "requires node filter"},
        warnings=("Lunations near a node are candidates; eclipse confirmation is not inferred.",),
    )
