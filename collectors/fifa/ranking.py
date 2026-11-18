from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime
from typing import Any, Protocol
from urllib.parse import urlencode

from bs4 import BeautifulSoup

from collectors.common.base import Collector, CollectorSpec
from collectors.common.http import SafeHttpClient
from collectors.common.normalization import normalize_name
from collectors.common.raw import collector_spec_from_config
from collectors.common.records import RankingRecord
from packages.common.provenance import DataGrade, SourceClaimInput

RANKING_API_SCHEMA = "fifa-ranking-api-v1"
DEFAULT_SCHEDULE_URL = (
    "https://api.fifa.com/api/v3/fifarankings/rankingschedules/all?type=0&gender=1&language=en"
)
RANKING_API_BASE = "https://api.fifa.com/api/v3/fifarankings/rankings/rankingsbyschedule"


class HttpGetter(Protocol):
    def get(self, url: str) -> bytes: ...


def _record_from_mapping(item: dict[str, Any], ranking_date: date) -> RankingRecord | None:
    name = item.get("teamName") or item.get("name") or item.get("team")
    rank = item.get("rank") or item.get("position")
    code = item.get("teamCode") or item.get("code") or item.get("id")
    if not name or not rank or not code:
        return None
    points = item.get("totalPoints") or item.get("points")
    return RankingRecord(
        team_code=str(code).upper(),
        team_name=normalize_name(str(name)),
        rank=int(rank),
        points=float(points) if points is not None else None,
        ranking_date=ranking_date,
    )


def parse_fifa_ranking(payload: bytes, ranking_date: date) -> list[RankingRecord]:
    """Legacy HTML fixture parser retained for archived snapshots and regression tests."""

    soup = BeautifulSoup(payload, "html.parser")
    records: list[RankingRecord] = []
    for script in soup.find_all("script", type="application/json"):
        try:
            node = json.loads(script.get_text())
        except json.JSONDecodeError:
            continue
        stack: list[Any] = [node]
        while stack:
            value = stack.pop()
            if isinstance(value, dict):
                record = _record_from_mapping(value, ranking_date)
                if record is not None:
                    records.append(record)
                stack.extend(value.values())
            elif isinstance(value, list):
                stack.extend(value)
    if not records:
        for row in soup.select("table tr"):
            cells = [cell.get_text(" ", strip=True) for cell in row.select("th,td")]
            if len(cells) < 3 or not cells[0].isdigit():
                continue
            records.append(
                RankingRecord(
                    rank=int(cells[0]),
                    team_name=normalize_name(cells[1]),
                    team_code=cells[2].upper(),
                    points=float(cells[3]) if len(cells) > 3 else None,
                    ranking_date=ranking_date,
                )
            )
    unique = {record.team_code: record for record in records}
    return sorted(unique.values(), key=lambda record: record.rank)


def _json_object(payload: bytes, label: str) -> dict[str, Any]:
    try:
        raw = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{label} is not valid JSON") from error
    if not isinstance(raw, dict):
        raise ValueError(f"{label} must be a JSON object")
    return raw


def latest_approved_schedule(
    payload: bytes,
    *,
    as_of: datetime | None = None,
) -> dict[str, Any]:
    raw = _json_object(payload, "FIFA ranking schedule response")
    results = raw.get("Results")
    if not isinstance(results, list):
        raise ValueError("FIFA ranking schedule response has no Results list")
    cutoff = (as_of or datetime.now(UTC)).astimezone(UTC)
    approved: list[tuple[datetime, dict[str, Any]]] = []
    for item in results:
        if not isinstance(item, dict) or item.get("RankingApproved") is not True:
            continue
        schedule_id = item.get("IdRankingSchedule")
        published = item.get("PublicationDateUTC")
        if not isinstance(schedule_id, str) or not isinstance(published, str):
            raise ValueError("approved FIFA ranking schedule is missing id or publication date")
        try:
            published_at = datetime.fromisoformat(published)
        except ValueError as error:
            raise ValueError("FIFA ranking publication date is not ISO-8601") from error
        if published_at.tzinfo is None or published_at.utcoffset() is None:
            raise ValueError("FIFA ranking publication date has no UTC offset")
        published_utc = published_at.astimezone(UTC)
        if published_utc <= cutoff:
            approved.append((published_utc, item))
    if not approved:
        raise ValueError("FIFA returned no approved men's football ranking schedule")
    return max(approved, key=lambda entry: entry[0])[1]


def _localized_team_name(raw: object) -> str:
    if not isinstance(raw, list) or not raw:
        raise ValueError("ranking team has no localized TeamName list")
    names = [
        item for item in raw if isinstance(item, dict) and isinstance(item.get("Description"), str)
    ]
    if not names:
        raise ValueError("ranking team has no valid localized name")
    preferred = next((item for item in names if item.get("Locale") == "en-GB"), names[0])
    return normalize_name(str(preferred["Description"]))


def parse_fifa_api_ranking(
    payload: bytes,
    ranking_date: date,
    *,
    minimum_records: int = 100,
) -> list[RankingRecord]:
    raw = _json_object(payload, "FIFA ranking response")
    if raw.get("ContinuationToken") is not None:
        raise ValueError("FIFA ranking response is paginated; refusing a partial ranking")
    results = raw.get("Results")
    if not isinstance(results, list):
        raise ValueError("FIFA ranking response has no Results list")
    records: list[RankingRecord] = []
    for index, item in enumerate(results):
        if not isinstance(item, dict):
            raise ValueError(f"FIFA ranking row {index} is not an object")
        code = item.get("IdCountry")
        rank = item.get("Rank")
        points = item.get("TotalPoints")
        if (
            not isinstance(code, str)
            or len(code) != 3
            or not code.isascii()
            or not code.isalpha()
            or not isinstance(rank, int)
            or rank <= 0
            or not isinstance(points, (int, float))
            or isinstance(points, bool)
        ):
            raise ValueError(f"FIFA ranking row {index} has an invalid code/rank/points contract")
        records.append(
            RankingRecord(
                team_code=code.upper(),
                team_name=_localized_team_name(item.get("TeamName")),
                rank=rank,
                points=float(points),
                ranking_date=ranking_date,
            )
        )
    if len(records) < minimum_records:
        raise ValueError(
            f"FIFA ranking is incomplete: {len(records)} records, expected at least "
            f"{minimum_records}"
        )
    if len({record.team_code for record in records}) != len(records):
        raise ValueError("FIFA ranking contains duplicate country codes")
    return sorted(records, key=lambda record: record.rank)


