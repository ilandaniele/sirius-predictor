from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

import yaml
from sqlalchemy.orm import Session

from collectors.common.base import Collector
from collectors.common.pipeline import UpdatePipeline, UpdateReport
from collectors.common.raw import raw_collector_from_config
from collectors.fifa import fifa_ranking_collector_from_config
from collectors.sirius_archive import sirius_archive_collector_from_config
from db.predictions import persist_prediction_manifest
from db.repository import append_claim, sync_source_catalog
from db.session import build_engine
from engine.config import Scenario, load_scenario, load_teams, teams_for_scenario
from packages.astrology import ChartRecalculationReport, recalculate_accepted_charts
from packages.common.config import ROOT, Settings, get_settings
from packages.common.provenance import SourceClaimInput
from packages.common.types import ModelMode
from packages.montecarlo import ParallelSimulationResult, run_parallel
from packages.reports import BracketExportSpec, export_five_brackets
from packages.sirius import SiriusReviewQueue


@dataclass(frozen=True, slots=True)
class UpdateCommand:
    iterations: int
    seed: int
    modes: tuple[ModelMode, ...]
    final_hour: int = 18
    workers: int | None = None
    format_size: int = 64


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
        reviewed_observations_path: str | Path | None,
    ) -> ParallelSimulationResult: ...


class PredictionArchive:
    def __init__(self, root: Path):
        self.root = root
        self.predictions = root / "predictions"
        self.latest_path = self.predictions / "latest.json"

    def load_latest(self, format_size: int | None = None) -> dict[str, Any] | None:
        path = (
            self.predictions / f"latest-{format_size}.json"
            if format_size is not None
            else self.latest_path
        )
        if not path.exists() and format_size == 64 and self.latest_path.exists():
            legacy = json.loads(self.latest_path.read_text(encoding="utf-8"))
            if legacy.get("format_size", 64) == 64:
                return legacy
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

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
        format_size = manifest.get("format_size")
        if format_size in {48, 64}:
            self._atomic_write(self.predictions / f"latest-{format_size}.json", serialized)
        return target

    def append_update_event(
        self,
        sources: list[dict[str, Any]],
        report: UpdateReport,
        claim_persistence: dict[str, int] | None = None,
    ) -> Path:
        created_at = datetime.now(UTC)
        payload = {
            "created_at": created_at.isoformat(),
            "sources": sources,
            "accepted_claims": len(report.accepted),
            "pending_review": len(report.pending_review),
            "conflicts": len(report.conflicts),
            "claim_persistence": claim_persistence or {},
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

    def history(self, limit: int = 100, format_size: int | None = None) -> list[dict[str, Any]]:
        if not self.predictions.exists():
            return []
        manifests = []
        for path in self.predictions.glob("*/manifest.json"):
            manifest = json.loads(path.read_text(encoding="utf-8"))
            if format_size is None or manifest.get("format_size", 64) == format_size:
                manifests.append(manifest)
        return sorted(manifests, key=lambda item: item["created_at"], reverse=True)[:limit]

    def probability_history(
        self, team_ids: set[str], format_size: int | None = None
    ) -> list[dict[str, Any]]:
        rows = []
        for manifest in reversed(self.history(limit=10_000, format_size=format_size)):
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
        (
            sirius_archive_collector_from_config(record)
            if record.get("id") == "sirius_blog"
            else fifa_ranking_collector_from_config(record)
            if record.get("id") == "fifa_ranking"
            else raw_collector_from_config(record, ROOT)
        )
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


def _git_state() -> dict[str, Any]:
    commit = _git_commit()
    diff = subprocess.run(
        ["git", "diff", "--binary", "HEAD", "--", "."],
        cwd=ROOT,
        check=False,
        capture_output=True,
        timeout=15,
    )
    untracked = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard", "-z"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        timeout=15,
    )
    digest = hashlib.sha256()
    dirty = bool(diff.stdout or untracked.stdout)
    digest.update(diff.stdout)
    root = ROOT.resolve()
    for raw_relative in sorted(value for value in untracked.stdout.split(b"\0") if value):
        relative = raw_relative.decode("utf-8", errors="surrogateescape")
        target = (root / relative).resolve()
        if root not in target.parents or not target.is_file():
            continue
        digest.update(raw_relative)
        digest.update(target.read_bytes())
    return {
        "git_commit": commit,
        "git_dirty": dirty,
        "working_tree_sha256": digest.hexdigest() if dirty else None,
    }


