from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from db.base import Base
from db.models import AstrologyChart as StoredAstrologyChart
from packages.astrology import (
    AstrologyChartCache,
    ChartRequest,
    GeoLocation,
    chart_input_hash,
    recalculate_accepted_charts,
)
from packages.common.provenance import DataGrade, SourceClaimInput


@pytest.fixture
def session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as value:
        yield value
    engine.dispose()


def _claim(value: object) -> SourceClaimInput:
    return SourceClaimInput(
        entity_type="Fixture",
        entity_key="final-2030",
        field_name="kickoff",
        value=value,
        source_id="official-fixture-source",
        source_url="https://example.com/fixture",
        consulted_at=datetime(2026, 8, 20, tzinfo=UTC),
        grade=DataGrade.A,
        confidence=1.0,
        official=True,
    )


def test_chart_cache_is_content_addressed_append_only_and_reusable(session: Session) -> None:
    cache = AstrologyChartCache(session)
    request = ChartRequest(
        datetime(2030, 7, 21, 16, tzinfo=UTC),
        location=None,
        time_known=True,
        house_system="P",
        label="Final 2030",
    )
    first = cache.get_or_calculate("Fixture", "final-2030", request)
    second = cache.get_or_calculate("Fixture", "final-2030", request)
    changed = cache.get_or_calculate(
        "Fixture",
        "final-2030",
        ChartRequest(
            datetime(2030, 7, 21, 16, 15, tzinfo=UTC),
            location=None,
            time_known=True,
            house_system="P",
            label="Final 2030",
        ),
    )
    session.commit()

    assert first.status == "recalculated"
    assert second.status == "hit"
    assert second.chart.to_dict() == first.chart.to_dict()
    assert second.input_hash == first.input_hash
    assert changed.status == "recalculated"
    assert changed.input_hash != first.input_hash
    assert session.scalar(select(func.count()).select_from(StoredAstrologyChart)) == 2

    stored = session.scalar(
        select(StoredAstrologyChart).where(StoredAstrologyChart.id == first.chart_id)
    )
    assert stored is not None
    stored.subject_id = "mutated"
    with pytest.raises(ValueError, match="append-only"):
        session.commit()
    session.rollback()


def test_hash_includes_location_parameters_and_ephemeris_identity() -> None:
    moment = datetime(2030, 7, 21, 16, tzinfo=UTC)
    madrid = ChartRequest(moment, GeoLocation(40.4168, -3.7038, "Madrid"), True, "P")
    lisbon = ChartRequest(moment, GeoLocation(38.7223, -9.1393, "Lisbon"), True, "P")
    assert chart_input_hash("Fixture", "final-2030", madrid) == chart_input_hash(
        "Fixture", "final-2030", madrid
    )
    assert chart_input_hash("Fixture", "final-2030", madrid) != chart_input_hash(
        "Fixture", "final-2030", lisbon
    )


def test_recalculation_requires_complete_known_time_and_provenance(session: Session) -> None:
    unknown_time = _claim(
        {
            "chart_request": {
                "moment": "1980-01-01T12:00:00+00:00",
                "time_known": False,
                "house_system": "P",
                "location": None,
            }
        }
    )
    incomplete = _claim({"moment": "2030-07-21T18:00:00+02:00"})
    report = recalculate_accepted_charts(session, [unknown_time, incomplete])
    assert report.requested_entities == ["Fixture:final-2030"]
    assert report.recalculated == []
    assert report.cache_hits == []
    assert [row["reason"] for row in report.skipped] == [
        "unknown time requires an explicit sensitivity analysis",
        "claim value has no complete chart_request object",
    ]
    assert session.scalar(select(func.count()).select_from(StoredAstrologyChart)) == 0


def test_selective_recalculation_reports_real_miss_then_hit(session: Session) -> None:
    valid = _claim(
        {
            "chart_request": {
                "moment": "2030-07-21T18:00:00+02:00",
                "time_known": True,
                "house_system": "P",
                "location": None,
                "bodies": ["Sun", "Moon"],
                "orbs": {"conjunction": 7.0},
                "label": "Final Mundial 2030",
            }
        }
    )
    unrelated = valid.model_copy(update={"entity_type": "Team", "entity_key": "ARG"})

    first = recalculate_accepted_charts(session, [valid, unrelated])
    second = recalculate_accepted_charts(session, [valid, unrelated])
    session.commit()

    assert first.to_dict()["recalculated_count"] == 1
    assert first.to_dict()["cache_hit_count"] == 0
    assert second.to_dict()["recalculated_count"] == 0
    assert second.to_dict()["cache_hit_count"] == 1
    assert first.recalculated[0]["input_hash"] == second.cache_hits[0]["input_hash"]
