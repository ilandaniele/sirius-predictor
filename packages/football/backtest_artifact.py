from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd  # type: ignore[import-untyped]

from engine.backtest import EDITION_FOLDERS, load_historical_matches
from engine.updates import StateStore
from packages.football.backtest import BACKTEST_MODELS, run_full_backtest

BACKTEST_SCHEMA = "backtest-manifest-v2"


def _records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    return json.loads(frame.to_json(orient="records", date_format="iso"))


def build_backtest_artifact(state_path: Path) -> dict[str, Any]:
    """Run temporal validation locally and return a traceable publication artifact."""

    historical_matches = load_historical_matches(EDITION_FOLDERS, StateStore(state_path))
    matches_by_edition: dict[int, list[Any]] = defaultdict(list)
    for match in historical_matches:
        matches_by_edition[match.edition].append(match)
    historical_editions = sorted(matches_by_edition)
    historical_shapes = {
        str(edition): {
            "matches": len(edition_matches),
            "teams": len({team for match in edition_matches for team in (match.home, match.away)}),
            "stages": dict(Counter(match.stage for match in edition_matches)),
            "champion": next(
                (match.winner for match in edition_matches if match.stage == "F"),
                None,
            ),
        }
        for edition, edition_matches in matches_by_edition.items()
    }
    backtest = run_full_backtest(historical_matches)
    consulted_at = datetime.now(UTC).isoformat()
    artifact = {
        "schema_version": BACKTEST_SCHEMA,
        "created_at": consulted_at,
        "sources": [
            {
                "source_id": "openfootball",
                "source_url": url,
                "consulted_at": consulted_at,
                "quality": "B",
                "fetch_status": "snapshot",
            }
            for url in sorted({match.source_url for match in historical_matches})
        ],
        "requested_editions": sorted(EDITION_FOLDERS),
        "available_editions": historical_editions,
        "missing_editions": sorted(set(EDITION_FOLDERS) - set(historical_editions)),
        "matches": len(historical_matches),
        "edition_shapes": historical_shapes,
        "time_quality": {
            quality: sum(match.time_quality == quality for match in historical_matches)
            for quality in sorted({match.time_quality for match in historical_matches})
        },
        "metrics": _records(backtest.metrics),
        "calibration": _records(backtest.calibration),
        "champion_ranking": _records(backtest.champion_ranking),
        "round_accuracy": _records(backtest.round_accuracy),
        "ablations": _records(backtest.ablations),
        "leakage_audit": _records(backtest.leakage_audit),
        "calibration_manifest": _records(backtest.calibration_manifest),
    }
    validate_backtest_artifact(artifact)
    return artifact


def validate_backtest_artifact(artifact: dict[str, Any]) -> None:
    if artifact.get("schema_version") != BACKTEST_SCHEMA:
        raise ValueError("unsupported backtest artifact schema")
    timestamp = datetime.fromisoformat(str(artifact.get("created_at")))
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ValueError("backtest created_at must include a UTC offset")
    sources = artifact.get("sources")
    if not isinstance(sources, list) or not sources:
        raise ValueError("backtest requires traceable sources")
    for source in sources:
        if (
            not isinstance(source, dict)
            or not source.get("source_id")
            or not source.get("source_url")
            or source.get("quality") not in {"A", "B", "C", "D", "X"}
        ):
            raise ValueError("backtest source provenance is incomplete")
        consulted_at = datetime.fromisoformat(str(source.get("consulted_at")))
        if consulted_at.tzinfo is None or consulted_at.utcoffset() is None:
            raise ValueError("backtest source consulted_at must include a UTC offset")
    metrics = artifact.get("metrics")
    if not isinstance(metrics, list) or {row.get("model") for row in metrics} != set(
        BACKTEST_MODELS
    ):
        raise ValueError("backtest metrics must keep all model variants separate")
    leakage = artifact.get("leakage_audit")
    if not isinstance(leakage, list) or not leakage:
        raise ValueError("backtest leakage audit is missing")
    if any(
        row.get("same_match_used") or row.get("future_edition_used_for_calibration")
        for row in leakage
    ):
        raise ValueError("backtest temporal leakage detected")
    if int(artifact.get("matches", 0)) <= 0:
        raise ValueError("backtest must include historical matches")
