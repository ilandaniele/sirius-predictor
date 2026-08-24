from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter

import pandas as pd  # type: ignore[import-untyped]

from engine.backtest import EDITION_FOLDERS, load_historical_matches
from engine.config import load_scenario, load_teams, teams_for_scenario, validate_scenario
from engine.updates import StateStore
from packages.common.types import ModelMode
from packages.football import DrawEngine
from packages.football.backtest import run_full_backtest
from packages.montecarlo import run_parallel
from packages.reports import export_five_brackets
from packages.sirius import sirius_application_status

ROOT = Path(__file__).resolve().parents[1]


def _records(frame: pd.DataFrame) -> list[dict[str, object]]:
    return json.loads(frame.to_json(orient="records", date_format="iso"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Run v0.4.0 release acceptance")
    parser.add_argument("--iterations", type=int, default=100_000)
    parser.add_argument("--workers", type=int, default=None)
    parser.add_argument("--format-size", type=int, choices=(48, 64), default=64)
    args = parser.parse_args()
    if args.iterations < 100_000:
        raise ValueError("release acceptance requires at least 100,000 iterations")

    scenario_path = (
        ROOT / "data" / ("scenario.yaml" if args.format_size == 64 else "scenario-48.yaml")
    )
    teams_path = ROOT / "data" / "teams.csv"
    scenario = load_scenario(scenario_path)
    teams = teams_for_scenario(load_teams(teams_path), scenario)
    validate_scenario(scenario, teams)
    output = ROOT / "storage" / "release-acceptance" / datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    output.mkdir(parents=True, exist_ok=False)

    historical_matches = load_historical_matches(EDITION_FOLDERS, StateStore(ROOT / "state"))
    historical_editions = sorted({match.edition for match in historical_matches})
    historical_shapes = {
        str(edition): {
            "matches": len(edition_matches),
            "teams": len({team for match in edition_matches for team in (match.home, match.away)}),
            "stages": dict(Counter(match.stage for match in edition_matches)),
            "champion": next(
                (match.winner for match in edition_matches if match.stage == "F"),
                None,
            ),
        }
        for edition in historical_editions
        if (edition_matches := [match for match in historical_matches if match.edition == edition])
    }
    backtest = run_full_backtest(historical_matches)
    consulted_at = datetime.now(UTC).isoformat()
    backtest_manifest = {
        "sources": [
            {
                "source_id": "openfootball",
                "source_url": url,
                "consulted_at": consulted_at,
                "quality": "B",
                "fetch_status": "snapshot",
            }
            for url in sorted({match.source_url for match in historical_matches})
        ],
        "requested_editions": sorted(EDITION_FOLDERS),
        "available_editions": historical_editions,
        "missing_editions": sorted(set(EDITION_FOLDERS) - set(historical_editions)),
        "matches": len(historical_matches),
        "edition_shapes": historical_shapes,
        "time_quality": {
            quality: sum(match.time_quality == quality for match in historical_matches)
            for quality in sorted({match.time_quality for match in historical_matches})
        },
        "metrics": _records(backtest.metrics),
        "calibration": _records(backtest.calibration),
        "champion_ranking": _records(backtest.champion_ranking),
        "round_accuracy": _records(backtest.round_accuracy),
        "ablations": _records(backtest.ablations),
        "leakage_audit": _records(backtest.leakage_audit),
        "calibration_manifest": _records(backtest.calibration_manifest),
    }
    (output / "backtest.json").write_text(
        json.dumps(backtest_manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    draw_started = perf_counter()
    draw_analysis = DrawEngine(teams, scenario).analyze(
        args.iterations,
        seed=2030,
        validate_each=True,
    )
    draw_seconds = perf_counter() - draw_started

    simulations = {}
    hybrid_result = None
    for mode in ModelMode:
        started = perf_counter()
        result = run_parallel(
            scenario_path,
            teams_path,
            iterations=args.iterations,
            seed=2030,
            mode=mode,
            final_hour=scenario.final.base_hour,
            workers=args.workers,
        )
        simulations[mode.value] = {
            "run_id": result.run_id,
            "seconds": perf_counter() - started,
            "workers": result.workers,
            "champion_probability_sum": float(result.ranking["Campeón %"].sum()),
            "top_20": result.ranking.head(20).to_dict(orient="records"),
            "argentina_stages": result.argentina_stages.to_dict(orient="records"),
            "argentina_rivals": {
                round_name: frame.head(20).to_dict(orient="records")
                for round_name, frame in result.argentina_rivals.items()
            },
            "final_pairs": result.final_pairs.head(20).to_dict(orient="records"),
            "sensitivity_rows": len(result.sensitivity),
            "top_brackets": [
                {key: value for key, value in bracket.items() if key != "representative"}
                for bracket in result.top_brackets
            ],
        }
        if mode == ModelMode.HYBRID:
            hybrid_result = result

    if hybrid_result is None or len(hybrid_result.top_brackets) != 5:
        raise RuntimeError("HYBRID did not produce exactly five bracket families")
    bracket_manifests = export_five_brackets(
        hybrid_result.top_brackets,
        teams,
        output / "brackets-4k",
        sirius_application=sirius_application_status(
            hybrid_result.sirius_assessments,
            hybrid_result.sirius_evidence_audit,
        ),
    )
    acceptance = {
        "teams": len(teams) == args.format_size,
        "legal_draws": draw_analysis.iterations >= 100_000,
        "simulations_each_mode": all(
            item["champion_probability_sum"] > 99.999 for item in simulations.values()
        ),
        "five_brackets": len(bracket_manifests) == 5,
        "three_formats": all(len(item["files"]) == 3 for item in bracket_manifests),
        "sensitivity_12_rows": all(item["sensitivity_rows"] == 12 for item in simulations.values()),
        "backtest_four_models": set(backtest.metrics["model"])
        == {"FOOTBALL_ONLY", "SIRIUS_PURIST", "SIRIUS_CALIBRATED", "HYBRID"},
        "backtest_no_temporal_leakage": bool(
            (~backtest.leakage_audit["same_match_used"]).all()
            and (~backtest.leakage_audit["future_edition_used_for_calibration"]).all()
        ),
        "backtest_historical_shapes": all(
            shape["matches"] == (104 if int(edition) == 2026 else 64)
            and shape["teams"] == (48 if int(edition) == 2026 else 32)
            and shape["champion"] is not None
            for edition, shape in historical_shapes.items()
        ),
        "backtest_all_champions_reported": set(backtest.champion_ranking["edition"])
        == set(EDITION_FOLDERS),
        "backtest_sirius_ranks_not_invented": bool(
            backtest.champion_ranking.loc[
                backtest.champion_ranking["model"].isin({"SIRIUS_PURIST", "SIRIUS_CALIBRATED"}),
                "rank",
            ]
            .isna()
            .all()
        ),
        "backtest_rating_ranks_tie_aware": bool(
            backtest.champion_ranking.loc[
                backtest.champion_ranking["status"] == "tied_pre_tournament_rating",
                "rank",
            ]
            .isna()
            .all()
        ),
    }
    manifest = {
        "release": "0.4.0",
        "created_at": datetime.now(UTC).isoformat(),
        "scenario": scenario.scenario_id,
        "format_size": args.format_size,
        "iterations_per_mode": args.iterations,
        "draw": {
            "seconds": draw_seconds,
            "iterations": draw_analysis.iterations,
            "unique_states": draw_analysis.unique_states,
            "lag_one_repeat_rate": draw_analysis.lag_one_repeat_rate,
            "difficulty_bands": draw_analysis.difficulty_bands,
        },
        "backtest": {
            "path": (output / "backtest.json").as_posix(),
            "matches": len(historical_matches),
            "available_editions": historical_editions,
            "missing_editions": backtest_manifest["missing_editions"],
            "models": sorted(str(model) for model in set(backtest.metrics["model"])),
        },
        "simulations": simulations,
        "brackets": bracket_manifests,
        "acceptance": acceptance,
    }
    (output / "acceptance.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    latest_backtest = ROOT / "storage" / "backtests" / "latest.json"
    latest_backtest.parent.mkdir(parents=True, exist_ok=True)
    latest_backtest.write_text(
        json.dumps(backtest_manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    if not all(acceptance.values()):
        failed = sorted(name for name, passed in acceptance.items() if not passed)
        raise RuntimeError(f"release acceptance failed: {failed}")
    print(json.dumps({"output": output.as_posix(), **manifest["acceptance"]}, indent=2))


if __name__ == "__main__":
    main()
