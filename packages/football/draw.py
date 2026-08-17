from __future__ import annotations

import random
from collections import Counter, defaultdict
from collections.abc import Iterator
from dataclasses import dataclass
from statistics import fmean

from engine.config import Scenario
from engine.domain import Team
from engine.draw import _group_is_valid, draw_groups, validate_draw


@dataclass(slots=True)
class DrawAnalysis:
    iterations: int
    target_id: str
    rival_probabilities: dict[int, list[dict[str, float | str]]]
    group_families: list[dict[str, float | int | str]]
    difficulty_bands: dict[str, float]
    unique_states: int
    lag_one_repeat_rate: float


class DrawEngine:
    def __init__(self, teams: list[Team], scenario: Scenario):
        self.teams = teams
        self.scenario = scenario
        self.team_map = {team.team_id: team for team in teams}

    def draw(self, seed: int) -> dict[str, list[Team]]:
        return draw_groups(self.teams, self.scenario, random.Random(seed))

    def _propose_swap(self, groups: dict[str, list[Team]], rng: random.Random) -> bool:
        names = list(groups)
        pot = rng.randint(1, self.scenario.format.pots)
        left_name, right_name = rng.sample(names, 2)
        left = groups[left_name]
        right = groups[right_name]
        left_index = next(index for index, team in enumerate(left) if team.pot == pot)
        right_index = next(index for index, team in enumerate(right) if team.pot == pot)
        left_team, right_team = left[left_index], right[right_index]
        anchors = self.scenario.draw.anchor_groups
        if left_team.team_id in anchors or right_team.team_id in anchors:
            return False
        left[left_index], right[right_index] = right_team, left_team
        if _group_is_valid(left, self.scenario.draw) and _group_is_valid(right, self.scenario.draw):
            return True
        left[left_index], right[right_index] = left_team, right_team
        return False

    @staticmethod
    def _signature(groups: dict[str, list[Team]]) -> str:
        return "|".join(",".join(team.team_id for team in group) for group in groups.values())

    def iter_legal_draws(
        self,
        count: int,
        seed: int,
        swaps_between_samples: int = 4,
    ) -> Iterator[dict[str, list[Team]]]:
        if count <= 0:
            raise ValueError("count must be positive")
        if swaps_between_samples <= 0:
            raise ValueError("swaps_between_samples must be positive")
        rng = random.Random(seed)
        groups = draw_groups(self.teams, self.scenario, rng)
        for _ in range(count):
            accepted = 0
            attempts = 0
            while accepted < swaps_between_samples and attempts < swaps_between_samples * 16:
                accepted += int(self._propose_swap(groups, rng))
                attempts += 1
            if accepted == 0:
                raise RuntimeError("draw chain could not find a legal transition")
            yield groups

    def analyze(
        self,
        count: int,
        seed: int = 2030,
        target_id: str = "ARG",
        validate_each: bool = False,
    ) -> DrawAnalysis:
        if target_id not in self.team_map:
            raise ValueError(f"unknown target team: {target_id}")
        rivals: dict[int, Counter[str]] = defaultdict(Counter)
        families: Counter[str] = Counter()
        difficulties: list[float] = []
        seen: set[str] = set()
        previous_signature: str | None = None
        repeated = 0
        for groups in self.iter_legal_draws(count, seed):
            if validate_each:
                validate_draw(groups, self.scenario)
            signature = self._signature(groups)
            seen.add(signature)
            repeated += int(signature == previous_signature)
            previous_signature = signature
            target_group = next(
                group
                for group in groups.values()
                if any(team.team_id == target_id for team in group)
            )
            opponents = [team for team in target_group if team.team_id != target_id]
            for team in opponents:
                rivals[team.pot][team.team_id] += 1
            family = "/".join(sorted(team.confed for team in opponents))
            families[family] += 1
            difficulties.append(fmean(team.projected_elo for team in opponents))
        ordered = sorted(difficulties)

        def quantile(fraction: float) -> float:
            return ordered[min(len(ordered) - 1, int(fraction * (len(ordered) - 1)))]

        return DrawAnalysis(
            iterations=count,
            target_id=target_id,
            rival_probabilities={
                pot: [
                    {
                        "team_id": team_id,
                        "team": self.team_map[team_id].team,
                        "probability": occurrences / count,
                    }
                    for team_id, occurrences in counts.most_common()
                ]
                for pot, counts in sorted(rivals.items())
            },
            group_families=[
                {"family": family, "count": occurrences, "probability": occurrences / count}
                for family, occurrences in families.most_common()
            ],
            difficulty_bands={"easy_max": quantile(1 / 3), "hard_min": quantile(2 / 3)},
            unique_states=len(seen),
            lag_one_repeat_rate=repeated / count,
        )
