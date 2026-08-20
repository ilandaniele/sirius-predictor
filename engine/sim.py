from __future__ import annotations

import hashlib
import json
import random
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from packages.common.types import ModelMode
from packages.sirius import build_sirius_assessments
from packages.sirius.models import SiriusAssessment

from .config import Scenario, load_scenario, load_teams, validate_scenario
from .domain import SimulationBundle, SimulationManifest, Team, TournamentResult
from .model import FootballMatchModel
from .sirius import SiriusExperimentalLayer
from .tournament import ROUND_SEQUENCE, simulate_tournament

STAGES = ("Group", "R32", "R16", "QF", "SF", "F", "Champion")
STAGE_INDEX = {stage: index for index, stage in enumerate(STAGES)}
PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _assessments(
    teams: list[Team],
    scenario: Scenario,
    reviewed_observations_path: str | Path | None = None,
) -> tuple[dict[str, SiriusAssessment], dict[str, Any]]:
    path = PROJECT_ROOT / scenario.models.sirius_observations_file
    return build_sirius_assessments(
        {team.team_id for team in teams},
        path,
        additional_observations_path=reviewed_observations_path,
    )


def _input_hash(
    teams: list[Team],
    scenario: Scenario,
    reviewed_observations_path: str | Path | None = None,
) -> str:
    static_observations_path = PROJECT_ROOT / scenario.models.sirius_observations_file
    payload = {
        "scenario": scenario.scenario_id,
        "as_of": scenario.as_of,
        "teams": [team.to_dict() for team in teams],
        "sirius_observations_sha256": hashlib.sha256(
            static_observations_path.read_bytes()
        ).hexdigest(),
        "reviewed_sirius_sha256": (
            hashlib.sha256(Path(reviewed_observations_path).read_bytes()).hexdigest()
            if reviewed_observations_path is not None
            else None
        ),
    }
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


def _sensitivity_table(
    pair: tuple[str, str] | None,
    teams: list[Team],
    scenario: Scenario,
    mode: str | ModelMode,
    reviewed_observations_path: str | Path | None = None,
) -> pd.DataFrame:
    if pair is None:
        return pd.DataFrame()
    assessments, _ = _assessments(teams, scenario, reviewed_observations_path)
    layer = SiriusExperimentalLayer(
        scenario.models.max_sirius_elo_adjustment, assessments=assessments
    )
    model = FootballMatchModel(teams, layer, mode=mode)
    ratings = {team.team_id: team.projected_elo for team in teams}
    team_map = {team.team_id: team.team for team in teams}
    base_date = datetime.fromisoformat(scenario.final.local_date)
    rows = []
    for hour in scenario.final.sensitivity_hours:
        for minute_delta in scenario.final.sensitivity_minutes:
            kickoff = datetime(
                base_date.year,
                base_date.month,
                base_date.day,
                hour,
                tzinfo=ZoneInfo(scenario.final.timezone),
            ) + timedelta(minutes=minute_delta)
            probabilities = model.probabilities(pair[0], pair[1], ratings, kickoff, "F")
            rows.append(
                {
                    "Finalista A": team_map[pair[0]],
                    "Finalista B": team_map[pair[1]],
                    "Hora local": kickoff.strftime("%H:%M"),
                    "P(A) %": 100 * probabilities.home,
                    "Empate 90' %": 100 * probabilities.draw,
                    "P(B) %": 100 * probabilities.away,
                    "Ajuste Sirius Elo": probabilities.sirius_adjustment,
                }
            )
    frame = pd.DataFrame(rows)
    spread = float(frame["P(A) %"].max() - frame["P(A) %"].min())
    robustness = "alta" if spread < 1.0 else ("media" if spread < 3.0 else "baja")
    frame["Rango P(A) pp"] = spread
    frame["Robustez"] = robustness
    return frame


