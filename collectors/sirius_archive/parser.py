from __future__ import annotations

import json
from datetime import datetime

from pydantic import BaseModel, HttpUrl


class ArchivedPrediction(BaseModel):
    published_at: datetime
    captured_at: datetime
    url: HttpUrl
    title: str
    content_sha256: str
    explicit_claims: list[str]
    inferred_notes: list[str]


def parse_archive_index(payload: bytes) -> list[ArchivedPrediction]:
    raw = json.loads(payload)
    if raw.get("schema_version") != "sirius-archive-v1":
        raise ValueError("unsupported Sirius archive schema")
    return [ArchivedPrediction.model_validate(item) for item in raw.get("posts", [])]
