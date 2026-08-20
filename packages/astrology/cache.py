from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from db.models import AstrologyChart as StoredAstrologyChart
from packages.common.provenance import SourceClaimInput

from .ephemeris import BODIES, DEFAULT_ORBS, chart, ephemeris_identity
from .models import (
    Aspect,
    AstrologyChart,
    BodyPosition,
    ChartRequest,
    GeoLocation,
    HouseAngles,
)

CHART_CACHE_SCHEMA = "astrology-chart-cache-v1"
CHART_ENTITY_TYPES = frozenset({"BirthData", "Fixture", "CoachDebutEvent"})


@dataclass(frozen=True, slots=True)
class ChartCacheResult:
    chart: AstrologyChart
    input_hash: str
    chart_id: str
    status: Literal["hit", "recalculated"]


@dataclass(slots=True)
class ChartRecalculationReport:
    requested_entities: list[str] = field(default_factory=list)
    recalculated: list[dict[str, str]] = field(default_factory=list)
    cache_hits: list[dict[str, str]] = field(default_factory=list)
    skipped: list[dict[str, str]] = field(default_factory=list)
    failed: list[dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "requested_entities": self.requested_entities,
            "requested_count": len(self.requested_entities),
            "recalculated": self.recalculated,
            "recalculated_count": len(self.recalculated),
            "cache_hits": self.cache_hits,
            "cache_hit_count": len(self.cache_hits),
            "skipped": self.skipped,
            "skipped_count": len(self.skipped),
            "failed": self.failed,
            "failed_count": len(self.failed),
        }


@dataclass(frozen=True, slots=True)
class _ParsedClaim:
    request: ChartRequest
    bodies: tuple[str, ...]
    orbs: dict[str, float]


def _canonical_json(payload: object) -> str:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _request_payload(request: ChartRequest) -> dict[str, Any]:
    return {
        "moment_utc": request.moment.astimezone(UTC).isoformat(),
        "location": (
            {
                "latitude": request.location.latitude,
                "longitude": request.location.longitude,
                "name": request.location.name,
            }
            if request.location is not None
            else None
        ),
        "time_known": request.time_known,
        "house_system": request.house_system,
        "label": request.label,
    }


def chart_input_hash(
    subject_type: str,
    subject_id: str,
    request: ChartRequest,
    bodies: tuple[str, ...] = BODIES,
    orbs: dict[str, float] | None = None,
) -> str:
    provider, ephemeris_version = ephemeris_identity()
    payload = {
        "schema_version": CHART_CACHE_SCHEMA,
        "subject_type": subject_type,
        "subject_id": subject_id,
        "request": _request_payload(request),
        "provider": provider,
        "ephemeris_version": ephemeris_version,
        "bodies": list(bodies),
        "orbs": {**DEFAULT_ORBS, **(orbs or {})},
    }
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _serialize_chart(value: AstrologyChart) -> dict[str, Any]:
    return {
        "request": _request_payload(value.request),
        "provider": value.provider,
        "ephemeris_version": value.ephemeris_version,
        "julian_day_ut": value.julian_day_ut,
        "positions": {
            name: {
                "name": position.name,
                "longitude": position.longitude,
                "latitude": position.latitude,
                "distance_au": position.distance_au,
                "speed_longitude": position.speed_longitude,
                "retrograde": position.retrograde,
            }
            for name, position in value.positions.items()
        },
        "houses": (
            {
                "cusps": list(value.houses.cusps),
                "ascendant": value.houses.ascendant,
                "midheaven": value.houses.midheaven,
                "armc": value.houses.armc,
                "vertex": value.houses.vertex,
                "house_system": value.houses.house_system,
            }
            if value.houses is not None
            else None
        ),
        "aspects": [
            {
                "body_a": aspect.body_a,
                "body_b": aspect.body_b,
                "aspect": aspect.aspect,
                "angle": aspect.angle,
                "orb": aspect.orb,
                "applying": aspect.applying,
            }
            for aspect in value.aspects
        ],
        "parameters": value.parameters,
    }


