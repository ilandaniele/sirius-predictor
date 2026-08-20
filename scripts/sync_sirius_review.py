from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy.orm import Session

from db.session import build_engine
from packages.common.config import ROOT, get_settings
from packages.sirius import SiriusReviewQueue
from services.api.update_pipeline import PredictionArchive


def latest_archive_snapshot(storage_path: Path) -> Path:
    event = PredictionArchive(storage_path).latest_update_event()
    source = next(
        (
            item
            for item in (event or {}).get("sources", [])
            if item.get("source_id") == "sirius_blog" and item.get("snapshot_path")
        ),
        None,
    )
    if source is None:
        raise FileNotFoundError("no Sirius archive snapshot is referenced by the latest update")
    root = (storage_path / "source_snapshots" / "sirius_blog").resolve()
    target = Path(str(source["snapshot_path"])).resolve()
    if root not in target.parents or not target.is_file():
        raise ValueError("latest Sirius archive snapshot path is invalid")
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(
            "latest Sirius snapshot uses the legacy raw format; run ACTUALIZAR first"
        ) from exc
    if payload.get("schema_version") != "sirius-archive-v2":
        raise ValueError("latest Sirius snapshot is not a sirius-archive-v2 corpus")
    return target


def main() -> None:
    settings = get_settings()
    archive_path = latest_archive_snapshot(settings.storage_path)
    engine = build_engine(settings.database_url)
    try:
        with Session(engine) as session:
            queue = SiriusReviewQueue(
                session,
                rules_path=ROOT / "data" / "sirius_rules.yaml",
                teams_path=settings.teams_path,
            )
            result = queue.sync_archive(archive_path.read_bytes())
            session.commit()
            result["review_snapshot"] = queue.export_reviewed_snapshot(
                settings.storage_path / "sirius-review"
            )
            result["queue"] = queue.list_candidates(status="all", limit=1)["counts"]
            print(json.dumps(result, ensure_ascii=False, indent=2))
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
