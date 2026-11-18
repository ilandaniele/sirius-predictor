from __future__ import annotations

import csv
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import yaml

from .domain import Team


class ScenarioValidationError(ValueError):
    """Raised when scenario data violates a structural invariant."""

    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("Invalid scenario:\n- " + "\n- ".join(errors))


@dataclass(frozen=True, slots=True)
class FormatSpec:
    teams: int
    pots: int
    pot_size: int
    groups: int
    group_size: int
    qualifiers_per_group: int
    best_third_placed: int = 0


@dataclass(frozen=True, slots=True)
class DrawSpec:
    version: str
    group_names: tuple[str, ...]
    confederation_limits: dict[str, int]
    sampling: str
    mcmc_swap_steps: int
    anchor_groups: dict[str, str]

    def confed_limit(self, confed: str) -> int:
        return int(self.confederation_limits.get(confed, self.confederation_limits["default"]))


@dataclass(frozen=True, slots=True)
class BracketSpec:
    version: str
    description: str
    opposite_group_offset: int


@dataclass(frozen=True, slots=True)
class FinalSpec:
    city: str
    local_date: str
    timezone: str
    base_hour: int
    sensitivity_hours: tuple[int, ...]
    sensitivity_minutes: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class ModelSpec:
    baseline_version: str
    sirius_version: str
    max_sirius_elo_adjustment: float
    sirius_observations_file: str = "data/sirius_observations.yaml"


@dataclass(frozen=True, slots=True)
class Scenario:
    scenario_id: str
    name: str
    status: str
    as_of: str
    format: FormatSpec
    hosts: tuple[str, ...]
    host_pot: int
    draw: DrawSpec
    bracket: BracketSpec
    final: FinalSpec
    assumptions: dict[str, str]
    models: ModelSpec


def _date_text(value: Any) -> str:
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def load_scenario(path: str | Path) -> Scenario:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return Scenario(
        scenario_id=str(raw["id"]),
        name=str(raw["name"]),
        status=str(raw["status"]),
        as_of=_date_text(raw["as_of"]),
        format=FormatSpec(**raw["format"]),
        hosts=tuple(raw["hosts"]["teams"]),
        host_pot=int(raw["hosts"]["pot"]),
        draw=DrawSpec(
            version=str(raw["draw"]["version"]),
            group_names=tuple(raw["draw"]["group_names"]),
            confederation_limits={
                str(key): int(value) for key, value in raw["draw"]["confederation_limits"].items()
            },
            sampling=str(raw["draw"]["sampling"]),
            mcmc_swap_steps=int(raw["draw"]["mcmc_swap_steps"]),
            anchor_groups={
                str(team_id): str(group_name)
                for team_id, group_name in raw["draw"].get("anchor_groups", {}).items()
            },
        ),
        bracket=BracketSpec(**raw["bracket"]),
        final=FinalSpec(
            city=str(raw["final"]["city"]),
            local_date=_date_text(raw["final"]["local_date"]),
            timezone=str(raw["final"]["timezone"]),
            base_hour=int(raw["final"]["base_hour"]),
            sensitivity_hours=tuple(int(v) for v in raw["final"]["sensitivity_hours"]),
            sensitivity_minutes=tuple(int(v) for v in raw["final"]["sensitivity_minutes"]),
        ),
        assumptions={str(k): str(v) for k, v in raw["assumptions"].items()},
        models=ModelSpec(**raw["models"]),
    )


def load_teams(path: str | Path) -> list[Team]:
    with Path(path).open(encoding="utf-8", newline="") as handle:
        rows = csv.DictReader(handle)
        return [
            Team(
                team_id=row["team_id"].strip(),
                team=row["team"].strip(),
                confed=row["confed"].strip(),
                host=row["host"].strip() == "1",
                pot=int(row["pot"]),
                projected_elo=float(row["projected_elo"]),
                rating_uncertainty=float(row["rating_uncertainty"]),
                sirius_index=float(row["sirius_index"]),
                sirius_confidence=float(row["sirius_confidence"]),
                qualification_status=row["qualification_status"].strip(),
                coach=row["coach"].strip(),
                captain=row["captain"].strip(),
                source_id=row["source_id"].strip(),
                as_of=row["as_of"].strip(),
            )
            for row in rows
        ]