def _source_manifest(report: UpdateReport, previous: dict[str, Any] | None) -> list[dict[str, Any]]:
    previous_sources = {item["source_id"]: item for item in (previous or {}).get("sources", [])}
    rows = []
    for outcome in report.outcomes:
        effective_hash = outcome.payload_sha256
        retained_previous = False
        if effective_hash is None and outcome.source_id in previous_sources:
            effective_hash = previous_sources[outcome.source_id].get("effective_sha256")
            retained_previous = True
        previous_source = previous_sources.get(outcome.source_id, {})
        snapshot_path = outcome.snapshot_path
        if snapshot_path is None and retained_previous:
            snapshot_path = previous_source.get("snapshot_path")
        # Accepted evidence is not automatically a model feature. The simulation currently
        # consumes the explicit scenario; reviewed Sirius evidence is attached separately.
        model_input = outcome.source_id == "scenario"
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
                "snapshot_path": snapshot_path,
                "error": outcome.error,
            }
        )
    return rows


def _reviewed_snapshot(settings: Settings) -> tuple[dict[str, Any] | None, Path | None]:
    pointer_path = settings.storage_path / "sirius-review" / "latest.json"
    if not pointer_path.is_file():
        return None, None
    pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    review_root = (settings.storage_path / "sirius-review").resolve()
    root = (review_root / "snapshots").resolve()
    relative_path = pointer.get("relative_path")
    target = (
        (review_root / str(relative_path)).resolve()
        if relative_path
        else Path(str(pointer.get("path", ""))).resolve()
    )
    snapshot_id = str(pointer.get("snapshot_id", ""))
    if (
        len(snapshot_id) != 64
        or any(character not in "0123456789abcdef" for character in snapshot_id)
        or root not in target.parents
        or target.name != f"{snapshot_id}.yaml"
        or not target.is_file()
    ):
        raise ValueError("invalid Sirius reviewed-observation snapshot pointer")
    snapshot = yaml.safe_load(target.read_text(encoding="utf-8"))
    records = snapshot.get("records", []) if isinstance(snapshot, dict) else []
    records_hash = hashlib.sha256(
        json.dumps(
            records,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    if (
        not isinstance(snapshot, dict)
        or snapshot.get("schema_version") != "sirius-observations-v1"
        or snapshot.get("snapshot_id") != snapshot_id
        or records_hash != snapshot_id
    ):
        raise ValueError("Sirius reviewed-observation snapshot failed integrity validation")
    return pointer, target


def _attach_review_snapshot(sources: list[dict[str, Any]], pointer: dict[str, Any] | None) -> None:
    if pointer is None:
        return
    sirius = next((item for item in sources if item["source_id"] == "sirius_blog"), None)
    if sirius is None:
        return
    sirius["review_snapshot_sha256"] = pointer["snapshot_id"]
    sirius["review_snapshot_path"] = pointer["path"]
    sirius["reviewed_observations"] = int(pointer.get("reviewed_observations", 0))


def _input_hash(
    command: UpdateCommand,
    scenario: Scenario,
    sources: list[dict[str, Any]],
    git_state: dict[str, Any] | None = None,
) -> str:
    code_state = git_state or _git_state()
    stable_sources = [
        {"source_id": item["source_id"], "sha256": item["effective_sha256"]}
        for item in sources
        if item["effective_sha256"] and item["model_input"]
    ]
    review_snapshots = [
        {
            "source_id": item["source_id"],
            "sha256": item["review_snapshot_sha256"],
        }
        for item in sources
        if item.get("review_snapshot_sha256")
    ]
    payload = {
        "scenario_id": scenario.scenario_id,
        "scenario_as_of": scenario.as_of,
        "scenario_sha256": hashlib.sha256(
            json.dumps(asdict(scenario), sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest(),
        "sources": stable_sources,
        "reviewed_sirius": review_snapshots,
        "sirius_observations_sha256": hashlib.sha256(
            (ROOT / scenario.models.sirius_observations_file).read_bytes()
        ).hexdigest(),
        "seed": command.seed,
        "iterations": command.iterations,
        "modes": [mode.value for mode in command.modes],
        "final_hour": command.final_hour,
        "model_version": scenario.models.sirius_version,
        "git_commit": code_state["git_commit"],
        "git_dirty": code_state["git_dirty"],
        "working_tree_sha256": code_state["working_tree_sha256"],
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
    git_state: dict[str, Any] | None = None,
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
    current_review = {
        item["source_id"]: item.get("review_snapshot_sha256")
        for item in sources
        if item.get("review_snapshot_sha256")
    }
    previous_review = {
        item["source_id"]: item.get("review_snapshot_sha256")
        for item in previous.get("sources", [])
        if item.get("review_snapshot_sha256")
    }
    scenario_hash = hashlib.sha256(
        json.dumps(asdict(scenario), sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()
    previous_scenario_hash = previous.get("scenario_sha256")
    observations_hash = hashlib.sha256(
        (ROOT / scenario.models.sirius_observations_file).read_bytes()
    ).hexdigest()
    code_state = git_state or _git_state()
    return bool(
        current_sources == previous_sources
        and current_review == previous_review
        and previous.get("seed") == command.seed
        and previous.get("simulations_count") == command.iterations
        and set(previous.get("simulations", {})) == {mode.value for mode in command.modes}
        and previous.get("final_hour", 18) == command.final_hour
        and previous.get("model_version") == model_version
        and previous.get("sirius_observations_sha256") == observations_hash
        and previous.get("git_commit") == code_state["git_commit"]
        and previous.get("git_dirty", False) == code_state["git_dirty"]
        and previous.get("working_tree_sha256") == code_state["working_tree_sha256"]
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
        "sirius_evidence_audit": result.sirius_evidence_audit,
    }


def _sirius_reasons(result: ParallelSimulationResult) -> dict[str, list[str]]:
    reasons: dict[str, list[str]] = {}
    for team_id, assessment in result.sirius_assessments.items():
        favorable = [
            f"A favor: {item['description']}" for item in assessment.get("favorable", [])[:2]
        ]
        adverse = [
            f"En contra: {item['description']}" for item in assessment.get("adverse", [])[:2]
        ]
        combined = favorable + adverse
        reasons[team_id] = combined or [
            "Sin testimonios Sirius revisados; el ajuste aplicado es neutral"
        ]
    return reasons


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

    def _recalculate_charts(self, claims: list[SourceClaimInput]) -> ChartRecalculationReport:
        relevant = [
            claim
            for claim in claims
            if claim.entity_type in {"BirthData", "Fixture", "CoachDebutEvent"}
        ]
        if not relevant:
            return ChartRecalculationReport()
        chart_engine = build_engine(self.settings.database_url)
        try:
            with Session(chart_engine) as chart_session:
                report = recalculate_accepted_charts(chart_session, relevant)
                chart_session.commit()
                return report
        finally:
            chart_engine.dispose()

    def _persist_claims(self, report: UpdateReport) -> dict[str, int]:
        claims = [claim for outcome in report.outcomes for claim in outcome.claims]
        if not claims:
            return {
                "observed": 0,
                "inserted": 0,
                "duplicates": 0,
                "eligible": 0,
                "pending": 0,
                "sources_created": 0,
                "sources_updated": 0,
            }
        raw_catalog = yaml.safe_load(self.settings.sources_path.read_text(encoding="utf-8"))
        if not isinstance(raw_catalog, list):
            raise ValueError("sources catalog must be a list")
        catalog = [dict(item) for item in raw_catalog if isinstance(item, dict)]
        configured_ids = {str(item.get("id")) for item in catalog}
        for collector in self.collectors:
            if collector.spec.source_id in configured_ids:
                continue
            catalog.append(
                {
                    "id": collector.spec.source_id,
                    "name": collector.spec.source_id,
                    "grade": collector.spec.grade.value,
                    "official": collector.spec.official,
                    "url": collector.spec.url,
                    "terms_url": collector.spec.terms_url,
                    "enabled": True,
                }
            )
        claim_engine = build_engine(self.settings.database_url)
        try:
            with Session(claim_engine) as claim_session:
                source_metrics = sync_source_catalog(claim_session, catalog)
                inserted = 0
                duplicates = 0
                eligible = 0
                pending = 0
                for claim in claims:
                    outcome = append_claim(claim_session, claim)
                    if not outcome.created:
                        duplicates += 1
                        continue
                    inserted += 1
                    eligible += int(outcome.eligible)
                    pending += int(not outcome.eligible)
                claim_session.commit()
        finally:
            claim_engine.dispose()
        return {
            "observed": len(claims),
            "inserted": inserted,
            "duplicates": duplicates,
            "eligible": eligible,
            "pending": pending,
            "sources_created": source_metrics["created"],
            "sources_updated": source_metrics["updated"],
        }

    def _persist_prediction(self, manifest: dict[str, Any], scenario: Scenario) -> dict[str, int]:
        prediction_engine = build_engine(self.settings.database_url)
        try:
            with Session(prediction_engine) as prediction_session:
                metrics = persist_prediction_manifest(
                    prediction_session,
                    manifest,
                    scenario,
                    self.settings.model_version,
                )
                prediction_session.commit()
                return metrics
        finally:
            prediction_engine.dispose()

    def run(self, command: UpdateCommand) -> UpdateExecution:
        scenario_path = self.settings.scenario_path_for(command.format_size)
        scenario = load_scenario(scenario_path)
        teams = teams_for_scenario(load_teams(self.settings.teams_path), scenario)
        previous = self.archive.load_latest(command.format_size)
        update = UpdatePipeline(
            self.collectors, self.settings.storage_path / "source_snapshots"
        ).run()
        claim_persistence = self._persist_claims(update)
        sirius_outcome = next(
            (
                outcome
                for outcome in update.outcomes
                if outcome.source_id == "sirius_blog"
                and outcome.status == "success"
                and outcome.snapshot_path
            ),
            None,
        )
        if sirius_outcome is not None:
            review_engine = build_engine(self.settings.database_url)
            try:
                with Session(review_engine) as review_session:
                    review_queue = SiriusReviewQueue(
                        review_session,
                        rules_path=ROOT / "data" / "sirius_rules.yaml",
                        teams_path=self.settings.teams_path,
                    )
                    review_queue.sync_archive(Path(str(sirius_outcome.snapshot_path)).read_bytes())
                    review_session.commit()
                    review_queue.export_reviewed_snapshot(
                        self.settings.storage_path / "sirius-review"
                    )
            finally:
                review_engine.dispose()
        sources = _source_manifest(update, previous)
        review_pointer, reviewed_observations_path = _reviewed_snapshot(self.settings)
        _attach_review_snapshot(sources, review_pointer)
        update_event_path = self.archive.append_update_event(
            sources,
            update,
            claim_persistence,
        )
        git_state = _git_state()
        snapshot_id = _input_hash(command, scenario, sources, git_state)
        existing = self.archive.load(snapshot_id)
        if existing is None and _matches_previous_inputs(
            previous,
            command,
            scenario,
            sources,
            self.settings.model_version,
            git_state,
        ):
            existing = previous
        if existing is not None:
            self._persist_prediction(existing, scenario)
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

        chart_recalculation = self._recalculate_charts(update.accepted)
        chart_recalculation_payload = chart_recalculation.to_dict()
        affected_charts = chart_recalculation.requested_entities
        simulations: dict[str, dict[str, Any]] = {}
        raw_results: dict[ModelMode, ParallelSimulationResult] = {}
        for mode in command.modes:
            result = self.simulator(
                scenario_path,
                self.settings.teams_path,
                command.iterations,
                command.seed,
                mode,
                command.final_hour,
                command.workers,
                reviewed_observations_path,
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
                    f"- Git commit: {git_state['git_commit']}",
                    f"- Git dirty: {git_state['git_dirty']}",
                    f"- Working tree SHA-256: {git_state['working_tree_sha256'] or 'clean'}",
                    f"- Resumen: {summary}",
                    f"- Cartas afectadas solicitadas: {len(affected_charts)}",
                    (f"- Cartas recalculadas: {chart_recalculation_payload['recalculated_count']}"),
                    f"- Aciertos de caché: {chart_recalculation_payload['cache_hit_count']}",
                    f"- Cartas omitidas: {chart_recalculation_payload['skipped_count']}",
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
                sirius_reasons=_sirius_reasons(hybrid_result),
                spec=self.bracket_spec,
            )
            bracket_manifest_path = (output_dir / "brackets" / "manifest.json").as_posix()

        manifest = {
            "schema_version": "prediction-manifest-v2",
            "snapshot_id": snapshot_id,
            "created_at": created_at,
            **git_state,
            "model_version": self.settings.model_version,
            "scenario_id": scenario.scenario_id,
            "format_size": scenario.format.teams,
            "scenario_sha256": hashlib.sha256(
                json.dumps(asdict(scenario), sort_keys=True, ensure_ascii=False).encode()
            ).hexdigest(),
            "sirius_observations_sha256": hashlib.sha256(
                (ROOT / scenario.models.sirius_observations_file).read_bytes()
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
            "chart_recalculation": chart_recalculation_payload,
            "sirius_recalculation": {
                "status": "completed",
                "review_snapshot_sha256": (
                    review_pointer.get("snapshot_id") if review_pointer is not None else None
                ),
                "reviewed_observations": (
                    int(review_pointer.get("reviewed_observations", 0))
                    if review_pointer is not None
                    else 0
                ),
                "modes": [mode.value for mode in command.modes],
            },
            "sirius_assessments": (
                hybrid_result.sirius_assessments if hybrid_result is not None else {}
            ),
            "sirius_evidence_audit": (
                hybrid_result.sirius_evidence_audit if hybrid_result is not None else {}
            ),
            "quality_pending_review": len(update.pending_review),
            "claim_persistence": claim_persistence,
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
        self._persist_prediction(manifest, scenario)
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
