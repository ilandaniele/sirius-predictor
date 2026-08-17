from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import requests
import yaml
from bs4 import BeautifulSoup

from .domain import SimulationBundle

MAX_SNAPSHOT_BYTES = 5 * 1024 * 1024
USER_AGENT = "Mundial2030SiriusEngine/0.2 (+local research dashboard)"


class StateStore:
    """SQLite metadata plus immutable content-addressed source snapshots."""

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.snapshot_root = self.root / "snapshots"
        self.snapshot_root.mkdir(parents=True, exist_ok=True)
        self.db_path = self.root / "sirius.db"
        self._initialize()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS source_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_id TEXT NOT NULL,
                    fetched_at TEXT NOT NULL,
                    url TEXT,
                    quality TEXT NOT NULL DEFAULT 'X',
                    status_code INTEGER,
                    content_type TEXT,
                    sha256 TEXT,
                    byte_count INTEGER NOT NULL DEFAULT 0,
                    relative_path TEXT,
                    changed INTEGER NOT NULL DEFAULT 0,
                    error TEXT
                );
                CREATE INDEX IF NOT EXISTS source_snapshots_source_time
                    ON source_snapshots(source_id, fetched_at DESC);
                CREATE TABLE IF NOT EXISTS simulation_runs (
                    run_id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    manifest_json TEXT NOT NULL,
                    summary_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS backtest_runs (
                    run_id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    editions TEXT NOT NULL,
                    metrics_json TEXT NOT NULL
                );
                """
            )
            columns = {
                str(row[1])
                for row in connection.execute("PRAGMA table_info(source_snapshots)").fetchall()
            }
            if "quality" not in columns:
                connection.execute(
                    "ALTER TABLE source_snapshots ADD COLUMN quality TEXT NOT NULL DEFAULT 'X'"
                )

    def _latest_hash(self, source_id: str) -> str | None:
        with self._connect() as connection:
            row = connection.execute(
                """SELECT sha256 FROM source_snapshots
                   WHERE source_id = ? AND sha256 IS NOT NULL
                   ORDER BY id DESC LIMIT 1""",
                (source_id,),
            ).fetchone()
        return str(row["sha256"]) if row else None

    def capture(
        self,
        source_id: str,
        url: str,
        payload: bytes,
        *,
        quality: str,
        status_code: int = 200,
        content_type: str = "application/octet-stream",
    ) -> dict[str, Any]:
        if quality not in {"A", "B", "C", "D", "X"}:
            raise ValueError(f"invalid data quality: {quality}")
        digest = hashlib.sha256(payload).hexdigest()
        previous = self._latest_hash(source_id)
        changed = previous is not None and previous != digest
        safe_id = re.sub(r"[^A-Za-z0-9_.-]", "_", source_id)
        directory = self.snapshot_root / safe_id
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / f"{digest}.bin"
        if not target.exists():
            target.write_bytes(payload)
        fetched_at = datetime.now().astimezone().isoformat(timespec="seconds")
        relative_path = target.relative_to(self.root).as_posix()
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO source_snapshots
                   (source_id, fetched_at, url, quality, status_code, content_type, sha256,
                    byte_count, relative_path, changed, error)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)""",
                (
                    source_id,
                    fetched_at,
                    url,
                    quality,
                    status_code,
                    content_type,
                    digest,
                    len(payload),
                    relative_path,
                    int(changed),
                ),
            )
        return {
            "source_id": source_id,
            "url": url,
            "fetched_at": fetched_at,
            "quality": quality,
            "status": "changed" if changed else ("new" if previous is None else "unchanged"),
            "sha256": digest,
            "bytes": len(payload),
            "error": None,
        }

    def capture_error(
        self, source_id: str, url: str, error: str, *, quality: str
    ) -> dict[str, Any]:
        if quality not in {"A", "B", "C", "D", "X"}:
            raise ValueError(f"invalid data quality: {quality}")
        fetched_at = datetime.now().astimezone().isoformat(timespec="seconds")
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO source_snapshots
                   (source_id, fetched_at, url, quality, byte_count, changed, error)
                   VALUES (?, ?, ?, ?, 0, 0, ?)""",
                (source_id, fetched_at, url, quality, error[:1000]),
            )
        return {
            "source_id": source_id,
            "url": url,
            "fetched_at": fetched_at,
            "quality": quality,
            "status": "error",
            "sha256": None,
            "bytes": 0,
            "error": error,
        }

    def snapshots(self, limit: int = 200) -> pd.DataFrame:
        with self._connect() as connection:
            rows = connection.execute(
                """SELECT source_id, url, quality, fetched_at, status_code, content_type, sha256,
                          byte_count, relative_path, changed, error
                   FROM source_snapshots ORDER BY id DESC LIMIT ?""",
                (limit,),
            ).fetchall()
        return pd.DataFrame([dict(row) for row in rows])

    def latest_payload(self, source_id: str) -> bytes | None:
        with self._connect() as connection:
            row = connection.execute(
                """SELECT relative_path FROM source_snapshots
                   WHERE source_id = ? AND relative_path IS NOT NULL
                   ORDER BY id DESC LIMIT 1""",
                (source_id,),
            ).fetchone()
        if row is None:
            return None
        target = self.root / str(row["relative_path"])
        return target.read_bytes() if target.exists() else None

    def record_simulation(self, bundle: SimulationBundle) -> None:
        summary = {
            "top_teams": bundle.ranking.head(10).to_dict(orient="records"),
            "top_brackets": [
                {key: value for key, value in bracket.items() if key != "representative"}
                for bracket in bundle.top_brackets
            ],
        }
        with self._connect() as connection:
            connection.execute(
                """INSERT OR REPLACE INTO simulation_runs
                   (run_id, created_at, manifest_json, summary_json) VALUES (?, ?, ?, ?)""",
                (
                    bundle.manifest.run_id,
                    bundle.manifest.created_at,
                    json.dumps(asdict(bundle.manifest), ensure_ascii=False),
                    json.dumps(summary, ensure_ascii=False),
                ),
            )

    def simulation_history(self, limit: int = 50) -> pd.DataFrame:
        with self._connect() as connection:
            rows = connection.execute(
                """SELECT run_id, created_at, manifest_json
                   FROM simulation_runs ORDER BY created_at DESC LIMIT ?""",
                (limit,),
            ).fetchall()
        result = []
        for row in rows:
            manifest = json.loads(row["manifest_json"])
            result.append(manifest)
        return pd.DataFrame(result)

    def record_backtest(self, run_id: str, editions: list[int], metrics: pd.DataFrame) -> None:
        with self._connect() as connection:
            connection.execute(
                """INSERT OR REPLACE INTO backtest_runs
                   (run_id, created_at, editions, metrics_json) VALUES (?, ?, ?, ?)""",
                (
                    run_id,
                    datetime.now().astimezone().isoformat(timespec="seconds"),
                    json.dumps(editions),
                    metrics.to_json(orient="records", force_ascii=False),
                ),
            )


def _read_response(response: requests.Response) -> bytes:
    response.raise_for_status()
    chunks: list[bytes] = []
    size = 0
    for chunk in response.iter_content(chunk_size=64 * 1024):
        if not chunk:
            continue
        size += len(chunk)
        if size > MAX_SNAPSHOT_BYTES:
            raise ValueError(f"source exceeds {MAX_SNAPSHOT_BYTES} byte safety limit")
        chunks.append(chunk)
    return b"".join(chunks)


def _csv_change_summary(previous: bytes | None, current: bytes) -> str:
    if previous is None:
        return "snapshot inicial"

    def indexed(payload: bytes) -> dict[str, dict[str, str]]:
        text = payload.decode("utf-8-sig")
        rows = csv.DictReader(io.StringIO(text))
        return {row.get("team_id", str(index)): row for index, row in enumerate(rows)}

    old, new = indexed(previous), indexed(current)
    added = sorted(set(new) - set(old))
    removed = sorted(set(old) - set(new))
    changed = []
    for team_id in sorted(set(old) & set(new)):
        fields = sorted(
            key for key in new[team_id] if old[team_id].get(key) != new[team_id].get(key)
        )
        if fields:
            changed.append(f"{team_id}({','.join(fields)})")
    pieces = []
    if added:
        pieces.append("altas: " + ", ".join(added))
    if removed:
        pieces.append("bajas: " + ", ".join(removed))
    if changed:
        pieces.append("cambios: " + "; ".join(changed))
    return " | ".join(pieces) if pieces else "sin cambios de campos"


def refresh_sources(
    project_root: str | Path,
    store: StateStore,
    sources_path: str | Path,
    timeout: float = 12.0,
) -> pd.DataFrame:
    project_root = Path(project_root)
    sources = yaml.safe_load(Path(sources_path).read_text(encoding="utf-8"))
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    rows: list[dict[str, Any]] = []
    for source in sources:
        if not source.get("enabled", False):
            continue
        source_id = str(source["id"])
        quality = str(source["grade"])
        url = source.get("url")
        if not url:
            continue
        try:
            if source.get("kind") == "local_csv":
                payload = (project_root / str(url)).read_bytes()
                previous = store.latest_payload(source_id)
                record = store.capture(
                    source_id,
                    str(url),
                    payload,
                    quality=quality,
                    content_type="text/csv",
                )
                record["details"] = _csv_change_summary(previous, payload)
                rows.append(record)
                continue
            response = session.get(str(url), timeout=timeout, stream=True)
            payload = _read_response(response)
            content_type = response.headers.get("Content-Type", "application/octet-stream")
            record = store.capture(
                source_id,
                str(url),
                payload,
                quality=quality,
                status_code=response.status_code,
                content_type=content_type,
            )
            if "html" in content_type.lower():
                title = BeautifulSoup(payload, "html.parser").title
                page_title = title.get_text(" ", strip=True) if title else "sin título"
                record["details"] = f"HTML: {page_title[:180]} · comparado por SHA-256"
            else:
                record["details"] = "contenido remoto comparado por SHA-256"
            rows.append(record)
        except Exception as exc:  # One failing source must not corrupt or stop the update.
            record = store.capture_error(
                source_id,
                str(url),
                f"{type(exc).__name__}: {exc}",
                quality=quality,
            )
            record["details"] = "se conserva el último snapshot válido"
            rows.append(record)
    return pd.DataFrame(rows)
