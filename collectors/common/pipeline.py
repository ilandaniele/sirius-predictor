from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from packages.common.provenance import SourceClaimInput, should_auto_replace

from .base import Collector, CollectorOutcome, ImmutableSnapshotStore

ClaimKey = tuple[str, str, str]


@dataclass(slots=True)
class UpdateReport:
    outcomes: list[CollectorOutcome]
    accepted: list[SourceClaimInput] = field(default_factory=list)
    pending_review: list[SourceClaimInput] = field(default_factory=list)
    conflicts: list[dict[str, object]] = field(default_factory=list)

    @property
    def changed_sources(self) -> int:
        return sum(outcome.status == "success" for outcome in self.outcomes)


class UpdatePipeline:
    def __init__(self, collectors: list[Collector], snapshot_root: Path):
        self.collectors = sorted(collectors, key=lambda item: item.spec.priority)
        self.snapshots = ImmutableSnapshotStore(snapshot_root)

    def run(self, current: dict[ClaimKey, SourceClaimInput] | None = None) -> UpdateReport:
        active = dict(current or {})
        outcomes = [collector.run(self.snapshots) for collector in self.collectors]
        report = UpdateReport(outcomes=outcomes)
        seen_payloads: set[tuple[ClaimKey, str]] = set()
        for outcome in outcomes:
            for claim in outcome.claims:
                key = (claim.entity_type, claim.entity_key, claim.field_name)
                fingerprint = (key, claim.model_dump_json(exclude={"consulted_at"}))
                if fingerprint in seen_payloads:
                    continue
                seen_payloads.add(fingerprint)
                previous = active.get(key)
                if previous is None:
                    if claim.manually_confirmed or (
                        claim.grade.value in {"A", "B"} and not claim.inferred
                    ):
                        active[key] = claim
                        report.accepted.append(claim)
                    else:
                        report.pending_review.append(claim)
                    continue
                if previous.value != claim.value:
                    report.conflicts.append({"key": key, "current": previous, "candidate": claim})
                if should_auto_replace(previous, claim):
                    active[key] = claim
                    report.accepted.append(claim)
                elif previous.value != claim.value:
                    report.pending_review.append(claim)
        return report
