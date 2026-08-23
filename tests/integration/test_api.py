import json
from collections.abc import Generator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from collectors.sirius_archive import build_archive_index
from db.base import Base
from db.models import DataQuality
from db.session import get_session
from packages.sirius import SiriusReviewQueue
from services.api import main as api_main
from services.api.main import create_app

client = TestClient(create_app())
pytestmark = pytest.mark.integration


def test_health_scenario_teams_and_draw_contracts() -> None:
    assert client.get("/health").json()["status"] == "ok"
    scenario = client.get("/api/v1/scenario")
    assert scenario.status_code == 200
    assert scenario.json()["data"]["format"]["teams"] == 64
    assert scenario.json()["provenance"][0]["quality"] == "X"
    teams = client.get("/api/v1/teams").json()
    assert len(teams["data"]) == 64
    assert teams["provenance"]
    draw = client.get("/api/v1/draw?seed=11").json()["data"]
    assert len(draw) == 16
    assert all(len(group) == 4 for group in draw.values())
    scenario_48 = client.get("/api/v1/scenario?format_size=48").json()["data"]
    assert scenario_48["format"]["teams"] == 48
    teams_48 = client.get("/api/v1/teams?format_size=48").json()["data"]
    assert len(teams_48) == 48
    draw_48 = client.get("/api/v1/draw?seed=11&format_size=48").json()["data"]
    assert len(draw_48) == 12
    backtest = client.get("/api/v1/backtesting/latest")
    assert backtest.status_code == 200
    payload = backtest.json()
    assert payload["data"] is not None or payload["warnings"]
    update = client.get("/api/v1/updates/latest")
    assert update.status_code == 200
    update_payload = update.json()
    assert update_payload["data"] is not None or update_payload["warnings"]


def test_invalid_query_and_security_headers() -> None:
    response = client.get("/api/v1/draw?seed=-1")
    assert response.status_code == 422
    assert response.headers["x-content-type-options"] == "nosniff"
    assert client.get("/api/v1/scenario?format_size=32").status_code == 422
    preflight = client.options(
        "/api/v1/sirius/review-candidates/sync",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "x-api-key,content-type",
        },
    )
    assert preflight.status_code == 200
    assert "x-api-key" in preflight.headers["access-control-allow-headers"].lower()


def test_bracket_svg_allows_same_origin_embedding_other_routes_stay_denied() -> None:
    snapshot_id = "0" * 64
    svg_response = client.get(f"/api/v1/predictions/{snapshot_id}/brackets/1.svg")
    assert svg_response.headers["x-frame-options"] == "SAMEORIGIN"
    other_response = client.get("/api/v1/scenario")
    assert other_response.headers["x-frame-options"] == "DENY"


def test_production_shape_disables_remote_monte_carlo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(api_main.settings, "allow_remote_compute", False)
    guarded_client = TestClient(create_app())
    simulation = guarded_client.post(
        "/api/v1/simulation-jobs",
        json={"format_size": 64, "iterations": 100, "mode": "HYBRID"},
    )
    update = guarded_client.post(
        "/api/v1/update-jobs",
        json={"format_size": 64, "iterations": 100},
    )
    assert simulation.status_code == 409
    assert update.status_code == 409
    assert "local simulation publisher" in simulation.json()["detail"]


def test_local_compute_routes_expose_input_contract_and_require_zip(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        api_main,
        "prepare_local_simulation",
        lambda _settings, _command: {
            "schema_version": "local-simulation-input-v1",
            "status": "ready",
            "input_id": "a" * 64,
        },
    )
    local_client = TestClient(create_app())
    prepared = local_client.post(
        "/api/v1/local-simulation-inputs",
        json={"format_size": 48, "iterations": 100, "workers": 1},
    )
    invalid_upload = local_client.post(
        "/api/v1/local-simulation-results",
        content=b"not-a-zip",
        headers={"Content-Type": "application/json"},
    )
    assert prepared.status_code == 200
    assert prepared.json()["data"]["status"] == "ready"
    assert invalid_upload.status_code == 415


def _review_archive_payload() -> bytes:
    entry = {
        "id": {"$t": "tag:blogger.com,1999:blog-1.post-99"},
        "published": {"$t": "2014-04-30T15:01:00-03:00"},
        "updated": {"$t": "2014-04-30T15:02:00-03:00"},
        "title": {"$t": "Mundial"},
        "content": {"$t": "Pronostico que Argentina llegara a la final. RS favorable."},
        "link": [
            {
                "rel": "alternate",
                "href": "https://astrologiadeportivaa.blogspot.com/post-99.html",
            }
        ],
    }
    return build_archive_index(
        [
            json.dumps(
                {
                    "feed": {
                        "openSearch$totalResults": {"$t": "1"},
                        "entry": [entry],
                    }
                }
            ).encode()
        ],
        datetime(2026, 8, 20, tzinfo=UTC),
    )


def test_sirius_review_api_is_manual_append_only_and_conflict_safe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = create_engine(f"sqlite:///{(tmp_path / 'api-review.db').as_posix()}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
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
            rules_path=api_main.ROOT / "data" / "sirius_rules.yaml",
            teams_path=api_main.settings.teams_path,
        )
        queue.sync_archive(_review_archive_payload())
        session.commit()

    def test_session() -> Generator[Session]:
        with factory() as session:
            yield session

    monkeypatch.setattr(api_main.settings, "storage_path", tmp_path / "storage")
    application = create_app()
    application.dependency_overrides[get_session] = test_session
    review_client = TestClient(application)

    pending = review_client.get("/api/v1/sirius/review-candidates").json()["data"]
    assert pending["counts"]["pending"] == 1
    candidate_id = pending["items"][0]["id"]
    request = {
        "action": "approved",
        "reviewer": "Ilan",
        "reason": "Contraste manual contra la publicaciÃ³n",
        "approval": {
            "team_id": "ARG",
            "feature_id": "solar_return",
            "polarity": "favorable",
            "strength": 0.8,
            "data_confidence": 0.7,
            "hour_robustness": 0.9,
            "description": "Testimonio revisado manualmente",
            "time_known": True,
            "time_source_url": "https://example.com/verified-time",
            "time_consulted_at": "2026-08-20T18:00:00-03:00",
            "time_data_grade": "B",
            "time_source_note": "Hora contrastada con la fuente",
        },
    }
    approved = review_client.post(
        f"/api/v1/sirius/review-candidates/{candidate_id}/decisions", json=request
    )
    assert approved.status_code == 200
    decision_id = approved.json()["data"]["decision"]["id"]
    assert approved.json()["data"]["review_snapshot"]["reviewed_observations"] == 1

    stale = review_client.post(
        f"/api/v1/sirius/review-candidates/{candidate_id}/decisions",
        json={
            "action": "rejected",
            "reviewer": "Ilan",
            "reason": "Segunda lectura del texto fuente",
        },
    )
    assert stale.status_code == 409
    rejected = review_client.post(
        f"/api/v1/sirius/review-candidates/{candidate_id}/decisions",
        json={
            "action": "rejected",
            "reviewer": "Ilan",
            "reason": "Segunda lectura del texto fuente",
            "expected_decision_id": decision_id,
        },
    )
    assert rejected.status_code == 200
    assert rejected.json()["data"]["review_snapshot"]["reviewed_observations"] == 0
    engine.dispose()
