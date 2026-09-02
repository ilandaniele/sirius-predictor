from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from engine.config import Scenario

from .models import (
    ModelVersion,
    PredictionSnapshot,
    SimulationRun,
    Tournament,
    TournamentFormat,
)

MODEL_NAME = "Mundial 2030 Sirius Engine"


def _build_version(manifest: dict[str, Any], semantic_version: str) -> str:
    code_identity = (
        manifest.get("working_tree_sha256")
        if manifest.get("git_dirty")
        else manifest.get("git_commit")
    )
    suffix = str(code_identity or "unavailable")[:12]
    return f"{semantic_version}+{suffix}"


def _tournament(session: Session, scenario: Scenario) -> Tournament:
    tournament = session.scalar(
        select(Tournament).where(
            Tournament.name == scenario.name,
            Tournament.edition == 2030,
        )
    )
    format_rules = json.loads(
        json.dumps(
            {
                "scenario_id": scenario.scenario_id,
                "pots": scenario.format.pots,
                "pot_size": scenario.format.pot_size,
                "best_third_placed": scenario.format.best_third_placed,
                "draw": asdict(scenario.draw),
                "bracket": asdict(scenario.bracket),
            },
            ensure_ascii=False,
        )
    )
    if tournament is not None:
        stored_format = session.get(TournamentFormat, tournament.format_id)
        if (
            stored_format is None
            or stored_format.team_count != scenario.format.teams
            or stored_format.group_count != scenario.format.groups
            or stored_format.group_size != scenario.format.group_size
            or stored_format.qualifiers_per_group != scenario.format.qualifiers_per_group
            or stored_format.rules != format_rules
            or tournament.status != scenario.status
            or tournament.assumptions != scenario.assumptions
        ):
            raise ValueError("stored tournament contract differs from immutable scenario")
        return tournament

    tournament_format = TournamentFormat(
        name=scenario.scenario_id,
        team_count=scenario.format.teams,
        group_count=scenario.format.groups,
        group_size=scenario.format.group_size,
        qualifiers_per_group=scenario.format.qualifiers_per_group,
        rules=format_rules,
    )
    session.add(tournament_format)
    session.flush()
    tournament = Tournament(
        name=scenario.name,
        edition=2030,
        format_id=tournament_format.id,
        status=scenario.status,
        assumptions=scenario.assumptions,
    )
    session.add(tournament)
    session.flush()
    return tournament


def _model_version(
    session: Session,
    manifest: dict[str, Any],
    scenario: Scenario,
    semantic_version: str,
    mode: str,
) -> ModelVersion:
    build_version = _build_version(manifest, semantic_version)
    existing = session.scalar(
        select(ModelVersion).where(
            ModelVersion.name == MODEL_NAME,
            ModelVersion.version == build_version,
            ModelVersion.mode == mode,
        )
    )
    feature_schema = {
        "mode": mode,
        "baseline_version": scenario.models.baseline_version,
        "sirius_version": scenario.models.sirius_version,
        "git_dirty": bool(manifest.get("git_dirty", False)),
        "working_tree_sha256": manifest.get("working_tree_sha256"),
        "ephemeris": manifest.get("ephemeris"),
    }
    weights = manifest.get("weights", {})
    raw_mode_weights = weights.get(mode, {}) if isinstance(weights, dict) else {}
    if not isinstance(raw_mode_weights, dict):
        raise ValueError(f"{mode}: model weights must be an object")
    mode_weights = dict(raw_mode_weights)
    if existing is not None:
        if (
            existing.feature_schema != feature_schema
            or existing.weights != mode_weights
            or existing.git_commit != manifest["git_commit"]
            or not existing.frozen
        ):
            raise ValueError("stored model version differs from immutable model build")
        return existing
    model = ModelVersion(
        name=MODEL_NAME,
        version=build_version,
        mode=mode,
        feature_schema=feature_schema,
        weights=mode_weights,
        git_commit=str(manifest["git_commit"]),
        frozen=True,
    )
    session.add(model)
    session.flush()
    return model


