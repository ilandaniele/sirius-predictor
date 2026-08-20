from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlsplit

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from collectors.sirius_archive import parse_archive_index
from db.base import new_id
from db.models import SiriusReviewCandidate, SiriusReviewDecision
from engine.config import load_teams

from .models import EvidenceLayer, Polarity

TECHNIQUE_ALIASES = {
    "federation_chart": "country_federation",
    "captain_chart": "captain",
    "eclipse": "lunations_eclipses_ingresses",
}


class ReviewConflictError(ValueError):
    """Raised when a reviewer acts on an obsolete decision version."""


def _utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _iso(value: datetime) -> str:
    return _utc(value).astimezone(UTC).isoformat()


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)


class SiriusReviewQueue:
    """Persistent, append-only review workflow for archive-derived candidates."""

    def __init__(
        self,
        session: Session,
        *,
        rules_path: str | Path,
        teams_path: str | Path,
    ) -> None:
        self.session = session
        self.rules_path = Path(rules_path)
        self.teams_path = Path(teams_path)

    def sync_archive(self, payload: bytes) -> dict[str, Any]:
        raw = json.loads(payload)
        consulted_at = datetime.fromisoformat(str(raw["consulted_at"]))
        posts = parse_archive_index(payload)
        candidates: list[dict[str, Any]] = []
        for post in posts:
            if not post.sports_relevant:
                continue
            for claim_index, claim_text in enumerate(post.explicit_claims):
                fingerprint_payload = {
                    "source_id": "sirius_blog",
                    "post_id": post.post_id,
                    "content_sha256": post.content_sha256,
                    "claim_index": claim_index,
                    "claim_text": claim_text,
                }
                fingerprint = hashlib.sha256(
                    json.dumps(
                        fingerprint_payload,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    ).encode("utf-8")
                ).hexdigest()
                candidates.append(
                    {
                        **fingerprint_payload,
                        "fingerprint": fingerprint,
                        "title": post.title,
                        "published_at": post.published_at,
                        "source_url": str(post.url),
                        "consulted_at": consulted_at,
                        "quality_code": post.quality,
                        "technique_mentions": post.technique_mentions,
                    }
                )

        fingerprints = [item["fingerprint"] for item in candidates]
        existing = (
            set(
                self.session.scalars(
                    select(SiriusReviewCandidate.fingerprint).where(
                        SiriusReviewCandidate.fingerprint.in_(fingerprints)
                    )
                )
            )
            if fingerprints
            else set()
        )
        inserted = 0
        for item in candidates:
            if item["fingerprint"] in existing:
                continue
            self.session.add(
                SiriusReviewCandidate(
                    fingerprint=item["fingerprint"],
                    post_id=item["post_id"],
                    claim_index=item["claim_index"],
                    claim_text=item["claim_text"],
                    title=item["title"],
                    published_at=item["published_at"],
                    source_id=item["source_id"],
                    source_url=item["source_url"],
                    consulted_at=item["consulted_at"],
                    quality_code=item["quality_code"],
                    content_sha256=item["content_sha256"],
                    technique_mentions=item["technique_mentions"],
                    inferred=True,
                )
            )
            inserted += 1
        self.session.flush()
        return {
            "sports_posts": sum(post.sports_relevant for post in posts),
            "candidate_sentences": len(candidates),
            "inserted": inserted,
            "already_present": len(candidates) - inserted,
        }

    def _latest_decisions(self) -> dict[str, SiriusReviewDecision]:
        rows = self.session.scalars(
            select(SiriusReviewDecision).order_by(
                SiriusReviewDecision.candidate_id,
                SiriusReviewDecision.decided_at.desc(),
                SiriusReviewDecision.created_at.desc(),
                SiriusReviewDecision.id.desc(),
            )
        )
        latest: dict[str, SiriusReviewDecision] = {}
        for row in rows:
            latest.setdefault(row.candidate_id, row)
        return latest

    @staticmethod
    def decision_view(decision: SiriusReviewDecision | None) -> dict[str, Any] | None:
        if decision is None:
            return None
        return {
            "id": decision.id,
            "action": decision.action,
            "reviewer": decision.reviewer,
            "reason": decision.reason,
            "decided_at": _iso(decision.decided_at),
            "supersedes_decision_id": decision.supersedes_decision_id,
            "observation": decision.observation,
        }

    def list_candidates(
        self,
        *,
        status: Literal["pending", "approved", "rejected", "all"] = "pending",
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        decisions = self._latest_decisions()
        rows = self.session.scalars(
            select(SiriusReviewCandidate).order_by(
                SiriusReviewCandidate.published_at.asc(),
                SiriusReviewCandidate.post_id.asc(),
                SiriusReviewCandidate.claim_index.asc(),
            )
        )
        items = []
        counts = {"pending": 0, "approved": 0, "rejected": 0}
        for candidate in rows:
            decision = decisions.get(candidate.id)
            candidate_status = decision.action if decision is not None else "pending"
            counts[candidate_status] += 1
            if status != "all" and candidate_status != status:
                continue
            normalized_techniques = sorted(
                {TECHNIQUE_ALIASES.get(value, value) for value in candidate.technique_mentions}
            )
            items.append(
                {
                    "id": candidate.id,
                    "fingerprint": candidate.fingerprint,
                    "post_id": candidate.post_id,
                    "claim_index": candidate.claim_index,
                    "claim_text": candidate.claim_text,
                    "title": candidate.title,
                    "published_at": _iso(candidate.published_at),
                    "source_id": candidate.source_id,
                    "source_url": candidate.source_url,
                    "consulted_at": _iso(candidate.consulted_at),
                    "quality": candidate.quality_code,
                    "content_sha256": candidate.content_sha256,
                    "technique_mentions": normalized_techniques,
                    "inferred": candidate.inferred,
                    "status": candidate_status,
                    "latest_decision": self.decision_view(decision),
                }
            )
        return {
            "counts": {**counts, "total": sum(counts.values())},
            "status": status,
            "offset": offset,
            "limit": limit,
            "items": items[offset : offset + limit],
        }

    def _rule(self, feature_id: str) -> dict[str, Any]:
        raw = yaml.safe_load(self.rules_path.read_text(encoding="utf-8"))
        rules = {str(item["id"]): item for item in raw.get("rules", [])}
        if feature_id not in rules:
            raise ValueError(f"unknown Sirius feature_id: {feature_id}")
        return dict(rules[feature_id])

    def decide(
        self,
        candidate_id: str,
        *,
        action: Literal["approved", "rejected"],
        reviewer: str,
        reason: str,
        expected_decision_id: str | None = None,
        approval: dict[str, Any] | None = None,
        decided_at: datetime | None = None,
    ) -> SiriusReviewDecision:
        candidate = self.session.get(
            SiriusReviewCandidate,
            candidate_id,
            with_for_update=True,
        )
        if candidate is None:
            raise LookupError("Sirius review candidate not found")
        if action not in {"approved", "rejected"}:
            raise ValueError("action must be approved or rejected")
        reviewer = reviewer.strip()
        reason = reason.strip()
        if len(reviewer) < 2:
            raise ValueError("reviewer must contain at least 2 characters")
        if len(reason) < 5:
            raise ValueError("reason must contain at least 5 characters")

        current = self._latest_decisions().get(candidate_id)
        current_id = current.id if current is not None else None
        if current_id != expected_decision_id:
            raise ReviewConflictError(
                "candidate decision changed; reload it and provide latest_decision.id"
            )

        decision_id = new_id()
        observation: dict[str, Any] | None = None
        if action == "approved":
            if approval is None:
                raise ValueError("approved decisions require a structured observation")
            required = {
                "team_id",
                "feature_id",
                "polarity",
                "strength",
                "data_confidence",
                "description",
                "time_known",
            }
            missing = sorted(required - set(approval))
            if missing:
                raise ValueError(f"approval is missing fields: {missing}")
            team_id = str(approval["team_id"]).strip().upper()
            valid_team_ids = {team.team_id for team in load_teams(self.teams_path)}
            if team_id not in valid_team_ids:
                raise ValueError(f"unknown team_id: {team_id}")
            feature_id = str(approval["feature_id"]).strip()
            rule = self._rule(feature_id)
            mentioned = {
                TECHNIQUE_ALIASES.get(value, value) for value in candidate.technique_mentions
            }
            if feature_id not in mentioned:
                raise ValueError(
                    "feature_id must be explicitly detected in the archived source candidate"
                )
            polarity = Polarity(str(approval["polarity"]))
            strength = float(approval["strength"])
            data_confidence = float(approval["data_confidence"])
            hour_robustness = approval.get("hour_robustness")
            if not 0 <= strength <= 1:
                raise ValueError("strength must be in [0, 1]")
            if not 0 <= data_confidence <= 1:
                raise ValueError("data_confidence must be in [0, 1]")
            if hour_robustness is not None and not 0 <= float(hour_robustness) <= 1:
                raise ValueError("hour_robustness must be in [0, 1]")
            time_known = bool(approval["time_known"])
            requires_known_time = bool(rule["requires_known_time"])
            if requires_known_time and not time_known:
                raise ValueError(
                    f"{feature_id} requires a verified real time; unknown time is never noon"
                )
            time_verification = None
            if requires_known_time:
                time_fields = {
                    "time_source_url": approval.get("time_source_url"),
                    "time_consulted_at": approval.get("time_consulted_at"),
                    "time_data_grade": approval.get("time_data_grade"),
                    "time_source_note": approval.get("time_source_note"),
                }
                missing_time_fields = sorted(
                    key for key, value in time_fields.items() if value is None or value == ""
                )
                if missing_time_fields:
                    raise ValueError(
                        "verified time requires provenance fields: "
                        f"{missing_time_fields}"
                    )
                time_consulted_at = approval["time_consulted_at"]
                if isinstance(time_consulted_at, str):
                    time_consulted_at = datetime.fromisoformat(time_consulted_at)
                if not isinstance(time_consulted_at, datetime):
                    raise ValueError("time_consulted_at must be an ISO-8601 datetime")
                if time_consulted_at.tzinfo is None:
                    raise ValueError("time_consulted_at must include an explicit UTC offset")
                time_data_grade = str(approval["time_data_grade"])
                if time_data_grade not in {"A", "B", "C", "D", "X"}:
                    raise ValueError("time_data_grade must be A, B, C, D or X")
                time_source_url = str(approval["time_source_url"])
                parsed_time_url = urlsplit(time_source_url)
                if parsed_time_url.scheme not in {"http", "https"} or not parsed_time_url.hostname:
                    raise ValueError("time_source_url must be an absolute HTTP(S) URL")
                time_source_note = str(approval["time_source_note"]).strip()
                if len(time_source_note) < 5:
                    raise ValueError("time_source_note must contain at least 5 characters")
                time_verification = {
                    "source_url": time_source_url,
                    "consulted_at": _iso(time_consulted_at),
                    "data_grade": time_data_grade,
                    "note": time_source_note,
                }
            description = str(approval["description"]).strip()
            if len(description) < 5:
                raise ValueError("description must contain at least 5 characters")
            observation = {
                "team_id": team_id,
                "feature_id": feature_id,
                "layer": EvidenceLayer(str(rule["layer"])).value,
                "polarity": polarity.value,
                "strength": strength,
                "data_grade": candidate.quality_code,
                "data_confidence": data_confidence,
                "hour_robustness": (
                    float(hour_robustness) if hour_robustness is not None else None
                ),
                "explicit_public_rule": bool(rule["explicit_public_rule"]),
                "description": description,
                "source_claim_ids": [f"sirius-review-candidate:{candidate.fingerprint}"],
                "source_url": candidate.source_url,
                "consulted_at": _iso(candidate.consulted_at),
                "manually_confirmed": True,
                "requires_known_time": requires_known_time,
                "time_known": time_known,
                "parameters": {
                    "review_decision_id": decision_id,
                    "reviewer": reviewer,
                    "candidate_fingerprint": candidate.fingerprint,
                    "post_id": candidate.post_id,
                    "content_sha256": candidate.content_sha256,
                    "time_verification": time_verification,
                },
            }
        elif approval is not None:
            raise ValueError("rejected decisions cannot carry an observation")

        decision = SiriusReviewDecision(
            id=decision_id,
            candidate_id=candidate.id,
            action=action,
            reviewer=reviewer,
            reason=reason,
            decided_at=decided_at or datetime.now(UTC),
            supersedes_decision_id=current_id,
            observation=observation,
        )
        self.session.add(decision)
        self.session.flush()
        return decision

    def reviewed_records(self) -> list[dict[str, Any]]:
        latest = self._latest_decisions()
        records = [
            dict(decision.observation)
            for decision in latest.values()
            if decision.action == "approved" and decision.observation is not None
        ]
        return sorted(
            records,
            key=lambda item: (
                str(item["team_id"]),
                str(item["feature_id"]),
                str(item["parameters"]["candidate_fingerprint"]),
            ),
        )

    def export_reviewed_snapshot(self, root: str | Path) -> dict[str, Any]:
        records = self.reviewed_records()
        record_bytes = json.dumps(
            records, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        digest = hashlib.sha256(record_bytes).hexdigest()
        target_root = Path(root)
        relative_path = Path("snapshots") / f"{digest}.yaml"
        immutable_path = target_root / relative_path
        payload = {
            "schema_version": "sirius-observations-v1",
            "status": "reviewed_observations_only",
            "snapshot_id": digest,
            "records": records,
        }
        serialized = yaml.safe_dump(payload, allow_unicode=True, sort_keys=False)
        if not immutable_path.exists():
            _atomic_write(immutable_path, serialized)
        _atomic_write(target_root / "latest.yaml", serialized)
        _atomic_write(
            target_root / "latest.json",
            json.dumps(
                {
                    "snapshot_id": digest,
                    "path": immutable_path.as_posix(),
                    "relative_path": relative_path.as_posix(),
                    "reviewed_observations": len(records),
                },
                ensure_ascii=False,
                indent=2,
            ),
        )
        return {
            "snapshot_id": digest,
            "path": immutable_path.as_posix(),
            "reviewed_observations": len(records),
        }
