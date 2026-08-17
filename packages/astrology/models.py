from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class GeoLocation:
    latitude: float
    longitude: float
    name: str = ""

    def __post_init__(self) -> None:
        if not -90 <= self.latitude <= 90:
            raise ValueError("latitude must be between -90 and 90")
        if not -180 <= self.longitude <= 180:
            raise ValueError("longitude must be between -180 and 180")


@dataclass(frozen=True, slots=True)
class ChartRequest:
    moment: datetime
    location: GeoLocation | None = None
    time_known: bool = True
    house_system: str = "P"
    label: str = ""

    def __post_init__(self) -> None:
        if self.moment.tzinfo is None or self.moment.utcoffset() is None:
            raise ValueError("chart moment must be timezone-aware")
        if len(self.house_system) != 1:
            raise ValueError("house_system must be a single Swiss Ephemeris code")


@dataclass(frozen=True, slots=True)
class BodyPosition:
    name: str
    longitude: float
    latitude: float
    distance_au: float
    speed_longitude: float
    retrograde: bool


@dataclass(frozen=True, slots=True)
class HouseAngles:
    cusps: tuple[float, ...]
    ascendant: float
    midheaven: float
    armc: float
    vertex: float
    house_system: str


@dataclass(frozen=True, slots=True)
class Aspect:
    body_a: str
    body_b: str
    aspect: str
    angle: float
    orb: float
    applying: bool | None


@dataclass(slots=True)
class AstrologyChart:
    request: ChartRequest
    provider: str
    ephemeris_version: str
    julian_day_ut: float
    positions: dict[str, BodyPosition]
    houses: HouseAngles | None
    aspects: list[Aspect]
    parameters: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class TechniqueResult:
    technique: str
    result: dict[str, Any]
    parameters: dict[str, Any]
    warnings: tuple[str, ...] = ()
