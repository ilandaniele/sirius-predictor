from __future__ import annotations

from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

from packages.common.provenance import DataGrade, SourceClaimInput

from .base import Collector, CollectorSpec
from .http import SafeHttpClient


class RawRemoteCollector(Collector):
    def __init__(self, spec: CollectorSpec, client: SafeHttpClient | None = None):
        self.spec = spec
        self.client = client or SafeHttpClient(spec.allowed_hosts)

    def fetch(self) -> bytes:
        return self.client.get(self.spec.url)

    def parse(self, payload: bytes, consulted_at: datetime) -> list[SourceClaimInput]:
        del payload, consulted_at
        return []


class LocalFileCollector(Collector):
    def __init__(self, spec: CollectorSpec, project_root: Path):
        self.spec = spec
        self.project_root = project_root.resolve()

    def fetch(self) -> bytes:
        target = (self.project_root / self.spec.url).resolve()
        if self.project_root not in target.parents:
            raise ValueError("local collector path escapes project root")
        return target.read_bytes()

    def parse(self, payload: bytes, consulted_at: datetime) -> list[SourceClaimInput]:
        del payload, consulted_at
        return []


def raw_collector_from_config(record: dict[str, object], project_root: Path) -> Collector:
    url = str(record["url"])
    is_local = not url.startswith("http")
    host = urlsplit(url).hostname if not is_local else "local.invalid"
    grade = str(record["grade"])
    terms_url = record.get("terms_url")
    robots_policy = record.get("robots_policy")
    spec = CollectorSpec(
        source_id=str(record["id"]),
        url=url,
        grade=DataGrade(grade),
        official=grade == "A",
        allowed_hosts=(str(host),),
        terms_url=str(terms_url) if terms_url else None,
        robots_policy=str(robots_policy) if robots_policy else "",
        priority={"A": 10, "B": 20, "C": 30, "D": 40, "X": 50}[grade],
    )
    if is_local:
        return LocalFileCollector(spec, project_root)
    return RawRemoteCollector(spec)
