from __future__ import annotations

import random
from dataclasses import asdict
from pathlib import Path
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy.orm import Session

from db.session import get_session
from engine.config import Scenario, load_scenario, load_teams, teams_for_scenario, validate_scenario
from engine.domain import Team
from engine.draw import draw_groups
from packages.common.config import ROOT, get_settings
from packages.sirius import ReviewConflictError, SiriusReviewQueue

from .catalog import (
    latest_backtest,
    latest_run_summary,
    latest_sirius_archive,
    manifest_provenance,
    provenance,
    source_catalog,
)
from .schemas import (
    ApiEnvelope,
    JobAccepted,
    SimulationRequest,
    SiriusReviewDecisionRequest,
    UpdateRequest,
)
from .security import InProcessRateLimiter, require_api_key
from .tasks import celery_app, run_simulation_task, update_world_cup_task
from .update_pipeline import PredictionArchive

settings = get_settings()
SessionDependency = Annotated[Session, Depends(get_session)]


def _scenario_inputs(format_size: int = 64) -> tuple[Scenario, list[Team]]:
    scenario = load_scenario(settings.scenario_path_for(format_size))
    teams = teams_for_scenario(load_teams(settings.teams_path), scenario)
    validate_scenario(scenario, teams)
    return scenario, teams


def _review_queue(session: Session) -> SiriusReviewQueue:
    return SiriusReviewQueue(
        session,
        rules_path=ROOT / "data" / "sirius_rules.yaml",
        teams_path=settings.teams_path,
    )


def _latest_sirius_snapshot_path() -> Path | None:
    event = PredictionArchive(settings.storage_path).latest_update_event()
    source = next(
        (
            item
            for item in (event or {}).get("sources", [])
            if item.get("source_id") == "sirius_blog" and item.get("snapshot_path")
        ),
        None,
    )
    if source is None:
        return None
    root = (settings.storage_path / "source_snapshots" / "sirius_blog").resolve()
    target = Path(str(source["snapshot_path"])).resolve()
    if root not in target.parents or not target.is_file():
        return None
    return target


