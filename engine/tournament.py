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
    stats = {
        team_id: {"pts": 0, "gf": 0, "ga": 0, "lot": float(rng.random())} for team_id in team_ids
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
        elif match.away_goals > match.home_goals:
            away["pts"] += 3
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
    return ordered


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
        ranking = _rank_group([team.team_id for team in group], group_matches, rng)
        tables[group_name] = ranking
        qualifiers.append((group_name, ranking[0], ranking[1]))
        stage_reached[ranking[0]] = "R32"
        stage_reached[ranking[1]] = "R32"

    first = {group: winner for group, winner, _ in qualifiers}
    second = {group: runner for group, _, runner in qualifiers}
    letters = list(scenario.draw.group_names)
    current: list[str] = []
    for index, group_name in enumerate(letters):
        opponent_group = letters[(index + scenario.bracket.opposite_group_offset) % len(letters)]
        result = model.simulate(
            first[group_name],
            second[opponent_group],
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
