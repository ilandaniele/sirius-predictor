from __future__ import annotations

import base64
import hashlib
import io
import json
import math
import shutil
import stat
import tempfile
import xml.etree.ElementTree as ElementTree
import zipfile
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

from PIL import Image

from engine.config import load_scenario, load_teams, teams_for_scenario
from packages.common.config import Settings
from packages.common.types import ModelMode
from packages.football.backtest_artifact import validate_backtest_artifact
from packages.sirius import sirius_application_status

from .update_pipeline import (
    PredictionArchive,
    UpdateCommand,
    UpdateOrchestrator,
    _argentina_probability,
    _ephemeris_manifest,
    _git_state,
    _input_hash,
    _scenario_sha256,
    _sirius_observations_sha256,
    _teams_sha256,
)

INPUT_SCHEMA = "local-simulation-input-v1"
RESULT_SCHEMA = "local-simulation-result-v1"
IMPORT_SCHEMA = "local-simulation-import-v1"
REQUIRED_MODES = tuple(mode.value for mode in ModelMode)
BRACKET_PATHS = {
    f"brackets/bracket-{rank}.{extension}"
    for rank in range(1, 6)
    for extension in ("png", "svg", "pdf")
}
ALLOWED_RESULT_PATHS = {
    "results.json",
    "backtest.json",
    "brackets/manifest.json",
    *BRACKET_PATHS,
}


class LocalComputeConflict(ValueError):
    """The frozen input can no longer be published without a new local run."""


