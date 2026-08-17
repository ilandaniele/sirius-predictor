import json
from datetime import date

import pytest

from collectors.common.records import BirthRecord
from collectors.fifa.ranking import parse_fifa_ranking
from collectors.fifa.structured import StructuredFifaParser
from collectors.natal.parser import parse_birth_records


def test_fifa_ranking_parser_supports_versioned_embedded_json() -> None:
    payload = b"""<script type="application/json">
    {"ranking":[{"rank":1,"teamName":"Argentina","teamCode":"ARG","totalPoints":1886.16}]}
    </script>"""
    records = parse_fifa_ranking(payload, date(2026, 8, 17))
    assert [(record.team_code, record.rank) for record in records] == [("ARG", 1)]


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
