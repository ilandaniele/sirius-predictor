from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from celery import Celery  # type: ignore[import-untyped]

from packages.common.config import ROOT, get_settings
from packages.common.types import ModelMode
from packages.montecarlo import run_parallel

from .update_pipeline import UpdateCommand, UpdateOrchestrator

settings = get_settings()
celery_app = Celery("sirius", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_track_started=True,
    task_time_limit=60 * 60,
    worker_prefetch_multiplier=1,
)


def _atomic_json_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


@celery_app.task(name="sirius.run_simulation")
def run_simulation_task(
    iterations: int,
    seed: int,
    mode: str,
    final_hour: int,
    workers: int | None = None,
) -> dict[str, Any]:
    result = run_parallel(
        ROOT / "data" / "scenario.yaml",
        ROOT / "data" / "teams.csv",
        iterations=iterations,
        seed=seed,
        mode=ModelMode(mode),
        final_hour=final_hour,
        workers=workers,
    )
    summary = {
        "run_id": result.run_id,
        "mode": result.mode.value,
        "iterations": result.iterations,
        "seed": result.seed,
        "workers": result.workers,
        "ranking": result.ranking.to_dict(orient="records"),
        "argentina_stages": result.argentina_stages.to_dict(orient="records"),
        "argentina_rivals": {
            key: value.to_dict(orient="records") for key, value in result.argentina_rivals.items()
        },
        "argentina_groups": result.argentina_groups.to_dict(orient="records"),
        "final_pairs": result.final_pairs.to_dict(orient="records"),
        "sensitivity": result.sensitivity.to_dict(orient="records"),
        "top_brackets": [
            {key: value for key, value in bracket.items() if key != "representative"}
            for bracket in result.top_brackets
        ],
    }
    run_path = settings.storage_path / "runs" / result.run_id / "summary.json"
    _atomic_json_write(run_path, summary)
    _atomic_json_write(settings.storage_path / "runs" / "latest.json", summary)
    return {"run_id": result.run_id, "path": run_path.as_posix()}


@celery_app.task(name="sirius.update_world_cup")
def update_world_cup_task(payload: dict[str, Any]) -> dict[str, Any]:
    command = UpdateCommand(
        iterations=int(payload["iterations"]),
        seed=int(payload["seed"]),
        modes=tuple(ModelMode(value) for value in payload["modes"]),
    )
    result = UpdateOrchestrator().run(command)
    return {
        "status": "complete",
        "snapshot_id": result.snapshot_id,
        "idempotent_replay": result.idempotent_replay,
        "summary": result.summary,
        "manifest_path": result.manifest_path,
    }
