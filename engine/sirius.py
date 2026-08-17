from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, datetime

from .domain import Team

try:  # Swiss Ephemeris is preferred; the fallback keeps the app operational and explicit.
    import swisseph as swe
except ImportError:  # pragma: no cover - exercised only in minimal installations
    swe = None


@dataclass(frozen=True, slots=True)
class EphemerisValue:
    longitude: float
    provider: str


def lunar_longitude(when: datetime) -> EphemerisValue:
    utc = when.astimezone(UTC)
    hour = utc.hour + utc.minute / 60 + utc.second / 3600
    if swe is not None:
        julian_day = swe.julday(utc.year, utc.month, utc.day, hour)
        longitude = float(swe.calc_ut(julian_day, swe.MOON)[0][0] % 360)
        return EphemerisValue(longitude=longitude, provider="Swiss Ephemeris")
    epoch = datetime(2000, 1, 1, 12, tzinfo=UTC)
    days = (utc - epoch).total_seconds() / 86400
    longitude = (218.316 + 13.176396 * days) % 360
    return EphemerisValue(longitude=longitude, provider="mean-lunar fallback")


class SiriusExperimentalLayer:
    """Small, bounded and auditable proxy for publicly described Sirius layers.

    The static index is scenario input, not a learned truth. Event-time modulation uses lunar
    longitude solely so kickoff sensitivity is measurable. The layer is never presented as
    scientifically validated and can be disabled completely by selecting baseline mode.
    """

    def __init__(self, max_elo_adjustment: float = 35.0):
        self.max_elo_adjustment = float(max_elo_adjustment)

    def components(
        self,
        team: Team,
        kickoff: datetime | None = None,
        round_name: str | None = None,
    ) -> dict[str, float | str]:
        """Expose structural, annual, temporal and uncertainty terms separately."""

        structural = team.sirius_index
        annual = 0.0
        temporal = 0.0
        if kickoff is None:
            temporal_status = "neutral_missing_round_time"
        else:
            moon = lunar_longitude(kickoff).longitude
            temporal = 0.35 * math.cos(math.radians(moon))
            temporal_status = "event_time_proxy"
        return {
            "structural": structural,
            "annual": annual,
            "temporal": temporal,
            "rival_specific": 0.0,
            "data_confidence": team.sirius_confidence,
            "round": round_name or "unknown",
            "temporal_status": temporal_status,
        }

    def adjustment(
        self,
        team: Team,
        kickoff: datetime | None = None,
        round_name: str | None = None,
    ) -> float:
        components = self.components(team, kickoff, round_name)
        signal = (
            float(components["structural"])
            + float(components["annual"])
            + float(components["temporal"])
        )
        return self.max_elo_adjustment * signal * float(components["data_confidence"])

    def matchup_delta(
        self,
        home: Team,
        away: Team,
        kickoff: datetime | None = None,
        round_name: str | None = None,
    ) -> float:
        return self.adjustment(home, kickoff, round_name) - self.adjustment(
            away, kickoff, round_name
        )

    def event_metadata(self, kickoff: datetime) -> dict[str, float | str]:
        moon = lunar_longitude(kickoff)
        return {
            "moon_longitude": round(moon.longitude, 6),
            "ephemeris_provider": moon.provider,
        }


def moon_sign_index(when: datetime) -> int:
    return int(lunar_longitude(when).longitude // 30) % 12
