from __future__ import annotations

from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

from collectors.common.base import Collector, CollectorSpec
from packages.common.provenance import DataGrade, SourceClaimInput

from .parser import parse_team_event_records

_ENTITY_TYPES = {
    "world_cup_debut": "WorldCupDebutEvent",
    "federation_founding": "FederationEvent",
    "coach_debut": "CoachDebutEvent",
}


class TeamEventCollector(Collector):
    """Publishes real, cited event-moment charts as claims.

    This is the "coach cycle" / "federation chart" / "world cup debut"
    methodology Sirius's own posts describe — an event chart cast for the
    documented moment of a real event (a federation's founding, a team's
    actual World Cup debut match, a coach's debut match in charge), not a
    person's unknowable personal birth hour. Every record here must carry a
    known exact moment with a UTC offset; there is no unknown-time variant
    for event charts (unlike BirthData's sensitivity-analysis fallback), so
    an event without a documented time is simply never added to the source
    file in the first place.
    """

    def __init__(self, spec: CollectorSpec, path: Path):
        self.spec = spec
        self.path = path

    def fetch(self) -> bytes:
        return self.path.read_bytes()

    def parse(self, payload: bytes, consulted_at: datetime) -> list[SourceClaimInput]:
        team_code, records = parse_team_event_records(payload)
        claims = []
        for record in records:
            entity_type = _ENTITY_TYPES[record.event_type]
            entity_key = (
                f"{team_code}:{record.coach_name}"
                if record.event_type == "coach_debut"
                else f"{team_code}:{record.event_type}"
            )
            chart_request: dict[str, object] = {
                "time_known": True,
                "moment": record.occurred_at.isoformat(),
                "house_system": "P",
                "location": {
                    "latitude": record.location.latitude,
                    "longitude": record.location.longitude,
                    "name": record.location.name,
                },
                "label": record.label,
            }
            claims.append(
                SourceClaimInput(
                    entity_type=entity_type,
                    entity_key=entity_key,
                    field_name="team_event",
                    value={
                        "team_code": team_code,
                        "event_type": record.event_type,
                        "occurred_at": record.occurred_at.isoformat(),
                        "coach_name": record.coach_name,
                        "chart_request": chart_request,
                    },
                    source_id=self.spec.source_id,
                    source_url=self.spec.url,
                    consulted_at=consulted_at,
                    grade=self.spec.grade,
                    confidence=0.85,
                    official=self.spec.official,
                    inferred=False,
                    manually_confirmed=True,
                    raw_reference=None,
                )
            )
        return claims


def team_event_collector_from_config(record: dict[str, object], project_root: Path) -> Collector:
    url = str(record["url"])
    host = urlsplit(url).hostname
    if host is None:
        raise ValueError("team event data source URL has no hostname")
    grade = DataGrade(str(record["grade"]))
    spec = CollectorSpec(
        source_id=str(record["id"]),
        url=url,
        grade=grade,
        official=grade == DataGrade.A,
        allowed_hosts=(host,),
        terms_url=str(record["terms_url"]),
        robots_policy=str(record["robots_policy"]),
        priority=20,
    )
    path = project_root / str(record["local_path"])
    return TeamEventCollector(spec, path)
