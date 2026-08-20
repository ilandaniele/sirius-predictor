from __future__ import annotations

import hashlib
import math
import re
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta, timezone

import numpy as np
import pandas as pd
import requests

from .model import elo_expectation
from .sirius import moon_sign_index
from .updates import USER_AGENT, StateStore

EDITION_FOLDERS = {
    2010: "2010--south_africa",
    2014: "2014--brazil",
    2018: "2018--russia",
    2022: "2022--qatar",
    2026: "2026--canada-usa-mexico",
}
RAW_BASE = "https://raw.githubusercontent.com/openfootball/worldcup/master"
DATE_RE = re.compile(
    r"^\s*(?:▪.*?\|\s*)?(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+"
    r"(?P<month>Jan|Feb|Mar|Apr|May|Jun|June|Jul|Aug|Sep|Oct|Nov|Dec)\s+"
    r"(?P<day>\d{1,2})"
)
SCORE_RE = re.compile(r"\s(?P<home_goals>\d+)-(?P<away_goals>\d+)(?:\s|$)")
TIME_RE = re.compile(
    r"^\s*(?:\((?P<match_number>\d+)\)\s*)?"
    r"(?P<hour>\d{1,2}):(?P<minute>\d{2})"
    r"(?:\s+UTC(?P<utc_offset>[+-]\d{1,2}(?::\d{2})?))?\s+"
)
EXTRA_TIME_RE = re.compile(r"^a\.e\.t\.?\s*", re.IGNORECASE)
SCORE_DETAIL_RE = re.compile(r"^\([^)]*\)\s*,?\s*")
PENALTY_RE = re.compile(
    r"^(?P<home_penalties>\d+)-(?P<away_penalties>\d+)\s+pen\.?\s*",
    re.IGNORECASE,
)
EXPECTED_EDITION_SHAPES = {
    2010: (64, 32),
    2014: (64, 32),
    2018: (64, 32),
    2022: (64, 32),
    2026: (104, 48),
}
EXPECTED_STAGE_COUNTS = {
    32: {"Group": 48, "R16": 8, "QF": 4, "SF": 2, "ThirdPlace": 1, "F": 1},
    48: {
        "Group": 72,
        "R32": 16,
        "R16": 8,
        "QF": 4,
        "SF": 2,
        "ThirdPlace": 1,
        "F": 1,
    },
}
MONTHS = {
    "Jan": 1,
    "Feb": 2,
    "Mar": 3,
    "Apr": 4,
    "May": 5,
    "Jun": 6,
    "June": 6,
    "Jul": 7,
    "Aug": 8,
    "Sep": 9,
    "Oct": 10,
    "Nov": 11,
    "Dec": 12,
}
ALIASES = {
    "United States": "USA",
    "United States of America": "USA",
    "Korea Republic": "South Korea",
    "IR Iran": "Iran",
}


@dataclass(frozen=True, slots=True)
class HistoricalMatch:
    edition: int
    kickoff: datetime | None
    home: str
    away: str
    home_goals: int
    away_goals: int
    time_quality: str
    source_url: str
    stage: str = "unknown"
    match_number: int | None = None
    penalty_home_goals: int | None = None
    penalty_away_goals: int | None = None
    source_sequence: int | None = None

    @property
    def winner(self) -> str | None:
        if self.home_goals > self.away_goals:
            return self.home
        if self.away_goals > self.home_goals:
            return self.away
        if self.penalty_home_goals is None or self.penalty_away_goals is None:
            return None
        if self.penalty_home_goals > self.penalty_away_goals:
            return self.home
        if self.penalty_away_goals > self.penalty_home_goals:
            return self.away
        return None


@dataclass(slots=True)
class BacktestResult:
    run_id: str
    metrics: pd.DataFrame
    predictions: pd.DataFrame
    calibration: pd.DataFrame
    data_quality: pd.DataFrame


class HistoricalDataValidationError(ValueError):
    pass


def _clean_team(value: str) -> str:
    name = re.sub(r"\s+", " ", value).strip(" ,")
    return ALIASES.get(name, name)


def _utc_offset(value: str) -> timezone:
    sign = -1 if value.startswith("-") else 1
    hours_text, _, minutes_text = value[1:].partition(":")
    offset = timedelta(hours=int(hours_text), minutes=int(minutes_text or "0"))
    return timezone(sign * offset)


