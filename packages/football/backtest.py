from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TypedDict

import pandas as pd  # type: ignore[import-untyped]

from engine.backtest import HistoricalMatch
from engine.model import elo_expectation
from engine.sirius import moon_sign_index

BACKTEST_MODELS = (
    "FOOTBALL_ONLY",
    "SIRIUS_PURIST",
    "SIRIUS_CALIBRATED",
    "HYBRID",
)
ABLATION_FEATURES = (
    "coach_cycle",
    "world_cup_debut",
    "solar_return",
    "lunar_return",
    "quarti_lunar",
    "part_of_fortune",
    "fixed_stars",
    "antiscia",
    "eclipses",
    "historical_moon_sign",
)


@dataclass(slots=True)
class FullBacktestResult:
    predictions: pd.DataFrame
    metrics: pd.DataFrame
    calibration: pd.DataFrame
    champion_ranking: pd.DataFrame
    round_accuracy: pd.DataFrame
    ablations: pd.DataFrame
    leakage_audit: pd.DataFrame
    calibration_manifest: pd.DataFrame


class CalibrationRecord(TypedDict):
    home_rating: float
    away_rating: float
    moon_delta: float
    actual_index: int


def _probabilities(home_rating: float, away_rating: float) -> tuple[float, float, float]:
    expectation = elo_expectation(home_rating, away_rating)
    draw = 0.27 * math.exp(-abs(home_rating - away_rating) / 700.0)
    decisive = 1.0 - draw
    return decisive * expectation, draw, decisive * (1 - expectation)


def _actual(match: HistoricalMatch) -> tuple[tuple[float, float, float], float, str]:
    if match.home_goals > match.away_goals:
        return (1.0, 0.0, 0.0), 1.0, match.home
    if match.home_goals < match.away_goals:
        return (0.0, 0.0, 1.0), 0.0, match.away
    return (0.0, 1.0, 0.0), 0.5, "draw"


def _argmax(values: tuple[float, float, float]) -> int:
    return max(range(len(values)), key=values.__getitem__)


def _select_alpha(history: list[CalibrationRecord]) -> float:
    if not history:
        return 1.0
    candidates = [index / 8 for index in range(17)]
    losses = []
    for alpha in candidates:
        total = 0.0
        for row in history:
            probabilities = _probabilities(
                row["home_rating"] + alpha * row["moon_delta"] / 2,
                row["away_rating"] - alpha * row["moon_delta"] / 2,
            )
            total -= math.log(max(probabilities[row["actual_index"]], 1e-12))
        losses.append(total / len(history))
    return float(candidates[min(range(len(losses)), key=losses.__getitem__)])


def _metrics(predictions: pd.DataFrame) -> pd.DataFrame:
    return (
        predictions.groupby("model", as_index=False)
        .agg(
            matches=("brier", "size"),
            log_loss=("log_loss", "mean"),
            brier=("brier", "mean"),
            accuracy=("correct", "mean"),
        )
        .sort_values("log_loss")
    )


