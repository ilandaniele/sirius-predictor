from __future__ import annotations

import json
from datetime import datetime

from pydantic import BaseModel, Field, model_validator

EVENT_TYPES = {"world_cup_debut", "federation_founding", "coach_debut"}


class GeoPoint(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    name: str = ""


class TeamEventRecord(BaseModel):
    event_type: str
    occurred_at: datetime
    location: GeoPoint
    label: str
    coach_name: str | None = None

    @model_validator(mode="after")
    def enforce_known_moment(self) -> TeamEventRecord:
        if self.event_type not in EVENT_TYPES:
            raise ValueError(f"unsupported event_type: {self.event_type}")
        if self.occurred_at.tzinfo is None or self.occurred_at.utcoffset() is None:
            raise ValueError("occurred_at must include a UTC offset; no naive moments")
        if self.event_type == "coach_debut" and not self.coach_name:
            raise ValueError("coach_debut events must name the coach")
        return self


def parse_team_event_records(payload: bytes) -> tuple[str, list[TeamEventRecord]]:
    raw = json.loads(payload)
    if raw.get("schema_version") != "sirius-team-events-v1":
        raise ValueError("unsupported team events schema")
    team_code = str(raw["team_code"])
    records = [TeamEventRecord.model_validate(item) for item in raw.get("events", [])]
    return team_code, records
