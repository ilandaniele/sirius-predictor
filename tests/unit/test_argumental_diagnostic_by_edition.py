from pathlib import Path

import pytest

import packages.football.backtest as backtest_module
from engine.backtest import HistoricalMatch
from packages.football.backtest import argumental_diagnostic_by_edition


def _match(edition: int) -> HistoricalMatch:
    return HistoricalMatch(
        edition=edition,
        kickoff=None,
        home="A",
        away="B",
        home_goals=1,
        away_goals=0,
        time_quality="exact",
        source_url="https://example.test",
        stage="Group",
    )


def _fake_result(rows: list[tuple[float, int, str]]) -> dict[str, object]:
    return {
        "teams_covered": len(rows),
        "rows": [{"team": team, "fortune_index": x, "stage_rank": y} for x, y, team in rows],
    }


def test_argumental_diagnostic_by_edition_reports_covered_and_pending(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "historical_coaches_2001.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(backtest_module, "ARGUMENTAL_DATA_DIR", tmp_path)
    monkeypatch.setattr(
        backtest_module,
        "_team_argumental_diagnostic",
        lambda matches, edition: _fake_result([(0.1, 1, "X")]),
    )

    result = argumental_diagnostic_by_edition([_match(2001), _match(2003)])

    assert result["editions_covered"] == [2001]
    assert result["editions_pending_research"] == [2003]
    assert set(result["by_edition"]) == {"2001"}
    assert result["pooled"] is None  # only one edition covered -- nothing to pool
    assert result["applied_to_model"] is False


def test_argumental_diagnostic_by_edition_pools_rows_across_covered_editions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "historical_coaches_2001.json").write_text("{}", encoding="utf-8")
    (tmp_path / "historical_coaches_2002.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(backtest_module, "ARGUMENTAL_DATA_DIR", tmp_path)

    per_edition = {
        2001: _fake_result([(0.5, 5, "X"), (0.4, 4, "Y"), (0.0, 0, "Z")]),
        2002: _fake_result([(0.3, 4, "X"), (-0.1, 0, "Y"), (0.0, 0, "Z")]),
    }
    monkeypatch.setattr(
        backtest_module,
        "_team_argumental_diagnostic",
        lambda matches, edition: per_edition[edition],
    )

    result = argumental_diagnostic_by_edition([_match(2001), _match(2002), _match(2003)])

    assert result["editions_covered"] == [2001, 2002]
    assert result["editions_pending_research"] == [2003]
    pooled = result["pooled"]
    assert pooled is not None
    assert pooled["editions"] == [2001, 2002]
    assert pooled["teams_covered"] == 6
    assert pooled["applied_to_model"] is False
    finding = pooled["finding"]
    assert isinstance(finding, str)
    assert "2001" in finding and "2002" in finding


def test_argumental_diagnostic_by_edition_handles_no_coach_data_at_all() -> None:
    result = argumental_diagnostic_by_edition([_match(1930)])
    assert result["editions_covered"] == []
    assert result["editions_pending_research"] == [1930]
    assert result["pooled"] is None
