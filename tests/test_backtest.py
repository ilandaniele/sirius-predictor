from engine.backtest import parse_openfootball, run_backtest

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


def test_backtest_compares_models_without_future_data():
    matches = parse_openfootball(SAMPLE, 2014, "fixture")
    result = run_backtest(matches)
    assert set(result.metrics["Modelo"]) == {"Baseline Elo", "Baseline + Sirius"}
    assert len(result.predictions) == 6
    assert not result.calibration.empty
    assert result.predictions["Brier"].ge(0).all()
    assert result.predictions["Log loss"].ge(0).all()
