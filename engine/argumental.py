from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from engine.backtest import HistoricalMatch
from packages.astrology.ephemeris import EphemerisUnavailable, chart
from packages.astrology.models import AstrologyChart, ChartRequest, GeoLocation
from packages.astrology.techniques import (
    RULERS,
    accidental_dignities,
    essential_dignities,
    sign_name,
    solar_return,
)
from packages.common.config import ROOT

# Astrología Argumental (Santiago Rodríguez Spuch, astrologiaargumental.blogspot.com) is
# the second independent astrology source in this project, distinct from Sirius. His
# flagship technique — the "método Frawley" — is horary astrology cast on the exact
# kickoff moment of one specific match, which this project cannot apply broadly: a
# Monte Carlo simulation plays out thousands of hypothetical brackets whose real kickoff
# times are unknown ahead of the draw, unlike the one match (the final) with a fixed
# date. But his OWN real final-analysis post for the actual 2026 World Cup final
# (Argentina vs España, astrologiaargumental.blogspot.com/2026/07/analisis-astrologico-
# final-del-mundial.html) names a second, genuinely team-level technique as the one that
# matters most: the coach's own "ciclo" (the coach-debut event chart) recast as a Solar
# Revolution (solar return) for the year in question — in his words, "siempre es
# importante lo más 'macro' la Solar" (the solar revolution is always the more
# important, 'macro' factor), used before the match chart for both De la Fuente
# (España) and Scaloni (Argentina). That is what this module computes: a real Swiss
# Ephemeris solar return on each team's coach_debut chart (data/events_<code>_coach_
# debut.json), scored from the same testimonies he cites in that post — the Midheaven
# ruler's essential/accidental dignity, and Jupiter/Saturn/Neptune aspects to the
# Midheaven ruler or Sun.
#
# This is our own computation applying his publicly documented method, not a number he
# has personally published — and unlike the Sirius moon-sign signal, it is NOT wired
# into FootballMatchModel or the Monte Carlo. It surfaces only as a labelled,
# diagnostic "complementary analysis", exactly like the rest of the Argumental
# integration.
#
# Real-world check: applying this exact final-post logic himself, Argumental predicted
# Argentina to beat España in the real 2026 final ("considero mejor a la Selección
# Argentina para ganar el Mundial 2026"). Real result: España won. Treat this module's
# output with the same caution that outcome implies.

DATA_DIR = ROOT / "data"

_ES_BODY = {
    "Sun": "Sol",
    "Moon": "Luna",
    "Mercury": "Mercurio",
    "Venus": "Venus",
    "Mars": "Marte",
    "Jupiter": "Júpiter",
    "Saturn": "Saturno",
    "Uranus": "Urano",
    "Neptune": "Neptuno",
    "Pluto": "Plutón",
}
_ES_ASPECT = {
    "conjunction": "conjunción",
    "sextile": "sextil",
    "square": "cuadratura",
    "trine": "trígono",
    "opposition": "oposición",
}
_ES_DIGNITY = {
    "domicile": "domicilio",
    "exaltation": "exaltación",
    "detriment": "exilio",
    "fall": "caída",
    "peregrine": "peregrino",
}

@dataclass(frozen=True, slots=True)
class RevolutionReading:
    midheaven_sign: str
    midheaven_ruler: str
    midheaven_ruler_dignity: str
    midheaven_ruler_house_class: str
    favorable_testimonies: tuple[str, ...]
    adverse_testimonies: tuple[str, ...]
    fortune_index: float


@dataclass(frozen=True, slots=True)
class CycleFortune:
    team_id: str
    coach_name: str
    debut_label: str
    solar_return_year: int
    solar_return_moment: str
    midheaven_sign: str
    midheaven_ruler: str
    midheaven_ruler_dignity: str
    midheaven_ruler_house_class: str
    favorable_testimonies: tuple[str, ...]
    adverse_testimonies: tuple[str, ...]
    fortune_index: float
    status: str


