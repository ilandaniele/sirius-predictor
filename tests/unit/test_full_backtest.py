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
    # Teams "A"/"B" have no data/historical_coaches_<edition>.json -- fortune_delta
    # falls back to neutral 0.0 everywhere, so gamma has nothing to fit and stays 0.
    assert manifests.loc[2010, "argumental_bonus_elo"] == 0.0
    assert manifests.loc[2014, "argumental_bonus_elo"] == 0.0
    assert result.next_edition_calibration["argumental_bonus_elo"] == 0.0
    assert result.leakage_audit.future_edition_used_for_calibration.eq(False).all()
    assert result.leakage_audit.same_match_used.eq(False).all()
    assert set(result.round_accuracy.stage) == {"Group", "F"}
    assert not result.champion_ranking.empty
    sirius_ranks = result.champion_ranking[
        result.champion_ranking.model.isin({"SIRIUS_PURIST", "SIRIUS_CALIBRATED"})
    ]
    assert sirius_ranks["rank"].isna().all()
    assert sirius_ranks.status.eq("not_evaluable_without_pre_tournament_forecast").all()
    first_edition_baselines = result.champion_ranking[
        (result.champion_ranking.edition == 2010)
        & result.champion_ranking.model.isin({"FOOTBALL_ONLY", "HYBRID"})
    ]
    assert first_edition_baselines["rank"].isna().all()
    assert first_edition_baselines.rank_min.eq(1).all()
    assert first_edition_baselines.rank_max.eq(2).all()
    assert first_edition_baselines.status.eq("tied_pre_tournament_rating").all()


def test_penalty_shootout_produces_auditable_champion() -> None:
    final = HistoricalMatch(
        edition=2022,
        kickoff=datetime(2022, 12, 18, 18, tzinfo=UTC),
        home="Argentina",
        away="France",
        home_goals=3,
        away_goals=3,
        penalty_home_goals=4,
        penalty_away_goals=2,
        time_quality="explicit_utc_offset",
        source_url="https://example.com/history",
        stage="F",
    )
    result = run_full_backtest([final])
    assert set(result.champion_ranking.champion) == {"Argentina"}


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