def create_app() -> FastAPI:
    application = FastAPI(
        title="Mundial 2030 Sirius Engine API",
        version="0.2.1",
        docs_url="/docs" if settings.environment != "production" else None,
        redoc_url=None,
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "Authorization", "X-API-Key"],
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
        return {"status": "ok", "version": "0.2.1"}

    @application.get("/api/v1/scenario", response_model=ApiEnvelope)
    def scenario_view(format_size: int = Query(default=64)) -> ApiEnvelope:
        scenario, _ = _scenario_inputs(format_size)
        return ApiEnvelope(
            data=asdict(scenario),
            provenance=[provenance("scenario", scenario.as_of)],
            assumptions=[
                (
                    "Formato 64/16×4 hipotético hasta confirmación oficial."
                    if format_size == 64
                    else (
                        "Formato 48/12×4: dos primeros y ocho mejores terceros; "
                        "cuadro 2030 proyectado."
                    )
                ),
                "Lionel Scaloni continúa con Argentina como supuesto de trabajo.",
            ],
            warnings=["La astrología es experimental y no está validada científicamente."],
        )

    @application.get("/api/v1/teams", response_model=ApiEnvelope)
    def teams_view(format_size: int = Query(default=64)) -> ApiEnvelope:
        scenario, teams = _scenario_inputs(format_size)
        return ApiEnvelope(
            data=[team.to_dict() for team in teams],
            provenance=[provenance("scenario", scenario.as_of)],
            assumptions=["Campo y bombos proyectados; no son clasificados oficiales."],
        )

    @application.get("/api/v1/draw", response_model=ApiEnvelope)
    def draw_view(
        seed: int = Query(default=2030, ge=0, le=2**31 - 1),
        format_size: int = Query(default=64),
    ) -> ApiEnvelope:
        scenario, teams = _scenario_inputs(format_size)
        groups = draw_groups(teams, scenario, random.Random(seed))
        return ApiEnvelope(
            data={name: [team.to_dict() for team in group] for name, group in groups.items()},
            provenance=[provenance("scenario", scenario.as_of)],
            assumptions=[scenario.bracket.description],
        )

    @application.get("/api/v1/sources", response_model=ApiEnvelope)
    def sources_view() -> ApiEnvelope:
        return ApiEnvelope(data=list(source_catalog().values()))

    @application.get("/api/v1/updates/latest", response_model=ApiEnvelope)
    def latest_update() -> ApiEnvelope:
        event = PredictionArchive(settings.storage_path).latest_update_event()
        source_rows = manifest_provenance(event.get("sources", [])) if event else []
        return ApiEnvelope(
            data=event,
            provenance=source_rows,
            warnings=[] if event else ["Todavía no existe un evento de actualización."],
        )

    @application.get("/api/v1/predictions/latest", response_model=ApiEnvelope)
    def latest_prediction(format_size: int = Query(default=64)) -> ApiEnvelope:
        manifest = PredictionArchive(settings.storage_path).load_latest(format_size)
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
                    "scenario_id": manifest.get("scenario_id"),
                    "format_size": manifest.get("format_size", format_size),
                    "bracket_urls": [
                        {
                            "rank": rank,
                            "png": f"/predictions/{manifest['snapshot_id']}/brackets/{rank}.png",
                            "svg": f"/predictions/{manifest['snapshot_id']}/brackets/{rank}.svg",
                            "pdf": f"/predictions/{manifest['snapshot_id']}/brackets/{rank}.pdf",
                        }
                        for rank in range(1, 6)
                    ]
                    if manifest.get("bracket_manifest_path")
                    else [],
                    "sirius_assessments": manifest.get("sirius_assessments", {}),
                    "sirius_evidence_audit": manifest.get("sirius_evidence_audit", {}),
                }
        if summary is None and format_size == 64:
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

    @application.get("/api/v1/sirius/archive", response_model=ApiEnvelope)
    def sirius_archive() -> ApiEnvelope:
        result = latest_sirius_archive(settings.storage_path)
        return ApiEnvelope(
            data=result,
            provenance=([provenance("sirius_blog", str(result["consulted_at"]))] if result else []),
            warnings=(
                []
                if result
                else ["El archivo histórico de Sirius todavía no fue capturado por ACTUALIZAR."]
            ),
        )

    @application.get("/api/v1/sirius/review-candidates", response_model=ApiEnvelope)
    def sirius_review_candidates(
        session: SessionDependency,
        status: Literal["pending", "approved", "rejected", "all"] = Query(default="pending"),
        limit: int = Query(default=50, ge=1, le=200),
        offset: int = Query(default=0, ge=0),
    ) -> ApiEnvelope:
        result = _review_queue(session).list_candidates(
            status=status,
            limit=limit,
            offset=offset,
        )
        consulted = next(
            (item["consulted_at"] for item in result["items"] if item.get("consulted_at")),
            None,
        )
        return ApiEnvelope(
            data=result,
            provenance=[provenance("sirius_blog", consulted)] if consulted else [],
            warnings=(
                []
                if result["counts"]["total"]
                else ["La cola está vacía; sincronizá el último archivo Sirius primero."]
            ),
        )

    @application.post(
        "/api/v1/sirius/review-candidates/sync",
        response_model=ApiEnvelope,
        dependencies=[Depends(require_api_key)],
    )
    def sync_sirius_review_candidates(session: SessionDependency) -> ApiEnvelope:
        snapshot_path = _latest_sirius_snapshot_path()
        if snapshot_path is None:
            raise HTTPException(status_code=404, detail="Sirius archive snapshot not found")
        queue = _review_queue(session)
        result = queue.sync_archive(snapshot_path.read_bytes())
        session.commit()
        result["review_snapshot"] = queue.export_reviewed_snapshot(
            settings.storage_path / "sirius-review"
        )
        archive = latest_sirius_archive(settings.storage_path)
        return ApiEnvelope(
            data=result,
            provenance=(
                [provenance("sirius_blog", str(archive["consulted_at"]))] if archive else []
            ),
            assumptions=[
                "Las frases detectadas siguen pendientes; la sincronización no aprueba evidencia."
            ],
        )

    @application.post(
        "/api/v1/sirius/review-candidates/{candidate_id}/decisions",
        response_model=ApiEnvelope,
        dependencies=[Depends(require_api_key)],
    )
    def decide_sirius_review_candidate(
        candidate_id: str,
        payload: SiriusReviewDecisionRequest,
        session: SessionDependency,
    ) -> ApiEnvelope:
        if len(candidate_id) > 64:
            raise ValueError("invalid candidate_id")
        queue = _review_queue(session)
        try:
            decision = queue.decide(
                candidate_id,
                action=payload.action,
                reviewer=payload.reviewer,
                reason=payload.reason,
                expected_decision_id=payload.expected_decision_id,
                approval=(payload.approval.model_dump() if payload.approval is not None else None),
            )
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ReviewConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        session.commit()
        review_snapshot = queue.export_reviewed_snapshot(settings.storage_path / "sirius-review")
        return ApiEnvelope(
            data={
                "decision": queue.decision_view(decision),
                "review_snapshot": review_snapshot,
            },
            provenance=(
                [provenance("sirius_blog", str(decision.observation.get("consulted_at")))]
                if decision.observation
                else []
            ),
            warnings=["Sirius es un modelo experimental sin validez científica demostrada."],
        )

    @application.get("/api/v1/predictions/history", response_model=ApiEnvelope)
    def prediction_history(
        teams: str = Query(default="ARG,ESP,FRA,BRA", max_length=200),
        format_size: int = Query(default=64),
    ) -> ApiEnvelope:
        team_ids = {value.strip().upper() for value in teams.split(",") if value.strip()}
        if not team_ids or len(team_ids) > 16:
            raise ValueError("request between 1 and 16 team IDs")
        archive = PredictionArchive(settings.storage_path)
        return ApiEnvelope(data=archive.probability_history(team_ids, format_size=format_size))

    @application.get("/api/v1/jobs/{job_id}", response_model=ApiEnvelope)
    def job_status(job_id: str) -> ApiEnvelope:
        if not 1 <= len(job_id) <= 128 or any(
            character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_"
            for character in job_id
        ):
            raise ValueError("invalid job_id")
        result = celery_app.AsyncResult(job_id)
        payload = result.result if result.successful() else None
        return ApiEnvelope(
            data={"job_id": job_id, "status": result.state.lower(), "result": payload},
        )

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

    @application.get("/api/v1/predictions/{snapshot_id}/brackets/{rank}.{extension}")
    def bracket_file(snapshot_id: str, rank: int, extension: str) -> FileResponse:
        if len(snapshot_id) != 64 or any(
            character not in "0123456789abcdef" for character in snapshot_id
        ):
            raise ValueError("snapshot_id must be a 64-character lowercase SHA-256")
        if rank not in range(1, 6) or extension not in {"png", "svg", "pdf"}:
            raise ValueError("bracket rank/extension must be 1-5 and png, svg or pdf")
        root = (settings.storage_path / "predictions" / snapshot_id / "brackets").resolve()
        target = (root / f"bracket-{rank}.{extension}").resolve()
        if root not in target.parents or not target.is_file():
            raise HTTPException(status_code=404, detail="bracket export not found")
        media_types = {"png": "image/png", "svg": "image/svg+xml", "pdf": "application/pdf"}
        return FileResponse(
            Path(target),
            media_type=media_types[extension],
            filename=f"mundial-2030-{snapshot_id[:8]}-llave-{rank}.{extension}",
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
            payload.format_size,
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