def score_revolution(revolution: AstrologyChart) -> RevolutionReading:
    """Score an already-cast solar-revolution chart from the testimonies Argumental
    cites in his own final-analysis post: Midheaven ruler dignity and angularity,
    then Jupiter/Saturn/Neptune aspects to that ruler or to the Sun.

    Pure and ephemeris-agnostic: takes a fully-built chart (real or, in tests, a
    manually constructed one) so the scoring logic is testable without Swiss
    Ephemeris installed.
    """

    if revolution.houses is None:
        raise ValueError("solar return chart always carries a known time and location")

    mc_sign = sign_name(revolution.houses.midheaven)
    mc_ruler = RULERS[mc_sign]
    dignity_row = essential_dignities(revolution).result[mc_ruler]
    accidental_row = accidental_dignities(revolution).result[mc_ruler]
    dignity = (
        "domicile"
        if dignity_row["domicile"]
        else "exaltation"
        if dignity_row["exaltation"]
        else "detriment"
        if dignity_row["detriment"]
        else "fall"
        if dignity_row["fall"]
        else "peregrine"
    )
    house_class = str(accidental_row["house_class"])

    score = 0.0
    favorable: list[str] = []
    adverse: list[str] = []
    ruler_es = _ES_BODY.get(mc_ruler, mc_ruler)
    dignity_es = _ES_DIGNITY[dignity]
    if dignity in {"domicile", "exaltation"}:
        score += 0.3
        favorable.append(f"{ruler_es} (regente del Medio Cielo) en {dignity_es} en {mc_sign}")
    elif dignity in {"detriment", "fall"}:
        score -= 0.3
        adverse.append(f"{ruler_es} (regente del Medio Cielo) en {dignity_es} en {mc_sign}")
    if house_class == "angular":
        score += 0.2
        favorable.append(f"{ruler_es} angular (casa {accidental_row['house']})")
    elif house_class == "cadent":
        score -= 0.15
        adverse.append(f"{ruler_es} cadente (casa {accidental_row['house']})")

    for aspect in revolution.aspects:
        bodies = {aspect.body_a, aspect.body_b}
        if not bodies & {mc_ruler, "Sun"}:
            continue
        other = next(iter(bodies - {mc_ruler, "Sun"}), None)
        if other is None:
            continue
        anchor_es = "Sol" if "Sun" in bodies else ruler_es
        aspect_es = _ES_ASPECT[aspect.aspect]
        if other == "Jupiter" and aspect.aspect in {"trine", "sextile", "conjunction"}:
            score += 0.15
            favorable.append(f"Júpiter en {aspect_es} a {anchor_es}")
        elif other in {"Saturn", "Neptune"} and aspect.aspect in {"square", "opposition"}:
            score -= 0.2
            adverse.append(f"{_ES_BODY[other]} en {aspect_es} a {anchor_es}")
        elif other in {"Saturn", "Neptune"} and aspect.aspect == "conjunction":
            score -= 0.15
            adverse.append(f"{_ES_BODY[other]} conjunto a {anchor_es}")

    return RevolutionReading(
        midheaven_sign=mc_sign,
        midheaven_ruler=mc_ruler,
        midheaven_ruler_dignity=dignity,
        midheaven_ruler_house_class=house_class,
        favorable_testimonies=tuple(favorable),
        adverse_testimonies=tuple(adverse),
        fortune_index=max(-1.0, min(1.0, score)),
    )


def _load_coach_debut_event(
    team_id: str, data_dir: Path | None = None
) -> tuple[datetime, GeoLocation, str, str] | None:
    directory = data_dir or DATA_DIR
    path = directory / f"events_{team_id.lower()}_coach_debut.json"
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    debut = next(
        (event for event in payload.get("events", []) if event.get("event_type") == "coach_debut"),
        None,
    )
    if debut is None:
        return None
    moment = datetime.fromisoformat(str(debut["occurred_at"]))
    location = GeoLocation(
        latitude=float(debut["location"]["latitude"]),
        longitude=float(debut["location"]["longitude"]),
        name=str(debut["location"].get("name", "")),
    )
    return moment, location, str(debut["coach_name"]), str(debut["label"])


