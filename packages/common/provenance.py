from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, HttpUrl, model_validator


class DataGrade(StrEnum):
    A = "A"
    B = "B"
    C = "C"
    D = "D"
    X = "X"

    @property
    def precedence(self) -> int:
        return {"A": 5, "B": 4, "C": 3, "D": 2, "X": 1}[self.value]


class SourceClaimInput(BaseModel):
    entity_type: str
    entity_key: str
    field_name: str
    value: Any
    source_id: str
    source_url: HttpUrl | None
    consulted_at: datetime
    grade: DataGrade
    confidence: float = Field(ge=0.0, le=1.0)
    official: bool = False
    inferred: bool = False
    manually_confirmed: bool = False
    raw_reference: str | None = None

    @model_validator(mode="after")
    def official_grade_consistency(self) -> SourceClaimInput:
        if self.consulted_at.tzinfo is None or self.consulted_at.utcoffset() is None:
            raise ValueError("consulted_at must be timezone-aware")
        if self.official and self.grade not in {DataGrade.A, DataGrade.B}:
            raise ValueError("an official claim must use quality A or B")
        return self


def should_auto_replace(current: SourceClaimInput, candidate: SourceClaimInput) -> bool:
    """Conservative precedence: uncertain scraped claims always require review."""

    if (
        candidate.grade in {DataGrade.C, DataGrade.D, DataGrade.X}
        and not candidate.manually_confirmed
    ):
        return False
    if current.grade == DataGrade.A and candidate.grade != DataGrade.A:
        return False
    if candidate.inferred and not candidate.manually_confirmed:
        return False
    if candidate.grade.precedence < current.grade.precedence:
        return False
    return candidate.consulted_at >= current.consulted_at