class FifaRankingCollector(Collector):
    spec = CollectorSpec(
        source_id="fifa_ranking",
        url=DEFAULT_SCHEDULE_URL,
        grade=DataGrade.A,
        official=True,
        allowed_hosts=("api.fifa.com",),
        terms_url="https://www.fifa.com/terms-of-service",
        robots_policy="official JSON endpoint used by the public FIFA ranking page; low rate",
        priority=10,
    )

    def __init__(
        self,
        client: HttpGetter | None = None,
        spec: CollectorSpec | None = None,
        minimum_records: int = 100,
    ):
        if spec is not None:
            self.spec = spec
        self.client = client or SafeHttpClient(self.spec.allowed_hosts)
        self.minimum_records = minimum_records

    @staticmethod
    def _ranking_url(schedule_id: str) -> str:
        query = urlencode({"rankingScheduleId": schedule_id, "language": "en"})
        return f"{RANKING_API_BASE}?{query}"

    def fetch(self) -> bytes:
        schedules_payload = self.client.get(self.spec.url)
        schedule = latest_approved_schedule(schedules_payload)
        schedule_id = str(schedule["IdRankingSchedule"])
        ranking_url = self._ranking_url(schedule_id)
        ranking_payload = self.client.get(ranking_url)
        # Validate both upstream contracts before the combined evidence snapshot is accepted.
        published_at = datetime.fromisoformat(str(schedule["PublicationDateUTC"]))
        parse_fifa_api_ranking(
            ranking_payload,
            published_at.date(),
            minimum_records=self.minimum_records,
        )
        envelope = {
            "schema_version": RANKING_API_SCHEMA,
            "schedule_url": self.spec.url,
            "ranking_url": ranking_url,
            "schedules_response_sha256": hashlib.sha256(schedules_payload).hexdigest(),
            "ranking_response_sha256": hashlib.sha256(ranking_payload).hexdigest(),
            "selected_schedule": schedule,
            "schedules_response": _json_object(schedules_payload, "FIFA ranking schedule response"),
            "ranking_response": _json_object(ranking_payload, "FIFA ranking response"),
        }
        return json.dumps(envelope, ensure_ascii=False, sort_keys=True).encode("utf-8")

    def parse(self, payload: bytes, consulted_at: datetime) -> list[SourceClaimInput]:
        envelope = _json_object(payload, "FIFA ranking evidence snapshot")
        if envelope.get("schema_version") != RANKING_API_SCHEMA:
            raise ValueError("unsupported FIFA ranking evidence schema")
        schedule = envelope.get("selected_schedule")
        schedules_response = envelope.get("schedules_response")
        ranking_response = envelope.get("ranking_response")
        ranking_url = envelope.get("ranking_url")
        if (
            not isinstance(schedule, dict)
            or schedule.get("RankingApproved") is not True
            or not isinstance(schedules_response, dict)
            or not isinstance(ranking_response, dict)
            or not isinstance(ranking_url, str)
        ):
            raise ValueError("FIFA ranking evidence snapshot is incomplete")
        effective_schedule = latest_approved_schedule(
            json.dumps(schedules_response, ensure_ascii=False).encode("utf-8"),
            as_of=consulted_at,
        )
        if effective_schedule.get("IdRankingSchedule") != schedule.get("IdRankingSchedule"):
            raise ValueError("selected FIFA ranking schedule does not match its evidence response")
        published_at = datetime.fromisoformat(str(schedule.get("PublicationDateUTC", "")))
        if published_at.tzinfo is None or published_at.utcoffset() is None:
            raise ValueError("FIFA ranking publication date has no UTC offset")
        ranking_payload = json.dumps(ranking_response, ensure_ascii=False).encode("utf-8")
        records = parse_fifa_api_ranking(
            ranking_payload,
            published_at.date(),
            minimum_records=self.minimum_records,
        )
        reference = json.dumps(
            {
                "ranking_schedule_id": schedule["IdRankingSchedule"],
                "published_at": published_at.isoformat(),
                "ranking_url": ranking_url,
            },
            sort_keys=True,
        )
        claims: list[SourceClaimInput] = []
        for record in records:
            for field_name, value in (
                ("name", record.team_name),
                ("rank", record.rank),
                ("points", record.points),
                ("ranking_date", record.ranking_date.isoformat()),
            ):
                claims.append(
                    SourceClaimInput(
                        entity_type="RankingSnapshot",
                        entity_key=record.team_code,
                        field_name=field_name,
                        value=value,
                        source_id=self.spec.source_id,
                        source_url=ranking_url,
                        consulted_at=consulted_at,
                        grade=self.spec.grade,
                        confidence=1.0,
                        official=self.spec.official,
                        inferred=False,
                        manually_confirmed=False,
                        raw_reference=reference,
                    )
                )
        return claims


def fifa_ranking_collector_from_config(record: dict[str, object]) -> FifaRankingCollector:
    return FifaRankingCollector(spec=collector_spec_from_config(record))
