from dataclasses import replace
from datetime import datetime
from zoneinfo import ZoneInfo

import numpy as np

from engine.model import FootballMatchModel, elo_expectation
from engine.sirius import SiriusExperimentalLayer, lunar_longitude
from packages.common.types import ModelMode


def test_probabilities_are_normalized(scenario, teams):
    # teams.csv carries no real Sirius prior (unsourced data was neutralized to 0 for
    # every team); inject synthetic, clearly-test-only values here so this test verifies
    # the scenario-proxy fallback mechanism itself, not production data content.
    synthetic_teams = [
        replace(team, sirius_index=0.3, sirius_confidence=0.6)
        if team.team_id == "ARG"
        else replace(team, sirius_index=-0.1, sirius_confidence=0.4)
        if team.team_id == "ESP"
        else team
        for team in teams
    ]
    layer = SiriusExperimentalLayer(scenario.models.max_sirius_elo_adjustment)
    model = FootballMatchModel(synthetic_teams, layer, mode="combined")
    ratings = {team.team_id: team.projected_elo for team in synthetic_teams}
    kickoff = datetime(2030, 7, 21, 18, tzinfo=ZoneInfo("Europe/Madrid"))
    probabilities = model.probabilities("ARG", "ESP", ratings, kickoff)
    assert np.isclose(probabilities.home + probabilities.draw + probabilities.away, 1.0)
    assert all(
        0 <= value <= 1 for value in (probabilities.home, probabilities.draw, probabilities.away)
    )
    assert probabilities.sirius_adjustment != 0


def test_expected_goals_uses_the_same_elo_scale_the_backtest_validates(teams):
    # engine.model.FootballMatchModel.expected_goals used to convert an Elo gap into a
    # goal share with a flatter /800 scale, while packages/football/backtest.py (the
    # module actually calibrated and validated against 360 real World Cup matches)
    # uses elo_expectation's standard /400 scale for the same purpose. That silent
    # mismatch made big favorites resolve far less decisively in the live simulation
    # than the calibrated model implies -- e.g. a ~440-point favorite winning only
    # ~72% of the time instead of the ~87-93% a real Elo gap that size predicts.
    layer = SiriusExperimentalLayer(0.0)
    model = FootballMatchModel(teams, layer, mode="baseline")
    home_rating, away_rating = 1960.0, 1520.0
    home_goals, away_goals = model.expected_goals(home_rating, away_rating)
    expected_share = elo_expectation(home_rating, away_rating)
    assert np.isclose(home_goals / model.total_goals, expected_share)
    assert np.isclose(home_goals + away_goals, model.total_goals)

    home_p, draw_p, away_p = model.probabilities_from_ratings(home_rating, away_rating)
    # A ~440-Elo-point favorite should win outright clearly more often than not, with
    # a real (not inflated) chance of a draw or upset -- not the previous ~72%/19%/9%.
    assert home_p > 0.8
    assert draw_p < 0.15
    assert away_p < 0.05


def test_host_nation_gets_a_football_only_edge_over_an_equal_rated_visitor(scenario, teams):
    # ARG (host) vs a non-host team with an artificially matched rating: without a
    # host boost this would be a 50/50 baseline; the host adjustment should tilt it.
    argentina = next(team for team in teams if team.team_id == "ARG")
    matched_teams = [
        replace(team, projected_elo=argentina.projected_elo, rating_uncertainty=0.0)
        if team.team_id == "BRA"
        else team
        for team in teams
    ]
    layer = SiriusExperimentalLayer(scenario.models.max_sirius_elo_adjustment)
    model = FootballMatchModel(matched_teams, layer, mode="baseline")
    ratings = {team.team_id: team.projected_elo for team in matched_teams}
    probabilities = model.probabilities("ARG", "BRA", ratings)
    assert probabilities.home > probabilities.away
    assert probabilities.baseline_home > probabilities.baseline_away


def test_host_edge_is_absent_in_sirius_only_ablation(scenario, teams):
    argentina = next(team for team in teams if team.team_id == "ARG")
    matched_teams = [
        replace(team, projected_elo=argentina.projected_elo, rating_uncertainty=0.0)
        if team.team_id == "BRA"
        else team
        for team in teams
    ]
    layer = SiriusExperimentalLayer(scenario.models.max_sirius_elo_adjustment)
    model = FootballMatchModel(matched_teams, layer, mode=ModelMode.SIRIUS_ONLY)
    assert model._host_bonus("ARG") == 0.0


def test_penalty_shootouts_are_dampened_toward_a_coin_flip(teams):
    layer = SiriusExperimentalLayer(0.0)
    model = FootballMatchModel(teams, layer, mode="baseline")
    strong, weak = 1900.0, 1500.0
    skill_probability = elo_expectation(strong, weak)
    dampened = 0.5 + (skill_probability - 0.5) * model.PENALTY_SKILL_WEIGHT
    assert 0.5 < dampened < skill_probability


def test_moon_sign_signal_uses_argentinas_published_record():
    from engine.sirius import moon_sign_signal

    # Leo (index 4): Sirius's own published record is 7W-2D-1L in 10 matches — a strongly
    # favorable, well-sampled record, so the shrinkage-dampened signal should be clearly
    # positive but still bounded to [-1, 1].
    leo_signal = moon_sign_signal("ARG", 4)
    assert 0.0 < leo_signal <= 1.0

    # Libra (index 6): 6W-0D-5L in 11 matches is close to a coin flip (Sirius himself
    # describes it as "mucha paridad"), so the signal should be small in magnitude.
    libra_signal = moon_sign_signal("ARG", 6)
    assert abs(libra_signal) < 0.2

    # An unlisted sign (e.g. Taurus, index 1) has no recorded evidence and must stay
    # neutral rather than being imputed.
    assert moon_sign_signal("ARG", 1) == 0.0

    # A team with no recorded Moon-sign evidence at all is always neutral.
    assert moon_sign_signal("ESP", 4) == 0.0


def test_temporal_component_only_activates_with_a_kickoff_and_known_evidence(scenario, teams):
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo

    from engine.sirius import SiriusExperimentalLayer, moon_sign_index

    argentina = next(team for team in teams if team.team_id == "ARG")
    layer = SiriusExperimentalLayer(scenario.models.max_sirius_elo_adjustment)

    # No kickoff: temporal stays neutral, exactly as before this feature existed.
    no_kickoff = layer.components(argentina, None, "F")
    assert no_kickoff["temporal"] == 0.0

    # The Moon cycles through all 12 signs in ~27-28 days, so scanning that span always
    # finds a date landing on a sign with known Argentina evidence (index 4, Leo) —
    # computed from the real ephemeris rather than assumed.
    start = datetime(2030, 7, 21, 12, tzinfo=ZoneInfo("UTC"))
    leo_kickoff = next(
        start + timedelta(hours=6 * step)
        for step in range(120)
        if moon_sign_index(start + timedelta(hours=6 * step)) == 4
    )
    with_kickoff = layer.components(argentina, leo_kickoff, "F")
    assert with_kickoff["temporal"] > 0.0
    assert with_kickoff["temporal_status"] == "historical_moon_sign_stats"


def test_lunar_value_and_hour_sensitivity():
    early = lunar_longitude(datetime(2030, 7, 21, 17, tzinfo=ZoneInfo("Europe/Madrid")))
    late = lunar_longitude(datetime(2030, 7, 21, 21, tzinfo=ZoneInfo("Europe/Madrid")))
    assert 0 <= early.longitude < 360
    assert 0 <= late.longitude < 360
    assert early.longitude != late.longitude
    assert early.provider in {"Swiss Ephemeris", "mean-lunar fallback"}
