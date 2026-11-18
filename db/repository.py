from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from packages.common.provenance import DataGrade, SourceClaimInput, should_auto_replace

from .models import Source, SourceClaim


@dataclass(frozen=True, slots=True)
class ClaimAppendOutcome:
    record: SourceClaim
    eligible: bool
    created: bool


def _utc_from_database(value: datetime) -> datetime:
    # SQLite drops timezone metadata from DateTime(timezone=True). All writes in this
    # repository are UTC, so restoring UTC here preserves the declared DB contract.
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def claim_fingerprint(claim: SourceClaimInput) -> str:
    payload = claim.model_dump(
        mode="json",
        exclude={"consulted_at"},
    )
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def append_claim(session: Session, claim: SourceClaimInput) -> ClaimAppendOutcome:
    """Append a claim once and derive eligibility without mutating earlier observations."""

    if claim.source_url is None:
        raise ValueError("persisted external claims require source_url")
    source = session.scalar(select(Source).where(Source.slug == claim.source_id))
    if source is None:
        raise LookupError(f"unknown source: {claim.source_id}")
    if source.quality_code != claim.grade.value or source.official != claim.official:
        raise ValueError(
            f"{claim.source_id}: claim quality/official status differs from source catalog"
        )
    fingerprint = claim_fingerprint(claim)
    duplicate = session.scalar(select(SourceClaim).where(SourceClaim.fingerprint == fingerprint))
    if duplicate is not None:
        return ClaimAppendOutcome(record=duplicate, eligible=duplicate.active, created=False)

    current = session.scalar(
        select(SourceClaim)
        .where(
            SourceClaim.entity_type == claim.entity_type,
            SourceClaim.entity_key == claim.entity_key,
            SourceClaim.field_name == claim.field_name,
            SourceClaim.active.is_(True),
        )
        .order_by(SourceClaim.consulted_at.desc(), SourceClaim.created_at.desc())
    )
    eligible = current is None and (
        claim.manually_confirmed
        or (claim.grade in {DataGrade.A, DataGrade.B} and not claim.inferred)
    )
    if current is not None:
        current_source = session.get(Source, current.source_id)
        if current_source is None:
            raise LookupError("eligible claim references a missing source")
        current_input = SourceClaimInput(
            entity_type=current.entity_type,
            entity_key=current.entity_key,
            field_name=current.field_name,
            value=current.value,
            source_id=current_source.slug,
            source_url=current.source_url,
            consulted_at=_utc_from_database(current.consulted_at),
            grade=DataGrade(current.quality_code),
            confidence=current.confidence,
            official=current.official,
            inferred=current.inferred,
            manually_confirmed=current.manually_confirmed,
            raw_reference=current.raw_reference,
        )
        eligible = should_auto_replace(current_input, claim)
    record = SourceClaim(
        entity_type=claim.entity_type,
        entity_key=claim.entity_key,
        field_name=claim.field_name,
        value=claim.value,
        fingerprint=fingerprint,
        source_id=source.id,
        source_url=str(claim.source_url),
        quality_code=claim.grade.value,
        consulted_at=claim.consulted_at.astimezone(UTC),
        confidence=claim.confidence,
        official=claim.official,
        inferred=claim.inferred,
        manually_confirmed=claim.manually_confirmed,
        active=eligible,
        raw_reference=claim.raw_reference,
    )
    try:
        with session.begin_nested():
            session.add(record)
            session.flush()
    except IntegrityError:
        concurrent = session.scalar(
            select(SourceClaim).where(SourceClaim.fingerprint == fingerprint)
        )
        if concurrent is None:  # pragma: no cover - defensive database race guard
            raise
        return ClaimAppendOutcome(
            record=concurrent,
            eligible=concurrent.active,
            created=False,
        )
    return ClaimAppendOutcome(record=record, eligible=eligible, created=True)


def sync_source_catalog(session: Session, records: list[dict[str, Any]]) -> dict[str, int]:
    """Synchronize mutable source metadata; claims retain URL/quality snapshots."""

    created = 0
    updated = 0
    for item in records:
        slug = str(item["id"])
        grade = DataGrade(str(item["grade"]))
        official = bool(item.get("official", grade == DataGrade.A))
        if official and grade not in {DataGrade.A, DataGrade.B}:
            raise ValueError(f"{slug}: official source must have quality A or B")
        source = session.scalar(select(Source).where(Source.slug == slug))
        values = {
            "name": str(item.get("name") or slug),
            "url": str(item["url"]) if item.get("url") else None,
            "quality_code": grade.value,
            "official": official,
            "enabled": bool(item.get("enabled", True)),
            "terms_url": str(item["terms_url"]) if item.get("terms_url") else None,
        }
        if source is None:
            session.add(Source(slug=slug, **values))
            created += 1
            continue
        if source.quality_code == DataGrade.A.value and grade in {DataGrade.C, DataGrade.D}:
            raise ValueError(
                f"{slug}: source A cannot be downgraded automatically to {grade.value}"
            )
        changed = False
        for field_name, value in values.items():
            if getattr(source, field_name) != value:
                setattr(source, field_name, value)
                changed = True
        updated += int(changed)
    session.flush()
    return {"created": created, "updated": updated}
