import random

import numpy as np

from engine.model import FootballMatchModel
from engine.sirius import SiriusExperimentalLayer
from engine.tournament import simulate_tournament


def test_complete_tournament(scenario, teams):
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
    assert len(result.groups) == 16
    assert len(result.matches) == 127  # 96 group matches + 31 knockout matches
    assert len(result.semifinalists) == 4
    assert result.champion_id != result.runner_up_id
    assert result.stage_reached[result.champion_id] == "Champion"
    assert set(result.stage_reached) == {team.team_id for team in teams}
