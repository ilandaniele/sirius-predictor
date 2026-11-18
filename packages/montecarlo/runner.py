from __future__ import annotations

import hashlib
import math
import os
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd  # type: ignore[import-untyped]

from engine.config import load_scenario, load_teams, teams_for_scenario
from engine.domain import SimulationBundle
from engine.sim import _sensitivity_table, run_engine
from packages.common.config import get_settings
from packages.common.types import ModelMode


@dataclass(slots=True)
class ParallelSimulationResult:
    mode: ModelMode
    iterations: int
    seed: int
    workers: int
    run_id: str
    ranking: pd.DataFrame
    argentina_stages: pd.DataFrame
    argentina_rivals: dict[str, pd.DataFrame]
    argentina_groups: pd.DataFrame
    final_pairs: pd.DataFrame
    top_brackets: list[dict[str, Any]]
    sensitivity: pd.DataFrame
    chunks: list[SimulationBundle]
    sirius_assessments: dict[str, dict[str, Any]]
    sirius_evidence_audit: dict[str, Any]


def _chunk_job(
    arguments: tuple[str, str, int, int, str, int, str | None, float | None, float | None],
) -> SimulationBundle:
    (
        scenario_path,
        teams_path,
        count,
        seed,
        mode,
        final_hour,
        reviewed_path,
        host_advantage_elo,
        penalty_skill_weight,
    ) = arguments
    scenario = load_scenario(scenario_path)
    teams = teams_for_scenario(load_teams(teams_path), scenario)
    return run_engine(
        teams,
        scenario,
        count,
        seed,
        mode,
        final_hour,
        top_bracket_limit=100,
        reviewed_observations_path=reviewed_path,
        host_advantage_elo=host_advantage_elo,
        penalty_skill_weight=penalty_skill_weight,
    )


def _weighted_frames(
    chunks: list[SimulationBundle],
    counts: list[int],
    attribute: str,
    key: str,
    probability_columns: list[str],
) -> pd.DataFrame:
    total = sum(counts)
    frames = []
    for chunk, count in zip(chunks, counts, strict=True):
        frame = getattr(chunk, attribute).copy()
        for column in probability_columns:
            frame[column] *= count / total
        frames.append(frame)
    combined = pd.concat(frames, ignore_index=True)
    aggregations = {column: "sum" for column in probability_columns}
    passthrough = {
        column: "first"
        for column in combined.columns
        if column not in probability_columns and column != key
    }
    return combined.groupby(key, as_index=False).agg({**aggregations, **passthrough})


def _combine_counts(
    chunks: list[SimulationBundle],
    attribute: str,
    key: str | list[str],
    count_column: str,
    probability_column: str,
    total_denominator: int | None,
) -> pd.DataFrame:
    frames = [getattr(chunk, attribute) for chunk in chunks]
    non_empty = [frame for frame in frames if not frame.empty]
    if not non_empty:
        return pd.DataFrame()
    combined = pd.concat(non_empty, ignore_index=True)
    keys = [key] if isinstance(key, str) else key
    output = combined.groupby(keys, as_index=False)[count_column].sum()
    denominator = total_denominator or int(output[count_column].sum())
    output[probability_column] = 100 * output[count_column] / max(1, denominator)
    return output.sort_values(count_column, ascending=False)