def run_engine(
    teams: list[Team],
    scenario: Scenario,
    n: int = 5_000,
    seed: int = 2030,
    mode: str | ModelMode = ModelMode.HYBRID,
    final_hour: int = 18,
    progress=None,
    top_bracket_limit: int = 5,
    reviewed_observations_path: str | Path | None = None,
) -> SimulationBundle:
    if n <= 0:
        raise ValueError("n must be positive")
    if final_hour not in scenario.final.sensitivity_hours:
        raise ValueError("final_hour must be one of the configured sensitivity hours")
    validate_scenario(scenario, teams)
    assessments, evidence_audit = _assessments(
        teams, scenario, reviewed_observations_path
    )
    layer = SiriusExperimentalLayer(
        scenario.models.max_sirius_elo_adjustment, assessments=assessments
    )
    model = FootballMatchModel(teams, layer, mode=mode)
    rng = np.random.default_rng(seed)
    draw_rng = random.Random(seed ^ 0x5F3759DF)
    team_map = {team.team_id: team for team in teams}
    reached = {team.team_id: Counter() for team in teams}
    rival_counts = {round_name: Counter() for round_name in ROUND_SEQUENCE}
    argentina_groups: Counter[str] = Counter()
    final_pairs: Counter[tuple[str, str]] = Counter()
    clusters: dict[str, dict[str, object]] = {}
    checkpoints = set(np.linspace(1, n, min(20, n), dtype=int).tolist())
    convergence_rows: list[dict[str, float | int]] = []

    for iteration in range(1, n + 1):
        tournament = simulate_tournament(
            teams, scenario, model, rng, draw_rng, final_hour=final_hour
        )
        for team_id, highest_stage in tournament.stage_reached.items():
            highest = STAGE_INDEX[highest_stage]
            for stage in STAGES[: highest + 1]:
                reached[team_id][stage] += 1
        for group in tournament.groups.values():
            if "ARG" in group:
                signature = " · ".join(
                    sorted(team_map[item].team for item in group if item != "ARG")
                )
                argentina_groups[signature] += 1
                break
        for match in tournament.matches:
            if match.round_name in rival_counts and "ARG" in {match.home_id, match.away_id}:
                opponent = match.away_id if match.home_id == "ARG" else match.home_id
                rival_counts[match.round_name][opponent] += 1
        pair = tuple(sorted((tournament.champion_id, tournament.runner_up_id)))
        final_pairs[pair] += 1
        cluster = clusters.setdefault(
            tournament.density_signature,
            {"count": 0, "representative": tournament},
        )
        cluster["count"] = int(cluster["count"]) + 1
        if iteration in checkpoints:
            convergence_rows.append(
                {
                    "Iteraciones": iteration,
                    "Argentina campeón %": 100 * reached["ARG"]["Champion"] / iteration,
                }
            )
        if progress is not None and (iteration == n or iteration % max(1, n // 100) == 0):
            progress(iteration / n)

    ranking_rows = []
    for team in teams:
        champion_probability = reached[team.team_id]["Champion"] / n
        margin = 1.96 * np.sqrt(champion_probability * (1 - champion_probability) / n)
        ranking_rows.append(
            {
                "ID": team.team_id,
                "Selección": team.team,
                "Campeón %": 100 * champion_probability,
                "IC95 ± pp": 100 * margin,
                "Final %": 100 * reached[team.team_id]["F"] / n,
                "Semi %": 100 * reached[team.team_id]["SF"] / n,
                "R32 %": 100 * reached[team.team_id]["R32"] / n,
                "Elo proyectado": team.projected_elo,
                "Índice Sirius": team.sirius_index,
                "Confianza Sirius": team.sirius_confidence,
                "Índice Recorrido": assessments[team.team_id].journey_index.value,
                "Índice Coronación": assessments[team.team_id].coronation_index.value,
                "Confianza Datos Sirius": assessments[team.team_id].data_confidence,
                "Evidencias Sirius": (
                    assessments[team.team_id].journey_index.evidence_count
                    + assessments[team.team_id].coronation_index.evidence_count
                ),
            }
        )
    ranking = pd.DataFrame(ranking_rows).sort_values("Campeón %", ascending=False)
    argentina_stages = pd.DataFrame(
        [
            {"Etapa alcanzada": stage, "Probabilidad %": 100 * reached["ARG"][stage] / n}
            for stage in STAGES
        ]
    )
    argentina_rivals: dict[str, pd.DataFrame] = {}
    for round_name, counts in rival_counts.items():
        total = sum(counts.values())
        argentina_rivals[round_name] = pd.DataFrame(
            [
                {
                    "Rival": team_map[team_id].team,
                    "Frecuencia condicional %": 100 * count / total if total else 0.0,
                    "Encuentros simulados": count,
                }
                for team_id, count in counts.most_common(12)
            ]
        )
    argentina_group_frame = pd.DataFrame(
        [
            {"Otros tres equipos": signature, "Frecuencia %": 100 * count / n, "Veces": count}
            for signature, count in argentina_groups.most_common(20)
        ]
    )
    final_pair_rows = [
        {
            "Finalista A": team_map[pair[0]].team,
            "Finalista B": team_map[pair[1]].team,
            "Frecuencia %": 100 * count / n,
            "Veces": count,
        }
        for pair, count in final_pairs.most_common(20)
    ]
    final_pair_frame = pd.DataFrame(final_pair_rows)
    top_brackets: list[dict[str, object]] = []
    for signature, cluster in sorted(
        clusters.items(), key=lambda item: int(item[1]["count"]), reverse=True
    )[:top_bracket_limit]:
        representative = cluster["representative"]
        assert isinstance(representative, TournamentResult)
        top_brackets.append(
            {
                "signature": signature,
                "count": int(cluster["count"]),
                "density_percent": 100 * int(cluster["count"]) / n,
                "champion": team_map[representative.champion_id].team,
                "runner_up": team_map[representative.runner_up_id].team,
                "representative": representative,
            }
        )
    most_common_pair = final_pairs.most_common(1)[0][0] if final_pairs else None
    digest = _input_hash(teams, scenario, reviewed_observations_path)
    run_id = hashlib.sha256(
        f"{digest}:{n}:{seed}:{model.mode.value}:{final_hour}".encode()
    ).hexdigest()[:16]
    manifest = SimulationManifest.now(
        run_id=run_id,
        scenario_id=scenario.scenario_id,
        scenario_as_of=scenario.as_of,
        iterations=n,
        seed=seed,
        mode=model.mode.value,
        final_hour=final_hour,
        baseline_version=scenario.models.baseline_version,
        sirius_version=scenario.models.sirius_version,
        input_sha256=digest,
    )
    return SimulationBundle(
        manifest=manifest,
        ranking=ranking,
        argentina_stages=argentina_stages,
        argentina_rivals=argentina_rivals,
        argentina_groups=argentina_group_frame,
        final_pairs=final_pair_frame,
        top_brackets=top_brackets,
        sensitivity=_sensitivity_table(
            most_common_pair,
            teams,
            scenario,
            mode,
            reviewed_observations_path,
        ),
        convergence=pd.DataFrame(convergence_rows),
        cluster_counts={
            signature: int(cluster["count"]) for signature, cluster in clusters.items()
        },
        samples=[item["representative"] for item in top_brackets],
        sirius_assessments={
            team_id: assessment.to_dict() for team_id, assessment in assessments.items()
        },
        sirius_evidence_audit=evidence_audit,
    )


def run(df=None, n: int = 5_000, seed: int = 2030):
    """Compatibility facade returning the four original dashboard values."""

    del df
    root = Path(__file__).resolve().parents[1]
    scenario = load_scenario(root / "data" / "scenario.yaml")
    teams = load_teams(root / "data" / "teams.csv")
    bundle = run_engine(teams, scenario, n=n, seed=seed)
    return (
        bundle.ranking,
        bundle.argentina_stages,
        bundle.argentina_rivals,
        bundle.argentina_groups,
    )
