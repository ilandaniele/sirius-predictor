from __future__ import annotations

from datetime import date, datetime, time

from pydantic import BaseModel, Field, model_validator


class RankingRecord(BaseModel):
    team_code: str
    team_name: str
    rank: int = Field(gt=0)
    points: float | None = None
    ranking_date: date


class TeamRecord(BaseModel):
    team_code: str
    team_name: str
    confederation: str
    qualification_status: str


class PersonRoleRecord(BaseModel):
    team_code: str
    person_name: str
    role: str
    starts_on: date
    ends_on: date | None = None


class VenueRecord(BaseModel):
    name: str
    city: str
    country_code: str
    timezone: str
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)


class FixtureRecord(BaseModel):
    external_id: str
    stage: str
    home_team_code: str | None = None
    away_team_code: str | None = None
    kickoff_utc: datetime | None = None
    venue_name: str | None = None
    home_goals: int | None = Field(default=None, ge=0)
    away_goals: int | None = Field(default=None, ge=0)
    status: str


class BirthRecord(BaseModel):
    person_name: str
    birth_date: date
    birth_time: time | None = None
    timezone: str | None = None
    place: str | None = None
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    time_known: bool = False
    rodden_rating: str | None = None

    @model_validator(mode="after")
    def enforce_unknown_time_policy(self) -> BirthRecord:
        if self.time_known and (self.birth_time is None or self.timezone is None):
            raise ValueError("known birth time requires both time and timezone")
        if not self.time_known and self.birth_time is not None:
            raise ValueError("unknown birth time must remain null; never impute 12:00")
        return self