def persist_prediction_manifest(
    session: Session,
    manifest: dict[str, Any],
    scenario: Scenario,
    semantic_version: str,
) -> dict[str, int]:
    """Persist one immutable prediction/run row per model mode, idempotently."""

    snapshot_key = str(manifest["snapshot_id"])
    if len(snapshot_key) != 64:
        raise ValueError("prediction snapshot key must be a SHA-256")
    format_size = int(manifest["format_size"])
    if format_size != scenario.format.teams:
        raise ValueError("prediction format differs from scenario")
    created_at = datetime.fromisoformat(str(manifest["created_at"]))
    if created_at.tzinfo is None or created_at.utcoffset() is None:
        raise ValueError("prediction timestamp must include a UTC offset")
    simulations = manifest.get("simulations")
    if not isinstance(simulations, dict) or not simulations:
        raise ValueError("prediction manifest has no model simulations")

    tournament = _tournament(session, scenario)
    snapshots_created = 0
    snapshots_existing = 0
    runs_created = 0
    runs_existing = 0
    for mode, result in simulations.items():
        if not isinstance(mode, str) or not isinstance(result, dict):
            raise ValueError("prediction simulation payload is invalid")
        model = _model_version(
            session,
            manifest,
            scenario,
            semantic_version,
            mode,
        )
        manifest_weights = manifest.get("weights", {})
        mode_weights = (
            dict(manifest_weights.get(mode, {}))
            if isinstance(manifest_weights, dict)
            and isinstance(manifest_weights.get(mode, {}), dict)
            else {}
        )
        snapshot = session.scalar(
            select(PredictionSnapshot).where(
                PredictionSnapshot.snapshot_key == snapshot_key,
                PredictionSnapshot.mode == mode,
            )
        )
        if snapshot is None:
            snapshot = PredictionSnapshot(
                snapshot_key=snapshot_key,
                mode=mode,
                format_size=format_size,
                tournament_id=tournament.id,
                model_version_id=model.id,
                git_commit=str(manifest["git_commit"]),
                inputs_hash=snapshot_key,
                sources=list(manifest.get("sources", [])),
                assumptions=dict(manifest.get("assumptions", {})),
                seed=int(manifest["seed"]),
                simulations=int(manifest["simulations_count"]),
                weights=mode_weights,
                results=result,
                created_at=created_at,
            )
            session.add(snapshot)
            session.flush()
            snapshots_created += 1
        else:
            expected_snapshot = {
                "format_size": format_size,
                "tournament_id": tournament.id,
                "model_version_id": model.id,
                "git_commit": str(manifest["git_commit"]),
                "inputs_hash": snapshot_key,
                "sources": list(manifest.get("sources", [])),
                "assumptions": dict(manifest.get("assumptions", {})),
                "seed": int(manifest["seed"]),
                "simulations": int(manifest["simulations_count"]),
                "weights": mode_weights,
                "results": result,
            }
            if any(
                getattr(snapshot, field_name) != value
                for field_name, value in expected_snapshot.items()
            ):
                raise ValueError("stored prediction differs from immutable manifest")
            snapshots_existing += 1

        run_id = result.get("run_id")
        if (
            not isinstance(run_id, str)
            or not 16 <= len(run_id) <= 64
            or any(character not in "0123456789abcdef" for character in run_id)
        ):
            raise ValueError(f"{mode}: simulation run_id must be a lowercase hex digest")
        run = session.scalar(select(SimulationRun).where(SimulationRun.run_id == run_id))
        if run is None:
            session.add(
                SimulationRun(
                    run_id=run_id,
                    prediction_snapshot_id=snapshot.id,
                    mode=mode,
                    seed=int(result["seed"]),
                    iterations=int(result["iterations"]),
                    status="completed",
                    started_at=created_at,
                    finished_at=created_at,
                    result=result,
                    created_at=created_at,
                )
            )
            session.flush()
            runs_created += 1
        else:
            # run_id is scoped to the Monte Carlo computation itself (scenario, teams,
            # observations, seed, iterations, mode, model version) and deliberately excludes
            # snapshot-only metadata like source consulted_at. A re-sync that only refreshes
            # timestamps therefore reuses the same run_id under a new snapshot_id; that is not
            # a collision as long as the recorded computation is byte-identical.
            if (
                run.mode != mode
                or run.seed != int(result["seed"])
                or run.iterations != int(result["iterations"])
                or run.status != "completed"
                or run.result != result
            ):
                raise ValueError("stored simulation run differs from immutable manifest")
            runs_existing += 1
    return {
        "snapshots_created": snapshots_created,
        "snapshots_existing": snapshots_existing,
        "runs_created": runs_created,
        "runs_existing": runs_existing,
    }
