from __future__ import annotations

from collections import Counter
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from .ephemeris import EphemerisUnavailable, chart
from .models import ChartRequest, GeoLocation, TechniqueResult
from .techniques import sign_name


def birth_time_sensitivity(
    birth_date: datetime,
    timezone_name: str,
    location: GeoLocation,
    step_minutes: int = 15,
) -> TechniqueResult:
    """Explicitly marginalize an unknown time; sampled times are never stored as real birth data."""

    if not 1 <= step_minutes <= 720:
        raise ValueError("step_minutes must be between 1 and 720")
    zone = ZoneInfo(timezone_name)
    start = datetime.combine(birth_date.date(), time.min, tzinfo=zone)
    samples = []
    sign_counts: dict[str, Counter[str]] = {}
    angle_values: dict[str, list[float]] = {"ascendant": [], "midheaven": []}
    for minutes in range(0, 24 * 60, step_minutes):
        moment = start + timedelta(minutes=minutes)
        try:
            current = chart(ChartRequest(moment, location, True, label="sensitivity sample"))
        except EphemerisUnavailable:
            current = chart(ChartRequest(moment, None, False, label="sensitivity sample"))
        placements = {
            body: sign_name(position.longitude) for body, position in current.positions.items()
        }
        for body, sign in placements.items():
            sign_counts.setdefault(body, Counter())[sign] += 1
        if current.houses is not None:
            angle_values["ascendant"].append(current.houses.ascendant)
            angle_values["midheaven"].append(current.houses.midheaven)
        samples.append({"time": moment.strftime("%H:%M"), "placements": placements})
    invariant = {
        body: next(iter(counts)) for body, counts in sign_counts.items() if len(counts) == 1
    }
    variable = {body: dict(counts) for body, counts in sign_counts.items() if len(counts) > 1}
    return TechniqueResult(
        technique="birth_time_sensitivity",
        result={
            "sample_count": len(samples),
            "invariant_signs": invariant,
            "variable_signs": variable,
            "angles_available": bool(angle_values["ascendant"]),
            "samples": samples,
        },
        parameters={
            "range": "00:00-23:59",
            "step_minutes": step_minutes,
            "timezone": timezone_name,
            "synthetic_times": True,
        },
        warnings=("Synthetic times are sensitivity samples, never asserted birth times.",),
    )


def kickoff_time_sensitivity(
    request: ChartRequest,
    hour_offsets: tuple[int, ...] = (-60, 0, 120, 180),
    minute_offsets: tuple[int, ...] = (-15, 0, 15),
) -> TechniqueResult:
    rows = []
    for hour_offset in hour_offsets:
        for minute_offset in minute_offsets:
            moment = request.moment + timedelta(minutes=hour_offset + minute_offset)
            current = chart(
                ChartRequest(
                    moment,
                    request.location,
                    request.time_known,
                    request.house_system,
                    "kickoff sensitivity",
                )
            )
            rows.append(
                {
                    "moment": moment.isoformat(),
                    "moon_longitude": current.positions["Moon"].longitude,
                    "ascendant": current.houses.ascendant if current.houses else None,
                    "midheaven": current.houses.midheaven if current.houses else None,
                }
            )
    return TechniqueResult(
        technique="kickoff_time_sensitivity",
        result={"samples": rows},
        parameters={"hour_offsets": hour_offsets, "minute_offsets": minute_offsets},
    )