def _json_bytes(payload: Any, *, pretty: bool = False) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=not pretty,
        indent=2 if pretty else None,
        separators=None if pretty else (",", ":"),
    ).encode("utf-8")


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _aware_timestamp(value: object, field_name: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError as exc:
        raise ValueError(f"{field_name} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field_name} must include a UTC offset")
    return parsed


def _safe_id(value: object, field_name: str) -> str:
    identifier = str(value)
    if len(identifier) != 64 or any(
        character not in "0123456789abcdef" for character in identifier
    ):
        raise ValueError(f"{field_name} must be a lowercase SHA-256")
    return identifier


class LocalInputStore:
    def __init__(self, storage_path: Path):
        self.root = storage_path / "local-compute" / "inputs"

    def path(self, input_id: str) -> Path:
        return self.root / _safe_id(input_id, "input_id") / "input.json"

    def append(self, payload: dict[str, Any]) -> Path:
        target = self.path(str(payload["input_id"]))
        serialized = _json_bytes(payload, pretty=True)
        if target.exists():
            if target.read_bytes() != serialized:
                raise ValueError("local input identifier collision")
            return target
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(".json.tmp")
        temporary.write_bytes(serialized)
        temporary.replace(target)
        return target

    def load(self, input_id: str) -> dict[str, Any]:
        target = self.path(input_id)
        if not target.is_file():
            raise FileNotFoundError(f"local simulation input not found: {input_id}")
        payload = json.loads(target.read_text(encoding="utf-8"))
        if payload.get("schema_version") != INPUT_SCHEMA:
            raise ValueError("unsupported local simulation input schema")
        return payload


def _changed_source_messages(
    previous: dict[str, Any] | None,
    sources: list[dict[str, Any]],
) -> list[str]:
    previous_hashes = {
        item["source_id"]: item.get("effective_sha256")
        for item in (previous or {}).get("sources", [])
    }
    return [
        f"fuente modificada: {source['source_id']}"
        for source in sources
        if source.get("effective_sha256") != previous_hashes.get(source["source_id"])
    ]


def prepare_local_simulation(settings: Settings, command: UpdateCommand) -> dict[str, Any]:
    if tuple(mode.value for mode in command.modes) != REQUIRED_MODES:
        raise ValueError("local publication requires FOOTBALL_ONLY, SIRIUS_ONLY and HYBRID")
    orchestrator = UpdateOrchestrator(settings=settings)
    prepared = orchestrator.prepare_inputs(command)
    if prepared.existing is not None:
        orchestrator._persist_prediction(prepared.existing, prepared.scenario)
        return {
            "schema_version": INPUT_SCHEMA,
            "status": "already_published",
            "snapshot_id": prepared.existing["snapshot_id"],
            "format_size": command.format_size,
            "detail": "Los inputs no cambiaron; se conserva el snapshot inmutable existente.",
        }

    chart_report = orchestrator._recalculate_charts(prepared.update.accepted)
    chart_payload = chart_report.to_dict()
    prepared_at = datetime.now(UTC).isoformat()
    conflict_messages = [
        f"conflicto pendiente: {conflict['key']}" for conflict in prepared.update.conflicts
    ]
    base_changes = _changed_source_messages(prepared.previous, prepared.sources) + conflict_messages
    job_core: dict[str, Any] = {
        "schema_version": INPUT_SCHEMA,
        "status": "ready",
        "prepared_at": prepared_at,
        "snapshot_id": prepared.snapshot_id,
        "previous_snapshot_id": (
            prepared.previous.get("snapshot_id") if prepared.previous is not None else None
        ),
        "model_version": settings.model_version,
        "git_commit": prepared.git_state["git_commit"],
        "git_dirty": prepared.git_state["git_dirty"],
        "working_tree_sha256": prepared.git_state.get("working_tree_sha256"),
        "scenario_id": prepared.scenario.scenario_id,
        "format_size": prepared.scenario.format.teams,
        "team_ids": [team.team_id for team in prepared.teams],
        "scenario_sha256": _scenario_sha256(prepared.scenario),
        "teams_sha256": _teams_sha256(prepared.teams),
        "sirius_observations_sha256": _sirius_observations_sha256(prepared.scenario),
        "ephemeris": _ephemeris_manifest(),
        "command": {
            "iterations": command.iterations,
            "seed": command.seed,
            "modes": [mode.value for mode in command.modes],
            "final_hour": command.final_hour,
            "workers": command.workers,
            "format_size": command.format_size,
        },
        "sources": prepared.sources,
        "assumptions": {
            **prepared.scenario.assumptions,
            "format_status": prepared.scenario.status,
            "bracket": prepared.scenario.bracket.description,
        },
        "successful_sources": sum(
            outcome.status == "success" for outcome in prepared.update.outcomes
        ),
        "quality_pending_review": len(prepared.update.pending_review),
        "claim_persistence": prepared.claim_persistence,
        "conflicts": len(prepared.update.conflicts),
        "base_relevant_changes": base_changes,
        "affected_charts": chart_report.requested_entities,
        "chart_recalculation": chart_payload,
        "review_snapshot_sha256": (
            prepared.review_pointer.get("snapshot_id")
            if prepared.review_pointer is not None
            else None
        ),
        "reviewed_observations": (
            int(prepared.review_pointer.get("reviewed_observations", 0))
            if prepared.review_pointer is not None
            else 0
        ),
        "reviewed_observations_path": (
            prepared.reviewed_observations_path.as_posix()
            if prepared.reviewed_observations_path is not None
            else None
        ),
        "update_event_path": prepared.update_event_path.as_posix(),
    }
    input_id = _sha256(
        _json_bytes(
            {
                "snapshot_id": prepared.snapshot_id,
                "prepared_at": prepared_at,
                "update_event_path": prepared.update_event_path.as_posix(),
            }
        )
    )
    job_core["input_id"] = input_id
    LocalInputStore(settings.storage_path).append(job_core)
    response = dict(job_core)
    response.pop("reviewed_observations_path", None)
    response["reviewed_observations_b64"] = (
        base64.b64encode(prepared.reviewed_observations_path.read_bytes()).decode("ascii")
        if prepared.reviewed_observations_path is not None
        else None
    )
    return response


def _validate_sources_do_not_downgrade(
    previous: dict[str, Any] | None,
    sources: list[dict[str, Any]],
) -> None:
    previous_sources = {
        str(item.get("source_id")): item for item in (previous or {}).get("sources", [])
    }
    for source in sources:
        prior = previous_sources.get(str(source.get("source_id")))
        if prior is None:
            continue
        changed = source.get("effective_sha256") != prior.get("effective_sha256")
        if changed and prior.get("quality") == "A" and source.get("quality") in {"C", "D"}:
            raise LocalComputeConflict(
                f"source {source.get('source_id')} cannot automatically replace A with "
                f"{source.get('quality')}"
            )


def _validate_result_payload(results: dict[str, Any], job: dict[str, Any]) -> None:
    if results.get("schema_version") != RESULT_SCHEMA:
        raise ValueError("unsupported local simulation result schema")
    if results.get("input_id") != job["input_id"]:
        raise ValueError("result input_id does not match frozen input")
    if results.get("snapshot_id") != job["snapshot_id"]:
        raise ValueError("result snapshot_id does not match frozen input")
    if results.get("model_version") != job["model_version"]:
        raise ValueError("result model version does not match frozen input")
    if results.get("ephemeris") != job.get("ephemeris"):
        raise ValueError("result ephemeris does not match frozen input")
    completed_at = _aware_timestamp(results.get("completed_at"), "completed_at")
    if completed_at < _aware_timestamp(job.get("prepared_at"), "prepared_at"):
        raise ValueError("completed_at cannot precede the frozen input")
    simulations = results.get("simulations")
    if not isinstance(simulations, dict) or tuple(simulations) != REQUIRED_MODES:
        raise ValueError("result must keep the three model modes separate and ordered")
    command = job["command"]
    for mode in REQUIRED_MODES:
        result = simulations[mode]
        if not isinstance(result, dict) or result.get("mode") != mode:
            raise ValueError(f"{mode}: invalid result payload")
        if result.get("iterations") != command["iterations"]:
            raise ValueError(f"{mode}: iteration count differs from frozen input")
        if result.get("seed") != command["seed"]:
            raise ValueError(f"{mode}: seed differs from frozen input")
        ranking = result.get("ranking")
        if not isinstance(ranking, list) or len(ranking) != job["format_size"]:
            raise ValueError(f"{mode}: ranking must contain every team")
        if {row.get("ID") for row in ranking if isinstance(row, dict)} != set(job["team_ids"]):
            raise ValueError(f"{mode}: ranking team IDs differ from frozen input")
        try:
            probability = sum(float(row["Campe\u00f3n %"]) for row in ranking)
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"{mode}: ranking probabilities are invalid") from exc
        if not math.isclose(probability, 100.0, abs_tol=1e-6):
            raise ValueError(f"{mode}: champion probabilities do not sum to 100")
        sensitivity = result.get("sensitivity", [])
        if len(sensitivity) != 12:
            raise ValueError(f"{mode}: final-hour sensitivity must contain 12 rows")
        expected_times = {
            "16:45",
            "17:00",
            "17:15",
            "17:45",
            "18:00",
            "18:15",
            "19:45",
            "20:00",
            "20:15",
            "20:45",
            "21:00",
            "21:15",
        }
        if {
            row.get("Hora local") for row in sensitivity if isinstance(row, dict)
        } != expected_times:
            raise ValueError(f"{mode}: final-hour sensitivity grid is invalid")
        workers = result.get("workers")
        if not isinstance(workers, int) or not 1 <= workers <= 64:
            raise ValueError(f"{mode}: worker count is invalid")
        run_id = str(result.get("run_id", ""))
        if not 16 <= len(run_id) <= 64 or any(
            character not in "0123456789abcdef" for character in run_id
        ):
            raise ValueError(f"{mode}: run_id must be a lowercase hex digest")
    primary_brackets = simulations[ModelMode.SIRIUS_ONLY.value].get("top_brackets", [])
    if len(primary_brackets) != 5:
        raise ValueError("SIRIUS_ONLY must contain exactly five decisive scenarios")
    for bracket in primary_brackets:
        if (
            not isinstance(bracket, dict)
            or bracket.get("scope") != "SF_AND_FINAL"
            or bracket.get("signature_version") != "decisive-v1"
            or not isinstance(bracket.get("decisive_matches"), list)
            or len(bracket["decisive_matches"]) != 3
        ):
            raise ValueError("SIRIUS_ONLY brackets must describe two semifinals and one final")
    if results.get("sirius_evidence_audit") != simulations[ModelMode.SIRIUS_ONLY.value].get(
        "sirius_evidence_audit"
    ):
        raise ValueError("top-level Sirius evidence audit differs from SIRIUS_ONLY")
    assessments = results.get("sirius_assessments")
    if not isinstance(assessments, dict) or any(
        not isinstance(assessment, dict) for assessment in assessments.values()
    ):
        raise ValueError("Sirius assessments must be an object")
    expected_application = sirius_application_status(
        assessments,
        results.get("sirius_evidence_audit", {}),
    )
    if results.get("sirius_application") != expected_application:
        raise ValueError("top-level Sirius application status is invalid")
    if simulations[ModelMode.SIRIUS_ONLY.value].get("sirius_application") != expected_application:
        raise ValueError("SIRIUS_ONLY Sirius application status differs from evidence")


