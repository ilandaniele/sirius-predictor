from __future__ import annotations

import json

from collectors.common.records import PersonRoleRecord


def parse_official_roles(payload: bytes) -> list[PersonRoleRecord]:
    raw = json.loads(payload)
    if raw.get("schema_version") != "sirius-federation-roles-v1":
        raise ValueError("unsupported federation roles schema")
    records = [PersonRoleRecord.model_validate(item) for item in raw.get("roles", [])]
    valid_roles = {"coach", "captain"}
    if any(record.role not in valid_roles for record in records):
        raise ValueError("role must be coach or captain")
    return records
