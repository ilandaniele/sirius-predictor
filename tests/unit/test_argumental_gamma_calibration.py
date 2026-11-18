from datetime import UTC, datetime

import pytest

import packages.football.backtest as backtest_module
from engine.backtest import HistoricalMatch
from packages.football.backtest import run_full_backtest


def match(edition: int, day: int, home: str, away: str, score: tuple[int, int]):
    return HistoricalMatch(
        edition=edition,
        kickoff=datetime(edition, 6, day, 18, tzinfo=UTC),
        home=home,
        away=away,
        home_goals=score[0],
        away_goals=score[1],
        time_quality="exact_utc",
        source_url="https://example.com/history",
        stage="Group",
    )


def test_gamma_stays_zero_without_any_researched_coach_data() -> None:
    matches = [match(2010, 1, "A", "B", (2, 0)), match(2014, 1, "B", "A", (0, 2))]
    result = run_full_backtest(matches)
    manifests = result.calibration_manifest.set_index("edition")
    assert manifests.loc[2010, "argumental_bonus_elo"] == 0.0
    assert manifests.loc[2014, "argumental_bonus_elo"] == 0.0


def test_gamma_calibrates_to_a_nonzero_weight_when_fortune_predicts_real_outcomes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # "High" always beats "Low" in the training edition (2010): a fortune_delta of
    # +2 (High's fortune=1.0 minus Low's fortune=-1.0) always coincides with a home
    # win here, a signal strong enough that a walk-forward fit on 2010 should pick
    # a real, nonzero Elo weight for 2014 (the edition it's evaluated against).
    monkeypatch.setattr(
        backtest_module,
        "_fortune_lookup",
        lambda edition: {"High": 1.0, "Low": -1.0},
    )

    matches = [
        match(2010, 1, "High", "Low", (3, 0)),
        match(2010, 2, "Low", "High", (0, 3)),
        match(2010, 3, "High", "Low", (2, 0)),
        match(2014, 1, "High", "Low", (1, 0)),
    ]
    result = run_full_backtest(matches)
    manifests = result.calibration_manifest.set_index("edition")
    assert manifests.loc[2010, "argumental_bonus_elo"] == 0.0  # nothing trained yet
    assert manifests.loc[2014, "argumental_bonus_elo"] > 0.0  # trained on 2010's real signal
