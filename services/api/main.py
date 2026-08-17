from __future__ import annotations

import random
from dataclasses import asdict
from typing import Annotated

from fastapi import Depends, FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from db.session import get_session
from engine.config import load_scenario, load_teams, validate_scenario
from engine.draw import draw_groups
from packages.common.config import get_settings

from .catalog import (
    latest_backtest,
    latest_run_summary,
    manifest_provenance,
    provenance,
    source_catalog,
)
from .schemas import ApiEnvelope, JobAccepted, SimulationRequest, UpdateRequest
from .security import InProcessRateLimiter, require_api_key
from .tasks import run_simulation_task, update_world_cup_task
from .update_pipeline import PredictionArchive

settings = get_settings()
SessionDependency = Annotated[Session, Depends(get_session)]


def create_app() -> FastAPI:
    application = FastAPI(
        title="Mundial 2030 Sirius Engine API",
        version="0.1.0",
        docs_url="/docs" if settings.environment != "production" else None,
        redoc_url=None,
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "Authorization"],
    )
    application.middleware("http")(InProcessRateLimiter(settings.post_rate_limit_per_minute))

    @application.middleware("http")
    async def security_headers(request: Request, call_next):  # type: ignore[no-untyped-def]
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-store" if request.method == "POST" else "no-cache"
        return response

    @application.exception_handler(ValueError)
    async def value_error_handler(_request: Request, exc: ValueError) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    @application.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "version": "0.1.0"}

    @application.get("/api/v1/scenario", response_model=ApiEnvelope)
    def scenario_view() -> ApiEnvelope:
        scenario = load_scenario(settings.scenario_path)
        return ApiEnvelope(
            data=asdict(scenario),
            provenance=[provenance("scenario", scenario.as_of)],
            assumptions=[
                "Formato 64/16×4 hipotético hasta confirmación oficial.",
                "Lionel Scaloni continúa con Argentina como supuesto de trabajo.",
            ],
            warnings=["La astrología es experimental y no está validada científicamente."],
        )

    @application.get("/api/v1/teams", response_model=ApiEnvelope)
    def teams_view() -> ApiEnvelope:
        scenario = load_scenario(settings.scenario_path)
        teams = load_teams(settings.teams_path)
        validate_scenario(scenario, teams)
        return ApiEnvelope(
            data=[team.to_dict() for team in teams],
            provenance=[provenance("scenario", scenario.as_of)],
            assumptions=["Campo y bombos proyectados; no son clasificados oficiales."],
        )

    @application.get("/api/v1/draw", response_model=ApiEnvelope)
    def draw_view(seed: int = Query(default=2030, ge=0, le=2**31 - 1)) -> ApiEnvelope:
        scenario = load_scenario(settings.scenario_path)
        teams = load_teams(settings.teams_path)
        groups = draw_groups(teams, scenario, random.Random(seed))
        return ApiEnvelope(
            data={name: [team.to_dict() for team in group] for name, group in groups.items()},
            provenance=[provenance("scenario", scenario.as_of)],
            assumptions=[scenario.bracket.description],
        )

    @application.get("/api/v1/sources", response_model=ApiEnvelope)
    def sources_view() -> ApiEnvelope:
        return ApiEnvelope(data=list(source_catalog().values()))

    @application.get("/api/v1/predictions/latest", response_model=ApiEnvelope)
    def latest_prediction() -> ApiEnvelope:
        manifest = PredictionArchive(settings.storage_path).load_latest()
        summary = None
        source_rows = []
        if manifest is not None:
            source_rows = manifest_provenance(manifest.get("sources", []))
            summary = manifest.get("simulations", {}).get("HYBRID")
            if summary is not None:
                comparison = {}
                for mode, simulation in manifest.get("simulations", {}).items():
                    argentina = next(
                        (row for row in simulation.get("ranking", []) if row.get("ID") == "ARG"),
                        None,
                    )
                    comparison[mode] = argentina.get("Campeón %") if argentina else None
                summary = {
                    **summary,
                    "snapshot_id": manifest["snapshot_id"],
                    "created_at": manifest["created_at"],
                    "model_version": manifest["model_version"],
                    "model_comparison": comparison,
                    "changes": manifest.get("relevant_changes", []),
                    "update_summary": manifest.get("summary"),
                }
        if summary is None:
            summary = latest_run_summary(settings.storage_path)
        return ApiEnvelope(
            data=summary,
            provenance=source_rows,
            warnings=[] if summary else ["Todavía no existe un PredictionSnapshot ejecutado."],
        )

    @application.get("/api/v1/backtesting/latest", response_model=ApiEnvelope)
    def backtesting_latest() -> ApiEnvelope:
        result = latest_backtest(settings.storage_path)
        source_rows = manifest_provenance(result.get("sources", [])) if result else []
        return ApiEnvelope(
            data=result,
            provenance=source_rows,
            warnings=[] if result else ["El backtest de aceptación todavía no fue ejecutado."],
        )

    @application.get("/api/v1/predictions/history", response_model=ApiEnvelope)
    def prediction_history(
        teams: str = Query(default="ARG,ESP,FRA,BRA", max_length=200),
    ) -> ApiEnvelope:
        team_ids = {value.strip().upper() for value in teams.split(",") if value.strip()}
        if not team_ids or len(team_ids) > 16:
            raise ValueError("request between 1 and 16 team IDs")
        archive = PredictionArchive(settings.storage_path)
        return ApiEnvelope(data=archive.probability_history(team_ids))

    @application.get("/api/v1/predictions/{snapshot_id}", response_model=ApiEnvelope)
    def prediction_snapshot(snapshot_id: str) -> ApiEnvelope:
        if len(snapshot_id) != 64 or any(
            character not in "0123456789abcdef" for character in snapshot_id
        ):
            raise ValueError("snapshot_id must be a 64-character lowercase SHA-256")
        manifest = PredictionArchive(settings.storage_path).load(snapshot_id)
        return ApiEnvelope(
            data=manifest,
            warnings=[] if manifest else ["PredictionSnapshot no encontrado."],
        )

    @application.post(
        "/api/v1/simulation-jobs",
        response_model=JobAccepted,
        status_code=202,
        dependencies=[Depends(require_api_key)],
    )
    def simulation_job(payload: SimulationRequest) -> JobAccepted:
        task = run_simulation_task.delay(
            payload.iterations,
            payload.seed,
            payload.mode.value,
            payload.final_hour,
            payload.workers,
        )
        return JobAccepted(
            job_id=str(task.id),
            status="queued",
            detail="Simulación encolada; el snapshot previo permanece inmutable.",
        )

    @application.post(
        "/api/v1/update-jobs",
        response_model=JobAccepted,
        status_code=202,
        dependencies=[Depends(require_api_key)],
    )
    def update_job(payload: UpdateRequest) -> JobAccepted:
        task = update_world_cup_task.delay(payload.model_dump(mode="json"))
        return JobAccepted(
            job_id=str(task.id),
            status="queued",
            detail="Actualización idempotente encolada.",
        )

    return application


app = create_app()


def run() -> None:
    import uvicorn

    uvicorn.run("services.api.main:app", host="127.0.0.1", port=8000, reload=False)
