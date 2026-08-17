from datetime import datetime
from zoneinfo import ZoneInfo

import numpy as np

from engine.model import FootballMatchModel
from engine.sirius import SiriusExperimentalLayer, lunar_longitude


def test_probabilities_are_normalized(scenario, teams):
    layer = SiriusExperimentalLayer(scenario.models.max_sirius_elo_adjustment)
    model = FootballMatchModel(teams, layer, mode="combined")
    ratings = {team.team_id: team.projected_elo for team in teams}
    kickoff = datetime(2030, 7, 21, 18, tzinfo=ZoneInfo("Europe/Madrid"))
    probabilities = model.probabilities("ARG", "ESP", ratings, kickoff)
    assert np.isclose(probabilities.home + probabilities.draw + probabilities.away, 1.0)
    assert all(
        0 <= value <= 1 for value in (probabilities.home, probabilities.draw, probabilities.away)
    )
    assert probabilities.sirius_adjustment != 0


def test_lunar_value_and_hour_sensitivity():
    early = lunar_longitude(datetime(2030, 7, 21, 17, tzinfo=ZoneInfo("Europe/Madrid")))
    late = lunar_longitude(datetime(2030, 7, 21, 21, tzinfo=ZoneInfo("Europe/Madrid")))
    assert 0 <= early.longitude < 360
    assert 0 <= late.longitude < 360
    assert early.longitude != late.longitude
    assert early.provider in {"Swiss Ephemeris", "mean-lunar fallback"}