def _validate_frozen_job(settings: Settings, job: dict[str, Any]) -> None:
    _safe_id(job.get("input_id"), "input_id")
    _safe_id(job.get("snapshot_id"), "snapshot_id")
    if job.get("format_size") not in {48, 64}:
        raise ValueError("frozen input format must be 48 or 64")
    command_payload = job.get("command")
    if (
        not isinstance(command_payload, dict)
        or tuple(command_payload.get("modes", [])) != REQUIRED_MODES
    ):
        raise ValueError("frozen input must keep the three model modes separate and ordered")
    sources = job.get("sources")
    if not isinstance(sources, list):
        raise ValueError("frozen input sources must be a list")
    for source in sources:
        if not isinstance(source, dict):
            raise ValueError("frozen input source must be an object")
        if not source.get("source_id") or not source.get("source_url"):
            raise ValueError("each source requires source_id and source_url")
        _aware_timestamp(source.get("consulted_at"), "source.consulted_at")
        if source.get("quality") not in {"A", "B", "C", "D", "X"}:
            raise ValueError("source quality must be A, B, C, D or X")
        effective_hash = source.get("effective_sha256")
        if effective_hash is not None:
            _safe_id(effective_hash, "source.effective_sha256")

    scenario = load_scenario(settings.scenario_path_for(int(job["format_size"])))
    teams = teams_for_scenario(load_teams(settings.teams_path), scenario)
    if _scenario_sha256(scenario) != job.get("scenario_sha256"):
        raise LocalComputeConflict("server scenario changed after inputs were frozen")
    if _teams_sha256(teams) != job.get("teams_sha256"):
        raise LocalComputeConflict("server teams changed after inputs were frozen")
    if job.get("team_ids") != [team.team_id for team in teams]:
        raise ValueError("frozen input team IDs differ from server teams")
    if _sirius_observations_sha256(scenario) != job.get("sirius_observations_sha256"):
        raise LocalComputeConflict("server Sirius observations changed after inputs were frozen")
    if _ephemeris_manifest() != job.get("ephemeris"):
        raise LocalComputeConflict("server ephemeris changed after inputs were frozen")
    git_state = {
        "git_commit": job.get("git_commit"),
        "git_dirty": job.get("git_dirty"),
        "working_tree_sha256": job.get("working_tree_sha256"),
    }
    command = UpdateCommand(
        iterations=int(command_payload["iterations"]),
        seed=int(command_payload["seed"]),
        modes=tuple(ModelMode(mode) for mode in command_payload["modes"]),
        final_hour=int(command_payload["final_hour"]),
        workers=(
            int(command_payload["workers"]) if command_payload.get("workers") is not None else None
        ),
        format_size=int(command_payload["format_size"]),
    )
    if _input_hash(command, scenario, sources, git_state, teams) != job["snapshot_id"]:
        raise ValueError("frozen input snapshot_id failed deterministic validation")
    expected_input_id = _sha256(
        _json_bytes(
            {
                "snapshot_id": job["snapshot_id"],
                "prepared_at": job["prepared_at"],
                "update_event_path": job["update_event_path"],
            }
        )
    )
    if expected_input_id != job["input_id"]:
        raise ValueError("frozen input input_id failed deterministic validation")