def _calibration(predictions: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, row in predictions.iterrows():
        for index, probability in enumerate((row.p_home, row.p_draw, row.p_away)):
            bin_index = min(9, int(float(probability) * 10))
            rows.append(
                {
                    "model": row.model,
                    "bin": bin_index,
                    "probability": float(probability),
                    "observed": int(index == row.actual_index),
                }
            )
    return (
        pd.DataFrame(rows)
        .groupby(["model", "bin"], as_index=False)
        .agg(
            mean_probability=("probability", "mean"),
            observed_frequency=("observed", "mean"),
            cases=("observed", "size"),
        )
    )


def _champion(matches: list[HistoricalMatch]) -> str | None:
    finals = [match for match in matches if match.stage == "F"]
    if not finals:
        return None
    return finals[-1].winner


def run_full_backtest(matches: list[HistoricalMatch]) -> FullBacktestResult:
    if not matches:
        raise ValueError("backtest requires matches")
    ordered = sorted(
        matches,
        key=lambda item: (
            item.edition,
            item.source_sequence is None,
            item.source_sequence if item.source_sequence is not None else 0,
            item.kickoff or datetime(item.edition, 1, 1, tzinfo=UTC),
            item.home,
            item.away,
        ),
    )
    ratings: defaultdict[str, float] = defaultdict(lambda: 1500.0)
    moon_history: defaultdict[tuple[str, int], list[float]] = defaultdict(list)
    calibration_history: list[CalibrationRecord] = []
    prediction_rows: list[dict[str, object]] = []
    leakage_rows: list[dict[str, object]] = []
    calibration_rows: list[dict[str, object]] = []
    champion_rows: list[dict[str, object]] = []

    by_edition: dict[int, list[HistoricalMatch]] = defaultdict(list)
    for match in ordered:
        by_edition[match.edition].append(match)

    previous_editions: list[int] = []
    for edition in sorted(by_edition):
        edition_matches = by_edition[edition]
        alpha = _select_alpha(calibration_history)
        calibration_rows.append(
            {
                "edition": edition,
                "alpha": alpha,
                "trained_on_editions": previous_editions.copy(),
                "same_edition_excluded": True,
            }
        )
        participants = {team for match in edition_matches for team in (match.home, match.away)}
        champion = _champion(edition_matches)
        if champion is not None:
            champion_rating = ratings[champion]
            rank_min = 1 + sum(ratings[team] > champion_rating for team in participants)
            rank_max = sum(ratings[team] >= champion_rating for team in participants)
            unique_rank = rank_min if rank_min == rank_max else None
            for model in BACKTEST_MODELS:
                rank_evaluable = model in {"FOOTBALL_ONLY", "HYBRID"}
                champion_rows.append(
                    {
                        "edition": edition,
                        "model": model,
                        "champion": champion,
                        "rank": unique_rank if rank_evaluable else None,
                        "rank_min": rank_min if rank_evaluable else None,
                        "rank_max": rank_max if rank_evaluable else None,
                        "participants": len(participants),
                        "status": (
                            "evaluated_pre_tournament_rating"
                            if rank_evaluable and unique_rank is not None
                            else "tied_pre_tournament_rating"
                            if rank_evaluable
                            else "not_evaluable_without_pre_tournament_forecast"
                        ),
                    }
                )

        edition_calibration: list[CalibrationRecord] = []
        for sequence, match in enumerate(edition_matches):
            actual, elo_score, _winner = _actual(match)
            actual_index = _argmax(actual)
            home_rating = ratings[match.home]
            away_rating = ratings[match.away]
            moon_delta = 0.0
            sign = None
            if match.kickoff is not None:
                sign = moon_sign_index(match.kickoff)
                home_records = moon_history[(match.home, sign)]
                away_records = moon_history[(match.away, sign)]
                home_rate = (sum(home_records) + 1.0) / (len(home_records) + 2.0)
                away_rate = (sum(away_records) + 1.0) / (len(away_records) + 2.0)
                moon_delta = 40.0 * (home_rate - away_rate)
            probabilities = {
                "FOOTBALL_ONLY": _probabilities(home_rating, away_rating),
                "SIRIUS_PURIST": _probabilities(1500 + moon_delta / 2, 1500 - moon_delta / 2),
                "SIRIUS_CALIBRATED": _probabilities(
                    1500 + alpha * moon_delta / 2,
                    1500 - alpha * moon_delta / 2,
                ),
                "HYBRID": _probabilities(
                    home_rating + alpha * moon_delta / 2,
                    away_rating - alpha * moon_delta / 2,
                ),
            }
            cutoff = (
                match.kickoff.isoformat()
                if match.kickoff
                else f"{edition}:sequence:{sequence}:before_observation"
            )
            for model, forecast in probabilities.items():
                prediction_rows.append(
                    {
                        "edition": edition,
                        "stage": match.stage,
                        "sequence": sequence,
                        "knowledge_cutoff": cutoff,
                        "home": match.home,
                        "away": match.away,
                        "model": model,
                        "p_home": forecast[0],
                        "p_draw": forecast[1],
                        "p_away": forecast[2],
                        "actual_index": actual_index,
                        "brier": sum(
                            (probability - outcome) ** 2
                            for probability, outcome in zip(forecast, actual, strict=True)
                        ),
                        "log_loss": -math.log(max(forecast[actual_index], 1e-12)),
                        "correct": int(_argmax(forecast) == actual_index),
                        "alpha": alpha,
                        "moon_delta": moon_delta,
                    }
                )
            leakage_rows.append(
                {
                    "edition": edition,
                    "sequence": sequence,
                    "cutoff": cutoff,
                    "rating_updates_before_prediction": sequence,
                    "same_match_used": False,
                    "future_edition_used_for_calibration": False,
                }
            )
            expected = elo_expectation(home_rating, away_rating)
            change = 24.0 * (elo_score - expected)
            ratings[match.home] += change
            ratings[match.away] -= change
            if sign is not None:
                moon_history[(match.home, sign)].append(elo_score)
                moon_history[(match.away, sign)].append(1.0 - elo_score)
            edition_calibration.append(
                {
                    "home_rating": home_rating,
                    "away_rating": away_rating,
                    "moon_delta": moon_delta,
                    "actual_index": actual_index,
                }
            )
        calibration_history.extend(edition_calibration)
        previous_editions.append(edition)

    predictions = pd.DataFrame(prediction_rows)
    metrics = _metrics(predictions)
    round_accuracy = (
        predictions.groupby(["model", "stage"], as_index=False)
        .agg(matches=("correct", "size"), accuracy=("correct", "mean"))
        .sort_values(["model", "stage"])
    )
    baseline = metrics.set_index("model").loc["FOOTBALL_ONLY", "log_loss"]
    ablation_rows = []
    for feature in ABLATION_FEATURES:
        if feature == "historical_moon_sign":
            without = predictions[predictions.model == "FOOTBALL_ONLY"].log_loss.mean()
            full = predictions[predictions.model == "HYBRID"].log_loss.mean()
            ablation_rows.append(
                {
                    "feature": feature,
                    "status": "evaluated_out_of_sample",
                    "full_log_loss": full,
                    "without_log_loss": without,
                    "delta_without_minus_full": without - full,
                }
            )
        else:
            ablation_rows.append(
                {
                    "feature": feature,
                    "status": "not_evaluable_missing_pre_match_data",
                    "full_log_loss": baseline,
                    "without_log_loss": None,
                    "delta_without_minus_full": None,
                }
            )
    return FullBacktestResult(
        predictions=predictions,
        metrics=metrics,
        calibration=_calibration(predictions),
        champion_ranking=pd.DataFrame(champion_rows),
        round_accuracy=round_accuracy,
        ablations=pd.DataFrame(ablation_rows),
        leakage_audit=pd.DataFrame(leakage_rows),
        calibration_manifest=pd.DataFrame(calibration_rows),
    )
