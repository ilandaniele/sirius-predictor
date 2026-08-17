from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

import yaml

from collectors.common.base import Collector
from collectors.common.pipeline import UpdatePipeline, UpdateReport
from collectors.common.raw import raw_collector_from_config
from engine.config import Scenario, load_scenario, load_teams
from packages.common.config import ROOT, Settings, get_settings
from packages.common.types import ModelMode
from packages.montecarlo import ParallelSimulationResult, run_parallel
from packages.reports import BracketExportSpec, export_five_brackets


@dataclass(frozen=True, slots=True)
class UpdateCommand:
    iterations: int
    seed: int
    modes: tuple[ModelMode, ...]
    final_hour: int = 18
    workers: int | None = None


@dataclass(slots=True)
class UpdateExecution:
    snapshot_id: str
    created_at: str
    idempotent_replay: bool
    summary: str
    relevant_changes: list[str]
    manifest_path: str
    report_path: str
    bracket_manifest_path: str | None
    update_event_path: str


class Simulator(Protocol):
    def __call__(
        self,
        scenario_path: str | Path,
        teams_path: str | Path,
        iterations: int,
        seed: int,
        mode: ModelMode,
        final_hour: int,
        workers: int | None,
    ) -> ParallelSimulationResult: ...


class PredictionArchive:
    def __init__(self, root: Path):
        self.root = root
        self.predictions = root / "predictions"
        self.latest_path = self.predictions / "latest.json"

    def load_latest(self) -> dict[str, Any] | None:
        if not self.latest_path.exists():
            return None
        return json.loads(self.latest_path.read_text(encoding="utf-8"))

    def load(self, snapshot_id: str) -> dict[str, Any] | None:
        path = self.predictions / snapshot_id / "manifest.json"
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None

    @staticmethod
    def _atomic_write(path: Path, payload: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(payload, encoding="utf-8")
        temporary.replace(path)

    def append(self, snapshot_id: str, manifest: dict[str, Any]) -> Path:
        target = self.predictions / snapshot_id / "manifest.json"
        if target.exists():
            raise FileExistsError(f"prediction snapshot already exists: {snapshot_id}")
        serialized = json.dumps(manifest, ensure_ascii=False, indent=2)
        self._atomic_write(target, serialized)
        self._atomic_write(self.latest_path, serialized)
        return target

    def append_update_event(
        self,
        sources: list[dict[str, Any]],
        report: UpdateReport,
    ) -> Path:
        created_at = datetime.now(UTC)
        payload = {
            "created_at": created_at.isoformat(),
            "sources": sources,
            "accepted_claims": len(report.accepted),
            "pending_review": len(report.pending_review),
            "conflicts": len(report.conflicts),
        }
        event_id = hashlib.sha256(
            json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest()
        payload["event_id"] = event_id
        target = (
            self.root
            / "update-events"
            / f"{created_at.strftime('%Y%m%dT%H%M%S.%fZ')}-{event_id}.json"
        )
        if target.exists():
            raise FileExistsError(f"update event already exists: {event_id}")
        self._atomic_write(target, json.dumps(payload, ensure_ascii=False, indent=2))
        return target

    def latest_update_event(self) -> dict[str, Any] | None:
        directory = self.root / "update-events"
        paths = sorted(directory.glob("*.json"), reverse=True) if directory.exists() else []
        return json.loads(paths[0].read_text(encoding="utf-8")) if paths else None

    def history(self, limit: int = 100) -> list[dict[str, Any]]:
        if not self.predictions.exists():
            return []
        manifests = []
        for path in self.predictions.glob("*/manifest.json"):
            manifests.append(json.loads(path.read_text(encoding="utf-8")))
        return sorted(manifests, key=lambda item: item["created_at"], reverse=True)[:limit]

    def probability_history(self, team_ids: set[str]) -> list[dict[str, Any]]:
        rows = []
        for manifest in reversed(self.history(limit=10_000)):
            for mode, simulation in manifest.get("simulations", {}).items():
                for team in simulation.get("ranking", []):
                    if team.get("ID") in team_ids:
                        rows.append(
                            {
                                "snapshot_id": manifest["snapshot_id"],
                                "created_at": manifest["created_at"],
                                "model_version": manifest["model_version"],
                                "mode": mode,
                                "team_id": team["ID"],
                                "team": team["Selección"],
                                "champion_probability": team["Campeón %"],
                            }
                        )
        return rows


def build_collectors(settings: Settings) -> list[Collector]:
    raw = yaml.safe_load(settings.sources_path.read_text(encoding="utf-8"))
    return [
        raw_collector_from_config(record, ROOT)
        for record in raw
        if record.get("enabled") and record.get("url")
    ]


def _git_commit() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=5,
    )
    return result.stdout.strip() if result.returncode == 0 else "unavailable"


def _source_manifest(report: UpdateReport, previous: dict[str, Any] | None) -> list[dict[str, Any]]:
    previous_sources = {item["source_id"]: item for item in (previous or {}).get("sources", [])}
    accepted_sources = {claim.source_id for claim in report.accepted}
    rows = []
    for outcome in report.outcomes:
        effective_hash = outcome.payload_sha256
        retained_previous = False
        if effective_hash is None and outcome.source_id in previous_sources:
            effective_hash = previous_sources[outcome.source_id].get("effective_sha256")
            retained_previous = True
        previous_source = previous_sources.get(outcome.source_id, {})
        model_input = (
            outcome.source_id == "scenario"
            or outcome.source_id in accepted_sources
            or bool(previous_source.get("model_input", False))
        )
        rows.append(
            {
                "source_id": outcome.source_id,
                "source_url": outcome.source_url,
                "quality": outcome.quality.value,
                "consulted_at": outcome.consulted_at.isoformat(),
                "fetch_status": outcome.status,
                "effective_sha256": effective_hash,
                "retained_previous": retained_previous,
                "model_input": model_input,
                "snapshot_path": outcome.snapshot_path,
                "error": outcome.error,
            }
        )
    return rows


def _input_hash(
    command: UpdateCommand,
    scenario: Scenario,
    sources: list[dict[str, Any]],
) -> str:
    stable_sources = [
        {"source_id": item["source_id"], "sha256": item["effective_sha256"]}
        for item in sources
        if item["effective_sha256"] and item["model_input"]
    ]
    payload = {
        "scenario_id": scenario.scenario_id,
        "scenario_as_of": scenario.as_of,
        "scenario_sha256": hashlib.sha256(
            json.dumps(asdict(scenario), sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest(),
        "sources": stable_sources,
        "seed": command.seed,
        "iterations": command.iterations,
        "modes": [mode.value for mode in command.modes],
        "final_hour": command.final_hour,
        "model_version": scenario.models.sirius_version,
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def _matches_previous_inputs(
    previous: dict[str, Any] | None,
    command: UpdateCommand,
    scenario: Scenario,
    sources: list[dict[str, Any]],
    model_version: str,
) -> bool:
    if previous is None:
        return False
    current_sources = {
        item["source_id"]: item["effective_sha256"]
        for item in sources
        if item["model_input"] and item["effective_sha256"]
    }
    previous_sources = {
        item["source_id"]: item.get("effective_sha256")
        for item in previous.get("sources", [])
        if item.get("model_input", item.get("source_id") == "scenario")
        and item.get("effective_sha256")
    }
    scenario_hash = hashlib.sha256(
        json.dumps(asdict(scenario), sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()
    previous_scenario_hash = previous.get("scenario_sha256")
    return bool(
        current_sources == previous_sources
        and previous.get("seed") == command.seed
        and previous.get("simulations_count") == command.iterations
        and set(previous.get("simulations", {})) == {mode.value for mode in command.modes}
        and previous.get("final_hour", 18) == command.final_hour
        and previous.get("model_version") == model_version
        and (previous_scenario_hash is None or previous_scenario_hash == scenario_hash)
    )


def _simulation_summary(result: ParallelSimulationResult) -> dict[str, Any]:
    return {
        "run_id": result.run_id,
        "mode": result.mode.value,
        "iterations": result.iterations,
        "seed": result.seed,
        "workers": result.workers,
        "ranking": result.ranking.to_dict(orient="records"),
        "argentina_stages": result.argentina_stages.to_dict(orient="records"),
        "argentina_rivals": {
            key: frame.to_dict(orient="records") for key, frame in result.argentina_rivals.items()
        },
        "argentina_groups": result.argentina_groups.to_dict(orient="records"),
        "final_pairs": result.final_pairs.to_dict(orient="records"),
        "sensitivity": result.sensitivity.to_dict(orient="records"),
        "top_brackets": [
            {key: value for key, value in bracket.items() if key != "representative"}
            for bracket in result.top_brackets
        ],
    }


def _argentina_probability(simulations: dict[str, dict[str, Any]]) -> float | None:
    hybrid = simulations.get(ModelMode.HYBRID.value)
    if not hybrid:
        return None
    argentina = next((row for row in hybrid["ranking"] if row["ID"] == "ARG"), None)
    return float(argentina["Campeón %"]) if argentina else None


class UpdateOrchestrator:
    def __init__(
        self,
        settings: Settings | None = None,
        collectors: list[Collector] | None = None,
        simulator: Simulator = run_parallel,
        bracket_spec: BracketExportSpec | None = None,
    ):
        self.settings = settings or get_settings()
        self.collectors = collectors if collectors is not None else build_collectors(self.settings)
        self.simulator = simulator
        self.archive = PredictionArchive(self.settings.storage_path)
        self.bracket_spec = bracket_spec

    def run(self, command: UpdateCommand) -> UpdateExecution:
        scenario = load_scenario(self.settings.scenario_path)
        teams = load_teams(self.settings.teams_path)
        previous = self.archive.load_latest()
        update = UpdatePipeline(
            self.collectors, self.settings.storage_path / "source_snapshots"
        ).run()
        sources = _source_manifest(update, previous)
        update_event_path = self.archive.append_update_event(sources, update)
        snapshot_id = _input_hash(command, scenario, sources)
        existing = self.archive.load(snapshot_id)
        if existing is None and _matches_previous_inputs(
            previous,
            command,
            scenario,
            sources,
            self.settings.model_version,
        ):
            existing = previous
        if existing is not None:
            snapshot_id = str(existing["snapshot_id"])
            successful_sources = sum(outcome.status == "success" for outcome in update.outcomes)
            return UpdateExecution(
                snapshot_id=snapshot_id,
                created_at=str(existing["created_at"]),
                idempotent_replay=True,
                summary=(
                    f"{successful_sources} fuentes actualizadas · "
                    "0 cambios de inputs · predicción sin cambios"
                ),
                relevant_changes=[],
                manifest_path=(self.archive.predictions / snapshot_id / "manifest.json").as_posix(),
                report_path=str(existing["report_path"]),
                bracket_manifest_path=existing.get("bracket_manifest_path"),
                update_event_path=update_event_path.as_posix(),
            )

        affected_charts = sorted(
            {
                f"{claim.entity_type}:{claim.entity_key}"
                for claim in update.accepted
                if claim.entity_type in {"BirthData", "Fixture", "CoachDebutEvent"}
            }
        )
        simulations: dict[str, dict[str, Any]] = {}
        raw_results: dict[ModelMode, ParallelSimulationResult] = {}
        for mode in command.modes:
            result = self.simulator(
                self.settings.scenario_path,
                self.settings.teams_path,
                command.iterations,
                command.seed,
                mode,
                command.final_hour,
                command.workers,
            )
            raw_results[mode] = result
            simulations[mode.value] = _simulation_summary(result)

        previous_probability = _argentina_probability((previous or {}).get("simulations", {}))
        current_probability = _argentina_probability(simulations)
        relevant_changes = []
        if previous_probability is not None and current_probability is not None:
            delta = current_probability - previous_probability
            if abs(delta) >= 0.05:
                relevant_changes.append(f"Argentina {delta:+.2f} pp")
        changed_sources = []
        previous_hashes = {
            item["source_id"]: item.get("effective_sha256")
            for item in (previous or {}).get("sources", [])
        }
        for source in sources:
            if source["effective_sha256"] != previous_hashes.get(source["source_id"]):
                changed_sources.append(source["source_id"])
        relevant_changes.extend(f"fuente modificada: {source}" for source in changed_sources)
        relevant_changes.extend(
            f"conflicto pendiente: {conflict['key']}" for conflict in update.conflicts
        )

        created_at = datetime.now(UTC).isoformat()
        output_dir = self.archive.predictions / snapshot_id
        report_path = output_dir / "report.md"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        successful_sources = sum(outcome.status == "success" for outcome in update.outcomes)
        summary_parts = [
            f"{successful_sources} fuentes actualizadas",
            f"{len(relevant_changes)} cambios relevantes",
            *relevant_changes[:3],
        ]
        summary = " · ".join(summary_parts)
        report_path.write_text(
            "\n".join(
                [
                    f"# Mundial 2030 Sirius Engine · {snapshot_id}",
                    "",
                    "> Astrología experimental sin validez científica demostrada.",
                    "",
                    f"- Creado: {created_at}",
                    f"- Git commit: {_git_commit()}",
                    f"- Resumen: {summary}",
                    f"- Cartas recalculadas: {len(affected_charts)}",
                    f"- Modos: {', '.join(simulations)}",
                    "",
                    "## Cambios",
                    *(f"- {change}" for change in relevant_changes),
                ]
            ),
            encoding="utf-8",
        )

        bracket_manifest_path = None
        hybrid_result = raw_results.get(ModelMode.HYBRID)
        if hybrid_result is not None:
            export_five_brackets(
                hybrid_result.top_brackets,
                teams,
                output_dir / "brackets",
                spec=self.bracket_spec,
            )
            bracket_manifest_path = (output_dir / "brackets" / "manifest.json").as_posix()

        manifest = {
            "snapshot_id": snapshot_id,
            "created_at": created_at,
            "git_commit": _git_commit(),
            "model_version": self.settings.model_version,
            "scenario_sha256": hashlib.sha256(
                json.dumps(asdict(scenario), sort_keys=True, ensure_ascii=False).encode()
            ).hexdigest(),
            "sources": sources,
            "assumptions": {
                **scenario.assumptions,
                "format_status": scenario.status,
                "bracket": scenario.bracket.description,
            },
            "seed": command.seed,
            "final_hour": command.final_hour,
            "simulations_count": command.iterations,
            "weights": {},
            "simulations": simulations,
            "affected_charts": affected_charts,
            "sirius_recalculation": "only_affected_entities",
            "quality_pending_review": len(update.pending_review),
            "conflicts": len(update.conflicts),
            "relevant_changes": relevant_changes,
            "summary": summary,
            "report_path": report_path.as_posix(),
            "bracket_manifest_path": bracket_manifest_path,
            "notifications": [
                {"channel": "local_event_log", "message": summary, "created_at": created_at}
            ],
        }
        manifest_path = self.archive.append(snapshot_id, manifest)
        return UpdateExecution(
            snapshot_id=snapshot_id,
            created_at=created_at,
            idempotent_replay=False,
            summary=summary,
            relevant_changes=relevant_changes,
            manifest_path=manifest_path.as_posix(),
            report_path=report_path.as_posix(),
            bracket_manifest_path=bracket_manifest_path,
            update_event_path=update_event_path.as_posix(),
        )
