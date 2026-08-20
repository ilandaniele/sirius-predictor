from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from packages.common.provenance import DataGrade, SourceClaimInput, should_auto_replace


def make_claim(grade: DataGrade, value: object, **changes: object) -> SourceClaimInput:
    values = {
        "entity_type": "Team",
        "entity_key": "ARG",
        "field_name": "coach",
        "value": value,
        "source_id": "source",
        "source_url": "https://example.com/source",
        "consulted_at": datetime(2026, 8, 17, tzinfo=UTC),
        "grade": grade,
        "confidence": 0.9,
        "official": grade == DataGrade.A,
        "inferred": False,
        "manually_confirmed": False,
    }
    values.update(changes)
    return SourceClaimInput.model_validate(values)


def test_grade_a_cannot_be_automatically_replaced_by_lower_quality() -> None:
    current = make_claim(DataGrade.A, "Lionel Scaloni")
    candidate = make_claim(
        DataGrade.C,
        "Otro",
        official=False,
        consulted_at=current.consulted_at + timedelta(days=1),
    )
    assert not should_auto_replace(current, candidate)


def test_newer_equal_quality_can_replace_but_inference_needs_review() -> None:
    current = make_claim(DataGrade.B, "A", official=False)
    newer = make_claim(
        DataGrade.B,
        "B",
        official=False,
        consulted_at=current.consulted_at + timedelta(days=1),
    )
    assert should_auto_replace(current, newer)
    assert not should_auto_replace(current, newer.model_copy(update={"inferred": True}))


def test_consulted_timestamp_requires_an_explicit_timezone() -> None:
    with pytest.raises(ValidationError, match="consulted_at must be timezone-aware"):
        make_claim(DataGrade.B, "value", consulted_at=datetime(2026, 8, 20))
