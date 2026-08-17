from __future__ import annotations

import random
from collections import defaultdict
from datetime import datetime
from itertools import combinations
from zoneinfo import ZoneInfo

import numpy as np

from .config import Scenario
from .domain import MatchResult, Team, TournamentResult
from .draw import draw_groups
from .model import FootballMatchModel

ROUND_SEQUENCE = ("R32", "R16", "QF", "SF", "F")
NEXT_STAGE = {"R32": "R16", "R16": "QF", "QF": "SF", "SF": "F", "F": "Champion"}


def _rank_group(
    team_ids: list[str], matches: list[MatchResult], rng: np.random.Generator
) -> list[str]:
    ranking, _ = _rank_group_with_stats(team_ids, matches, rng)
    return ranking


def _rank_group_with_stats(
    team_ids: list[str], matches: list[MatchResult], rng: np.random.Generator
) -> tuple[list[str], dict[str, dict[str, float]]]:
    stats = {
        team_id: {"pts": 0.0, "gf": 0.0, "ga": 0.0, "wins": 0.0, "lot": float(rng.random())}
        for team_id in team_ids
    }
    for match in matches:
        home = stats[match.home_id]
        away = stats[match.away_id]
        home["gf"] += match.home_goals
        home["ga"] += match.away_goals
        away["gf"] += match.away_goals
        away["ga"] += match.home_goals
        if match.home_goals > match.away_goals:
            home["pts"] += 3
            home["wins"] += 1
        elif match.away_goals > match.home_goals:
            away["pts"] += 3
            away["wins"] += 1
        else:
            home["pts"] += 1
            away["pts"] += 1

    def primary(team_id: str) -> tuple[int, int, int]:
        row = stats[team_id]
        return int(row["pts"]), int(row["gf"] - row["ga"]), int(row["gf"])

    buckets: dict[tuple[int, int, int], list[str]] = defaultdict(list)
    for team_id in team_ids:
        buckets[primary(team_id)].append(team_id)
    ordered: list[str] = []
    for key in sorted(buckets, reverse=True):
        tied = buckets[key]
        if len(tied) == 1:
            ordered.extend(tied)
            continue
        head = {team_id: {"pts": 0, "gf": 0, "ga": 0} for team_id in tied}
        for match in matches:
            if match.home_id not in head or match.away_id not in head:
                continue
            home, away = head[match.home_id], head[match.away_id]
            home["gf"] += match.home_goals
            home["ga"] += match.away_goals
            away["gf"] += match.away_goals
            away["ga"] += match.home_goals
            if match.home_goals > match.away_goals:
                home["pts"] += 3
            elif match.away_goals > match.home_goals:
                away["pts"] += 3
            else:
                home["pts"] += 1
                away["pts"] += 1
        tied.sort(
            key=lambda team_id: (
                head[team_id]["pts"],
                head[team_id]["gf"] - head[team_id]["ga"],
                head[team_id]["gf"],
                stats[team_id]["lot"],
            ),
            reverse=True,
        )
        ordered.extend(tied)
    return ordered, stats


def _cross_group_order(
    team_ids: list[str], stats: dict[str, dict[str, float]]
) -> list[str]:
    """Rank teams from different groups with the available sporting tiebreakers.

    Fair-play points are not simulated. The pre-sampled lot is therefore the
    final deterministic-for-seed tiebreaker and is recorded by the simulation.
    """

    return sorted(
        team_ids,
        key=lambda team_id: (
            stats[team_id]["pts"],
            stats[team_id]["gf"] - stats[team_id]["ga"],
            stats[team_id]["gf"],
            stats[team_id]["wins"],
            stats[team_id]["lot"],
        ),
        reverse=True,
    )


def _projected_48_pairings(
    seeded: list[str],
    unseeded: list[str],
    team_groups: dict[str, str],
    scenario: Scenario,
) -> list[tuple[str, str]]:
    """Create a reproducible projected R32 while avoiding same-group rematches."""

    group_index = {name: index for index, name in enumerate(scenario.draw.group_names)}

    def preference(seed: str, opponent: str) -> tuple[int, str]:
        target = (
            group_index[team_groups[seed]] + scenario.bracket.opposite_group_offset
        ) % scenario.format.groups
        opponent_index = group_index[team_groups[opponent]]
        distance = min(
            (opponent_index - target) % scenario.format.groups,
            (target - opponent_index) % scenario.format.groups,
        )
        return distance, opponent

    def search(index: int, remaining: tuple[str, ...]) -> list[tuple[str, str]] | None:
        if index == len(seeded):
            return []
        seed = seeded[index]
        candidates = sorted(
            (team for team in remaining if team_groups[team] != team_groups[seed]),
            key=lambda team: preference(seed, team),
        )
        for opponent in candidates:
            tail = search(index + 1, tuple(team for team in remaining if team != opponent))
            if tail is not None:
                return [(seed, opponent), *tail]
        return None

    pairings = search(0, tuple(unseeded))
    if pairings is None:
        raise RuntimeError("the projected 48-team R32 could not avoid same-group rematches")
    return pairings


