from __future__ import annotations

import argparse
import base64
import json
import os
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import requests
import yaml

from engine.config import load_scenario, load_teams, teams_for_scenario, validate_scenario
from packages.astrology import ephemeris_identity
from packages.common.config import ROOT, get_settings
from packages.common.types import ModelMode
from packages.football.backtest_artifact import build_backtest_artifact
from packages.montecarlo import run_parallel
from packages.reports import export_five_brackets
from packages.sirius import sirius_application_status
from services.api.local_compute import ALLOWED_RESULT_PATHS, RESULT_SCHEMA, _sha256
from services.api.update_pipeline import (
    _git_state,
    _scenario_sha256,
    _simulation_summary,
    _sirius_observations_sha256,
    _sirius_reasons,
    _teams_sha256,
)


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Freeze inputs on Fly, simulate locally, and publish a verified bundle"
    )
    parser.add_argument("--format-size", type=int, choices=(48, 64), default=64)
    parser.add_argument("--iterations", type=int, default=100_000)
    parser.add_argument("--seed", type=int, default=2030)
    parser.add_argument("--final-hour", type=int, choices=(17, 18, 20, 21), default=18)
    parser.add_argument("--workers", type=int, default=None)
    parser.add_argument(
        "--server",
        default=get_settings().public_url,
    )
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--no-upload", action="store_true")
    parser.add_argument("--output", type=Path, default=ROOT / "storage" / "outbox")
    args = parser.parse_args()
    if args.iterations < 100:
        parser.error("--iterations must be at least 100")
    if args.workers is not None and not 1 <= args.workers <= 64:
        parser.error("--workers must be between 1 and 64")
    if args.workers is None:
        args.workers = min(64, max(1, (os.cpu_count() or 2) - 1))
    return args


def _api_url(server: str, endpoint: str) -> str:
    base = server.rstrip("/")
    if not base.endswith("/api/v1"):
        base += "/api/v1"
    return f"{base}/{endpoint.lstrip('/')}"


def _response_json(response: requests.Response) -> dict[str, Any]:
    try:
        payload = response.json()
    except requests.JSONDecodeError as exc:
        raise RuntimeError(f"Servidor {response.status_code}: respuesta no JSON") from exc
    if not response.ok:
        detail = payload.get("detail", payload)
        raise RuntimeError(f"Servidor {response.status_code}: {detail}")
    if not isinstance(payload, dict):
        raise RuntimeError("La respuesta del servidor no es un objeto JSON")
    return payload


def _require_swiss_ephemeris() -> None:
    try:
        import swisseph  # noqa: F401
    except ImportError as exc:
        raise RuntimeError(
            "Falta Swiss Ephemeris. Usá SIMULAR_Y_PUBLICAR.cmd para crear un entorno "
            "compatible con Python 3.12."
        ) from exc


