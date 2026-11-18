from collections import Counter
from dataclasses import replace

import pytest

from engine.config import ScenarioValidationError, validate_scenario


def test_fixed_scenario_contract(scenario, teams):
    validate_scenario(scenario, teams)
    assert scenario.scenario_id == "mundial-2030-sirius-v3"
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
    argentina = next(team for team in teams if team.team_id == "ARG")
    assert argentina.coach == "Lionel Scaloni"
    assert argentina.captain == "Cristian Romero"
    assert argentina.as_of == "2026-08-31"
    assert scenario.assumptions["argentina_captain"] == "Cristian Romero"
    assert scenario.assumptions["argentina_captain_natal_source"] == (
        "natal_cristian_romero"
    )
    assert scenario.assumptions["messi_retirement_source"] == (
        "messi_international_retirement_2026"
    )
    assert scenario.final.sensitivity_minutes == (-15, 0, 15)


def test_argentina_captain_cannot_drift_from_the_versioned_scenario(scenario, teams):
    altered = [
        replace(team, captain="Enzo Fernández") if team.team_id == "ARG" else team
        for team in teams
    ]
    with pytest.raises(ScenarioValidationError, match="Argentina captain"):
        validate_scenario(scenario, altered)