def _deserialize_chart(payload: dict[str, Any]) -> AstrologyChart:
    request_payload = payload["request"]
    location_payload = request_payload.get("location")
    location = (
        GeoLocation(
            latitude=float(location_payload["latitude"]),
            longitude=float(location_payload["longitude"]),
            name=str(location_payload.get("name", "")),
        )
        if location_payload is not None
        else None
    )
    request = ChartRequest(
        moment=datetime.fromisoformat(str(request_payload["moment_utc"])),
        location=location,
        time_known=bool(request_payload["time_known"]),
        house_system=str(request_payload["house_system"]),
        label=str(request_payload.get("label", "")),
    )
    houses_payload = payload.get("houses")
    houses = (
        HouseAngles(
            cusps=tuple(float(item) for item in houses_payload["cusps"]),
            ascendant=float(houses_payload["ascendant"]),
            midheaven=float(houses_payload["midheaven"]),
            armc=float(houses_payload["armc"]),
            vertex=float(houses_payload["vertex"]),
            house_system=str(houses_payload["house_system"]),
        )
        if houses_payload is not None
        else None
    )
    return AstrologyChart(
        request=request,
        provider=str(payload["provider"]),
        ephemeris_version=str(payload["ephemeris_version"]),
        julian_day_ut=float(payload["julian_day_ut"]),
        positions={
            name: BodyPosition(
                name=str(position["name"]),
                longitude=float(position["longitude"]),
                latitude=float(position["latitude"]),
                distance_au=float(position["distance_au"]),
                speed_longitude=float(position["speed_longitude"]),
                retrograde=bool(position["retrograde"]),
            )
            for name, position in payload["positions"].items()
        },
        houses=houses,
        aspects=[
            Aspect(
                body_a=str(aspect["body_a"]),
                body_b=str(aspect["body_b"]),
                aspect=str(aspect["aspect"]),
                angle=float(aspect["angle"]),
                orb=float(aspect["orb"]),
                applying=(bool(aspect["applying"]) if aspect.get("applying") is not None else None),
            )
            for aspect in payload["aspects"]
        ],
        parameters=dict(payload["parameters"]),
    )


class AstrologyChartCache:
    """Append-only, content-addressed storage for deterministic chart calculations."""

    def __init__(self, session: Session):
        self.session = session

    def get_or_calculate(
        self,
        subject_type: str,
        subject_id: str,
        request: ChartRequest,
        *,
        bodies: tuple[str, ...] = BODIES,
        orbs: dict[str, float] | None = None,
        provenance: dict[str, Any] | None = None,
    ) -> ChartCacheResult:
        input_hash = chart_input_hash(subject_type, subject_id, request, bodies, orbs)
        existing = self.session.scalar(
            select(StoredAstrologyChart).where(StoredAstrologyChart.input_hash == input_hash)
        )
        if existing is not None:
            return ChartCacheResult(
                chart=_deserialize_chart(existing.result),
                input_hash=input_hash,
                chart_id=existing.id,
                status="hit",
            )

        calculated = chart(request, bodies=bodies, orbs=orbs)
        parameters = {
            "schema_version": CHART_CACHE_SCHEMA,
            "calculation": {
                "bodies": list(bodies),
                "orbs": {**DEFAULT_ORBS, **(orbs or {})},
            },
            "initial_source_provenance": provenance,
        }
        stored = StoredAstrologyChart(
            subject_type=subject_type,
            subject_id=subject_id,
            input_hash=input_hash,
            chart_time_utc=request.moment.astimezone(UTC),
            latitude=request.location.latitude if request.location is not None else None,
            longitude=request.location.longitude if request.location is not None else None,
            house_system=(
                request.house_system
                if request.time_known and request.location is not None
                else None
            ),
            ephemeris_version=calculated.ephemeris_version,
            parameters=parameters,
            result=_serialize_chart(calculated),
        )
        try:
            with self.session.begin_nested():
                self.session.add(stored)
                self.session.flush()
        except IntegrityError:
            concurrent = self.session.scalar(
                select(StoredAstrologyChart).where(StoredAstrologyChart.input_hash == input_hash)
            )
            if concurrent is None:  # pragma: no cover - defensive database race guard
                raise
            return ChartCacheResult(
                chart=_deserialize_chart(concurrent.result),
                input_hash=input_hash,
                chart_id=concurrent.id,
                status="hit",
            )
        return ChartCacheResult(
            chart=calculated,
            input_hash=input_hash,
            chart_id=stored.id,
            status="recalculated",
        )


