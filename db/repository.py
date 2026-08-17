from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from packages.common.provenance import DataGrade, SourceClaimInput, should_auto_replace

from .models import Source, SourceClaim


def append_claim(session: Session, claim: SourceClaimInput) -> tuple[SourceClaim, bool]:
    source = session.scalar(select(Source).where(Source.slug == claim.source_id))
    if source is None:
        raise LookupError(f"unknown source: {claim.source_id}")
    current = session.scalar(
        select(SourceClaim)
        .where(
            SourceClaim.entity_type == claim.entity_type,
            SourceClaim.entity_key == claim.entity_key,
            SourceClaim.field_name == claim.field_name,
            SourceClaim.active.is_(True),
        )
        .order_by(SourceClaim.consulted_at.desc())
    )
    activate = current is None
    if current is not None:
        current_source = session.get(Source, current.source_id)
        if current_source is None:
            raise LookupError("active claim references a missing source")
        current_input = SourceClaimInput(
            entity_type=current.entity_type,
            entity_key=current.entity_key,
            field_name=current.field_name,
            value=current.value,
            source_id=current_source.slug,
            source_url=current_source.url,
            consulted_at=current.consulted_at,
            grade=DataGrade(current_source.quality_code),
            confidence=current.confidence,
            official=current.official,
            inferred=current.inferred,
            manually_confirmed=current.manually_confirmed,
            raw_reference=current.raw_reference,
        )
        activate = should_auto_replace(current_input, claim)
        if activate:
            current.active = False
    record = SourceClaim(
        entity_type=claim.entity_type,
        entity_key=claim.entity_key,
        field_name=claim.field_name,
        value=claim.value,
        source_id=source.id,
        consulted_at=claim.consulted_at,
        confidence=claim.confidence,
        official=claim.official,
        inferred=claim.inferred,
        manually_confirmed=claim.manually_confirmed,
        active=activate,
        raw_reference=claim.raw_reference,
    )
    session.add(record)
    session.flush()
    return record, activate