def _away_and_penalties(value: str) -> tuple[str, int | None, int | None]:
    remainder = value.strip()
    remainder = EXTRA_TIME_RE.sub("", remainder, count=1)
    while True:
        reduced = SCORE_DETAIL_RE.sub("", remainder, count=1)
        if reduced == remainder:
            break
        remainder = reduced
    penalty = PENALTY_RE.match(remainder)
    if penalty is None:
        return _clean_team(remainder), None, None
    remainder = remainder[penalty.end() :]
    return (
        _clean_team(remainder),
        int(penalty.group("home_penalties")),
        int(penalty.group("away_penalties")),
    )


def parse_openfootball(text: str, edition: int, source_url: str) -> list[HistoricalMatch]:
    current_date: tuple[int, int] | None = None
    current_stage = "unknown"
    matches: list[HistoricalMatch] = []
    for source_sequence, raw_line in enumerate(text.splitlines()):
        heading = raw_line.casefold()
        if "third place" in heading or "third-place" in heading:
            current_stage = "ThirdPlace"
        elif "final" in heading and "semi" not in heading and "quarter" not in heading:
            current_stage = "F"
        elif "semi-final" in heading or "semifinal" in heading:
            current_stage = "SF"
        elif "quarter-final" in heading or "quarterfinal" in heading:
            current_stage = "QF"
        elif "round of 16" in heading or "last 16" in heading:
            current_stage = "R16"
        elif "round of 32" in heading or "last 32" in heading:
            current_stage = "R32"
        elif "group" in heading:
            current_stage = "Group"
        match_line = raw_line
        date_match = DATE_RE.match(raw_line)
        if date_match:
            current_date = (MONTHS[date_match.group("month")], int(date_match.group("day")))
            match_line = raw_line[date_match.end() :]
        if "@" not in match_line:
            continue
        score_match = SCORE_RE.search(match_line)
        if score_match is None:
            continue
        prefix = match_line[: score_match.start()]
        time_match = TIME_RE.match(prefix)
        if time_match:
            home = prefix[time_match.end() :]
            quality = (
                "explicit_utc_offset"
                if time_match.group("utc_offset")
                else "listed_time_timezone_unknown"
            )
        else:
            home = prefix
            quality = "date_only"
        penalty_home_goals = None
        penalty_away_goals = None
        if re.search(r"\s+v\s+", home):
            home, away = re.split(r"\s+v\s+", home, maxsplit=1)
        else:
            before_venue = match_line[score_match.end() :].split("@", 1)[0].strip()
            if not before_venue:
                continue
            away, penalty_home_goals, penalty_away_goals = _away_and_penalties(before_venue)
        kickoff = None
        if current_date and time_match and time_match.group("utc_offset"):
            local_kickoff = datetime(
                edition,
                current_date[0],
                current_date[1],
                int(time_match.group("hour")),
                int(time_match.group("minute")),
                tzinfo=_utc_offset(time_match.group("utc_offset")),
            )
            kickoff = local_kickoff.astimezone(UTC)
        matches.append(
            HistoricalMatch(
                edition=edition,
                kickoff=kickoff,
                home=_clean_team(home),
                away=_clean_team(away),
                home_goals=int(score_match.group("home_goals")),
                away_goals=int(score_match.group("away_goals")),
                time_quality=quality,
                source_url=source_url,
                stage=current_stage,
                match_number=(
                    int(time_match.group("match_number"))
                    if time_match and time_match.group("match_number")
                    else None
                ),
                penalty_home_goals=penalty_home_goals,
                penalty_away_goals=penalty_away_goals,
                source_sequence=source_sequence,
            )
        )
    return matches


