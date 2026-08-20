from dataclasses import replace
from datetime import UTC, datetime

import pytest

from engine.backtest import (
    HistoricalDataValidationError,
    HistoricalMatch,
    parse_openfootball,
    run_backtest,
    validate_historical_edition,
)

SAMPLE = """
= World Cup 2014
Thu Jun 12
  17:00 UTC-3  Brazil v Croatia  3-1 (1-1) @ Arena
Fri Jun 13
  13:00 UTC-3  Mexico  1-0 (0-0)  Cameroon @ Stadium
Tue Jun 17
  16:00 UTC-3  Brazil  0-0  Mexico @ Arena
"""


def test_parser_supports_both_openfootball_styles():
    matches = parse_openfootball(SAMPLE, 2014, "fixture")
    assert len(matches) == 3
    assert (matches[0].home, matches[0].away) == ("Brazil", "Croatia")
    assert (matches[1].home, matches[1].away) == ("Mexico", "Cameroon")
    assert matches[0].kickoff == datetime(2014, 6, 12, 20, tzinfo=UTC)


def test_parser_removes_match_annotations_and_records_penalties() -> None:
    sample = """
= World Cup 2026
▪ Round of 32
Sun Jun 28
  (73) 12:00 UTC-7  South Africa 0-1 (0-0) Canada @ Stadium
Mon Jun 29
  (74) 16:30 UTC-4  Germany 1-1 a.e.t. (1-1, 0-1), 3-4 pen. Paraguay @ Stadium
"""
    matches = parse_openfootball(sample, 2026, "fixture")
    assert (matches[0].home, matches[0].away) == ("South Africa", "Canada")
    assert matches[0].match_number == 73
    assert (matches[1].home, matches[1].away) == ("Germany", "Paraguay")
    assert (matches[1].penalty_home_goals, matches[1].penalty_away_goals) == (3, 4)
    assert matches[1].winner == "Paraguay"


def test_parser_does_not_invent_utc_when_timezone_is_missing() -> None:
    matches = parse_openfootball(
        """= World Cup 2022\nSun Nov 20\n  19:00 Qatar 2-0 Ecuador @ Stadium\n""",
        2022,
        "fixture",
    )
    assert matches[0].kickoff is None
    assert matches[0].time_quality == "listed_time_timezone_unknown"


def test_historical_shape_validation_rejects_leaked_score_annotations() -> None:
    stages = ["Group"] * 48 + ["R16"] * 8 + ["QF"] * 4
    stages += ["SF"] * 2 + ["ThirdPlace", "F"]
    teams = [f"Team {index:02d}" for index in range(32)]
    matches = [
        HistoricalMatch(
            edition=2022,
            kickoff=None,
            home=teams[index % 32],
            away=teams[(index + 1) % 32],
            home_goals=1,
            away_goals=0,
            time_quality="date_only",
            source_url="https://example.com/history",
            stage=stage,
            source_sequence=index,
        )
        for index, stage in enumerate(stages)
    ]
    validate_historical_edition(matches, 2022)
    matches[0] = replace(matches[0], home="(0-0) Team 00")
    with pytest.raises(HistoricalDataValidationError, match="team"):
        validate_historical_edition(matches, 2022)


def test_backtest_compares_models_without_future_data():
    matches = parse_openfootball(SAMPLE, 2014, "fixture")
    result = run_backtest(matches)
    assert set(result.metrics["Modelo"]) == {"Baseline Elo", "Baseline + Sirius"}
    assert len(result.predictions) == 6
    assert not result.calibration.empty
    assert result.predictions["Brier"].ge(0).all()
    assert result.predictions["Log loss"].ge(0).all()
