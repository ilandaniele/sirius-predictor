from __future__ import annotations

import hashlib
import io
import json
import zipfile
from pathlib import Path

import pytest
from PIL import Image
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from db.base import Base
from db.models import PredictionSnapshot, SimulationRun
from engine.config import load_scenario, load_teams, teams_for_scenario
from packages.common.config import Settings
from packages.common.types import ModelMode
from packages.football.backtest import BACKTEST_MODELS
from packages.football.backtest_artifact import BACKTEST_SCHEMA
from services.api.local_compute import (
    ALLOWED_RESULT_PATHS,
    INPUT_SCHEMA,
    RESULT_SCHEMA,
    LocalComputeConflict,
    LocalInputStore,
    import_local_result,
)
from services.api.update_pipeline import (
    PredictionArchive,
    UpdateCommand,
    _ephemeris_manifest,
    _git_state,
    _input_hash,
    _scenario_sha256,
    _sirius_observations_sha256,
    _teams_sha256,
)

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[2]


def _settings(tmp_path: Path) -> Settings:
    database_url = f"sqlite:///{(tmp_path / 'local-compute.db').as_posix()}"
    engine = create_engine(database_url)
    Base.metadata.create_all(engine)
    engine.dispose()
    return Settings(
        storage_path=tmp_path / "storage",
        database_url=database_url,
        scenario_path=ROOT / "data" / "scenario.yaml",
        scenario_48_path=ROOT / "data" / "scenario-48.yaml",
        teams_path=ROOT / "data" / "teams.csv",
        sources_path=ROOT / "data" / "sources.yaml",
    )


