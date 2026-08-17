from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator

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
    iterations: int = Field(default=100_000, ge=100, le=1_000_000)
    seed: int = Field(default=2030, ge=0, le=2**31 - 1)
    modes: list[ModelMode] = Field(default_factory=lambda: list(ModelMode))


class ApiEnvelope(BaseModel):
    data: Any
    provenance: list[ProvenanceView] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