def _read_verified_bundle(
    bundle_path: Path, max_uncompressed_bytes: int
) -> tuple[dict[str, bytes], dict[str, str]]:
    with zipfile.ZipFile(bundle_path) as archive:
        infos = archive.infolist()
        names = [info.filename for info in infos]
        if len(names) != len(set(names)):
            raise ValueError("result bundle contains duplicate paths")
        if "bundle.json" not in names:
            raise ValueError("result bundle has no bundle.json")
        if len(infos) > len(ALLOWED_RESULT_PATHS) + 1:
            raise ValueError("result bundle contains too many files")
        total_size = 0
        for info in infos:
            path = PurePosixPath(info.filename)
            if path.is_absolute() or ".." in path.parts or "\\" in info.filename:
                raise ValueError("result bundle contains an unsafe path")
            if info.flag_bits & 0x1:
                raise ValueError("encrypted result bundles are not supported")
            if stat.S_IFMT(info.external_attr >> 16) == stat.S_IFLNK:
                raise ValueError("result bundle cannot contain symbolic links")
            total_size += info.file_size
        if total_size > max_uncompressed_bytes:
            raise ValueError("uncompressed result bundle exceeds the configured limit")
        bundle = json.loads(archive.read("bundle.json"))
        if bundle.get("schema_version") != RESULT_SCHEMA:
            raise ValueError("unsupported result bundle schema")
        raw_files = bundle.get("files")
        if not isinstance(raw_files, list):
            raise ValueError("bundle file manifest must be a list")
        declared = {str(item.get("path")): item for item in raw_files if isinstance(item, dict)}
        if len(declared) != len(raw_files):
            raise ValueError("bundle file manifest contains duplicates or invalid records")
        if set(declared) != ALLOWED_RESULT_PATHS or set(names) != {
            "bundle.json",
            *ALLOWED_RESULT_PATHS,
        }:
            raise ValueError("result bundle file set is incomplete or unexpected")
        payloads: dict[str, bytes] = {}
        digests: dict[str, str] = {}
        for name in sorted(ALLOWED_RESULT_PATHS):
            payload = archive.read(name)
            record = declared[name]
            digest = _sha256(payload)
            if record.get("bytes") != len(payload) or record.get("sha256") != digest:
                raise ValueError(f"result bundle checksum failed: {name}")
            payloads[name] = payload
            digests[name] = digest
        payloads["bundle.json"] = archive.read("bundle.json")
        return payloads, digests