def _job(
    settings: Settings,
    *,
    source_quality: str = "B",
    effective_hash: str = "1" * 64,
    previous_snapshot_id: str | None = None,
    format_size: int = 64,
) -> dict[str, object]:
    scenario = load_scenario(settings.scenario_path_for(format_size))
    teams = teams_for_scenario(load_teams(settings.teams_path), scenario)
    git_state = _git_state()
    sources = [
        {
            "source_id": "scenario",
            "source_url": "https://example.com/scenario",
            "quality": source_quality,
            "consulted_at": "2026-08-20T20:00:00+00:00",
            "fetch_status": "success",
            "effective_sha256": effective_hash,
            "retained_previous": False,
            "model_input": True,
            "snapshot_path": "/data/storage/source_snapshots/scenario/1.bin",
            "error": None,
        }
    ]
    command = UpdateCommand(
        iterations=100,
        seed=2030,
        modes=tuple(ModelMode),
        final_hour=18,
        workers=1,
        format_size=format_size,
    )
    snapshot_id = _input_hash(command, scenario, sources, git_state, teams)
    prepared_at = "2026-08-20T20:00:00+00:00"
    update_event_path = "/data/storage/update-events/event.json"
    input_id = hashlib.sha256(
        json.dumps(
            {
                "snapshot_id": snapshot_id,
                "prepared_at": prepared_at,
                "update_event_path": update_event_path,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    return {
        "schema_version": INPUT_SCHEMA,
        "status": "ready",
        "input_id": input_id,
        "prepared_at": prepared_at,
        "snapshot_id": snapshot_id,
        "previous_snapshot_id": previous_snapshot_id,
        "model_version": settings.model_version,
        **git_state,
        "scenario_id": scenario.scenario_id,
        "format_size": format_size,
        "team_ids": [team.team_id for team in teams],
        "scenario_sha256": _scenario_sha256(scenario),
        "teams_sha256": _teams_sha256(teams),
        "sirius_observations_sha256": _sirius_observations_sha256(scenario),
        "ephemeris": _ephemeris_manifest(),
        "command": {
            "iterations": 100,
            "seed": 2030,
            "modes": [mode.value for mode in ModelMode],
            "final_hour": 18,
            "workers": 1,
            "format_size": format_size,
        },
        "sources": sources,
        "assumptions": {"scientific_status": "experimental"},
        "successful_sources": 1,
        "quality_pending_review": 0,
        "claim_persistence": {"observed": 0, "inserted": 0},
        "conflicts": 0,
        "base_relevant_changes": ["fuente modificada: scenario"],
        "affected_charts": [],
        "chart_recalculation": {},
        "review_snapshot_sha256": None,
        "reviewed_observations": 0,
        "reviewed_observations_path": None,
        "update_event_path": update_event_path,
    }


def _simulation(mode: ModelMode, teams: list[object], marker: str) -> dict[str, object]:
    ranking = []
    for index, team in enumerate(teams):
        ranking.append(
            {
                "ID": team.team_id,
                "Selección": team.team,
                "Campeón %": 100.0 if index == 0 else 0.0,
                "Final %": 100.0 if index < 2 else 0.0,
                "Semi %": 100.0 if index < 4 else 0.0,
                "R32 %": 50.0,
            }
        )
    return {
        "run_id": marker * 16,
        "mode": mode.value,
        "iterations": 100,
        "seed": 2030,
        "workers": 1,
        "ranking": ranking,
        "argentina_stages": [],
        "argentina_rivals": {},
        "argentina_groups": [],
        "final_pairs": [],
        "sensitivity": [
            {"Hora local": value}
            for value in (
                "16:45",
                "17:00",
                "17:15",
                "17:45",
                "18:00",
                "18:15",
                "19:45",
                "20:00",
                "20:15",
                "20:45",
                "21:00",
                "21:15",
            )
        ],
        "top_brackets": (
            [
                {
                    "signature": str(index),
                    "signature_version": "decisive-v1",
                    "scope": "SF_AND_FINAL",
                    "density_percent": 1.0,
                    "decisive_matches": [
                        {"round": "SF"},
                        {"round": "SF"},
                        {"round": "F"},
                    ],
                }
                for index in range(5)
            ]
            if mode == ModelMode.HYBRID
            else []
        ),
        "sirius_evidence_audit": {},
        "sirius_application": {
            "status": "neutral_no_reviewed_evidence",
            "label": "Sirius neutral: sin evidencia revisada",
            "effective": False,
            "reviewed_observations": 0,
            "pending_observations": 0,
            "teams_with_evidence": 0,
            "teams_with_nonzero_adjustment": 0,
        },
    }


def _png() -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (960, 540), "#071019").save(output, format="PNG")
    return output.getvalue()


def _write_bundle(path: Path, settings: Settings, job: dict[str, object]) -> str:
    scenario = load_scenario(settings.scenario_path_for(int(job["format_size"])))
    teams = teams_for_scenario(load_teams(settings.teams_path), scenario)
    simulations = {
        mode.value: _simulation(mode, teams, marker)
        for mode, marker in zip(ModelMode, "bcd", strict=True)
    }
    payloads: dict[str, bytes] = {
        "results.json": json.dumps(
            {
                "schema_version": RESULT_SCHEMA,
                "input_id": job["input_id"],
                "snapshot_id": job["snapshot_id"],
                "model_version": job["model_version"],
                "ephemeris": job["ephemeris"],
                "completed_at": "2026-08-20T21:00:00+00:00",
                "simulations": simulations,
                "sirius_assessments": {},
                "sirius_evidence_audit": {},
                "sirius_application": {
                    "status": "neutral_no_reviewed_evidence",
                    "label": "Sirius neutral: sin evidencia revisada",
                    "effective": False,
                    "reviewed_observations": 0,
                    "pending_observations": 0,
                    "teams_with_evidence": 0,
                    "teams_with_nonzero_adjustment": 0,
                },
            },
            ensure_ascii=False,
        ).encode(),
        "backtest.json": json.dumps(
            {
                "schema_version": BACKTEST_SCHEMA,
                "created_at": "2026-08-20T20:30:00+00:00",
                "sources": [
                    {
                        "source_id": "openfootball",
                        "source_url": "https://example.com/worldcup.txt",
                        "consulted_at": "2026-08-20T20:30:00+00:00",
                        "quality": "B",
                        "fetch_status": "snapshot",
                    }
                ],
                "requested_editions": [2022],
                "available_editions": [2022],
                "missing_editions": [],
                "matches": 1,
                "edition_shapes": {},
                "time_quality": {"exact": 1},
                "metrics": [{"model": model} for model in BACKTEST_MODELS],
                "calibration": [],
                "champion_ranking": [],
                "round_accuracy": [],
                "ablations": [],
                "leakage_audit": [
                    {
                        "same_match_used": False,
                        "future_edition_used_for_calibration": False,
                    }
                ],
                "calibration_manifest": [],
            }
        ).encode(),
    }
    png = _png()
    bracket_manifest = []
    for rank in range(1, 6):
        files = {}
        for extension, payload in {
            "png": png,
            "svg": b'<svg xmlns="http://www.w3.org/2000/svg" width="960" height="540"></svg>',
            "pdf": b"%PDF-1.4\n%%EOF\n",
        }.items():
            name = f"brackets/bracket-{rank}.{extension}"
            payloads[name] = payload
            files[extension] = {
                "path": f"C:/local/{name}",
                "sha256": hashlib.sha256(payload).hexdigest(),
                "bytes": len(payload),
            }
        bracket_manifest.append(
            {
                "rank": rank,
                "scope": "SF_AND_FINAL",
                "signature_version": "decisive-v1",
                "signature": str(rank - 1),
                "champion_id": teams[0].team_id,
                "runner_up_id": teams[1].team_id,
                "density_percent": 1.0,
                "decisive_matches": [
                    {"round": "SF"},
                    {"round": "SF"},
                    {"round": "F"},
                ],
                "sirius_application": {
                    "status": "neutral_no_reviewed_evidence",
                    "label": "Sirius neutral: sin evidencia revisada",
                    "effective": False,
                    "reviewed_observations": 0,
                    "pending_observations": 0,
                    "teams_with_evidence": 0,
                    "teams_with_nonzero_adjustment": 0,
                },
                "reasons": [],
                "canvas": {"width": 960, "height": 540},
                "files": files,
            }
        )
    payloads["brackets/manifest.json"] = json.dumps(bracket_manifest).encode()
    assert set(payloads) == ALLOWED_RESULT_PATHS
    envelope = {
        "schema_version": RESULT_SCHEMA,
        "input_id": job["input_id"],
        "snapshot_id": job["snapshot_id"],
        "files": [
            {
                "path": name,
                "sha256": hashlib.sha256(payload).hexdigest(),
                "bytes": len(payload),
            }
            for name, payload in sorted(payloads.items())
        ],
    }
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("bundle.json", json.dumps(envelope))
        for name, payload in payloads.items():
            archive.writestr(name, payload)
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.mark.parametrize("format_size", [48, 64])
def test_local_result_import_is_verified_append_only_and_idempotent(
    tmp_path: Path,
    format_size: int,
) -> None:
    settings = _settings(tmp_path)
    job = _job(settings, format_size=format_size)
    LocalInputStore(settings.storage_path).append(job)
    bundle = tmp_path / "result.zip"
    digest = _write_bundle(bundle, settings, job)

    first = import_local_result(settings, bundle, digest)
    second = import_local_result(settings, bundle, digest)

    assert first["status"] == "published"
    assert second["status"] == "already_published"
    manifest = PredictionArchive(settings.storage_path).load_latest(format_size)
    assert manifest is not None
    assert manifest["snapshot_id"] == job["snapshot_id"]
    assert manifest["execution"] == {
        "compute_location": "local",
        "input_id": job["input_id"],
        "bundle_sha256": digest,
    }
    assert Path(manifest["bracket_manifest_path"]).is_file()
    backtest = json.loads((settings.storage_path / "backtests" / "latest.json").read_text())
    assert backtest["publication"]["snapshot_id"] == job["snapshot_id"]
    with Session(create_engine(settings.database_url)) as session:
        assert session.scalar(select(func.count()).select_from(PredictionSnapshot)) == 3
        assert session.scalar(select(func.count()).select_from(SimulationRun)) == 3


def test_local_result_rejects_a_tampered_file(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    job = _job(settings)
    LocalInputStore(settings.storage_path).append(job)
    bundle = tmp_path / "tampered.zip"
    _write_bundle(bundle, settings, job)
    with zipfile.ZipFile(bundle) as archive:
        original = {name: archive.read(name) for name in archive.namelist()}
    replacement = tmp_path / "tampered-replacement.zip"
    with zipfile.ZipFile(replacement, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, payload in original.items():
            archive.writestr(name, b"{}" if name == "results.json" else payload)
    replacement.replace(bundle)
    with pytest.raises(ValueError, match="checksum failed"):
        import_local_result(settings, bundle, hashlib.sha256(bundle.read_bytes()).hexdigest())


def test_local_result_rejects_automatic_grade_a_to_c_downgrade(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    previous_job = _job(settings, source_quality="A")
    LocalInputStore(settings.storage_path).append(previous_job)
    previous_bundle = tmp_path / "previous.zip"
    previous_digest = _write_bundle(previous_bundle, settings, previous_job)
    import_local_result(settings, previous_bundle, previous_digest)

    job = _job(
        settings,
        source_quality="C",
        effective_hash="2" * 64,
        previous_snapshot_id=str(previous_job["snapshot_id"]),
    )
    LocalInputStore(settings.storage_path).append(job)
    bundle = tmp_path / "downgrade.zip"
    digest = _write_bundle(bundle, settings, job)

    with pytest.raises(LocalComputeConflict, match="cannot automatically replace A with C"):
        import_local_result(settings, bundle, digest)