def validate_historical_edition(matches: list[HistoricalMatch], edition: int) -> None:
    expected_matches, expected_teams = EXPECTED_EDITION_SHAPES[edition]
    teams = {team for match in matches for team in (match.home, match.away)}
    suspicious = sorted(
        team
        for team in teams
        if not team
        or team.startswith("(")
        or "a.e.t" in team.casefold()
        or " pen." in team.casefold()
        or re.match(r"^\d{1,3}:\d{2}\b", team)
    )
    finals = [match for match in matches if match.stage == "F"]
    stage_counts = Counter(match.stage for match in matches)
    if len(matches) != expected_matches:
        raise HistoricalDataValidationError(
            f"{edition}: expected {expected_matches} matches, parsed {len(matches)}"
        )
    if len(teams) != expected_teams:
        raise HistoricalDataValidationError(
            f"{edition}: expected {expected_teams} teams, parsed {len(teams)}"
        )
    if suspicious:
        raise HistoricalDataValidationError(
            f"{edition}: score or time annotations leaked into team names: {suspicious[:5]}"
        )
    if stage_counts != EXPECTED_STAGE_COUNTS[expected_teams]:
        raise HistoricalDataValidationError(
            f"{edition}: unexpected stage counts: {dict(stage_counts)}"
        )
    if len(finals) != 1 or finals[0].winner is None:
        raise HistoricalDataValidationError(
            f"{edition}: expected one final with a decisive winner"
        )


def _download_or_cache(url: str, source_id: str, store: StateStore) -> bytes:
    try:
        response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=20)
        response.raise_for_status()
        payload = response.content
        if len(payload) > 5 * 1024 * 1024:
            raise ValueError("historical source exceeds 5 MB")
        store.capture(
            source_id,
            url,
            payload,
            quality="B",
            status_code=response.status_code,
            content_type=response.headers.get("Content-Type", "text/plain"),
        )
        return payload
    except Exception:
        cached = store.latest_payload(source_id)
        if cached is None:
            raise
        return cached


def load_historical_matches(editions: Iterable[int], store: StateStore) -> list[HistoricalMatch]:
    matches: list[HistoricalMatch] = []
    for edition in editions:
        if edition not in EDITION_FOLDERS:
            raise ValueError(f"unsupported edition: {edition}")
        folder = EDITION_FOLDERS[edition]
        edition_matches: list[HistoricalMatch] = []
        for part in ("cup.txt", "cup_finals.txt"):
            url = f"{RAW_BASE}/{folder}/{part}"
            source_id = f"openfootball_{edition}_{part.replace('.', '_')}"
            payload = _download_or_cache(url, source_id, store)
            edition_matches.extend(
                parse_openfootball(payload.decode("utf-8-sig"), edition, url)
            )
        edition_matches = [
            replace(match, source_sequence=sequence)
            for sequence, match in enumerate(edition_matches)
        ]
        validate_historical_edition(edition_matches, edition)
        matches.extend(edition_matches)
    return matches


def _probabilities(home_rating: float, away_rating: float) -> np.ndarray:
    expectation = elo_expectation(home_rating, away_rating)
    draw = 0.27 * math.exp(-abs(home_rating - away_rating) / 700.0)
    decisive = 1.0 - draw
    return np.asarray([decisive * expectation, draw, decisive * (1.0 - expectation)])


def _actual(match: HistoricalMatch) -> tuple[np.ndarray, float]:
    if match.home_goals > match.away_goals:
        return np.asarray([1.0, 0.0, 0.0]), 1.0
    if match.home_goals < match.away_goals:
        return np.asarray([0.0, 0.0, 1.0]), 0.0
    return np.asarray([0.0, 1.0, 0.0]), 0.5