def _canonical_bracket_manifest(
    payload: bytes,
    target_directory: Path,
    verified_files: dict[str, bytes],
    verified_digests: dict[str, str],
) -> list[dict[str, Any]]:
    manifest = json.loads(payload)
    if not isinstance(manifest, list) or len(manifest) != 5:
        raise ValueError("bracket manifest must describe exactly five brackets")
    ranks = []
    for item in manifest:
        rank = int(item.get("rank", 0))
        if rank not in {1, 2, 3, 4, 5}:
            raise ValueError(f"bracket rank out of range: {rank}")
        ranks.append(rank)
        canvas = item.get("canvas")
        if (
            not isinstance(canvas, dict)
            or int(canvas.get("width", 0)) < 960
            or int(canvas.get("height", 0)) < 540
        ):
            raise ValueError(f"bracket {rank}: invalid canvas")
        files = item.get("files")
        if not isinstance(files, dict) or set(files) != {"png", "svg", "pdf"}:
            raise ValueError(f"bracket {rank}: invalid file manifest")
        for extension, metadata in files.items():
            name = f"brackets/bracket-{rank}.{extension}"
            payload_bytes = verified_files[name]
            if (
                not isinstance(metadata, dict)
                or metadata.get("sha256") != verified_digests[name]
                or metadata.get("bytes") != len(payload_bytes)
            ):
                raise ValueError(f"bracket {rank}: internal checksum mismatch")
            _validate_bracket_asset(
                extension,
                payload_bytes,
                int(canvas["width"]),
                int(canvas["height"]),
            )
            metadata["path"] = (target_directory / f"bracket-{rank}.{extension}").as_posix()
    if sorted(ranks) != [1, 2, 3, 4, 5]:
        raise ValueError("bracket ranks must be 1 through 5")
    return manifest


