from __future__ import annotations

import math
from datetime import datetime

import numpy as np

from packages.common.types import ModelMode

from .domain import MatchProbabilities, MatchResult, Team
from .sirius import SiriusExperimentalLayer


def elo_expectation(a: float, b: float) -> float:
    return float(1.0 / (1.0 + 10.0 ** ((b - a) / 400.0)))


def p_win(a: float, b: float) -> float:
    """Compatibility alias for the original engine API."""

    return elo_expectation(a, b)


def sample_strength(row, rng: np.random.Generator) -> float:
    """Sample one tournament-level football rating, keeping data confidence separate."""

    rating = float(getattr(row, "projected_elo", 1500.0))
    uncertainty = float(getattr(row, "rating_uncertainty", 0.0))
    return float(rng.normal(rating, uncertainty))


def _poisson_mass(lam: float, maximum: int = 10) -> np.ndarray:
    values = [math.exp(-lam)]
    for goals in range(1, maximum + 1):
        values.append(values[-1] * lam / goals)
    return np.asarray(values, dtype=float)


class FootballMatchModel:
    """Versioned Elo-Poisson football baseline with an optional bounded Sirius layer.

    Two football-analytics adjustments, independent of the Sirius layer:

    - ``host_advantage_elo``: the intuitive claim ("hosts overperform their
      seeding") does NOT survive contact with the real prequential backtest in
      packages/football/backtest.py, which calibrates this exact parameter
      by grid-searching log-loss against every real World Cup, walk-forward
      with no leakage. The evidence-backed value moves as more editions are
      played — South Africa 2010 and Qatar 2022 both underperformed as
      hosts while Brazil 2014 and Russia 2018 overperformed, so a fit
      trained only through 2022 lands at 0.0, while the fit trained through
      2026 (the one actually used to forecast a not-yet-played tournament)
      lands at +50 — well below the ~100 Elo figure often cited for generic
      tournament home advantage. The class-level default of 0.0 here is
      just the conservative fallback for callers that skip calibration
      entirely (e.g. unit tests); real runs always pass in a freshly
      computed value. See packages/football/backtest.py::HOST_BONUS_CANDIDATES
      / _select_beta / next_edition_calibration for how to recompute it as
      new World Cups complete.
    - ``penalty_skill_weight``: shootout research (e.g. Bar-Eli et al. on
      penalty psychology) finds outcomes are close to a coin flip regardless
      of overall team quality — pressure and individual randomness dominate
      far more than in 90 minutes of open play. The Elo-implied skill edge is
      therefore heavily dampened toward 0.5 rather than applied at full
      strength.

    Both are constructor parameters, not just class constants, so a caller
    (e.g. the publish pipeline) can pass in a freshly recalibrated value
    without touching this file.
    """

    HOST_ADVANTAGE_ELO = 0.0
    PENALTY_SKILL_WEIGHT = 0.35

    def __init__(
        self,
        teams: list[Team],
        sirius: SiriusExperimentalLayer,
        mode: str | ModelMode = ModelMode.HYBRID,
        total_goals: float = 2.65,
        host_advantage_elo: float | None = None,
        penalty_skill_weight: float | None = None,
    ):
        aliases = {
            "baseline": ModelMode.FOOTBALL_ONLY,
            "combined": ModelMode.HYBRID,
            "sirius": ModelMode.SIRIUS_ONLY,
        }
        normalized_mode = aliases.get(str(mode))
        if normalized_mode is None:
            try:
                normalized_mode = ModelMode(str(mode))
            except ValueError as exc:
                raise ValueError("mode must be FOOTBALL_ONLY, SIRIUS_ONLY or HYBRID") from exc
        self.teams = {team.team_id: team for team in teams}
        self.sirius = sirius
        self.mode = normalized_mode
        self.total_goals = float(total_goals)
        self.HOST_ADVANTAGE_ELO = (
            float(host_advantage_elo)
            if host_advantage_elo is not None
            else type(self).HOST_ADVANTAGE_ELO
        )
        self.PENALTY_SKILL_WEIGHT = (
            float(penalty_skill_weight)
            if penalty_skill_weight is not None
            else type(self).PENALTY_SKILL_WEIGHT
        )

    def _host_bonus(self, team_id: str) -> float:
        if self.mode == ModelMode.SIRIUS_ONLY:
            return 0.0
        team = self.teams.get(team_id)
        return self.HOST_ADVANTAGE_ELO if team is not None and team.host else 0.0

    def expected_goals(self, home_rating: float, away_rating: float) -> tuple[float, float]:
        share = 1.0 / (1.0 + 10.0 ** ((away_rating - home_rating) / 800.0))
        return self.total_goals * share, self.total_goals * (1.0 - share)

    def probabilities_from_ratings(
        self, home_rating: float, away_rating: float
    ) -> tuple[float, float, float]:
        home_lambda, away_lambda = self.expected_goals(home_rating, away_rating)
        home_mass = _poisson_mass(home_lambda)
        away_mass = _poisson_mass(away_lambda)
        matrix = np.outer(home_mass, away_mass)
        home = float(np.tril(matrix, -1).sum())
        draw = float(np.trace(matrix))
        away = float(np.triu(matrix, 1).sum())
        total = home + draw + away
        return home / total, draw / total, away / total

    def probabilities(
        self,
        home_id: str,
        away_id: str,
        ratings: dict[str, float],
        kickoff: datetime | None = None,
        round_name: str | None = None,
    ) -> MatchProbabilities:
        home_host_bonus = self._host_bonus(home_id)
        away_host_bonus = self._host_bonus(away_id)
        baseline = self.probabilities_from_ratings(
            ratings[home_id] + home_host_bonus, ratings[away_id] + away_host_bonus
        )
        adjustment = 0.0
        if self.mode != ModelMode.FOOTBALL_ONLY:
            adjustment = self.sirius.matchup_delta(
                self.teams[home_id], self.teams[away_id], kickoff, round_name
            )
        model_home = ratings[home_id] + home_host_bonus
        model_away = ratings[away_id] + away_host_bonus
        if self.mode == ModelMode.SIRIUS_ONLY:
            model_home = 1500.0
            model_away = 1500.0
        combined = self.probabilities_from_ratings(
            model_home + adjustment / 2,
            model_away - adjustment / 2,
        )
        return MatchProbabilities(
            home=combined[0],
            draw=combined[1],
            away=combined[2],
            baseline_home=baseline[0],
            baseline_draw=baseline[1],
            baseline_away=baseline[2],
            sirius_adjustment=adjustment,
        )

    def simulate(
        self,
        home_id: str,
        away_id: str,
        ratings: dict[str, float],
        rng: np.random.Generator,
        round_name: str,
        match_index: int,
        knockout: bool,
        kickoff: datetime | None = None,
    ) -> MatchResult:
        probabilities = self.probabilities(home_id, away_id, ratings, kickoff, round_name)
        adjustment = probabilities.sirius_adjustment
        model_home = ratings[home_id] + self._host_bonus(home_id)
        model_away = ratings[away_id] + self._host_bonus(away_id)
        if self.mode == ModelMode.SIRIUS_ONLY:
            model_home = 1500.0
            model_away = 1500.0
        home_lambda, away_lambda = self.expected_goals(
            model_home + adjustment / 2,
            model_away - adjustment / 2,
        )
        home_goals = int(rng.poisson(home_lambda))
        away_goals = int(rng.poisson(away_lambda))
        decided_by = "regulation"
        if home_goals > away_goals:
            winner = home_id
        elif away_goals > home_goals:
            winner = away_id
        elif not knockout:
            winner = None
            decided_by = "draw"
        else:
            extra_home = int(rng.poisson(home_lambda / 3.0))
            extra_away = int(rng.poisson(away_lambda / 3.0))
            home_goals += extra_home
            away_goals += extra_away
            if home_goals > away_goals:
                winner = home_id
                decided_by = "extra_time"
            elif away_goals > home_goals:
                winner = away_id
                decided_by = "extra_time"
            else:
                skill_probability = elo_expectation(
                    model_home + adjustment / 2,
                    model_away - adjustment / 2,
                )
                penalty_probability = 0.5 + (skill_probability - 0.5) * self.PENALTY_SKILL_WEIGHT
                winner = home_id if rng.random() < penalty_probability else away_id
                decided_by = "penalties"
        return MatchResult(
            round_name=round_name,
            match_index=match_index,
            home_id=home_id,
            away_id=away_id,
            home_goals=home_goals,
            away_goals=away_goals,
            winner_id=winner,
            decided_by=decided_by,
            probabilities=probabilities,
        )