def _metrics(frame: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (edition, model), group in frame.groupby(["Edición", "Modelo"]):
        rows.append(
            {
                "Edición": str(int(edition)),
                "Modelo": model,
                "Partidos": len(group),
                "Brier": float(group["Brier"].mean()),
                "Log loss": float(group["Log loss"].mean()),
                "Accuracy %": 100 * float(group["Correcto"].mean()),
            }
        )
    total = frame.groupby("Modelo").agg(
        Partidos=("Brier", "size"),
        Brier=("Brier", "mean"),
        **{"Log loss": ("Log loss", "mean"), "Accuracy %": ("Correcto", "mean")},
    )
    for model, row in total.iterrows():
        rows.append(
            {
                "Edición": "Total",
                "Modelo": model,
                "Partidos": int(row["Partidos"]),
                "Brier": float(row["Brier"]),
                "Log loss": float(row["Log loss"]),
                "Accuracy %": 100 * float(row["Accuracy %"]),
            }
        )
    return pd.DataFrame(rows)


def _calibration(frame: pd.DataFrame) -> pd.DataFrame:
    expanded = []
    columns = (("local", "P local"), ("empate", "P empate"), ("visitante", "P visitante"))
    for _, row in frame.iterrows():
        for outcome, column in columns:
            probability = float(row[column])
            bin_index = min(int(probability * 10), 9)
            expanded.append(
                {
                    "Modelo": row["Modelo"],
                    "Bin": f"{bin_index / 10:.1f}–{(bin_index + 1) / 10:.1f}",
                    "Probabilidad": probability,
                    "Observado": float(row["Resultado"] == outcome),
                }
            )
    return (
        pd.DataFrame(expanded)
        .groupby(["Modelo", "Bin"], as_index=False)
        .agg(
            **{
                "Probabilidad media": ("Probabilidad", "mean"),
                "Frecuencia observada": ("Observado", "mean"),
                "Casos": ("Observado", "size"),
            }
        )
    )


def run_backtest(matches: list[HistoricalMatch]) -> BacktestResult:
    if not matches:
        raise ValueError("backtest requires at least one match")
    ratings: defaultdict[str, float] = defaultdict(lambda: 1500.0)
    moon_history: defaultdict[tuple[str, int], list[float]] = defaultdict(list)
    rows: list[dict[str, object]] = []
    for match in matches:
        actual, elo_score = _actual(match)
        result_label = ("local", "empate", "visitante")[int(np.argmax(actual))]
        baseline = _probabilities(ratings[match.home], ratings[match.away])
        moon_delta = 0.0
        sign = None
        if match.kickoff is not None:
            sign = moon_sign_index(match.kickoff)
            home_records = moon_history[(match.home, sign)]
            away_records = moon_history[(match.away, sign)]
            home_rate = (sum(home_records) + 1.0) / (len(home_records) + 2.0)
            away_rate = (sum(away_records) + 1.0) / (len(away_records) + 2.0)
            moon_delta = 40.0 * (home_rate - away_rate)
        combined = _probabilities(
            ratings[match.home] + moon_delta / 2,
            ratings[match.away] - moon_delta / 2,
        )
        for model_name, probabilities in (
            ("Baseline Elo", baseline),
            ("Baseline + Sirius", combined),
        ):
            predicted_index = int(np.argmax(probabilities))
            actual_index = int(np.argmax(actual))
            rows.append(
                {
                    "Edición": match.edition,
                    "Fecha": match.kickoff.isoformat() if match.kickoff else None,
                    "Local": match.home,
                    "Visitante": match.away,
                    "Marcador": f"{match.home_goals}-{match.away_goals}",
                    "Resultado": result_label,
                    "Modelo": model_name,
                    "P local": probabilities[0],
                    "P empate": probabilities[1],
                    "P visitante": probabilities[2],
                    "Brier": float(np.square(probabilities - actual).sum()),
                    "Log loss": float(-math.log(max(probabilities[actual_index], 1e-12))),
                    "Correcto": predicted_index == actual_index,
                    "Ajuste lunar Elo": moon_delta if model_name.endswith("Sirius") else 0.0,
                    "Calidad hora": match.time_quality,
                }
            )
        expected = elo_expectation(ratings[match.home], ratings[match.away])
        change = 24.0 * (elo_score - expected)
        ratings[match.home] += change
        ratings[match.away] -= change
        if sign is not None:
            moon_history[(match.home, sign)].append(elo_score)
            moon_history[(match.away, sign)].append(1.0 - elo_score)
    predictions = pd.DataFrame(rows)
    metrics = _metrics(predictions)
    calibration = _calibration(predictions)
    quality = (
        predictions[predictions["Modelo"] == "Baseline Elo"]
        .groupby(["Edición", "Calidad hora"])
        .size()
        .reset_index(name="Partidos")
    )
    digest = hashlib.sha256(
        "|".join(
            f"{match.edition}:{match.home}:{match.away}:{match.home_goals}:{match.away_goals}"
            for match in matches
        ).encode("utf-8")
    ).hexdigest()[:16]
    return BacktestResult(
        run_id=digest,
        metrics=metrics,
        predictions=predictions,
        calibration=calibration,
        data_quality=quality,
    )