def _validate_review_snapshot(payload: bytes, expected_hash: str) -> None:
    snapshot = yaml.safe_load(payload)
    records = snapshot.get("records", []) if isinstance(snapshot, dict) else []
    records_hash = _sha256(
        json.dumps(
            records,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    )
    if (
        not isinstance(snapshot, dict)
        or snapshot.get("schema_version") != "sirius-observations-v1"
        or snapshot.get("snapshot_id") != expected_hash
        or records_hash != expected_hash
    ):
        raise RuntimeError("El snapshot Sirius revisado descargado no supera integridad")


def _validate_frozen_input(job: dict[str, Any]) -> tuple[Path, Path, list[Any]]:
    scenario_path = get_settings().scenario_path_for(int(job["format_size"]))
    teams_path = get_settings().teams_path
    scenario = load_scenario(scenario_path)
    teams = teams_for_scenario(load_teams(teams_path), scenario)
    validate_scenario(scenario, teams)
    if scenario.scenario_id != job["scenario_id"]:
        raise RuntimeError("El escenario local no coincide con el input congelado en Fly")
    if _scenario_sha256(scenario) != job["scenario_sha256"]:
        raise RuntimeError("La configuración local del escenario no coincide con Fly")
    if _teams_sha256(teams) != job["teams_sha256"]:
        raise RuntimeError("Los equipos locales no coinciden con el input congelado en Fly")
    if _sirius_observations_sha256(scenario) != job["sirius_observations_sha256"]:
        raise RuntimeError("Las observaciones Sirius locales no coinciden con Fly")
    provider, version = ephemeris_identity()
    if {"provider": provider, "version": version} != job["ephemeris"]:
        raise RuntimeError("La versión local de Swiss Ephemeris no coincide con Fly")
    local_git = _git_state()
    remote_git = {
        "git_commit": job["git_commit"],
        "git_dirty": job["git_dirty"],
        "working_tree_sha256": job.get("working_tree_sha256"),
    }
    if local_git != remote_git:
        raise RuntimeError(
            "El código local no coincide con el desplegado en Fly. Publicá el código y reintentá."
        )
    return scenario_path, teams_path, teams


def _bundle(
    directory: Path,
    output_path: Path,
    input_id: str,
    snapshot_id: str,
) -> None:
    file_records = []
    for relative in sorted(ALLOWED_RESULT_PATHS):
        payload = (directory / relative).read_bytes()
        file_records.append({"path": relative, "sha256": _sha256(payload), "bytes": len(payload)})
    envelope = {
        "schema_version": RESULT_SCHEMA,
        "input_id": input_id,
        "snapshot_id": snapshot_id,
        "created_at": datetime.now(UTC).isoformat(),
        "files": file_records,
    }
    (directory / "bundle.json").write_text(
        json.dumps(envelope, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_suffix(".zip.tmp")
    with zipfile.ZipFile(
        temporary,
        mode="w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=6,
    ) as archive:
        archive.write(directory / "bundle.json", "bundle.json")
        for relative in sorted(ALLOWED_RESULT_PATHS):
            archive.write(directory / relative, relative)
    temporary.replace(output_path)


def _write_status(
    directory: Path,
    stage: str,
    message: str,
    **details: Any,
) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "status.json").write_text(
        json.dumps(
            {
                "stage": stage,
                "message": message,
                "updated_at": datetime.now(UTC).isoformat(),
                **details,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def main() -> None:
    args = _arguments()
    _require_swiss_ephemeris()
    settings = get_settings()
    api_key = args.api_key or (
        settings.api_key.get_secret_value() if settings.api_key is not None else None
    )
    if not api_key:
        raise RuntimeError("Falta SIRIUS_API_KEY en .env")
    headers = {"X-API-Key": api_key}
    print("1/8 · Fly prepara y congela fuentes e inputs livianos…", flush=True)
    prepared_response = requests.post(
        _api_url(args.server, "local-simulation-inputs"),
        headers={**headers, "Content-Type": "application/json"},
        json={
            "format_size": args.format_size,
            "iterations": args.iterations,
            "seed": args.seed,
            "final_hour": args.final_hour,
            "workers": args.workers,
        },
        timeout=(30, 900),
    )
    prepared = _response_json(prepared_response)["data"]
    if prepared["status"] == "already_published":
        print(f"Sin cálculo: el snapshot {prepared['snapshot_id']} ya está publicado.")
        return

    scenario_path, teams_path, teams = _validate_frozen_input(prepared)
    print(f"2/8 · Input {prepared['input_id'][:12]} validado contra el código local.", flush=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    work = (
        args.output.resolve()
        / "runs"
        / f"sirius-{args.format_size}-{prepared['snapshot_id'][:16]}-{timestamp}"
    )
    work.mkdir(parents=True, exist_ok=False)
    _write_status(work, "prepared", "Input congelado y validado")
    print(f"Carpeta permanente del cálculo: {work}", flush=True)
    try:
        reviewed_path: Path | None = None
        encoded_review = prepared.get("reviewed_observations_b64")
        if encoded_review is not None:
            reviewed_payload = base64.b64decode(encoded_review, validate=True)
            expected_review = str(prepared["review_snapshot_sha256"])
            _validate_review_snapshot(reviewed_payload, expected_review)
            reviewed_path = work / "reviewed-observations.yaml"
            reviewed_path.write_bytes(reviewed_payload)

        print(
            "3/8 · Calibrando contra Mundiales reales (2010-2026, walk-forward)…",
            flush=True,
        )
        _write_status(work, "backtesting", "Ejecutando backtesting y auditoría de leakage")
        backtest = build_backtest_artifact(ROOT / "state")
        (work / "backtest.json").write_text(
            json.dumps(backtest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        next_calibration = backtest["next_edition_calibration"]
        calibrated_host_bonus = float(next_calibration["host_bonus_elo"])
        print(
            f"Ventaja de local calibrada con datos reales: +{calibrated_host_bonus:.0f} Elo "
            f"(entrenado con {', '.join(str(e) for e in sorted(backtest['available_editions']))}) "
            "— no se aplica: Sirius mismo descarta la condición de local como factor "
            "(ver su análisis de Brasil vs Croacia, Mundial 2014). Se deja publicado sólo "
            "como referencia diagnóstica.",
            flush=True,
        )
        host_advantage_elo = 0.0

        print(
            f"4/8 · HYBRID primero · {args.iterations:,} simulaciones locales…",
            flush=True,
        )
        _write_status(work, "simulating_hybrid", "Ejecutando HYBRID")
        raw_results = {
            ModelMode.HYBRID: run_parallel(
                scenario_path,
                teams_path,
                iterations=args.iterations,
                seed=args.seed,
                mode=ModelMode.HYBRID,
                final_hour=args.final_hour,
                workers=args.workers,
                reviewed_observations_path=reviewed_path,
                host_advantage_elo=host_advantage_elo,
            )
        }
        hybrid_result = raw_results[ModelMode.HYBRID]
        application = sirius_application_status(
            hybrid_result.sirius_assessments,
            hybrid_result.sirius_evidence_audit,
        )
        print(f"Sirius: {application['label']}.", flush=True)

        print(
            "5/8 · Generando cinco imágenes de semifinales, final y campeón…",
            flush=True,
        )
        bracket_directory = work / "brackets"
        _write_status(
            work,
            "rendering_images",
            "Generando imágenes de cruces decisivos",
            sirius_application=application,
        )
        export_five_brackets(
            hybrid_result.top_brackets,
            teams,
            bracket_directory,
            sirius_reasons=_sirius_reasons(hybrid_result),
            sirius_application=application,
        )
        print(f"Imágenes listas y persistentes: {bracket_directory}", flush=True)

        for index, mode in enumerate(
            (ModelMode.FOOTBALL_ONLY, ModelMode.SIRIUS_ONLY),
            start=1,
        ):
            print(
                f"6/8 · Modelo de control {index}/2: {mode.value} · "
                f"{args.iterations:,} simulaciones locales…",
                flush=True,
            )
            _write_status(work, "simulating_controls", f"Ejecutando {mode.value}")
            raw_results[mode] = run_parallel(
                scenario_path,
                teams_path,
                iterations=args.iterations,
                seed=args.seed,
                mode=mode,
                final_hour=args.final_hour,
                workers=args.workers,
                reviewed_observations_path=reviewed_path,
                host_advantage_elo=host_advantage_elo,
            )

        simulations = {mode.value: _simulation_summary(raw_results[mode]) for mode in ModelMode}
        print("7/8 · Armando el bundle…", flush=True)
        results = {
            "schema_version": RESULT_SCHEMA,
            "input_id": prepared["input_id"],
            "snapshot_id": prepared["snapshot_id"],
            "model_version": prepared["model_version"],
            "ephemeris": prepared["ephemeris"],
            "completed_at": datetime.now(UTC).isoformat(),
            "simulations": simulations,
            "sirius_assessments": hybrid_result.sirius_assessments,
            "sirius_evidence_audit": hybrid_result.sirius_evidence_audit,
            "sirius_application": application,
        }
        (work / "results.json").write_text(
            json.dumps(results, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        bundle_path = args.output.resolve() / (
            f"sirius-{args.format_size}-{prepared['snapshot_id']}.zip"
        )
        _bundle(work, bundle_path, prepared["input_id"], prepared["snapshot_id"])
        print(f"Bundle verificable guardado: {bundle_path}", flush=True)
        if args.no_upload:
            _write_status(
                work,
                "complete_local",
                "Imágenes y bundle generados; subida omitida",
                bundle_path=str(bundle_path),
                brackets_path=str(bracket_directory),
                sirius_application=application,
            )
            print("8/8 · Listo. Subida omitida por --no-upload.")
            return

        print(
            "8/8 · Subiendo resultados, backtest e imágenes; Fly valida antes de publicar…",
            flush=True,
        )
        _write_status(work, "uploading", "Subiendo bundle verificado a Fly")
        with bundle_path.open("rb") as handle:
            uploaded = requests.post(
                _api_url(args.server, "local-simulation-results"),
                headers={**headers, "Content-Type": "application/zip"},
                data=handle,
                timeout=(30, 900),
            )
        published = _response_json(uploaded)["data"]
        print(
            f"Publicado: snapshot {published['snapshot_id']} · formato "
            f"{published['format_size']} · {published['status']}",
            flush=True,
        )
        _write_status(
            work,
            "published",
            "Resultados publicados en Fly",
            bundle_path=str(bundle_path),
            brackets_path=str(bracket_directory),
            sirius_application=application,
            publication=published,
        )
    except Exception as exc:
        _write_status(
            work,
            "failed",
            str(exc),
            retained_files=True,
        )
        print(f"El cálculo falló, pero los archivos parciales quedaron en: {work}", flush=True)
        raise


if __name__ == "__main__":
    main()
