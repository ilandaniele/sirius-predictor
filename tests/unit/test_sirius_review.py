import json
from collections.abc import Generator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from collectors.argumental_archive import build_archive_index as build_argumental_archive_index
from collectors.argumental_archive import parse_archive_index as argumental_parse_archive_index
from collectors.sirius_archive import build_archive_index
from db.base import Base
from db.models import DataQuality, SiriusReviewDecision
from engine.config import load_scenario, load_teams, teams_for_scenario
from engine.sim import run_engine
from packages.common.types import ModelMode
from packages.sirius import ReviewConflictError, SiriusReviewQueue, load_reviewed_observations

ROOT = Path(__file__).resolve().parents[2]


def _archive_payload() -> bytes:
    entry = {
        "id": {"$t": "tag:blogger.com,1999:blog-1.post-42"},
        "published": {"$t": "2014-04-30T15:01:00-03:00"},
        "updated": {"$t": "2014-04-30T15:02:00-03:00"},
        "title": {"$t": "Mundial"},
        "content": {
            "$t": "Pronostico que Argentina llegara a la final. Revolucion solar favorable."
        },
        "link": [
            {
                "rel": "alternate",
                "href": "https://astrologiadeportivaa.blogspot.com/post-42.html",
            }
        ],
    }
    page = json.dumps(
        {
            "feed": {
                "openSearch$totalResults": {"$t": "1"},
                "entry": [entry],
            }
        }
    ).encode()
    return build_archive_index([page], datetime(2026, 8, 20, tzinfo=UTC))


@pytest.fixture
def review_queue(tmp_path: Path) -> Generator[tuple[SiriusReviewQueue, Session]]:
    engine = create_engine(f"sqlite:///{(tmp_path / 'review.db').as_posix()}")
    Base.metadata.create_all(engine)
    session = Session(engine)
    session.add(
        DataQuality(
            code="B",
            label="Archivo confiable",
            precedence=4,
            requires_manual_review=False,
        )
    )
    session.commit()
    queue = SiriusReviewQueue(
        session,
        rules_path=ROOT / "data" / "sirius_rules.yaml",
        teams_path=ROOT / "data" / "teams.csv",
    )
    yield queue, session
    session.close()
    engine.dispose()


def _approval(*, time_known: bool) -> dict[str, object]:
    return {
        "team_id": "ARG",
        "feature_id": "solar_return",
        "polarity": "favorable",
        "strength": 0.8,
        "data_confidence": 0.7,
        "hour_robustness": 0.9 if time_known else None,
        "description": "Testimonio revisado manualmente",
        "time_known": time_known,
        "time_source_url": "https://example.com/verified-time" if time_known else None,
        "time_consulted_at": "2026-08-20T18:00:00-03:00" if time_known else None,
        "time_data_grade": "B" if time_known else None,
        "time_source_note": "Hora contrastada con la fuente" if time_known else None,
    }


def test_archive_candidates_are_idempotent_and_never_auto_approved(
    review_queue: tuple[SiriusReviewQueue, Session],
) -> None:
    queue, session = review_queue
    first = queue.sync_archive(_archive_payload())
    session.commit()
    second = queue.sync_archive(_archive_payload())
    session.commit()
    result = queue.list_candidates()
    assert first == {
        "sports_posts": 1,
        "candidate_sentences": 1,
        "inserted": 1,
        "already_present": 0,
    }
    assert second["inserted"] == 0
    assert result["counts"] == {"pending": 1, "approved": 0, "rejected": 0, "total": 1}
    assert result["items"][0]["inferred"] is True


