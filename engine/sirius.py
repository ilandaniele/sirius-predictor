from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime

from packages.sirius.models import SiriusAssessment

from .domain import Team

try:  # Swiss Ephemeris is preferred; the fallback keeps the app operational and explicit.
    import swisseph as swe
except ImportError:  # pragma: no cover - exercised only in minimal installations
    swe = None

# Real, published win/draw/loss-by-Moon-sign World Cup records, in Sirius's own words on
# his blog (astrologiadeportivaa.blogspot.com), one post per Argentina match at the 2026
# World Cup. This is his single most publicly validated technique (picked up by national
# and international media during the 2022 and 2026 cycles). Sign indices follow
# moon_sign_index(): 0=Aries, 1=Taurus, 2=Gemini, 3=Cancer, 4=Leo, 5=Virgo, 6=Libra,
# 7=Scorpio, 8=Sagittarius, 9=Capricorn, 10=Aquarius, 11=Pisces. Coverage is necessarily
# partial (only the signs Sirius discussed before an ARG match under that sign) —
# unlisted (team, sign) pairs are left as "no evidence" rather than imputed.
#   Aries:       vs Egipto, 6/7/2026   — "jugó 8 partidos ... ganó 5 y perdió 3"
#   Gemini:      vs Suiza, 9/7/2026    — "jugó 8 partidos ... ganó 5, empató 1 y perdió 2"
#   Cancer:      vs Argelia, 15/6/2026 — "nunca perdió ... ganó 3 y empató 2"
#   Leo:         vs Inglaterra, 13/7/2026 — "jugó 10 partidos: ganó 7, empató 2 y perdió 1"
#   Libra:       vs España, 17/7/2026  — "jugó 11 partidos: ganó 6 y perdió 5" (most recent
#                count; supersedes the 10-match figure from the earlier Austria post)
#   Sagittarius: vs Jordania, 26/6/2026 — "jugó 6 partidos ... ganó 3, empató 1 y perdió 2"
#   Aquarius:    vs Cabo Verde, 30/6/2026 — "jugó 6 partidos ... ganó 4 y perdió 2"
MOON_SIGN_RECORDS: dict[str, dict[int, tuple[int, int, int]]] = {
    "ARG": {
        0: (5, 0, 3),  # Aries
        2: (5, 1, 2),  # Gemini
        3: (3, 2, 0),  # Cancer
        4: (7, 2, 1),  # Leo
        6: (6, 0, 5),  # Libra
        8: (3, 1, 2),  # Sagittarius
        10: (4, 0, 2),  # Aquarius
    },
}

# Pseudo-sample size for confidence shrinkage: a sign with only a handful of recorded
# matches gets pulled hard toward "no signal"; the shrinkage only relaxes once the sample
# is comparably sized to this constant.
_MOON_SIGN_SHRINKAGE_K = 5.0


def moon_sign_signal(team_id: str, sign_index: int) -> float:
    """A small, shrinkage-dampened signal in roughly [-1, 1] from a team's real,
    Sirius-published World-Cup win/draw/loss record under a given Moon sign.

    Returns 0.0 (no signal) when the team/sign combination has no recorded evidence,
    exactly like every other "missing evidence is neutral" path in this module.
    """

    record = MOON_SIGN_RECORDS.get(team_id, {}).get(sign_index)
    if record is None:
        return 0.0
    wins, draws, losses = record
    total = wins + draws + losses
    if total == 0:
        return 0.0
    win_rate = (wins + 0.5 * draws) / total
    shrinkage = total / (total + _MOON_SIGN_SHRINKAGE_K)
    signal = shrinkage * (win_rate - 0.5) * 2.0
    return max(-1.0, min(1.0, signal))


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
    """Bounded adapter from reviewed Sirius assessments to match strength.

    When assessments are supplied, missing evidence is neutral. Direct callers
    without assessments retain the explicitly labelled scenario proxy for
    backwards compatibility; production simulations always supply assessments.
    """

    def __init__(
        self,
        max_elo_adjustment: float = 35.0,
        assessments: Mapping[str, SiriusAssessment] | None = None,
    ):
        self.max_elo_adjustment = float(max_elo_adjustment)
        self.assessments = dict(assessments or {})

    def components(
        self,
        team: Team,
        kickoff: datetime | None = None,
        round_name: str | None = None,
    ) -> dict[str, float | str]:
        """Expose structural, annual, temporal and uncertainty terms separately."""

        assessment = self.assessments.get(team.team_id)
        if assessment is None:
            structural = team.sirius_index
            annual = 0.0
            confidence = team.sirius_confidence
            evidence_status = "scenario_proxy_x"
        else:
            structural = (
                (assessment.journey_index.value - 50.0) / 50.0
                if assessment.journey_index.value is not None
                else 0.0
            )
            annual = (
                0.5 * (assessment.coronation_index.value - 50.0) / 50.0
                if assessment.coronation_index.value is not None
                else 0.0
            )
            confidence = assessment.data_confidence
            evidence_status = assessment.journey_index.status
        temporal = 0.0
        if kickoff is None:
            temporal_status = "neutral_missing_round_time"
        else:
            temporal = moon_sign_signal(team.team_id, moon_sign_index(kickoff))
            temporal_status = (
                "historical_moon_sign_stats"
                if temporal != 0.0
                else "event_chart_available_no_team_testimony"
            )
        return {
            "structural": structural,
            "annual": annual,
            "temporal": temporal,
            "rival_specific": 0.0,
            "data_confidence": confidence,
            "round": round_name or "unknown",
            "temporal_status": temporal_status,
            "evidence_status": evidence_status,
        }

    def adjustment(
        self,
        team: Team,
        kickoff: datetime | None = None,
        round_name: str | None = None,
    ) -> float:
        components = self.components(team, kickoff, round_name)
        # The temporal (Moon-sign) term is independently sourced and shrinkage-weighted
        # by its own sample size (see moon_sign_signal); it is not gated behind
        # data_confidence, which reflects only the structural/annual assessment evidence.
        assessed_signal = float(components["structural"]) + float(components["annual"])
        temporal_signal = float(components["temporal"])
        weighted_signal = assessed_signal * float(components["data_confidence"]) + temporal_signal
        return self.max_elo_adjustment * weighted_signal

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