def teams_for_scenario(teams: list[Team], scenario: Scenario) -> list[Team]:
    """Derive a deterministic 48/64-team field from the canonical projection.

    The six configured hosts are retained. Remaining places and rebuilt pots
    follow the existing projected Elo. This is a scenario projection, never an
    assertion that a team has officially qualified.
    """

    if scenario.format.teams == len(teams) and all(
        sum(team.pot == pot for team in teams) == scenario.format.pot_size
        for pot in range(1, scenario.format.pots + 1)
    ):
        return list(teams)
    if scenario.format.teams not in {48, 64}:
        raise ScenarioValidationError(
            [f"only 48 and 64 team projections are supported, got {scenario.format.teams}"]
        )

    hosts = [team for team in teams if team.team_id in scenario.hosts]
    if len(hosts) != len(scenario.hosts):
        raise ScenarioValidationError(["the canonical field does not contain every host"])
    non_hosts = sorted(
        (team for team in teams if team.team_id not in scenario.hosts),
        key=lambda team: (-team.projected_elo, team.team_id),
    )
    selected = hosts + non_hosts[: scenario.format.teams - len(hosts)]
    host_ids = {team.team_id for team in hosts}
    ordered_non_hosts = sorted(
        (team for team in selected if team.team_id not in host_ids),
        key=lambda team: (-team.projected_elo, team.team_id),
    )
    pot_assignments = {team.team_id: scenario.host_pot for team in hosts}
    cursor = 0
    for pot in range(1, scenario.format.pots + 1):
        places = (
            scenario.format.pot_size - len(hosts)
            if pot == scenario.host_pot
            else scenario.format.pot_size
        )
        for team in ordered_non_hosts[cursor : cursor + places]:
            pot_assignments[team.team_id] = pot
        cursor += places
    projected = [replace(team, pot=pot_assignments[team.team_id]) for team in selected]
    return sorted(projected, key=lambda team: (team.pot, -team.projected_elo, team.team_id))


def validate_scenario(scenario: Scenario, teams: list[Team]) -> None:
    errors: list[str] = []
    spec = scenario.format
    if len(teams) != spec.teams:
        errors.append(f"expected {spec.teams} teams, found {len(teams)}")
    ids = [team.team_id for team in teams]
    names = [team.team for team in teams]
    if len(set(ids)) != len(ids):
        errors.append("team_id values must be unique")
    if len(set(names)) != len(names):
        errors.append("team names must be unique")
    if spec.pots * spec.pot_size != spec.teams:
        errors.append("pots * pot_size must equal teams")
    if spec.groups * spec.group_size != spec.teams:
        errors.append("groups * group_size must equal teams")
    if spec.groups * spec.qualifiers_per_group + spec.best_third_placed != 32:
        errors.append("group qualification must produce a 32-team knockout field")
    if len(scenario.draw.group_names) != spec.groups:
        errors.append("group_names count must equal groups")
    for pot in range(1, spec.pots + 1):
        count = sum(team.pot == pot for team in teams)
        if count != spec.pot_size:
            errors.append(f"pot {pot} must have {spec.pot_size} teams, found {count}")
    actual_hosts = {team.team_id for team in teams if team.host}
    expected_hosts = set(scenario.hosts)
    if actual_hosts != expected_hosts:
        errors.append(
            f"host ids differ: expected {sorted(expected_hosts)}, found {sorted(actual_hosts)}"
        )
    wrong_host_pot = [team.team_id for team in teams if team.host and team.pot != scenario.host_pot]
    if wrong_host_pot:
        errors.append(f"hosts outside pot {scenario.host_pot}: {wrong_host_pot}")
    confeds = {team.confed for team in teams}
    for confed in confeds:
        count = sum(team.confed == confed for team in teams)
        capacity = spec.groups * scenario.draw.confed_limit(confed)
        if count > capacity:
            errors.append(f"{confed} has {count} teams but draw capacity is {capacity}")
    for team in teams:
        if not 0.0 <= team.sirius_confidence <= 1.0:
            errors.append(f"{team.team_id}: sirius_confidence outside [0, 1]")
        if team.rating_uncertainty < 0:
            errors.append(f"{team.team_id}: rating_uncertainty must be non-negative")
    argentina = next((team for team in teams if team.team_id == "ARG"), None)
    if argentina is None or argentina.coach != scenario.assumptions["argentina_coach"]:
        errors.append("Argentina coach does not match the fixed scenario assumption")
    if argentina is None or argentina.captain != scenario.assumptions["argentina_captain"]:
        errors.append("Argentina captain does not match the fixed scenario assumption")
    if errors:
        raise ScenarioValidationError(errors)
