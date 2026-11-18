from __future__ import annotations

from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

from collectors.common.base import Collector, CollectorSpec
from packages.common.provenance import DataGrade, SourceClaimInput

from .parser import parse_birth_records


class NatalBirthDataCollector(Collector):
    """Publishes curated, individually-cited birth data as BirthData claims.

    Reads a local, human-curated JSON file (one real citation per collector,
    matching every other source in data/sources.yaml) rather than fetching a
    remote URL. Chart computation (packages.astrology.recalculate_accepted_charts)
    only accepts claims with a known exact time; an unknown-time record is still
    published honestly here (birth_time/timezone stay null, never imputed to
    noon) so it is visible in the append-only claims ledger even though it
    cannot yet feed a real ephemeris chart — it will be reported as skipped
    with an explicit "unknown time" reason rather than silently dropped.
    """

    def __init__(self, spec: CollectorSpec, path: Path):
        self.spec = spec
        self.path = path

    def fetch(self) -> bytes:
        return self.path.read_bytes()

    def parse(self, payload: bytes, consulted_at: datetime) -> list[SourceClaimInput]:
        records = parse_birth_records(payload)
        claims = []
        for record in records:
            chart_request: dict[str, object] = {"time_known": record.time_known}
            claims.append(
                SourceClaimInput(
                    entity_type="BirthData",
                    entity_key=record.person_name,
                    field_name="birth_data",
                    value={
                        "person_name": record.person_name,
                        "birth_date": record.birth_date.isoformat(),
                        "birth_time": (
                            record.birth_time.isoformat() if record.birth_time else None
                        ),
                        "timezone": record.timezone,
                        "place": record.place,
                        "latitude": record.latitude,
                        "longitude": record.longitude,
                        "time_known": record.time_known,
                        "rodden_rating": record.rodden_rating,
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


def natal_collector_from_config(record: dict[str, object], project_root: Path) -> Collector:
    url = str(record["url"])
    host = urlsplit(url).hostname
    if host is None:
        raise ValueError("natal data source URL has no hostname")
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
    return NatalBirthDataCollector(spec, path)
