from collections import Counter

from engine.config import validate_scenario


def test_fixed_scenario_contract(scenario, teams):
    validate_scenario(scenario, teams)
    assert len(teams) == 64
    assert Counter(team.pot for team in teams) == {1: 16, 2: 16, 3: 16, 4: 16}
    assert {team.team_id for team in teams if team.host} == {
        "ESP",
        "POR",
        "MAR",
        "ARG",
        "PAR",
        "UR",
    }
    assert next(team for team in teams if team.team_id == "ARG").coach == "Lionel Scaloni"
    assert scenario.final.sensitivity_minutes == (-15, 0, 15)
