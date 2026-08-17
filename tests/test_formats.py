import random
from pathlib import Path

import numpy as np

from engine.config import load_scenario, load_teams, teams_for_scenario, validate_scenario
from engine.model import FootballMatchModel
from engine.sirius import SiriusExperimentalLayer
from engine.tournament import simulate_tournament

ROOT = Path(__file__).resolve().parents[1]


def test_48_team_projection_and_tournament_are_complete() -> None:
    scenario = load_scenario(ROOT / "data" / "scenario-48.yaml")
    teams = teams_for_scenario(load_teams(ROOT / "data" / "teams.csv"), scenario)
    validate_scenario(scenario, teams)
    assert len(teams) == 48
    assert {pot: sum(team.pot == pot for team in teams) for pot in range(1, 5)} == {
        1: 12,
        2: 12,
        3: 12,
        4: 12,
    }
    assert {team.team_id for team in teams if team.host} == set(scenario.hosts)

    model = FootballMatchModel(
        teams,
        SiriusExperimentalLayer(scenario.models.max_sirius_elo_adjustment),
        mode="baseline",
    )
    result = simulate_tournament(
        teams,
        scenario,
        model,
        np.random.default_rng(2030),
        random.Random(2030),
        final_hour=18,
    )
    assert len(result.groups) == 12
    assert len(result.matches) == 103  # 72 group matches + 31 knockout matches.
    assert sum(stage != "Group" for stage in result.stage_reached.values()) == 32
    group_by_team = {
        team_id: group_name
        for group_name, team_ids in result.groups.items()
        for team_id in team_ids
    }
    r32 = [match for match in result.matches if match.round_name == "R32"]
    assert len(r32) == 16
    assert all(group_by_team[match.home_id] != group_by_team[match.away_id] for match in r32)


def test_64_is_unchanged_and_default() -> None:
    scenario = load_scenario(ROOT / "data" / "scenario.yaml")
    canonical = load_teams(ROOT / "data" / "teams.csv")
    assert teams_for_scenario(canonical, scenario) == canonical
    assert scenario.format.teams == 64
    assert scenario.format.best_third_placed == 0
