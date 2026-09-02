import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
import yaml

from collectors.common.base import ImmutableSnapshotStore
from collectors.common.records import BirthRecord
from collectors.events import team_event_collector_from_config
from collectors.events.parser import parse_team_event_records
from collectors.fifa.ranking import (
    FifaRankingCollector,
    latest_approved_schedule,
    parse_fifa_api_ranking,
    parse_fifa_ranking,
)
from collectors.fifa.structured import StructuredFifaParser
from collectors.natal import natal_collector_from_config
from collectors.natal.parser import parse_birth_records
from packages.astrology import recalculate_accepted_charts


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


def test_natal_collector_publishes_an_unknown_time_birth_data_claim(tmp_path: Path) -> None:
    data_path = tmp_path / "natal.json"
    data_path.write_text(
        json.dumps(
            {
                "schema_version": "sirius-birth-data-v1",
                "records": [
                    {
                        "person_name": "Lionel Sebastián Scaloni",
                        "birth_date": "1978-05-16",
                        "birth_time": None,
                        "timezone": "America/Argentina/Buenos_Aires",
                        "place": "Pujato, Santa Fe, Argentina",
                        "latitude": -32.9833,
                        "longitude": -61.15,
                        "time_known": False,
                        "rodden_rating": "X",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    collector = natal_collector_from_config(
        {
            "id": "natal_scaloni",
            "url": "https://es.wikipedia.org/wiki/Lionel_Scaloni",
            "grade": "B",
            "local_path": "natal.json",
            "terms_url": "https://foundation.wikimedia.org/wiki/Policy:Terms_of_Use",
            "robots_policy": "curated_local_file_cites_public_biography",
        },
        tmp_path,
    )
    payload = collector.fetch()
    claims = collector.parse(payload, datetime(2026, 8, 24, tzinfo=UTC))
    assert len(claims) == 1
    claim = claims[0]
    assert claim.entity_type == "BirthData"
    assert claim.entity_key == "Lionel Sebastián Scaloni"
    assert claim.manually_confirmed is True
    assert claim.value["time_known"] is False
    assert claim.value["birth_time"] is None
    assert claim.value["chart_request"] == {"time_known": False}

    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session as OrmSession

    from db.base import Base

    engine = create_engine(f"sqlite:///{(tmp_path / 'astro.db').as_posix()}")
    Base.metadata.create_all(engine)
    with OrmSession(engine) as session:
        report = recalculate_accepted_charts(session, claims)
    assert report.recalculated == []
    assert report.failed == []
    assert report.skipped == []
    assert len(report.sensitivity_computed) == 1


def test_all_curated_natal_data_files_parse_and_never_impute_a_time() -> None:
    natal_dir = Path(__file__).resolve().parents[2] / "data"
    paths = sorted(natal_dir.glob("natal_*.json"))
    assert len(paths) >= 8
    for path in paths:
        records = parse_birth_records(path.read_bytes())
        assert len(records) == 1
        record = records[0]
        assert record.person_name
        assert record.time_known is False
        assert record.birth_time is None
        assert record.timezone
        assert record.latitude is not None
        assert record.longitude is not None


def test_enzo_natal_data_is_sourced_and_keeps_unknown_time_explicit() -> None:
    root = Path(__file__).resolve().parents[2]
    records = parse_birth_records((root / "data" / "natal_enzo_fernandez.json").read_bytes())
    assert len(records) == 1
    record = records[0]
    assert record.person_name == "Enzo Fernández"
    assert record.birth_date.isoformat() == "2001-01-17"
    assert record.birth_time is None
    assert record.time_known is False
    assert record.rodden_rating == "X"

    sources = yaml.safe_load((root / "data" / "sources.yaml").read_text(encoding="utf-8"))
    source = next(item for item in sources if item["id"] == "natal_enzo_fernandez")
    assert source["grade"] == "B"
    assert source["consulted_at"].isoformat() == "2026-08-31"
    assert [item["grade"] for item in source["field_sources"]] == ["A", "B"]


def test_cristian_romero_natal_data_is_sourced_and_keeps_unknown_time_explicit() -> None:
    root = Path(__file__).resolve().parents[2]
    records = parse_birth_records((root / "data" / "natal_cristian_romero.json").read_bytes())
    assert len(records) == 1
    record = records[0]
    assert record.person_name == "Cristian Romero"
    assert record.birth_date.isoformat() == "1998-04-27"
    assert record.birth_time is None
    assert record.time_known is False
    assert record.rodden_rating == "X"

    sources = yaml.safe_load((root / "data" / "sources.yaml").read_text(encoding="utf-8"))
    source = next(item for item in sources if item["id"] == "natal_cristian_romero")
    assert source["grade"] == "B"
    assert source["consulted_at"].isoformat() == "2026-08-31"
    assert [item["grade"] for item in source["field_sources"]] == ["A", "B"]


def test_team_event_record_requires_a_timezone_aware_moment() -> None:
    with pytest.raises(ValueError, match="UTC offset"):
        parse_team_event_records(
            json.dumps(
                {
                    "schema_version": "sirius-team-events-v1",
                    "team_code": "ARG",
                    "events": [
                        {
                            "event_type": "world_cup_debut",
                            "occurred_at": "1930-07-15T16:00:00",
                            "location": {"latitude": -34.9011, "longitude": -56.1645},
                            "label": "sin offset",
                        }
                    ],
                }
            ).encode()
        )


def test_coach_debut_event_requires_a_coach_name() -> None:
    with pytest.raises(ValueError, match="must name the coach"):
        parse_team_event_records(
            json.dumps(
                {
                    "schema_version": "sirius-team-events-v1",
                    "team_code": "ARG",
                    "events": [
                        {
                            "event_type": "coach_debut",
                            "occurred_at": "2018-08-14T20:00:00-03:00",
                            "location": {"latitude": -34.6037, "longitude": -58.3816},
                            "label": "sin nombre de DT",
                        }
                    ],
                }
            ).encode()
        )


def test_team_event_collector_publishes_a_known_time_chart(tmp_path: Path) -> None:
    data_path = tmp_path / "events.json"
    data_path.write_text(
        json.dumps(
            {
                "schema_version": "sirius-team-events-v1",
                "team_code": "ARG",
                "events": [
                    {
                        "event_type": "world_cup_debut",
                        "occurred_at": "1930-07-15T16:00:00-03:00",
                        "location": {
                            "latitude": -34.9011,
                            "longitude": -56.1645,
                            "name": "Montevideo, Uruguay",
                        },
                        "label": "Argentina vs Francia, debut mundialista 1930",
                    },
                    {
                        "event_type": "coach_debut",
                        "occurred_at": "2018-08-14T20:00:00-03:00",
                        "location": {
                            "latitude": -34.6037,
                            "longitude": -58.3816,
                            "name": "Buenos Aires, Argentina",
                        },
                        "label": "Primer partido de Scaloni al mando de Argentina",
                        "coach_name": "Lionel Scaloni",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    collector = team_event_collector_from_config(
        {
            "id": "events_arg",
            "url": "https://es.wikipedia.org/wiki/Selecci%C3%B3n_de_f%C3%BAtbol_de_Argentina",
            "grade": "B",
            "local_path": "events.json",
            "terms_url": "https://foundation.wikimedia.org/wiki/Policy:Terms_of_Use",
            "robots_policy": "curated_local_file_cites_public_record",
        },
        tmp_path,
    )
    payload = collector.fetch()
    claims = collector.parse(payload, datetime(2026, 8, 25, tzinfo=UTC))
    assert len(claims) == 2
    debut, coach = claims
    assert debut.entity_type == "WorldCupDebutEvent"
    assert debut.entity_key == "ARG:world_cup_debut"
    assert debut.value["chart_request"]["moment"] == "1930-07-15T16:00:00-03:00"
    assert coach.entity_type == "CoachDebutEvent"
    assert coach.entity_key == "ARG:Lionel Scaloni"

    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session as OrmSession

    from db.base import Base
    from packages.astrology import ephemeris_available

    engine = create_engine(f"sqlite:///{(tmp_path / 'astro.db').as_posix()}")
    Base.metadata.create_all(engine)
    with OrmSession(engine) as session:
        report = recalculate_accepted_charts(session, claims)
    if ephemeris_available():
        assert report.failed == []
        assert report.skipped == []
        assert len(report.recalculated) == 2
    else:
        # Houses require Swiss Ephemeris; environments without the optional
        # astro dependency installed fail loudly rather than skip the
        # location silently, matching test_astrology.py's tolerance for
        # either provider being present.
        assert len(report.failed) == 2
        assert all("Swiss Ephemeris" in item["reason"] for item in report.failed)


def test_all_curated_team_event_files_have_known_utc_offset_moments() -> None:
    events_dir = Path(__file__).resolve().parents[2] / "data"
    paths = sorted(events_dir.glob("events_*.json"))
    for path in paths:
        team_code, records = parse_team_event_records(path.read_bytes())
        assert team_code
        assert records
        for record in records:
            assert record.occurred_at.utcoffset() is not None
            assert record.label
