from __future__ import annotations

import hashlib
import random
import re
import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy.orm import Session

from collectors.argumental_archive import parse_archive_index as argumental_parse_archive_index
from collectors.sirius_archive import parse_archive_index as sirius_parse_archive_index
from db.session import get_session
from engine.argumental import all_cycle_fortunes
from engine.config import Scenario, load_scenario, load_teams, teams_for_scenario, validate_scenario
from engine.domain import Team
from engine.draw import draw_groups
from packages.common.config import ROOT, get_settings
from packages.common.types import ModelMode
from packages.sirius import ReviewConflictError, SiriusReviewQueue, build_sirius_assessments

from .catalog import (
    latest_argumental_archive,
    latest_backtest,
    latest_run_summary,
    latest_sirius_archive,
    manifest_provenance,
    provenance,
    source_catalog,
    track_record_audit,
)
from .local_compute import LocalComputeConflict, import_local_result, prepare_local_simulation
from .schemas import (
    ApiEnvelope,
    JobAccepted,
    LocalSimulationInputRequest,
    SimulationRequest,
    SiriusReviewDecisionRequest,
    UpdateRequest,
)
from .security import InProcessRateLimiter, require_api_key, require_remote_compute_enabled
from .tasks import celery_app, run_simulation_task, update_world_cup_task
from .update_pipeline import PredictionArchive, UpdateCommand, _reviewed_snapshot

settings = get_settings()
SessionDependency = Annotated[Session, Depends(get_session)]


def _scenario_inputs(format_size: int = 64) -> tuple[Scenario, list[Team]]:
    scenario = load_scenario(settings.scenario_path_for(format_size))
    teams = teams_for_scenario(load_teams(settings.teams_path), scenario)
    validate_scenario(scenario, teams)
    return scenario, teams


_ASTRO_SOURCES: dict[str, dict[str, str]] = {
    "sirius": {
        "source_id": "sirius_blog",
        "rules_path": "sirius_rules.yaml",
        "review_folder": "sirius-review",
        "parser": "sirius",
    },
    "argumental": {
        "source_id": "argumental_blog",
        "rules_path": "argumental_rules.yaml",
        "review_folder": "argumental-review",
        "parser": "argumental",
    },
}


def _review_queue(
    session: Session, source: Literal["sirius", "argumental"] = "sirius"
) -> SiriusReviewQueue:
    config = _ASTRO_SOURCES[source]
    return SiriusReviewQueue(
        session,
        rules_path=ROOT / "data" / config["rules_path"],
        teams_path=settings.teams_path,
        source_id=config["source_id"],
        parse_archive_index=(
            argumental_parse_archive_index if source == "argumental" else sirius_parse_archive_index
        ),
    )


def _latest_archive_snapshot_path(
    source: Literal["sirius", "argumental"] = "sirius",
) -> Path | None:
    config = _ASTRO_SOURCES[source]
    source_id = config["source_id"]
    event = PredictionArchive(settings.storage_path).latest_update_event()
    item = next(
        (
            entry
            for entry in (event or {}).get("sources", [])
            if entry.get("source_id") == source_id and entry.get("snapshot_path")
        ),
        None,
    )
    if item is None:
        return None
    root = (settings.storage_path / "source_snapshots" / source_id).resolve()
    target = Path(str(item["snapshot_path"])).resolve()
    if root not in target.parents or not target.is_file():
        return None
    return target


_EMBEDDABLE_BRACKET_SVG_RE = re.compile(r"^/api/v1/predictions/[0-9a-f]{64}/brackets/[1-5]\.svg$")


