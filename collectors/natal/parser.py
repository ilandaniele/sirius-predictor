from __future__ import annotations

import json

from collectors.common.records import BirthRecord


def parse_birth_records(payload: bytes) -> list[BirthRecord]:
    raw = json.loads(payload)
    if raw.get("schema_version") != "sirius-birth-data-v1":
        raise ValueError("unsupported birth data schema")
    return [BirthRecord.model_validate(item) for item in raw.get("records", [])]
