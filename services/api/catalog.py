from __future__ import annotations

import json
from collections import Counter
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from packages.common.config import ROOT

from .schemas import ProvenanceView
from .update_pipeline import PredictionArchive


@lru_cache(maxsize=1)
def source_catalog() -> dict[str, dict[str, Any]]:
    path = ROOT / "data" / "sources.yaml"
    records = yaml.safe_load(path.read_text(encoding="utf-8"))
    return {str(record["id"]): record for record in records}


def provenance(source_id: str, consulted_at: str) -> ProvenanceView:
    source = source_catalog()[source_id]
    url = source.get("url")
    return ProvenanceView(
        source_id=source_id,
        name=str(source["name"]),
        url=str(url) if url is not None else None,
        consulted_at=consulted_at,
        quality=str(source["grade"]),
        official=source.get("grade") == "A",
        status="enabled" if source.get("enabled") else "disabled",
    )


def latest_run_summary(storage_path: Path) -> dict[str, Any] | None:
    latest = storage_path / "runs" / "latest.json"
    if not latest.exists():
        return None
    return json.loads(latest.read_text(encoding="utf-8"))


def manifest_provenance(items: list[dict[str, Any]]) -> list[ProvenanceView]:
    catalog = source_catalog()
    rows = []
    for item in items:
        source_id = str(item["source_id"])
        source = catalog.get(source_id, {})
        rows.append(
            ProvenanceView(
                source_id=source_id,
                name=str(source.get("name", source_id)),
                url=item.get("source_url"),
                consulted_at=str(item["consulted_at"]),
                quality=str(item["quality"]),
                official=bool(source.get("grade") == "A"),
                status=str(item.get("fetch_status", "snapshot")),
            )
        )
    return rows


def latest_backtest(storage_path: Path) -> dict[str, Any] | None:
    path = storage_path / "backtests" / "latest.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _latest_archive(
    storage_path: Path, source_id: str, schema_version: str, limit: int = 50
) -> dict[str, Any] | None:
    event = PredictionArchive(storage_path).latest_update_event()
    if event is None:
        return None
    source = next(
        (item for item in event.get("sources", []) if item.get("source_id") == source_id),
        None,
    )
    if source is None or not source.get("snapshot_path"):
        return None
    snapshot_root = (storage_path / "source_snapshots").resolve()
    target = Path(str(source["snapshot_path"])).resolve()
    if snapshot_root not in target.parents or not target.is_file():
        return None
    raw = json.loads(target.read_text(encoding="utf-8"))
    if raw.get("schema_version") != schema_version:
        return None
    sports_posts = [post for post in raw.get("posts", []) if post.get("sports_relevant")]
    techniques = Counter(
        technique for post in sports_posts for technique in post.get("technique_mentions", [])
    )
    return {
        "source_name": raw["source_name"],
        "source_url": raw["source_url"],
        "consulted_at": raw["consulted_at"],
        "quality": raw["quality"],
        "declared_total": raw["declared_total"],
        "captured_total": raw["captured_total"],
        "complete": raw["complete"],
        "earliest_published_at": raw["earliest_published_at"],
        "latest_published_at": raw["latest_published_at"],
        "sports_relevant_total": raw["sports_relevant_total"],
        "technique_mentions": dict(techniques.most_common()),
        "review_policy": "candidate_only_manual_confirmation_required",
        "recent_sports_posts": list(reversed(sports_posts))[:limit],
    }


def latest_sirius_archive(storage_path: Path, limit: int = 50) -> dict[str, Any] | None:
    return _latest_archive(storage_path, "sirius_blog", "sirius-archive-v2", limit)


def latest_argumental_archive(storage_path: Path, limit: int = 50) -> dict[str, Any] | None:
    return _latest_archive(storage_path, "argumental_blog", "argumental-archive-v1", limit)