def run_parallel(
    scenario_path: str | Path,
    teams_path: str | Path,
    iterations: int = 100_000,
    seed: int = 2030,
    mode: ModelMode = ModelMode.SIRIUS_ONLY,
    final_hour: int = 18,
    workers: int | None = None,
    reviewed_observations_path: str | Path | None = None,
    host_advantage_elo: float | None = None,
    penalty_skill_weight: float | None = None,
) -> ParallelSimulationResult:
    if iterations <= 0:
        raise ValueError("iterations must be positive")
    scenario = load_scenario(scenario_path)
    teams = teams_for_scenario(load_teams(teams_path), scenario)
    worker_count = max(1, min(workers or (os.cpu_count() or 1), iterations))
    base, remainder = divmod(iterations, worker_count)
    counts = [base + int(index < remainder) for index in range(worker_count)]
    seeds = [seed + 1_000_003 * index for index in range(worker_count)]
    jobs = [
        (
            str(scenario_path),
            str(teams_path),
            count,
            chunk_seed,
            mode.value,
            final_hour,
            str(reviewed_observations_path) if reviewed_observations_path else None,
            host_advantage_elo,
            penalty_skill_weight,
        )
        for count, chunk_seed in zip(counts, seeds, strict=True)
    ]
    if worker_count == 1:
        chunks = [_chunk_job(jobs[0])]
    else:
        with ProcessPoolExecutor(max_workers=worker_count) as executor:
            chunks = list(executor.map(_chunk_job, jobs))

    ranking = _weighted_frames(
        chunks,
        counts,
        "ranking",
        "ID",
        ["Campeón %", "Final %", "Semi %", "R32 %"],
    )
    champion_probability = ranking["Campeón %"] / 100
    ranking["IC95 ± pp"] = (
        100 * 1.96 * (champion_probability * (1 - champion_probability) / iterations).pow(0.5)
    )
    ranking = ranking.sort_values("Campeón %", ascending=False)
    argentina_stages = _weighted_frames(
        chunks,
        counts,
        "argentina_stages",
        "Etapa alcanzada",
        ["Probabilidad %"],
    )
    rival_rounds = set().union(*(chunk.argentina_rivals for chunk in chunks))
    argentina_rivals = {}
    for round_name in sorted(rival_rounds):
        frames = [
            chunk.argentina_rivals[round_name]
            for chunk in chunks
            if round_name in chunk.argentina_rivals and not chunk.argentina_rivals[round_name].empty
        ]
        if not frames:
            argentina_rivals[round_name] = pd.DataFrame()
            continue
        combined = pd.concat(frames, ignore_index=True)
        grouped = combined.groupby("Rival", as_index=False)["Encuentros simulados"].sum()
        grouped["Frecuencia condicional %"] = (
            100 * grouped["Encuentros simulados"] / grouped["Encuentros simulados"].sum()
        )
        argentina_rivals[round_name] = grouped.sort_values("Encuentros simulados", ascending=False)
    argentina_groups = _combine_counts(
        chunks,
        "argentina_groups",
        "Otros tres equipos",
        "Veces",
        "Frecuencia %",
        iterations,
    )
    final_pairs = _combine_counts(
        chunks,
        "final_pairs",
        ["Finalista A", "Finalista B"],
        "Veces",
        "Frecuencia %",
        iterations,
    )
    sensitivity = pd.DataFrame()
    if not final_pairs.empty:
        name_to_id = {team.team: team.team_id for team in teams}
        leading_final = final_pairs.iloc[0]
        pair = (
            name_to_id[str(leading_final["Finalista A"])],
            name_to_id[str(leading_final["Finalista B"])],
        )
        sensitivity = _sensitivity_table(
            pair,
            teams,
            scenario,
            mode,
            reviewed_observations_path,
            host_advantage_elo,
            penalty_skill_weight,
        )
    cluster_counts: Counter[str] = Counter()
    representatives: dict[str, dict[str, Any]] = {}
    for chunk in chunks:
        cluster_counts.update(chunk.cluster_counts)
        for bracket in chunk.top_brackets:
            signature = str(bracket["signature"])
            representatives.setdefault(signature, dict(bracket))
    top_brackets = sorted(
        representatives.values(),
        key=lambda item: cluster_counts[str(item["signature"])],
        reverse=True,
    )[:5]
    for bracket in top_brackets:
        bracket["count"] = cluster_counts[str(bracket["signature"])]
        bracket["density_percent"] = 100 * int(bracket["count"]) / iterations
    run_id = hashlib.sha256(
        (
            f"{scenario.scenario_id}:{chunks[0].manifest.input_sha256}:"
            f"{iterations}:{seed}:{mode.value}:{final_hour}:{worker_count}:"
            f"{host_advantage_elo}:{penalty_skill_weight}:"
            f"{get_settings().model_version}"
        ).encode()
    ).hexdigest()[:16]
    if not math.isclose(float(ranking["Campeón %"].sum()), 100.0, abs_tol=1e-9):
        raise RuntimeError("parallel aggregation lost champion probability mass")
    return ParallelSimulationResult(
        mode=mode,
        iterations=iterations,
        seed=seed,
        workers=worker_count,
        run_id=run_id,
        ranking=ranking,
        argentina_stages=argentina_stages,
        argentina_rivals=argentina_rivals,
        argentina_groups=argentina_groups,
        final_pairs=final_pairs,
        top_brackets=top_brackets,
        sensitivity=sensitivity,
        chunks=chunks,
        sirius_assessments=chunks[0].sirius_assessments,
        sirius_evidence_audit=chunks[0].sirius_evidence_audit,
    )
