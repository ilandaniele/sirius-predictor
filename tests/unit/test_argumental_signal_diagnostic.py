import json
from pathlib import Path

import pytest

from engine import argumental
from engine.argumental import CycleFortune, argumental_signal_diagnostic
from engine.backtest import HistoricalMatch


def _match(stage: str, home: str, away: str, home_goals: int, away_goals: int) -> HistoricalMatch:
    return HistoricalMatch(
        edition=2099,
        kickoff=None,
        home=home,
        away=away,
        home_goals=home_goals,
        away_goals=away_goals,
        time_quality="exact",
        source_url="https://example.test",
        stage=stage,
    )


def _fortune(team_id: str, fortune_index: float) -> CycleFortune:
    return CycleFortune(
        team_id=team_id,
        coach_name="Test Coach",
        debut_label="test debut",
        solar_return_year=2099,
        solar_return_moment="2099-01-01T00:00:00+00:00",
        midheaven_sign="Leo",
        midheaven_ruler="Sun",
        midheaven_ruler_dignity="domicile",
        midheaven_ruler_house_class="angular",
        favorable_testimonies=(),
        adverse_testimonies=(),
        fortune_index=fortune_index,
        status="computed",
    )


def test_argumental_signal_diagnostic_reports_missing_coach_data(tmp_path: Path) -> None:
    result = argumental_signal_diagnostic([], 1930, data_dir=tmp_path)
    assert result["status"] == "no_historical_coach_data"
    assert result["teams_covered"] == 0


def test_argumental_signal_diagnostic_reports_insufficient_data(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "historical_coaches_2099.json").write_text(
        json.dumps({"coaches": {"A": {}}}), encoding="utf-8"
    )
    matches = [_match("Group", "A", "B", 1, 1)]

    monkeypatch.setattr(
        argumental,
        "historical_coach_cycle_fortune",
        lambda team, edition, data_dir=None: _fortune(team, 0.1) if team == "A" else None,
    )

    result = argumental_signal_diagnostic(matches, 2099, data_dir=tmp_path)
    assert result["status"] == "insufficient_data"
    assert result["teams_covered"] == 1


def test_argumental_signal_diagnostic_computes_perfect_correlation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    teams = ["A", "B", "C", "D", "E"]
    (tmp_path / "historical_coaches_2099.json").write_text(
        json.dumps({"coaches": {team: {} for team in teams}}), encoding="utf-8"
    )
    matches = [
        _match("F", "A", "B", 2, 1),  # A champion (rank 5), B final loser (rank 4)
        _match("SF", "C", "A", 0, 3),  # C semifinalist (rank 3)
        _match("Group", "D", "E", 1, 1),  # D, E eliminated in group (rank 0)
    ]
    fortune_by_team = {"A": 0.5, "B": 0.4, "C": 0.3, "D": 0.0, "E": 0.0}

    monkeypatch.setattr(
        argumental,
        "historical_coach_cycle_fortune",
        lambda team, edition, data_dir=None: _fortune(team, fortune_by_team[team]),
    )

    result = argumental_signal_diagnostic(matches, 2099, data_dir=tmp_path)

    assert result["champion"] == "A"
    assert result["teams_covered"] == 5
    assert result["pearson_r"] == pytest.approx(1.0, abs=1e-6)
    assert result["statistically_significant_p05"] is True
    assert result["advanced_past_group"] == {"n": 3, "mean_fortune_index": pytest.approx(0.4)}
    assert result["eliminated_in_group"] == {"n": 2, "mean_fortune_index": pytest.approx(0.0)}
    assert result["applied_to_model"] is False
    finding = result["finding"]
    assert isinstance(finding, str)
    assert "no es un backtest walk-forward completo" in finding.lower()