def _validate_bracket_asset(extension: str, payload: bytes, width: int, height: int) -> None:
    if extension == "png":
        try:
            with Image.open(io.BytesIO(payload)) as image:
                image.verify()
            with Image.open(io.BytesIO(payload)) as image:
                if image.format != "PNG" or image.size != (width, height):
                    raise ValueError("PNG format or dimensions differ from bracket manifest")
        except (OSError, SyntaxError) as exc:
            raise ValueError("invalid bracket PNG") from exc
        return
    if extension == "pdf":
        if not payload.startswith(b"%PDF-") or b"%%EOF" not in payload[-1024:]:
            raise ValueError("invalid bracket PDF")
        return
    if extension != "svg":
        raise ValueError("unsupported bracket asset extension")
    if b"<!DOCTYPE" in payload.upper() or b"<!ENTITY" in payload.upper():
        raise ValueError("unsafe bracket SVG declaration")
    try:
        root = ElementTree.fromstring(payload)
    except ElementTree.ParseError as exc:
        raise ValueError("invalid bracket SVG") from exc
    allowed_tags = {"svg", "rect", "text"}
    if root.attrib.get("width") != str(width) or root.attrib.get("height") != str(height):
        raise ValueError("SVG dimensions differ from bracket manifest")
    for element in root.iter():
        tag = element.tag.rsplit("}", 1)[-1]
        if tag not in allowed_tags:
            raise ValueError(f"unsafe bracket SVG element: {tag}")
        if any(
            attribute.lower().startswith("on") or attribute.lower().endswith("href")
            for attribute in element.attrib
        ):
            raise ValueError("unsafe bracket SVG attribute")


def _relevant_changes(
    previous: dict[str, Any] | None,
    simulations: dict[str, dict[str, Any]],
    base_changes: list[str],
) -> list[str]:
    changes = list(base_changes)
    previous_probability = _argentina_probability((previous or {}).get("simulations", {}))
    current_probability = _argentina_probability(simulations)
    if previous_probability is not None and current_probability is not None:
        delta = current_probability - previous_probability
        if abs(delta) >= 0.05:
            changes.insert(0, f"Argentina {delta:+.2f} pp")
    return changes