def _claim_request(claim: SourceClaimInput) -> tuple[_ParsedClaim | None, str | None]:
    if claim.source_url is None:
        return None, "source provenance is missing its URL"
    if not isinstance(claim.value, dict):
        return None, "claim value has no complete chart_request object"
    raw = claim.value.get("chart_request")
    if not isinstance(raw, dict):
        return None, "claim value has no complete chart_request object"
    if not isinstance(raw.get("time_known"), bool):
        return None, "chart_request.time_known must be explicit"
    if raw["time_known"] is False:
        return None, "unknown time requires an explicit sensitivity analysis"
    if not isinstance(raw.get("moment"), str):
        return None, "chart_request.moment must be an ISO timestamp with UTC offset"
    try:
        moment = datetime.fromisoformat(raw["moment"])
    except ValueError:
        return None, "chart_request.moment is not a valid ISO timestamp"
    if moment.tzinfo is None or moment.utcoffset() is None:
        return None, "chart_request.moment must include a UTC offset"
    house_system = raw.get("house_system")
    if not isinstance(house_system, str) or len(house_system) != 1:
        return None, "chart_request.house_system must be one explicit code"

    location = None
    raw_location = raw.get("location")
    if raw_location is not None:
        if not isinstance(raw_location, dict):
            return None, "chart_request.location must be an object or null"
        try:
            latitude = float(raw_location["latitude"])
            longitude = float(raw_location["longitude"])
            location = GeoLocation(
                latitude=latitude,
                longitude=longitude,
                name=str(raw_location.get("name", "")),
            )
        except (KeyError, TypeError, ValueError) as error:
            return None, f"invalid chart_request.location: {error}"

    raw_bodies = raw.get("bodies", list(BODIES))
    if (
        not isinstance(raw_bodies, list)
        or not raw_bodies
        or any(not isinstance(item, str) for item in raw_bodies)
    ):
        return None, "chart_request.bodies must be a non-empty string list"
    bodies = tuple(raw_bodies)
    unsupported = sorted(set(bodies) - set(BODIES))
    if unsupported:
        return None, f"unsupported bodies: {unsupported}"

    raw_orbs = raw.get("orbs", {})
    if not isinstance(raw_orbs, dict) or set(raw_orbs) - set(DEFAULT_ORBS):
        return None, "chart_request.orbs contains unsupported aspects"
    try:
        orbs = {str(name): float(value) for name, value in raw_orbs.items()}
    except (TypeError, ValueError):
        return None, "chart_request.orbs must contain numeric values"
    if any(value < 0 or value > 30 for value in orbs.values()):
        return None, "chart_request.orbs must be between 0 and 30 degrees"

    try:
        request = ChartRequest(
            moment=moment,
            location=location,
            time_known=True,
            house_system=house_system,
            label=str(raw.get("label", "")),
        )
    except (TypeError, ValueError) as error:
        return None, str(error)
    return _ParsedClaim(request=request, bodies=bodies, orbs=orbs), None


def recalculate_accepted_charts(
    session: Session,
    claims: list[SourceClaimInput],
) -> ChartRecalculationReport:
    relevant = [claim for claim in claims if claim.entity_type in CHART_ENTITY_TYPES]
    report = ChartRecalculationReport(
        requested_entities=sorted({f"{claim.entity_type}:{claim.entity_key}" for claim in relevant})
    )
    cache = AstrologyChartCache(session)
    for claim in relevant:
        entity = f"{claim.entity_type}:{claim.entity_key}"
        parsed, reason = _claim_request(claim)
        if parsed is None:
            report.skipped.append(
                {
                    "entity": entity,
                    "field": claim.field_name,
                    "source_id": claim.source_id,
                    "reason": reason or "invalid chart request",
                }
            )
            continue
        provenance = {
            "source_id": claim.source_id,
            "source_url": str(claim.source_url),
            "consulted_at": claim.consulted_at.isoformat(),
            "quality": claim.grade.value,
            "confidence": claim.confidence,
            "official": claim.official,
            "manually_confirmed": claim.manually_confirmed,
            "raw_reference": claim.raw_reference,
        }
        try:
            result = cache.get_or_calculate(
                claim.entity_type,
                claim.entity_key,
                parsed.request,
                bodies=parsed.bodies,
                orbs=parsed.orbs,
                provenance=provenance,
            )
        except (RuntimeError, ValueError) as error:
            report.failed.append(
                {
                    "entity": entity,
                    "field": claim.field_name,
                    "source_id": claim.source_id,
                    "reason": str(error),
                }
            )
            continue
        row = {
            "entity": entity,
            "chart_id": result.chart_id,
            "input_hash": result.input_hash,
        }
        if result.status == "hit":
            report.cache_hits.append(row)
        else:
            report.recalculated.append(row)
    return report
