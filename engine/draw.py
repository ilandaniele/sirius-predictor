from __future__ import annotations

import random
from collections import Counter
from collections.abc import Iterable

from .config import DrawSpec, Scenario
from .domain import Team


class DrawError(RuntimeError):
    """Raised when the projected field cannot satisfy the draw constraints."""


def group_valid(group: Iterable[Team], candidate: Team, draw: DrawSpec | None = None) -> bool:
    counts = Counter(team.confed for team in group)
    if draw is None:
        limit = 2 if candidate.confed == "UEFA" else 1
    else:
        limit = draw.confed_limit(candidate.confed)
    return counts[candidate.confed] < limit


def _assign_pot(
    groups: dict[str, list[Team]],
    pot_teams: list[Team],
    draw: DrawSpec,
    rng: random.Random,
) -> bool:
    pending_groups = list(groups)

    def search(remaining_groups: list[str], remaining_teams: list[Team]) -> bool:
        if not remaining_groups:
            return True
        candidate_map = {
            name: [team for team in remaining_teams if group_valid(groups[name], team, draw)]
            for name in remaining_groups
        }
        minimum = min(len(candidates) for candidates in candidate_map.values())
        if minimum == 0:
            return False
        constrained = [
            name for name, candidates in candidate_map.items() if len(candidates) == minimum
        ]
        group_name = rng.choice(constrained)
        candidates = candidate_map[group_name][:]
        rng.shuffle(candidates)
        next_groups = [name for name in remaining_groups if name != group_name]
        for team in candidates:
            groups[group_name].append(team)
            next_teams = [
                candidate for candidate in remaining_teams if candidate.team_id != team.team_id
            ]
            if search(next_groups, next_teams):
                return True
            groups[group_name].pop()
        return False

    return search(pending_groups, pot_teams)


def _group_is_valid(group: list[Team], draw: DrawSpec) -> bool:
    counts = Counter(team.confed for team in group)
    return all(count <= draw.confed_limit(confed) for confed, count in counts.items())


def _symmetric_swaps(
    groups: dict[str, list[Team]], scenario: Scenario, rng: random.Random, steps: int
) -> None:
    """Apply symmetric valid swap proposals to reduce construction-order effects.

    This Markov transition has a uniform stationary distribution over its connected state space.
    The manifest exposes the algorithm/version; it is an extrapolation, not an official FIFA draw.
    """

    names = list(groups)
    for _ in range(steps):
        pot = rng.randint(1, scenario.format.pots)
        left_name, right_name = rng.sample(names, 2)
        left_group, right_group = groups[left_name], groups[right_name]
        left_index = next(index for index, team in enumerate(left_group) if team.pot == pot)
        right_index = next(index for index, team in enumerate(right_group) if team.pot == pot)
        left_team, right_team = left_group[left_index], right_group[right_index]
        if (
            left_team.team_id in scenario.draw.anchor_groups
            or right_team.team_id in scenario.draw.anchor_groups
        ):
            continue
        left_group[left_index], right_group[right_index] = right_team, left_team
        if not (
            _group_is_valid(left_group, scenario.draw)
            and _group_is_valid(right_group, scenario.draw)
        ):
            left_group[left_index], right_group[right_index] = left_team, right_team


def validate_draw(groups: dict[str, list[Team]], scenario: Scenario) -> None:
    errors: list[str] = []
    if set(groups) != set(scenario.draw.group_names):
        errors.append("draw group names do not match the scenario")
    for team_id, expected_group in scenario.draw.anchor_groups.items():
        if expected_group not in groups or all(
            team.team_id != team_id for team in groups[expected_group]
        ):
            errors.append(f"anchored team {team_id} is not in group {expected_group}")
    seen: list[str] = []
    for name, group in groups.items():
        if len(group) != scenario.format.group_size:
            errors.append(f"group {name} has {len(group)} teams")
        pots = Counter(team.pot for team in group)
        expected_pots = set(range(1, scenario.format.pots + 1))
        if set(pots) != expected_pots or any(value != 1 for value in pots.values()):
            errors.append(f"group {name} does not contain exactly one team per pot")
        confeds = Counter(team.confed for team in group)
        for confed, count in confeds.items():
            if count > scenario.draw.confed_limit(confed):
                errors.append(f"group {name} violates {confed} limit")
        seen.extend(team.team_id for team in group)
    if len(seen) != scenario.format.teams or len(set(seen)) != len(seen):
        errors.append("draw must contain every team exactly once")
    if errors:
        raise DrawError("Invalid draw: " + "; ".join(errors))


def draw_groups(
    teams: list[Team], scenario: Scenario, rng: random.Random, attempts: int = 64
) -> dict[str, list[Team]]:
    by_pot = {
        pot: [team for team in teams if team.pot == pot]
        for pot in range(1, scenario.format.pots + 1)
    }
    for _ in range(attempts):
        groups = {name: [] for name in scenario.draw.group_names}
        anchored_ids = set(scenario.draw.anchor_groups)
        for team_id, group_name in scenario.draw.anchor_groups.items():
            matches = [team for team in by_pot[1] if team.team_id == team_id]
            if len(matches) != 1 or group_name not in groups:
                raise DrawError(f"invalid draw anchor: {team_id} -> {group_name}")
            groups[group_name].append(matches[0])
        first_pot = [team for team in by_pot[1] if team.team_id not in anchored_ids]
        rng.shuffle(first_pot)
        open_groups = [name for name in scenario.draw.group_names if not groups[name]]
        for name, team in zip(open_groups, first_pot, strict=True):
            groups[name].append(team)
        feasible = True
        for pot in range(2, scenario.format.pots + 1):
            pool = by_pot[pot][:]
            rng.shuffle(pool)
            if not _assign_pot(groups, pool, scenario.draw, rng):
                feasible = False
                break
        if feasible:
            _symmetric_swaps(groups, scenario, rng, scenario.draw.mcmc_swap_steps)
            for group in groups.values():
                group.sort(key=lambda team: team.pot)
            validate_draw(groups, scenario)
            return groups
    raise DrawError(
        "No legal draw was found. Validate pot sizes, confederation allocation and constraints."
    )


def draw_16_groups(df, seed: int | None = None, attempts: int = 64):
    """Compatibility adapter for the original DataFrame API."""

    from pathlib import Path

    from .config import load_scenario, load_teams

    del df  # The professional engine reads the validated canonical contract.
    root = Path(__file__).resolve().parents[1]
    scenario = load_scenario(root / "data" / "scenario.yaml")
    teams = load_teams(root / "data" / "teams.csv")
    return draw_groups(teams, scenario, random.Random(seed), attempts=attempts)
