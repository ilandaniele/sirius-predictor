from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from collectors.common.records import FixtureRecord, PersonRoleRecord, TeamRecord, VenueRecord


class StructuredFifaParser:
    """Parser for versioned normalized fixtures captured from an official adapter.

    The upstream FIFA schema is deliberately not guessed. An adapter must first map its payload to
    the explicit keys below; schema drift then fails loudly and the previous snapshot stays active.
    """

    @staticmethod
    def parse(payload: bytes) -> dict[str, list[Any]]:
        raw = json.loads(payload)
        if raw.get("schema_version") != "sirius-fifa-v1":
            raise ValueError("unsupported or missing normalized FIFA schema_version")
        return {
            "teams": [TeamRecord.model_validate(item) for item in raw.get("teams", [])],
            "roles": [PersonRoleRecord.model_validate(item) for item in raw.get("roles", [])],
            "venues": [VenueRecord.model_validate(item) for item in raw.get("venues", [])],
            "fixtures": [FixtureRecord.model_validate(item) for item in raw.get("fixtures", [])],
        }


def fixture_change_fields(old: FixtureRecord, new: FixtureRecord) -> set[str]:
    return {
        field for field in FixtureRecord.model_fields if getattr(old, field) != getattr(new, field)
    }


def fixture_kickoff_is_future(record: FixtureRecord, now: datetime) -> bool:
    return record.kickoff_utc is not None and record.kickoff_utc > now
