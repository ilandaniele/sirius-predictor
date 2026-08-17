import math
from datetime import UTC, datetime

from engine.backtest import HistoricalMatch
from packages.football.backtest import BACKTEST_MODELS, run_full_backtest


def match(edition: int, day: int, home: str, away: str, score: tuple[int, int], stage: str):
    return HistoricalMatch(
        edition=edition,
        kickoff=datetime(edition, 6, day, 18, tzinfo=UTC),
        home=home,
        away=away,
        home_goals=score[0],
        away_goals=score[1],
        time_quality="exact_utc",
        source_url="https://example.com/history",
        stage=stage,
    )


def test_full_backtest_uses_only_prior_editions_for_calibration() -> None:
    matches = [
        match(2010, 1, "A", "B", (1, 0), "Group"),
        match(2010, 2, "A", "B", (2, 0), "F"),
        match(2014, 1, "A", "B", (0, 1), "Group"),
        match(2014, 2, "B", "A", (1, 0), "F"),
    ]
    result = run_full_backtest(matches)
    assert set(result.metrics.model) == set(BACKTEST_MODELS)
    manifests = result.calibration_manifest.set_index("edition")
    assert manifests.loc[2010, "trained_on_editions"] == []
    assert manifests.loc[2014, "trained_on_editions"] == [2010]
    assert result.leakage_audit.future_edition_used_for_calibration.eq(False).all()
    assert result.leakage_audit.same_match_used.eq(False).all()
    assert set(result.round_accuracy.stage) == {"Group", "F"}
    assert not result.champion_ranking.empty


def test_unavailable_ablations_are_reported_instead_of_invented() -> None:
    result = run_full_backtest(
        [
            match(2010, 1, "A", "B", (1, 0), "Group"),
            match(2010, 2, "A", "B", (1, 0), "F"),
        ]
    )
    unavailable = result.ablations[result.ablations.feature == "solar_return"].iloc[0]
    assert unavailable.status == "not_evaluable_missing_pre_match_data"
    assert math.isnan(unavailable.without_log_loss)
