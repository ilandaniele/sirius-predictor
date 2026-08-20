from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, HttpUrl, field_validator, model_validator

from packages.common.types import ModelMode


class ProvenanceView(BaseModel):
    source_id: str
    name: str
    url: str | None
    consulted_at: str
    quality: str
    official: bool
    status: str


class SimulationRequest(BaseModel):
    format_size: Literal[48, 64] = 64
    iterations: int = Field(default=100_000, ge=100, le=1_000_000)
    seed: int = Field(default=2030, ge=0, le=2**31 - 1)
    mode: ModelMode = ModelMode.HYBRID
    final_hour: int = 18
    workers: int | None = Field(default=None, ge=1, le=64)

    @field_validator("final_hour")
    @classmethod
    def valid_final_hour(cls, value: int) -> int:
        if value not in {17, 18, 20, 21}:
            raise ValueError("final_hour must be 17, 18, 20 or 21")
        return value


class JobAccepted(BaseModel):
    job_id: str
    status: str
    detail: str


class UpdateRequest(BaseModel):
    format_size: Literal[48, 64] = 64
    iterations: int = Field(default=100_000, ge=100, le=1_000_000)
    seed: int = Field(default=2030, ge=0, le=2**31 - 1)
    modes: list[ModelMode] = Field(default_factory=lambda: list(ModelMode))


class SiriusObservationApproval(BaseModel):
    team_id: str = Field(min_length=2, max_length=12)
    feature_id: str = Field(min_length=2, max_length=100)
    polarity: Literal["favorable", "adverse", "neutral"]
    strength: float = Field(ge=0, le=1)
    data_confidence: float = Field(ge=0, le=1)
    hour_robustness: float | None = Field(default=None, ge=0, le=1)
    description: str = Field(min_length=5, max_length=1000)
    time_known: bool = False
    time_source_url: HttpUrl | None = None
    time_consulted_at: datetime | None = None
    time_data_grade: Literal["A", "B", "C", "D", "X"] | None = None
    time_source_note: str | None = Field(default=None, min_length=5, max_length=1000)


class SiriusReviewDecisionRequest(BaseModel):
    action: Literal["approved", "rejected"]
    reviewer: str = Field(min_length=2, max_length=160)
    reason: str = Field(min_length=5, max_length=2000)
    expected_decision_id: str | None = None
    approval: SiriusObservationApproval | None = None

    @model_validator(mode="after")
    def matching_payload(self) -> SiriusReviewDecisionRequest:
        if self.action == "approved" and self.approval is None:
            raise ValueError("approved decisions require approval")
        if self.action == "rejected" and self.approval is not None:
            raise ValueError("rejected decisions cannot include approval")
        return self


class ApiEnvelope(BaseModel):
    data: Any
    provenance: list[ProvenanceView] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
