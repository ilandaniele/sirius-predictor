from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from db.base import Base
from db.models import ModelVersion, PredictionSnapshot, SimulationRun, Tournament
from db.predictions import persist_prediction_manifest
from engine.config import load_scenario

ROOT = Path(__file__).resolve().parents[2]


def _manifest() -> dict[str, object]:
    simulations = {}
    for marker, mode in zip("abc", ("FOOTBALL_ONLY", "SIRIUS_ONLY", "HYBRID"), strict=True):
        simulations[mode] = {
            "run_id": marker * 64,
            "mode": mode,
            "iterations": 100,
            "seed": 2030,
            "workers": 1,
            "ranking": [],
        }
    return {
        "snapshot_id": "d" * 64,
        "created_at": "2026-08-20T20:00:00+00:00",
        "git_commit": "e" * 40,
        "git_dirty": False,
        "working_tree_sha256": None,
        "format_size": 64,
        "sources": [],
        "assumptions": {"scientific_status": "experimental"},
        "seed": 2030,
        "simulations_count": 100,
        "weights": {},
        "simulations": simulations,
    }


def test_prediction_manifest_persists_one_immutable_row_per_mode(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite:///{(tmp_path / 'predictions.db').as_posix()}")
    Base.metadata.create_all(engine)
    scenario = load_scenario(ROOT / "data" / "scenario.yaml")
    manifest = _manifest()

    with Session(engine) as session:
        first = persist_prediction_manifest(session, manifest, scenario, "0.2.1")
        session.commit()
    with Session(engine) as session:
        second = persist_prediction_manifest(session, manifest, scenario, "0.2.1")
        session.commit()
        assert session.scalar(select(func.count()).select_from(PredictionSnapshot)) == 3
        assert session.scalar(select(func.count()).select_from(SimulationRun)) == 3
        assert session.scalar(select(func.count()).select_from(ModelVersion)) == 3
        assert session.scalar(select(func.count()).select_from(Tournament)) == 1

        snapshot = session.scalar(
            select(PredictionSnapshot).where(PredictionSnapshot.mode == "HYBRID")
        )
        assert snapshot is not None
        assert snapshot.snapshot_key == "d" * 64
        assert snapshot.format_size == 64
        snapshot.seed = 999
        with pytest.raises(ValueError, match="append-only"):
            session.commit()
        session.rollback()

    assert first == {
        "snapshots_created": 3,
        "snapshots_existing": 0,
        "runs_created": 3,
        "runs_existing": 0,
    }
    assert second == {
        "snapshots_created": 0,
        "snapshots_existing": 3,
        "runs_created": 0,
        "runs_existing": 3,
    }
    engine.dispose()


def test_prediction_replay_detects_relational_divergence(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite:///{(tmp_path / 'divergence.db').as_posix()}")
    Base.metadata.create_all(engine)
    scenario = load_scenario(ROOT / "data" / "scenario.yaml")
    manifest = _manifest()
    with Session(engine) as session:
        persist_prediction_manifest(session, manifest, scenario, "0.2.1")
        session.commit()

    changed = _manifest()
    changed["seed"] = 2031
    with Session(engine) as session, pytest.raises(ValueError, match="stored prediction differs"):
        persist_prediction_manifest(session, changed, scenario, "0.2.1")
    engine.dispose()
