from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from packages.common.provenance import DataGrade
from packages.common.types import SiriusMode

from .engine import SiriusEngine
from .models import EvidenceLayer, FeatureObservation, Polarity, SiriusAssessment


def load_reviewed_observations(
    path: str | Path,
    team_ids: set[str],
) -> tuple[dict[str, list[FeatureObservation]], dict[str, Any]]:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if raw.get("schema_version") != "sirius-observations-v1":
        raise ValueError("unsupported Sirius observations schema")
    selected: dict[str, list[FeatureObservation]] = {team_id: [] for team_id in team_ids}
    pending = 0
    for record in raw.get("records", []):
        required = {
            "team_id",
            "feature_id",
            "layer",
            "polarity",
            "strength",
            "data_grade",
            "data_confidence",
            "explicit_public_rule",
            "description",
            "source_claim_ids",
            "source_url",
            "consulted_at",
            "manually_confirmed",
        }
        missing = sorted(required - set(record))
        if missing:
            raise ValueError(f"Sirius observation is missing provenance fields: {missing}")
        if not record["manually_confirmed"]:
            pending += 1
            continue
        team_id = str(record["team_id"])
        if team_id not in selected:
            continue
        if record.get("requires_known_time") and not record.get("time_known", False):
            raise ValueError(f"{team_id}:{record['feature_id']} requires a known real time")
        selected[team_id].append(
            FeatureObservation(
                feature_id=str(record["feature_id"]),
                layer=EvidenceLayer(str(record["layer"])),
                polarity=Polarity(str(record["polarity"])),
                strength=float(record["strength"]),
                data_grade=DataGrade(str(record["data_grade"])),
                data_confidence=float(record["data_confidence"]),
                hour_robustness=(
                    float(record["hour_robustness"])
                    if record.get("hour_robustness") is not None
                    else None
                ),
                explicit_public_rule=bool(record["explicit_public_rule"]),
                description=str(record["description"]),
                parameters={
                    **dict(record.get("parameters", {})),
                    "source_url": str(record["source_url"]),
                    "consulted_at": str(record["consulted_at"]),
                },
                source_claim_ids=tuple(str(value) for value in record["source_claim_ids"]),
            )
        )
    audit = {
        "schema_version": raw["schema_version"],
        "reviewed_observations": sum(len(items) for items in selected.values()),
        "pending_observations": pending,
        "teams_with_evidence": sum(bool(items) for items in selected.values()),
    }
    return selected, audit


def build_sirius_assessments(
    team_ids: set[str],
    observations_path: str | Path,
    mode: SiriusMode = SiriusMode.PURIST,
) -> tuple[dict[str, SiriusAssessment], dict[str, Any]]:
    observations, audit = load_reviewed_observations(observations_path, team_ids)
    engine = SiriusEngine()
    return (
        {
            team_id: engine.evaluate(team_id, items, mode=mode)
            for team_id, items in observations.items()
        },
        audit,
    )