def _cycle_fortune_from_event(
    label_id: str,
    coach_name: str,
    debut_label: str,
    debut_moment: datetime,
    location: GeoLocation,
    year: int,
) -> CycleFortune:
    """Shared core for both the live (current-coach) and historical (per-edition)
    lookups: cast the coach-cycle solar revolution for `year` and score it."""

    try:
        natal = chart(ChartRequest(debut_moment, location, True, label=debut_label))
        revolution_result = solar_return(natal, year, location)
        moment = datetime.fromisoformat(str(revolution_result.result["exact_moment"]))
        revolution = chart(
            ChartRequest(moment, location, True, label=f"{label_id} {coach_name} SR {year}")
        )
    except EphemerisUnavailable:
        return CycleFortune(
            team_id=label_id,
            coach_name=coach_name,
            debut_label=debut_label,
            solar_return_year=year,
            solar_return_moment="",
            midheaven_sign="",
            midheaven_ruler="",
            midheaven_ruler_dignity="",
            midheaven_ruler_house_class="",
            favorable_testimonies=(),
            adverse_testimonies=(),
            fortune_index=0.0,
            status="ephemeris_unavailable",
        )
    reading = score_revolution(revolution)
    return CycleFortune(
        team_id=label_id,
        coach_name=coach_name,
        debut_label=debut_label,
        solar_return_year=year,
        solar_return_moment=moment.isoformat(),
        midheaven_sign=reading.midheaven_sign,
        midheaven_ruler=reading.midheaven_ruler,
        midheaven_ruler_dignity=reading.midheaven_ruler_dignity,
        midheaven_ruler_house_class=reading.midheaven_ruler_house_class,
        favorable_testimonies=reading.favorable_testimonies,
        adverse_testimonies=reading.adverse_testimonies,
        fortune_index=reading.fortune_index,
        status="computed",
    )


def coach_cycle_fortune(
    team_id: str, year: int, data_dir: Path | None = None
) -> CycleFortune | None:
    """Real Swiss Ephemeris solar-return reading of a team's coach-cycle chart,
    scored from the same testimonies Argumental cites as his primary technique.

    Returns None only when there is no coach_debut event on file for this team
    (missing evidence stays neutral, same convention as the rest of the project).
    """

    loaded = _load_coach_debut_event(team_id, data_dir)
    if loaded is None:
        return None
    debut_moment, location, coach_name, debut_label = loaded
    return _cycle_fortune_from_event(team_id, coach_name, debut_label, debut_moment, location, year)


def historical_coach_cycle_fortune(
    team_name: str, edition: int, data_dir: Path | None = None
) -> CycleFortune | None:
    """Same technique, applied to a real PAST World Cup edition's actual coach —
    for backtesting the signal against a tournament that already happened, using
    data/historical_coaches_<edition>.json (keyed by team name, not team_id, to
    match engine.backtest's real historical match records).

    Returns None when the edition file doesn't exist or the team isn't in it
    (e.g. deliberately excluded for lacking a confirmed kickoff time).
    """

    directory = data_dir or DATA_DIR
    path = directory / f"historical_coaches_{edition}.json"
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    entry = payload.get("coaches", {}).get(team_name)
    if entry is None:
        return None
    debut = entry["debut"]
    debut_moment = datetime.fromisoformat(str(debut["occurred_at"]))
    location = GeoLocation(
        latitude=float(debut["location"]["latitude"]),
        longitude=float(debut["location"]["longitude"]),
        name=str(debut["location"].get("name", "")),
    )
    return _cycle_fortune_from_event(
        team_name, str(entry["coach_name"]), str(debut["label"]), debut_moment, location, edition
    )


def all_cycle_fortunes(
    team_ids: list[str], year: int, data_dir: Path | None = None
) -> dict[str, CycleFortune]:
    results: dict[str, CycleFortune] = {}
    for team_id in team_ids:
        fortune = coach_cycle_fortune(team_id, year, data_dir)
        if fortune is not None:
            results[team_id] = fortune
    return results


_STAGE_RANK = {"Group": 0, "R32": 0, "R16": 1, "QF": 2, "SF": 3, "ThirdPlace": 3, "F": 4}


def _furthest_stage(
    matches: list[HistoricalMatch], edition: int
) -> tuple[dict[str, int], str | None]:
    furthest: dict[str, int] = {}
    champion = None
    for match in matches:
        if match.edition != edition:
            continue
        rank = _STAGE_RANK.get(match.stage)
        if rank is not None:
            for team in (match.home, match.away):
                if team not in furthest or rank > furthest[team]:
                    furthest[team] = rank
        if match.stage == "F" and match.winner:
            champion = match.winner
    if champion is not None:
        furthest[champion] = 5
    return furthest, champion