def test_approval_requires_real_time_and_can_be_superseded_without_mutation(
    review_queue: tuple[SiriusReviewQueue, Session], tmp_path: Path
) -> None:
    queue, session = review_queue
    queue.sync_archive(_archive_payload())
    session.commit()
    candidate_id = queue.list_candidates()["items"][0]["id"]

    with pytest.raises(ValueError, match="verified real time"):
        queue.decide(
            candidate_id,
            action="approved",
            reviewer="Ilan",
            reason="Contraste manual con el post",
            approval=_approval(time_known=False),
        )

    missing_time_provenance = _approval(time_known=True)
    missing_time_provenance["time_source_url"] = None
    with pytest.raises(ValueError, match="provenance fields"):
        queue.decide(
            candidate_id,
            action="approved",
            reviewer="Ilan",
            reason="Contraste manual con el post",
            approval=missing_time_provenance,
        )

    approved = queue.decide(
        candidate_id,
        action="approved",
        reviewer="Ilan",
        reason="Contraste manual con el post",
        approval=_approval(time_known=True),
    )
    session.commit()
    snapshot = queue.export_reviewed_snapshot(tmp_path / "reviewed")
    observations, audit = load_reviewed_observations(snapshot["path"], {"ARG", "ESP"})
    assert snapshot["reviewed_observations"] == 1
    assert len(observations["ARG"]) == 1
    assert audit["reviewed_observations"] == 1
    assert observations["ARG"][0].data_grade.value == "B"
    assert (
        observations["ARG"][0].parameters["time_verification"]["source_url"]
        == "https://example.com/verified-time"
    )
    scenario = load_scenario(ROOT / "data" / "scenario.yaml")
    teams = teams_for_scenario(load_teams(ROOT / "data" / "teams.csv"), scenario)
    simulation = run_engine(
        teams,
        scenario,
        n=1,
        mode=ModelMode.FOOTBALL_ONLY,
        reviewed_observations_path=snapshot["path"],
    )
    assert simulation.sirius_evidence_audit["reviewed_observations"] == 1
    assert simulation.sirius_assessments["ARG"]["journey_index"]["evidence_count"] == 1

    with pytest.raises(ReviewConflictError, match="reload"):
        queue.decide(
            candidate_id,
            action="rejected",
            reviewer="Ilan",
            reason="Nueva lectura del texto fuente",
        )
    rejected = queue.decide(
        candidate_id,
        action="rejected",
        reviewer="Ilan",
        reason="Nueva lectura del texto fuente",
        expected_decision_id=approved.id,
    )
    session.commit()
    assert rejected.supersedes_decision_id == approved.id
    assert queue.reviewed_records() == []
    empty_snapshot = queue.export_reviewed_snapshot(tmp_path / "reviewed")
    empty_simulation = run_engine(
        teams,
        scenario,
        n=1,
        mode=ModelMode.FOOTBALL_ONLY,
        reviewed_observations_path=empty_snapshot["path"],
    )
    assert empty_simulation.manifest.input_sha256 != simulation.manifest.input_sha256
    assert empty_simulation.manifest.run_id != simulation.manifest.run_id
    assert session.scalar(
        select(SiriusReviewDecision).where(SiriusReviewDecision.id == approved.id)
    )


def test_feature_must_be_explicitly_detected_in_candidate(
    review_queue: tuple[SiriusReviewQueue, Session],
) -> None:
    queue, session = review_queue
    queue.sync_archive(_archive_payload())
    session.commit()
    candidate_id = queue.list_candidates()["items"][0]["id"]
    approval = _approval(time_known=True)
    approval["feature_id"] = "transits"
    with pytest.raises(ValueError, match="explicitly detected"):
        queue.decide(
            candidate_id,
            action="approved",
            reviewer="Ilan",
            reason="La técnica no figura en el candidato",
            approval=approval,
        )


def _argumental_archive_payload() -> bytes:
    entry = {
        "id": {"$t": "tag:blogger.com,1999:blog-2.post-9"},
        "published": {"$t": "2026-07-11T15:01:00-03:00"},
        "updated": {"$t": "2026-07-11T15:02:00-03:00"},
        "title": {"$t": "Mundial Argentina vs Brasil"},
        "content": {
            "$t": (
                "Analisis del partido mediante el metodo Frawley: Argentina ganara la final."
            )
        },
        "link": [
            {
                "rel": "alternate",
                "href": "https://astrologiaargumental.blogspot.com/post-9.html",
            }
        ],
    }
    page = json.dumps(
        {
            "feed": {
                "openSearch$totalResults": {"$t": "1"},
                "entry": [entry],
            }
        }
    ).encode()
    return build_argumental_archive_index([page], datetime(2026, 8, 20, tzinfo=UTC))


def test_review_queues_do_not_leak_candidates_across_sources(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite:///{(tmp_path / 'multi-source.db').as_posix()}")
    Base.metadata.create_all(engine)
    session = Session(engine)
    session.add(
        DataQuality(
            code="B",
            label="Archivo confiable",
            precedence=4,
            requires_manual_review=False,
        )
    )
    session.commit()

    sirius = SiriusReviewQueue(
        session,
        rules_path=ROOT / "data" / "sirius_rules.yaml",
        teams_path=ROOT / "data" / "teams.csv",
        source_id="sirius_blog",
    )
    argumental = SiriusReviewQueue(
        session,
        rules_path=ROOT / "data" / "argumental_rules.yaml",
        teams_path=ROOT / "data" / "teams.csv",
        source_id="argumental_blog",
        parse_archive_index=argumental_parse_archive_index,
    )
    sirius.sync_archive(_archive_payload())
    argumental.sync_archive(_argumental_archive_payload())
    session.commit()

    sirius_items = sirius.list_candidates(status="all")["items"]
    argumental_items = argumental.list_candidates(status="all")["items"]
    assert sirius_items and argumental_items
    assert all(item["source_id"] == "sirius_blog" for item in sirius_items)
    assert all(item["source_id"] == "argumental_blog" for item in argumental_items)

    argumental_candidate_id = argumental_items[0]["id"]
    with pytest.raises(LookupError):
        sirius.decide(
            argumental_candidate_id,
            action="rejected",
            reviewer="Ilan",
            reason="No pertenece a esta cola de revisión",
        )
    session.close()
    engine.dispose()
