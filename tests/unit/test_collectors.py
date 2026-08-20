import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from collectors.common.base import ImmutableSnapshotStore
from collectors.common.records import BirthRecord
from collectors.fifa.ranking import (
    FifaRankingCollector,
    latest_approved_schedule,
    parse_fifa_api_ranking,
    parse_fifa_ranking,
)
from collectors.fifa.structured import StructuredFifaParser
from collectors.natal.parser import parse_birth_records


def test_fifa_ranking_parser_supports_versioned_embedded_json() -> None:
    payload = b"""<script type="application/json">
    {"ranking":[{"rank":1,"teamName":"Argentina","teamCode":"ARG","totalPoints":1886.16}]}
    </script>"""
    records = parse_fifa_ranking(payload, date(2026, 8, 17))
    assert [(record.team_code, record.rank) for record in records] == [("ARG", 1)]


def _schedule_payload() -> bytes:
    return json.dumps(
        {
            "ContinuationToken": None,
            "Results": [
                {
                    "IdRankingSchedule": "future-unapproved",
                    "Gender": 1,
                    "SportType": 0,
                    "PublicationDateUTC": None,
                    "RankingApproved": False,
                },
                {
                    "IdRankingSchedule": "future-approved-but-unpublished",
                    "Gender": 1,
                    "SportType": 0,
                    "PublicationDateUTC": "2026-09-01T10:00:00Z",
                    "RankingApproved": True,
                },
                {
                    "IdRankingSchedule": "approved-old",
                    "Gender": 1,
                    "SportType": 0,
                    "PublicationDateUTC": "2026-06-11T10:00:00Z",
                    "RankingApproved": True,
                },
                {
                    "IdRankingSchedule": "approved-latest",
                    "Gender": 1,
                    "SportType": 0,
                    "PublicationDateUTC": "2026-07-20T08:37:28.979Z",
                    "RankingApproved": True,
                },
            ],
        }
    ).encode()


def _ranking_payload() -> bytes:
    return json.dumps(
        {
            "ContinuationToken": None,
            "ContinuationHash": None,
            "Results": [
                {
                    "IdCountry": "ESP",
                    "Rank": 1,
                    "TotalPoints": 1995.881879,
                    "TeamName": [{"Locale": "en-GB", "Description": "Spain"}],
                },
                {
                    "IdCountry": "ARG",
                    "Rank": 2,
                    "TotalPoints": 1970.36539,
                    "TeamName": [{"Locale": "en-GB", "Description": "Argentina"}],
                },
            ],
        }
    ).encode()


class _FakeFifaClient:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def get(self, url: str) -> bytes:
        self.calls.append(url)
        return _schedule_payload() if len(self.calls) == 1 else _ranking_payload()


def test_official_fifa_api_uses_latest_approved_complete_ranking(tmp_path: Path) -> None:
    schedule = latest_approved_schedule(
        _schedule_payload(),
        as_of=datetime(2026, 8, 20, tzinfo=UTC),
    )
    assert schedule["IdRankingSchedule"] == "approved-latest"
    records = parse_fifa_api_ranking(
        _ranking_payload(),
        date(2026, 7, 20),
        minimum_records=2,
    )
    assert [(record.team_code, record.rank) for record in records] == [
        ("ESP", 1),
        ("ARG", 2),
    ]

    client = _FakeFifaClient()
    collector = FifaRankingCollector(client=client, minimum_records=2)
    outcome = collector.run(ImmutableSnapshotStore(tmp_path / "snapshots"))
    assert outcome.status == "success"
    assert outcome.payload_sha256 is not None
    assert len(outcome.claims) == 8
    assert outcome.claims[0].source_url is not None
    assert "approved-latest" in str(outcome.claims[0].source_url)
    assert outcome.claims[0].consulted_at.tzinfo is not None
    assert json.loads(outcome.claims[0].raw_reference or "{}")["published_at"].startswith(
        "2026-07-20"
    )
    snapshot = json.loads(Path(str(outcome.snapshot_path)).read_text(encoding="utf-8"))
    assert snapshot["schema_version"] == "fifa-ranking-api-v1"
    assert snapshot["schedules_response_sha256"]
    assert snapshot["ranking_response_sha256"]


def test_fifa_api_refuses_partial_or_malformed_rankings() -> None:
    partial = json.loads(_ranking_payload())
    partial["ContinuationToken"] = "next-page"
    with pytest.raises(ValueError, match="partial ranking"):
        parse_fifa_api_ranking(
            json.dumps(partial).encode(),
            date(2026, 7, 20),
            minimum_records=2,
        )
    malformed = json.loads(_ranking_payload())
    malformed["Results"][0]["TotalPoints"] = None
    with pytest.raises(ValueError, match="invalid code/rank/points"):
        parse_fifa_api_ranking(
            json.dumps(malformed).encode(),
            date(2026, 7, 20),
            minimum_records=2,
        )


def test_structured_parser_fails_on_schema_drift() -> None:
    with pytest.raises(ValueError, match="schema_version"):
        StructuredFifaParser.parse(b'{"teams": []}')


def test_unknown_birth_time_stays_null_and_never_becomes_noon() -> None:
    payload = json.dumps(
        {
            "schema_version": "sirius-birth-data-v1",
            "records": [
                {
                    "person_name": "Persona sin hora",
                    "birth_date": "1970-01-01",
                    "birth_time": None,
                    "time_known": False,
                }
            ],
        }
    ).encode()
    assert parse_birth_records(payload)[0].birth_time is None
    with pytest.raises(ValueError, match="must remain null"):
        BirthRecord(
            person_name="Persona",
            birth_date=date(1970, 1, 1),
            birth_time="12:00",
            time_known=False,
        )
