from fastapi.testclient import TestClient

from services.api.main import create_app

client = TestClient(create_app())


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
