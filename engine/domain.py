from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class Team:
    team_id: str
    team: str
    confed: str
    host: bool
    pot: int
    projected_elo: float
    rating_uncertainty: float
    sirius_index: float
    sirius_confidence: float
    qualification_status: str
    coach: str
    captain: str
    source_id: str
    as_of: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class MatchProbabilities:
    home: float
    draw: float
    away: float
    baseline_home: float
    baseline_draw: float
    baseline_away: float
    sirius_adjustment: float = 0.0


@dataclass(frozen=True, slots=True)
class MatchResult:
    round_name: str
    match_index: int
    home_id: str
    away_id: str
    home_goals: int
    away_goals: int
    winner_id: str | None
    decided_by: str
    probabilities: MatchProbabilities

    def to_dict(self) -> dict[str, Any]:
        row = asdict(self)
        probabilities = row.pop("probabilities")
        row.update({f"p_{key}": value for key, value in probabilities.items()})
        return row


@dataclass(slots=True)
class TournamentResult:
    groups: dict[str, list[str]]
    group_tables: dict[str, list[str]]
    matches: list[MatchResult]
    champion_id: str
    runner_up_id: str
    semifinalists: tuple[str, ...]
    stage_reached: dict[str, str]

    @property
    def density_signature(self) -> str:
        semifinalists = ",".join(sorted(self.semifinalists))
        return f"{self.champion_id}|{self.runner_up_id}|{semifinalists}"


@dataclass(frozen=True, slots=True)
class SimulationManifest:
    run_id: str
    created_at: str
    scenario_id: str
    scenario_as_of: str
    iterations: int
    seed: int
    mode: str
    final_hour: int
    baseline_version: str
    sirius_version: str
    input_sha256: str

    @classmethod
    def now(cls, **kwargs: Any) -> SimulationManifest:
        return cls(created_at=datetime.now().astimezone().isoformat(timespec="seconds"), **kwargs)


@dataclass(slots=True)
class SimulationBundle:
    manifest: SimulationManifest
    ranking: Any
    argentina_stages: Any
    argentina_rivals: dict[str, Any]
    argentina_groups: Any
    final_pairs: Any
    top_brackets: list[dict[str, Any]]
    sensitivity: Any
    convergence: Any
    cluster_counts: dict[str, int] = field(default_factory=dict)
    samples: list[TournamentResult] = field(default_factory=list)
    sirius_assessments: dict[str, dict[str, Any]] = field(default_factory=dict)
    sirius_evidence_audit: dict[str, Any] = field(default_factory=dict)