def correlation_stats(rows: list[tuple[float, int, str]]) -> dict[str, object]:
    """Pearson correlation + group comparison between a fortune_index and a
    stage_rank across a set of (fortune_index, stage_rank, team_label) rows. Pure
    statistics, no data loading -- reused both per-edition and pooled across
    editions in argumental_diagnostic_by_edition.
    """

    n = len(rows)
    if n < 3:
        return {"teams_covered": n, "status": "insufficient_data"}

    xs = [row[0] for row in rows]
    ys = [float(row[1]) for row in rows]
    mean_x, mean_y = sum(xs) / n, sum(ys) / n
    cov = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys, strict=True)) / n
    std_x = (sum((x - mean_x) ** 2 for x in xs) / n) ** 0.5
    std_y = (sum((y - mean_y) ** 2 for y in ys) / n) ** 0.5
    pearson_r = cov / (std_x * std_y) if std_x > 0 and std_y > 0 else 0.0
    # Rough two-tailed significance check (t-test on the correlation, df = n-2); no
    # scipy dependency, just enough to avoid overclaiming a small-sample correlation.
    df = n - 2
    t_stat = pearson_r * (df**0.5) / max(1e-9, (1 - pearson_r**2) ** 0.5) if df > 0 else 0.0
    significant = abs(t_stat) >= 2.05  # ~p<0.05 two-tailed for df in the high-20s

    advanced = [x for x, y, _ in rows if y > 0]
    eliminated_group = [x for x, y, _ in rows if y == 0]

    return {
        "teams_covered": n,
        "pearson_r": round(pearson_r, 3),
        "t_statistic": round(t_stat, 3),
        "statistically_significant_p05": significant,
        "advanced_past_group": {
            "n": len(advanced),
            "mean_fortune_index": round(sum(advanced) / len(advanced), 3) if advanced else None,
        },
        "eliminated_in_group": {
            "n": len(eliminated_group),
            "mean_fortune_index": (
                round(sum(eliminated_group) / len(eliminated_group), 3)
                if eliminated_group
                else None
            ),
        },
    }


def argumental_signal_diagnostic(
    matches: list[HistoricalMatch], edition: int, data_dir: Path | None = None
) -> dict[str, object]:
    """Honest first check of whether the coach-cycle solar-revolution fortune index
    predicts anything real, against one full past World Cup edition (real matches,
    real results). One edition alone is not a proper multi-edition backtest, so
    this reports that edition's correlation transparently rather than pretending
    it's enough to calibrate a real parameter -- argumental_diagnostic_by_edition
    (packages/football/backtest.py) pools the raw rows across every edition this
    project has researched coach data for. Never applied to the live model.
    """

    furthest, champion = _furthest_stage(matches, edition)
    coaches_path = (data_dir or DATA_DIR) / f"historical_coaches_{edition}.json"
    if not coaches_path.exists():
        return {
            "edition": edition,
            "teams_covered": 0,
            "status": "no_historical_coach_data",
            "finding": f"No hay data/historical_coaches_{edition}.json todavía.",
            "rows": [],
        }
    coached_teams = sorted(json.loads(coaches_path.read_text(encoding="utf-8"))["coaches"])

    rows: list[tuple[float, int, str]] = []
    for team in coached_teams:
        fortune = historical_coach_cycle_fortune(team, edition, data_dir)
        if fortune is None or fortune.status != "computed" or team not in furthest:
            continue
        rows.append((fortune.fortune_index, furthest[team], team))
    row_dicts = [{"team": team, "fortune_index": x, "stage_rank": y} for x, y, team in rows]

    stats = correlation_stats(rows)
    if stats.get("status") == "insufficient_data":
        return {
            "edition": edition,
            "teams_covered": len(rows),
            "status": "insufficient_data",
            "finding": (
                f"Solo {len(rows)} equipos con dato completo — insuficiente para correlacionar."
            ),
            "rows": row_dicts,
        }

    pearson_r = float(stats["pearson_r"])  # type: ignore[arg-type]
    significant = bool(stats["statistically_significant_p05"])
    return {
        "edition": edition,
        "champion": champion,
        **stats,
        "applied_to_model": False,
        "finding": (
            f"Con los {len(rows)} equipos con dato completo del Mundial {edition} real, "
            f"r={pearson_r:.3f} entre el índice de fortuna y la ronda alcanzada "
            f"({'compatible con una señal real' if pearson_r > 0 else 'sin dirección clara'}, "
            f"{'diferencia estadísticamente significativa' if significant else 'NO significativa'} "
            f"con una sola edición). No es un backtest walk-forward completo por sí solo — "
            "hace falta combinar esto con otras ediciones reales investigadas para tener "
            "poder estadístico; esto es un chequeo honesto por edición, no un parámetro "
            "para aplicar."
        ),
        "rows": row_dicts,
    }