def import_local_result(
    settings: Settings,
    bundle_path: Path,
    bundle_sha256: str,
) -> dict[str, Any]:
    files, digests = _read_verified_bundle(bundle_path, settings.local_result_max_bytes * 2)
    bundle = json.loads(files["bundle.json"])
    input_id = _safe_id(bundle.get("input_id"), "input_id")
    job = LocalInputStore(settings.storage_path).load(input_id)
    _validate_frozen_job(settings, job)
    results = json.loads(files["results.json"])
    _validate_result_payload(results, job)
    backtest = json.loads(files["backtest.json"])
    validate_backtest_artifact(backtest)
    if bundle.get("input_id") != input_id or bundle.get("snapshot_id") != job["snapshot_id"]:
        raise ValueError("bundle envelope does not match its result payload")

    current_git_state = _git_state()
    expected_git_state = {
        "git_commit": job["git_commit"],
        "git_dirty": job["git_dirty"],
        "working_tree_sha256": job.get("working_tree_sha256"),
    }
    if current_git_state != expected_git_state:
        raise LocalComputeConflict(
            "server code changed after inputs were frozen; prepare a new run"
        )

    archive = PredictionArchive(settings.storage_path)
    current = archive.load_latest(int(job["format_size"]))
    current_id = current.get("snapshot_id") if current is not None else None
    if current_id not in {job.get("previous_snapshot_id"), job["snapshot_id"]}:
        raise LocalComputeConflict(
            "a newer prediction was published after inputs were frozen; prepare a new run"
        )
    _validate_sources_do_not_downgrade(current, list(job["sources"]))

    scenario = load_scenario(settings.scenario_path_for(int(job["format_size"])))
    if _scenario_sha256(scenario) != job["scenario_sha256"]:
        raise LocalComputeConflict("server scenario changed after inputs were frozen")
    completed_at = _aware_timestamp(results["completed_at"], "completed_at").isoformat()
    simulations = dict(results["simulations"])
    relevant_changes = _relevant_changes(
        current,
        simulations,
        list(job.get("base_relevant_changes", [])),
    )
    summary = " · ".join(
        [
            f"{job['successful_sources']} fuentes actualizadas",
            f"{len(relevant_changes)} cambios relevantes",
            *relevant_changes[:3],
        ]
    )
    snapshot_id = str(job["snapshot_id"])
    final_directory = archive.predictions / snapshot_id
    bracket_directory = final_directory / "brackets"
    bracket_manifest = _canonical_bracket_manifest(
        files["brackets/manifest.json"],
        bracket_directory,
        files,
        digests,
    )
    primary_brackets = simulations[ModelMode.SIRIUS_ONLY.value]["top_brackets"]
    if any(
        not math.isclose(
            float(bracket_manifest[index]["density_percent"]),
            float(primary_brackets[index]["density_percent"]),
            abs_tol=1e-9,
        )
        for index in range(5)
    ):
        raise ValueError("bracket asset densities differ from SIRIUS_ONLY results")
    if any(
        bracket_manifest[index].get("signature") != primary_brackets[index].get("signature")
        or bracket_manifest[index].get("scope") != "SF_AND_FINAL"
        or bracket_manifest[index].get("signature_version") != "decisive-v1"
        or bracket_manifest[index].get("sirius_application") != results["sirius_application"]
        for index in range(5)
    ):
        raise ValueError("bracket assets differ from decisive SIRIUS_ONLY scenarios")
    report_path = final_directory / "report.md"
    bracket_manifest_path = bracket_directory / "manifest.json"
    manifest = {
        "schema_version": "prediction-manifest-v2",
        "snapshot_id": snapshot_id,
        "created_at": completed_at,
        "git_commit": job["git_commit"],
        "git_dirty": job["git_dirty"],
        "working_tree_sha256": job.get("working_tree_sha256"),
        "model_version": job["model_version"],
        "scenario_id": job["scenario_id"],
        "format_size": job["format_size"],
        "scenario_sha256": job["scenario_sha256"],
        "teams_sha256": job["teams_sha256"],
        "sirius_observations_sha256": job["sirius_observations_sha256"],
        "ephemeris": job["ephemeris"],
        "sources": job["sources"],
        "assumptions": job["assumptions"],
        "seed": job["command"]["seed"],
        "final_hour": job["command"]["final_hour"],
        "simulations_count": job["command"]["iterations"],
        "weights": {},
        "simulations": simulations,
        "affected_charts": job["affected_charts"],
        "chart_recalculation": job["chart_recalculation"],
        "sirius_recalculation": {
            "status": "completed",
            "review_snapshot_sha256": job.get("review_snapshot_sha256"),
            "reviewed_observations": job.get("reviewed_observations", 0),
            "modes": list(REQUIRED_MODES),
        },
        "sirius_assessments": results.get("sirius_assessments", {}),
        "sirius_evidence_audit": results.get("sirius_evidence_audit", {}),
        "sirius_application": results["sirius_application"],
        "quality_pending_review": job["quality_pending_review"],
        "claim_persistence": job["claim_persistence"],
        "conflicts": job["conflicts"],
        "relevant_changes": relevant_changes,
        "summary": summary,
        "report_path": report_path.as_posix(),
        "bracket_manifest_path": bracket_manifest_path.as_posix(),
        "execution": {
            "compute_location": "local",
            "input_id": input_id,
            "bundle_sha256": bundle_sha256,
        },
        "notifications": [
            {"channel": "local_event_log", "message": summary, "created_at": completed_at}
        ],
    }
    report = "\n".join(
        [
            f"# Mundial 2030 Sirius Engine · {snapshot_id}",
            "",
            "> Astrología experimental sin validez científica demostrada.",
            "",
            f"- Creado: {completed_at}",
            "- Cómputo: local; publicación validada en Fly",
            f"- Input congelado: {input_id}",
            f"- Bundle SHA-256: {bundle_sha256}",
            f"- Git commit: {job['git_commit']}",
            (f"- Efemérides: {job['ephemeris']['provider']} {job['ephemeris']['version']}"),
            f"- Resumen: {summary}",
            f"- Modos: {', '.join(REQUIRED_MODES)}",
            "",
            "## Cambios",
            *(f"- {change}" for change in relevant_changes),
        ]
    )

    stage_root = archive.predictions
    stage_root.mkdir(parents=True, exist_ok=True)
    created_directory = False
    if final_directory.exists():
        existing_manifest = archive.load(snapshot_id)
        if existing_manifest != manifest:
            raise LocalComputeConflict("immutable prediction already exists with different results")
    else:
        stage = Path(tempfile.mkdtemp(prefix=f".{snapshot_id}-", dir=stage_root))
        try:
            stage_brackets = stage / "brackets"
            stage_brackets.mkdir(parents=True)
            for name in sorted(BRACKET_PATHS):
                (stage / name).write_bytes(files[name])
            (stage_brackets / "manifest.json").write_bytes(
                _json_bytes(bracket_manifest, pretty=True)
            )
            (stage / "report.md").write_text(report, encoding="utf-8")
            (stage / "manifest.json").write_bytes(_json_bytes(manifest, pretty=True))
            stage.replace(final_directory)
            created_directory = True
        except Exception:
            shutil.rmtree(stage, ignore_errors=True)
            raise

    orchestrator = UpdateOrchestrator(settings=settings, collectors=[])
    try:
        persistence = orchestrator._persist_prediction(manifest, scenario)
    except Exception:
        if created_directory:
            shutil.rmtree(final_directory, ignore_errors=True)
        raise
    published_backtest = {
        **backtest,
        "publication": {
            "snapshot_id": snapshot_id,
            "input_id": input_id,
            "bundle_sha256": bundle_sha256,
        },
    }
    backtest_directory = settings.storage_path / "backtests"
    backtest_directory.mkdir(parents=True, exist_ok=True)
    backtest_path = backtest_directory / f"{snapshot_id}.json"
    serialized_backtest = _json_bytes(published_backtest, pretty=True)
    if backtest_path.exists() and backtest_path.read_bytes() != serialized_backtest:
        raise LocalComputeConflict("immutable backtest already exists with different results")
    if not backtest_path.exists():
        backtest_path.write_bytes(serialized_backtest)
    PredictionArchive._atomic_write(
        backtest_directory / "latest.json",
        serialized_backtest.decode(),
    )
    archive.publish(manifest)

    imported_at = datetime.now(UTC).isoformat()
    audit = {
        "schema_version": IMPORT_SCHEMA,
        "input_id": input_id,
        "snapshot_id": snapshot_id,
        "bundle_sha256": bundle_sha256,
        "imported_at": imported_at,
        "persistence": persistence,
    }
    audit_directory = settings.storage_path / "local-compute" / "imports" / input_id
    audit_directory.mkdir(parents=True, exist_ok=True)
    audit_path = audit_directory / f"{bundle_sha256}.json"
    serialized_audit = _json_bytes(audit, pretty=True)
    if not audit_path.exists():
        audit_path.write_bytes(serialized_audit)
    return {
        "status": "published" if created_directory else "already_published",
        "snapshot_id": snapshot_id,
        "format_size": job["format_size"],
        "created_at": completed_at,
        "summary": summary,
        "bundle_sha256": bundle_sha256,
        "persistence": persistence,
    }
