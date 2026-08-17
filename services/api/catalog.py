from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from packages.common.config import ROOT

from .schemas import ProvenanceView


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
    import json

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
    import json

    return json.loads(path.read_text(encoding="utf-8"))