def _final_kickoff(scenario: Scenario, final_hour: int) -> datetime:
    date = datetime.fromisoformat(scenario.final.local_date)
    return datetime(
        date.year,
        date.month,
        date.day,
        final_hour,
        0,
        tzinfo=ZoneInfo(scenario.final.timezone),
    )


def simulate_tournament(
    teams: list[Team],
    scenario: Scenario,
    model: FootballMatchModel,
    rng: np.random.Generator,
    draw_rng: random.Random,
    final_hour: int,
) -> TournamentResult:
    groups = draw_groups(teams, scenario, draw_rng)
    ratings = {
        team.team_id: float(rng.normal(team.projected_elo, team.rating_uncertainty))
        for team in teams
    }
    matches: list[MatchResult] = []
    tables: dict[str, list[str]] = {}
    qualifiers: list[tuple[str, str, str]] = []
    group_stats: dict[str, dict[str, float]] = {}
    team_groups: dict[str, str] = {}
    stage_reached = {team.team_id: "Group" for team in teams}
    group_match_index = 0
    for group_name, group in groups.items():
        group_matches: list[MatchResult] = []
        for home, away in combinations(group, 2):
            result = model.simulate(
                home.team_id,
                away.team_id,
                ratings,
                rng,
                round_name="Group",
                match_index=group_match_index,
                knockout=False,
            )
            group_match_index += 1
            group_matches.append(result)
            matches.append(result)
        ranking, stats = _rank_group_with_stats(
            [team.team_id for team in group], group_matches, rng
        )
        group_stats.update(stats)
        team_groups.update({team.team_id: group_name for team in group})
        tables[group_name] = ranking
        qualifiers.append((group_name, ranking[0], ranking[1]))
        stage_reached[ranking[0]] = "R32"
        stage_reached[ranking[1]] = "R32"

    first = {group: winner for group, winner, _ in qualifiers}
    second = {group: runner for group, _, runner in qualifiers}
    letters = list(scenario.draw.group_names)
    if scenario.format.best_third_placed:
        thirds = _cross_group_order(
            [tables[group][2] for group in letters], group_stats
        )[: scenario.format.best_third_placed]
        for team_id in thirds:
            stage_reached[team_id] = "R32"
        ordered_runners = _cross_group_order(list(second.values()), group_stats)
        seeded = [first[group] for group in letters] + ordered_runners[:4]
        unseeded = ordered_runners[4:] + thirds
        r32_pairings = _projected_48_pairings(
            seeded, unseeded, team_groups, scenario
        )
    else:
        r32_pairings = [
            (
                first[group_name],
                second[
                    letters[
                        (index + scenario.bracket.opposite_group_offset) % len(letters)
                    ]
                ],
            )
            for index, group_name in enumerate(letters)
        ]
    current: list[str] = []
    for index, (home_id, away_id) in enumerate(r32_pairings):
        result = model.simulate(
            home_id,
            away_id,
            ratings,
            rng,
            round_name="R32",
            match_index=index,
            knockout=True,
        )
        matches.append(result)
        current.append(str(result.winner_id))
        stage_reached[str(result.winner_id)] = "R16"

    semifinalists: tuple[str, ...] = ()
    runner_up = ""
    for round_name in ("R16", "QF", "SF", "F"):
        if round_name == "SF":
            semifinalists = tuple(current)
        next_round: list[str] = []
        for index in range(0, len(current), 2):
            kickoff = _final_kickoff(scenario, final_hour) if round_name == "F" else None
            result = model.simulate(
                current[index],
                current[index + 1],
                ratings,
                rng,
                round_name=round_name,
                match_index=index // 2,
                knockout=True,
                kickoff=kickoff,
            )
            matches.append(result)
            winner = str(result.winner_id)
            next_round.append(winner)
            stage_reached[winner] = NEXT_STAGE[round_name]
            if round_name == "F":
                runner_up = result.away_id if winner == result.home_id else result.home_id
        current = next_round

    return TournamentResult(
        groups={name: [team.team_id for team in group] for name, group in groups.items()},
        group_tables=tables,
        matches=matches,
        champion_id=current[0],
        runner_up_id=runner_up,
        semifinalists=semifinalists,
        stage_reached=stage_reached,
    )
