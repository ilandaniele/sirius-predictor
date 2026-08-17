from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from packages.common.provenance import DataGrade, SourceClaimInput


@dataclass(frozen=True, slots=True)
class CollectorSpec:
    source_id: str
    url: str
    grade: DataGrade
    official: bool
    allowed_hosts: tuple[str, ...]
    terms_url: str | None
    robots_policy: str
    priority: int

    def validate_governance(self) -> None:
        if not self.terms_url:
            raise ValueError(f"{self.source_id}: terms_url must be reviewed and recorded")
        if not self.robots_policy:
            raise ValueError(f"{self.source_id}: robots policy must be recorded")


@dataclass(slots=True)
class CollectorOutcome:
    source_id: str
    source_url: str
    quality: DataGrade
    consulted_at: datetime
    status: str
    payload_sha256: str | None = None
    snapshot_path: str | None = None
    claims: list[SourceClaimInput] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    error: str | None = None


class ImmutableSnapshotStore:
    def __init__(self, root: Path):
        self.root = root

    def write(self, source_id: str, payload: bytes) -> tuple[str, str]:
        digest = hashlib.sha256(payload).hexdigest()
        target = self.root / source_id / f"{digest}.bin"
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            target.write_bytes(payload)
        return digest, target.as_posix()


class Collector(ABC):
    spec: CollectorSpec

    @abstractmethod
    def fetch(self) -> bytes:
        raise NotImplementedError

    @abstractmethod
    def parse(self, payload: bytes, consulted_at: datetime) -> list[SourceClaimInput]:
        raise NotImplementedError

    def run(self, snapshots: ImmutableSnapshotStore) -> CollectorOutcome:
        consulted_at = datetime.now(UTC)
        try:
            self.spec.validate_governance()
            payload = self.fetch()
            digest, path = snapshots.write(self.spec.source_id, payload)
            claims = self.parse(payload, consulted_at)
            return CollectorOutcome(
                source_id=self.spec.source_id,
                source_url=self.spec.url,
                quality=self.spec.grade,
                consulted_at=consulted_at,
                status="success",
                payload_sha256=digest,
                snapshot_path=path,
                claims=claims,
            )
        except Exception as exc:
            return CollectorOutcome(
                source_id=self.spec.source_id,
                source_url=self.spec.url,
                quality=self.spec.grade,
                consulted_at=consulted_at,
                status="error",
                error=f"{type(exc).__name__}: {exc}",
            )


def claim_from_record(
    spec: CollectorSpec,
    consulted_at: datetime,
    entity_type: str,
    entity_key: str,
    field_name: str,
    value: Any,
    confidence: float,
    raw_reference: str | None = None,
) -> SourceClaimInput:
    return SourceClaimInput(
        entity_type=entity_type,
        entity_key=entity_key,
        field_name=field_name,
        value=value,
        source_id=spec.source_id,
        source_url=spec.url,
        consulted_at=consulted_at,
        grade=spec.grade,
        confidence=confidence,
        official=spec.official,
        inferred=False,
        manually_confirmed=False,
        raw_reference=raw_reference,
    )
