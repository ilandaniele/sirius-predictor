from engine.sim import run_engine
from packages.common.types import ModelMode


def test_three_model_modes_are_separate_and_reproducible(scenario, teams) -> None:
    outputs = {mode: run_engine(teams, scenario, n=40, seed=55, mode=mode) for mode in ModelMode}
    assert {bundle.manifest.mode for bundle in outputs.values()} == {
        mode.value for mode in ModelMode
    }
    football_again = run_engine(
        teams,
        scenario,
        n=40,
        seed=55,
        mode=ModelMode.FOOTBALL_ONLY,
    )
    assert outputs[ModelMode.FOOTBALL_ONLY].ranking["Campeón %"].tolist() == (
        football_again.ranking["Campeón %"].tolist()
    )
    football = outputs[ModelMode.FOOTBALL_ONLY].ranking.set_index("ID")["Campeón %"]
    sirius = outputs[ModelMode.SIRIUS_ONLY].ranking.set_index("ID")["Campeón %"]
    assert not football.equals(sirius)


def test_sirius_components_do_not_invent_missing_round_times(scenario, teams) -> None:
    from engine.sirius import SiriusExperimentalLayer

    argentina = next(team for team in teams if team.team_id == "ARG")
    components = SiriusExperimentalLayer().components(argentina, None, "QF")
    assert components["annual"] == 0
    assert components["temporal"] == 0
    assert components["temporal_status"] == "neutral_missing_round_time"
