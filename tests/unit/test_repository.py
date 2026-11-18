from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from db.base import Base
from db.models import DataQuality, Source, SourceClaim
from db.repository import append_claim, claim_fingerprint, sync_source_catalog
from packages.common.provenance import DataGrade, SourceClaimInput


@pytest.fixture
def session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as value:
        for code, precedence in (("A", 5), ("B", 4), ("C", 3), ("D", 2), ("X", 1)):
            value.add(
                DataQuality(
                    code=code,
                    label=code,
                    precedence=precedence,
                    requires_manual_review=code in {"C", "D", "X"},
                )
            )
        value.add_all(
            [
                Source(
                    slug="ranking",
                    name="Official ranking",
                    url="https://example.com/ranking",
                    quality_code="A",
                    official=True,
                    enabled=True,
                    terms_url="https://example.com/terms",
                ),
                Source(
                    slug="archive",
                    name="Archive",
                    url="https://example.com/archive",
                    quality_code="B",
                    official=False,
                    enabled=True,
                    terms_url="https://example.com/terms",
                ),
                Source(
                    slug="secondary",
                    name="Secondary",
                    url="https://example.com/secondary",
                    quality_code="C",
                    official=False,
                    enabled=True,
                    terms_url="https://example.com/terms",
                ),
            ]
        )
        value.commit()
        yield value
    engine.dispose()


def _claim(
    value: object,
    *,
    grade: DataGrade = DataGrade.A,
    consulted_at: datetime | None = None,
) -> SourceClaimInput:
    source_ids = {
        DataGrade.A: "ranking",
        DataGrade.B: "archive",
        DataGrade.C: "secondary",
    }
    return SourceClaimInput(
        entity_type="RankingSnapshot",
        entity_key="ARG",
        field_name="rank",
        value=value,
        source_id=source_ids[grade],
        source_url=f"https://example.com/{source_ids[grade]}/approved",
        consulted_at=consulted_at or datetime(2026, 8, 20, tzinfo=UTC),
        grade=grade,
        confidence=1.0 if grade == DataGrade.A else 0.7,
        official=grade == DataGrade.A,
    )


def test_claims_are_deduplicated_append_only_and_keep_provenance(session: Session) -> None:
    first_input = _claim(1)
    first = append_claim(session, first_input)
    duplicate = append_claim(
        session,
        first_input.model_copy(
            update={"consulted_at": first_input.consulted_at + timedelta(hours=1)}
        ),
    )
    lower = append_claim(
        session,
        _claim(
            2,
            grade=DataGrade.C,
            consulted_at=first_input.consulted_at + timedelta(hours=2),
        ),
    )
    newer_equal = append_claim(
        session,
        _claim(3, consulted_at=first_input.consulted_at + timedelta(hours=3)),
    )
    session.commit()

    assert first.created and first.eligible
    assert duplicate.record.id == first.record.id
    assert not duplicate.created
    assert not lower.eligible
    assert newer_equal.eligible
    assert first.record.active is True
    assert session.scalar(select(func.count()).select_from(SourceClaim)) == 3
    assert first.record.fingerprint == claim_fingerprint(first_input)
    assert first.record.source_url == "https://example.com/ranking/approved"
    assert first.record.quality_code == "A"

    source = session.scalar(select(Source).where(Source.slug == "ranking"))
    assert source is not None
    source.url = "https://example.com/new-catalog-url"
    session.commit()
    assert first.record.source_url == "https://example.com/ranking/approved"

    first.record.value = 999
    with pytest.raises(ValueError, match="append-only"):
        session.commit()
    session.rollback()


def test_source_catalog_cannot_downgrade_a_to_c(session: Session) -> None:
    with pytest.raises(ValueError, match="cannot be downgraded"):
        sync_source_catalog(
            session,
            [
                {
                    "id": "ranking",
                    "name": "Official ranking",
                    "grade": "C",
                    "official": False,
                    "url": "https://example.com/ranking",
                    "terms_url": "https://example.com/terms",
                }
            ],
        )


def test_first_uncertain_or_inferred_claim_is_never_eligible_without_review(
    session: Session,
) -> None:
    uncertain = _claim(10, grade=DataGrade.C).model_copy(update={"entity_key": "BRA"})
    inferred_archive = _claim(11, grade=DataGrade.B).model_copy(
        update={"entity_key": "ESP", "inferred": True, "official": False}
    )
    assert not append_claim(session, uncertain).eligible
    assert not append_claim(session, inferred_archive).eligible
