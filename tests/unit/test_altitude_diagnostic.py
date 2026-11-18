from datetime import UTC, datetime

from engine.backtest import HistoricalMatch
from packages.football.backtest import altitude_diagnostic, match_altitude_m, run_full_backtest


def match(
    edition: int,
    day: int,
    home: str,
    away: str,
    score: tuple[int, int],
    venue: str | None,
):
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
        venue=venue,
    )


def test_match_altitude_resolves_known_venues_in_either_format() -> None:
    stadium_format = match(2010, 1, "A", "B", (1, 0), "Ellis Park Stadium, Johannesburg")
    city_only_format = match(2026, 1, "A", "B", (1, 0), "Mexico City")
    assert match_altitude_m(stadium_format) == 1753
    assert match_altitude_m(city_only_format) == 2240


def test_match_altitude_is_none_for_unknown_or_missing_venue() -> None:
    unknown_city = match(2010, 1, "A", "B", (1, 0), "Some New Stadium, Neverland")
    no_venue = match(2010, 1, "A", "B", (1, 0), None)
    assert match_altitude_m(unknown_city) is None
    assert match_altitude_m(no_venue) is None


def test_altitude_diagnostic_buckets_matches_and_never_recommends_applying() -> None:
    matches = [
        match(2010, 1, "A", "B", (1, 1), "Ellis Park Stadium, Johannesburg"),  # 1753m, draw
        match(2010, 2, "A", "B", (2, 0), "Cape Town Stadium, Cape Town"),  # 20m, decisive
        match(2010, 3, "A", "B", (0, 0), "Unmapped Ground, Neverland"),  # unmapped
    ]
    result = altitude_diagnostic(matches)
    assert result["matches_total"] == 3
    assert result["matches_mapped"] == 2
    assert result["venues_unmapped"] == ["Unmapped Ground, Neverland"]
    assert result["applied_to_model"] is False
    thresholds = result["thresholds_m"]
    assert isinstance(thresholds, dict)
    high_1200 = thresholds["1200"]["high_altitude"]
    low_1200 = thresholds["1200"]["low_altitude"]
    assert high_1200 == {"matches": 1, "draws": 1, "draw_rate": 100.0, "avg_goals": 2.0}
    assert low_1200 == {"matches": 1, "draws": 0, "draw_rate": 0.0, "avg_goals": 2.0}


def test_altitude_diagnostic_handles_no_mapped_matches() -> None:
    result = altitude_diagnostic([match(2010, 1, "A", "B", (1, 0), None)])
    assert result["matches_mapped"] == 0
    thresholds = result["thresholds_m"]
    assert isinstance(thresholds, dict)
    assert thresholds["1200"]["high_altitude"]["matches"] == 0


def test_run_full_backtest_includes_altitude_diagnostic() -> None:
    matches = [
        match(2010, 1, "A", "B", (1, 0), "Ellis Park Stadium, Johannesburg"),
        match(2010, 2, "A", "B", (2, 0), "Cape Town Stadium, Cape Town"),
    ]
    result = run_full_backtest(matches)
    assert result.altitude_diagnostic["matches_total"] == 2
    assert result.altitude_diagnostic["applied_to_model"] is False