def create_app() -> FastAPI:
    application = FastAPI(
        title="Mundial 2030 Sirius Engine API",
        version=settings.model_version,
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
        response.headers["X-Frame-Options"] = (
            "SAMEORIGIN" if _EMBEDDABLE_BRACKET_SVG_RE.match(request.url.path) else "DENY"
        )
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-store" if request.method == "POST" else "no-cache"
        return response

    @application.exception_handler(ValueError)
    async def value_error_handler(_request: Request, exc: ValueError) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    @application.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "version": settings.model_version}

    @application.get("/api/v1/scenario", response_model=ApiEnvelope)
    def scenario_view(format_size: int = Query(default=64)) -> ApiEnvelope:
        scenario, _ = _scenario_inputs(format_size)
        return ApiEnvelope(
            data=asdict(scenario),
            provenance=[
                provenance("scenario", scenario.as_of),
                provenance("messi_international_retirement_2026", scenario.as_of),
            ],
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
                (
                    "Cristian 'Cuti' Romero se usa como capitán proyectado de Argentina; "
                    "no es una designación oficial confirmada."
                ),
            ],
            warnings=["La astrología es experimental y no está validada científicamente."],
        )

    @application.get("/api/v1/teams", response_model=ApiEnvelope)
    def teams_view(format_size: int = Query(default=64)) -> ApiEnvelope:
        scenario, teams = _scenario_inputs(format_size)
        return ApiEnvelope(
            data=[team.to_dict() for team in teams],
            provenance=[
                provenance("scenario", scenario.as_of),
                provenance("messi_international_retirement_2026", scenario.as_of),
            ],
            assumptions=[
                "Campo y bombos proyectados; no son clasificados oficiales.",
                "Cristian Romero es una elección de escenario X, no una capitanía oficial.",
            ],
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

    @application.get("/api/v1/audit/track-record", response_model=ApiEnvelope)
    def track_record_view() -> ApiEnvelope:
        audit = track_record_audit()
        return ApiEnvelope(
            data=audit,
            provenance=[
                provenance("sirius_blog", str(audit["consulted_at"])),
                provenance("argumental_blog", str(audit["consulted_at"])),
            ],
            warnings=[
                "Auditoría independiente de récords autoinformados; no afecta ningún cálculo "
                "del motor ni del Monte Carlo."
            ],
        )

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
            summary = manifest.get("simulations", {}).get("SIRIUS_ONLY")
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
                    "sirius_application": manifest.get("sirius_application", {}),
                    "chart_recalculation": manifest.get("chart_recalculation", {}),
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
        snapshot_path = _latest_archive_snapshot_path("sirius")
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

    @application.get("/api/v1/argumental/archive", response_model=ApiEnvelope)
    def argumental_archive() -> ApiEnvelope:
        result = latest_argumental_archive(settings.storage_path)
        return ApiEnvelope(
            data=result,
            provenance=(
                [provenance("argumental_blog", str(result["consulted_at"]))] if result else []
            ),
            warnings=(
                []
                if result
                else [
                    "El archivo de Astrología Argumental todavía no fue capturado por ACTUALIZAR."
                ]
            ),
        )

    @application.get("/api/v1/argumental/cycle-fortune", response_model=ApiEnvelope)
    def argumental_cycle_fortune(format_size: int = Query(default=64)) -> ApiEnvelope:
        scenario, teams = _scenario_inputs(format_size)
        year = int(scenario.final.local_date[:4])
        fortunes = all_cycle_fortunes([team.team_id for team in teams], year)
        unavailable = any(item.status == "ephemeris_unavailable" for item in fortunes.values())
        return ApiEnvelope(
            data={team_id: asdict(item) for team_id, item in fortunes.items()},
            provenance=[provenance("argumental_blog", scenario.as_of)],
            warnings=(
                [
                    "Cálculo propio aplicando la técnica pública de Astrología Argumental "
                    "(revolución solar del ciclo del DT); no es un pronóstico suyo. "
                    "Nunca influye en el Monte Carlo.",
                    *(
                        ["Swiss Ephemeris no disponible en este entorno: valores neutros."]
                        if unavailable
                        else []
                    ),
                ]
            ),
        )

    @application.get("/api/v1/argumental/review-candidates", response_model=ApiEnvelope)
    def argumental_review_candidates(
        session: SessionDependency,
        status: Literal["pending", "approved", "rejected", "all"] = Query(default="pending"),
        limit: int = Query(default=50, ge=1, le=200),
        offset: int = Query(default=0, ge=0),
    ) -> ApiEnvelope:
        result = _review_queue(session, "argumental").list_candidates(
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
            provenance=[provenance("argumental_blog", consulted)] if consulted else [],
            warnings=(
                []
                if result["counts"]["total"]
                else ["La cola está vacía; sincronizá el archivo de Argumental primero."]
            ),
        )

    @application.post(
        "/api/v1/argumental/review-candidates/sync",
        response_model=ApiEnvelope,
        dependencies=[Depends(require_api_key)],
    )
    def sync_argumental_review_candidates(session: SessionDependency) -> ApiEnvelope:
        snapshot_path = _latest_archive_snapshot_path("argumental")
        if snapshot_path is None:
            raise HTTPException(status_code=404, detail="Argumental archive snapshot not found")
        queue = _review_queue(session, "argumental")
        result = queue.sync_archive(snapshot_path.read_bytes())
        session.commit()
        result["review_snapshot"] = queue.export_reviewed_snapshot(
            settings.storage_path / "argumental-review"
        )
        archive = latest_argumental_archive(settings.storage_path)
        return ApiEnvelope(
            data=result,
            provenance=(
                [provenance("argumental_blog", str(archive["consulted_at"]))] if archive else []
            ),
            assumptions=[
                "Las frases detectadas siguen pendientes; la sincronización no aprueba evidencia."
            ],
        )

    @application.post(
        "/api/v1/argumental/review-candidates/{candidate_id}/decisions",
        response_model=ApiEnvelope,
        dependencies=[Depends(require_api_key)],
    )
    def decide_argumental_review_candidate(
        candidate_id: str,
        payload: SiriusReviewDecisionRequest,
        session: SessionDependency,
    ) -> ApiEnvelope:
        if len(candidate_id) > 64:
            raise ValueError("invalid candidate_id")
        queue = _review_queue(session, "argumental")
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
        review_snapshot = queue.export_reviewed_snapshot(
            settings.storage_path / "argumental-review"
        )
        return ApiEnvelope(
            data={
                "decision": queue.decision_view(decision),
                "review_snapshot": review_snapshot,
            },
            provenance=(
                [provenance("argumental_blog", str(decision.observation.get("consulted_at")))]
                if decision.observation
                else []
            ),
            warnings=["Astrología Argumental es una fuente experimental sin validez científica."],
        )

    @application.get("/api/v1/astrology/combined-assessment", response_model=ApiEnvelope)
    def combined_astrology_assessment(format_size: int = Query(default=64)) -> ApiEnvelope:
        _, teams = _scenario_inputs(format_size)
        team_ids = {team.team_id for team in teams}
        base_path = ROOT / "data" / "sirius_observations.yaml"
        _, sirius_reviewed_path = _reviewed_snapshot(settings, "sirius-review")
        _, argumental_reviewed_path = _reviewed_snapshot(settings, "argumental-review")
        additional = [
            path for path in (sirius_reviewed_path, argumental_reviewed_path) if path is not None
        ]
        sirius_only, sirius_audit = build_sirius_assessments(
            team_ids,
            base_path,
            additional_observations_path=sirius_reviewed_path,
        )
        argumental_only, argumental_audit = build_sirius_assessments(
            team_ids,
            base_path,
            additional_observations_path=argumental_reviewed_path,
        )
        combined, combined_audit = build_sirius_assessments(
            team_ids,
            base_path,
            additional_observations_path=additional,
        )
        return ApiEnvelope(
            data={
                "sirius": {team_id: item.to_dict() for team_id, item in sirius_only.items()},
                "argumental": {
                    team_id: item.to_dict() for team_id, item in argumental_only.items()
                },
                "combined": {team_id: item.to_dict() for team_id, item in combined.items()},
                "sirius_evidence_audit": sirius_audit,
                "argumental_evidence_audit": argumental_audit,
                "combined_evidence_audit": combined_audit,
            },
            provenance=[],
            warnings=[
                "Cálculo descriptivo en vivo (no ligado a una simulación puntual); no influye en "
                "el Monte Carlo, que sigue separando FOOTBALL_ONLY, SIRIUS_ONLY e HYBRID.",
                "Astrología Argumental (método Frawley, astrología electiva y mundana) es una "
                "segunda fuente pública experimental sin validez científica demostrada.",
            ],
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
            content_disposition_type="inline",
        )

    @application.post(
        "/api/v1/local-simulation-inputs",
        response_model=ApiEnvelope,
        dependencies=[Depends(require_api_key)],
    )
    def local_simulation_input(payload: LocalSimulationInputRequest) -> ApiEnvelope:
        result = prepare_local_simulation(
            settings,
            UpdateCommand(
                iterations=payload.iterations,
                seed=payload.seed,
                modes=tuple(ModelMode),
                final_hour=payload.final_hour,
                workers=payload.workers,
                format_size=payload.format_size,
            ),
        )
        return ApiEnvelope(
            data=result,
            assumptions=[
                "El servidor congela inputs; Monte Carlo y llaves se calculan localmente."
            ],
            warnings=["La astrología se mantiene como modelo experimental separado."],
        )

    @application.post(
        "/api/v1/local-simulation-results",
        response_model=ApiEnvelope,
        dependencies=[Depends(require_api_key)],
    )
    async def local_simulation_result(request: Request) -> ApiEnvelope:
        if request.headers.get("content-type", "").split(";", 1)[0] != "application/zip":
            raise HTTPException(status_code=415, detail="Content-Type must be application/zip")
        incoming = settings.storage_path / "local-compute" / "incoming"
        incoming.mkdir(parents=True, exist_ok=True)
        temporary_path: Path | None = None
        digest = hashlib.sha256()
        total = 0
        try:
            with tempfile.NamedTemporaryFile(
                prefix="result-",
                suffix=".zip",
                dir=incoming,
                delete=False,
            ) as handle:
                temporary_path = Path(handle.name)
                async for chunk in request.stream():
                    total += len(chunk)
                    if total > settings.local_result_max_bytes:
                        raise HTTPException(status_code=413, detail="result bundle is too large")
                    digest.update(chunk)
                    handle.write(chunk)
            try:
                result = await run_in_threadpool(
                    import_local_result, settings, temporary_path, digest.hexdigest()
                )
            except FileNotFoundError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            except LocalComputeConflict as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
            return ApiEnvelope(
                data=result,
                assumptions=["Los resultados se calcularon localmente sobre inputs congelados."],
            )
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

    @application.post(
        "/api/v1/simulation-jobs",
        response_model=JobAccepted,
        status_code=202,
        dependencies=[Depends(require_api_key), Depends(require_remote_compute_enabled)],
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
        dependencies=[Depends(require_api_key), Depends(require_remote_compute_enabled)],
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
