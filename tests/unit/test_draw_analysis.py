from packages.football import DrawEngine


def test_argentina_and_spain_are_anchored_in_opposite_sectors(scenario, teams) -> None:
    groups = DrawEngine(teams, scenario).draw(2030)
    assert groups["A"][0].team_id == "ARG"
    assert groups["I"][0].team_id == "ESP"
    assert scenario.bracket.opposite_group_offset == 8


def test_draw_analysis_has_probabilities_families_and_difficulty(scenario, teams) -> None:
    analysis = DrawEngine(teams, scenario).analyze(200, seed=7, validate_each=True)
    assert set(analysis.rival_probabilities) == {2, 3, 4}
    for rivals in analysis.rival_probabilities.values():
        assert abs(sum(float(item["probability"]) for item in rivals) - 1.0) < 1e-12
    assert analysis.group_families
    assert analysis.difficulty_bands["easy_max"] <= analysis.difficulty_bands["hard_min"]
    assert analysis.unique_states > 100


def test_100_000_draws_never_violate_constraints(scenario, teams) -> None:
    analysis = DrawEngine(teams, scenario).analyze(
        100_000,
        seed=2030,
        validate_each=True,
    )
    assert analysis.iterations == 100_000
    assert analysis.unique_states > 10_000
    assert analysis.lag_one_repeat_rate < 0.001
