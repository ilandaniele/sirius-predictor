import json
from datetime import datetime
from pathlib import Path

from collectors.common.base import Collector, CollectorSpec
from packages.common.config import Settings
from packages.common.provenance import DataGrade, SourceClaimInput
from packages.common.types import ModelMode
from packages.montecarlo import run_parallel
from packages.reports import BracketExportSpec
from services.api.update_pipeline import PredictionArchive, UpdateCommand, UpdateOrchestrator

ROOT = Path(__file__).resolve().parents[2]


class StaticCollector(Collector):
    spec = CollectorSpec(
        source_id="static",
        url="https://example.com/static",
        grade=DataGrade.B,
        official=False,
        allowed_hosts=("example.com",),
        terms_url="https://example.com/terms",
        robots_policy="test fixture",
        priority=1,
    )

    def fetch(self) -> bytes:
        return b"stable-payload"

    def parse(self, payload: bytes, consulted_at: datetime) -> list[SourceClaimInput]:
        del payload, consulted_at
        return []


class MutableObservationalCollector(StaticCollector):
    payload = b"first"

    def fetch(self) -> bytes:
        return self.payload


def test_full_update_is_idempotent_and_never_overwrites_prediction(tmp_path) -> None:
    settings = Settings(
        storage_path=tmp_path / "storage",
        scenario_path=ROOT / "data" / "scenario.yaml",
        teams_path=ROOT / "data" / "teams.csv",
        sources_path=ROOT / "data" / "sources.yaml",
    )
    calls = 0

    def simulator(*args, **kwargs):
        nonlocal calls
        calls += 1
        return run_parallel(*args, **kwargs)

    orchestrator = UpdateOrchestrator(
        settings=settings,
        collectors=[StaticCollector()],
        simulator=simulator,
        bracket_spec=BracketExportSpec(960, 540, 20),
    )
    command = UpdateCommand(
        iterations=15,
        seed=2030,
        modes=(ModelMode.FOOTBALL_ONLY, ModelMode.SIRIUS_ONLY, ModelMode.HYBRID),
        workers=1,
    )
    first = orchestrator.run(command)
    second = orchestrator.run(command)
    assert first.snapshot_id == second.snapshot_id
    assert not first.idempotent_replay
    assert second.idempotent_replay
    assert calls == 3
    assert Path(first.manifest_path).exists()
    assert Path(first.report_path).exists()
    manifest = PredictionArchive(settings.storage_path).load(first.snapshot_id)
    assert manifest is not None
    assert manifest["sources"][0]["source_url"] == "https://example.com/static"
    assert manifest["sources"][0]["quality"] == "B"
    assert first.bracket_manifest_path is not None
    assert Path(first.update_event_path).exists()
    assert Path(second.update_event_path).exists()
    assert first.update_event_path != second.update_event_path
    bracket_directory = Path(first.bracket_manifest_path).parent
    assert len(list(bracket_directory.glob("bracket-*.png"))) == 5
    first_bytes = Path(first.manifest_path).read_bytes()
    third = orchestrator.run(
        UpdateCommand(
            iterations=15,
            seed=2031,
            modes=command.modes,
            workers=1,
        )
    )
    assert third.snapshot_id != first.snapshot_id
    assert Path(first.manifest_path).read_bytes() == first_bytes
    archive = PredictionArchive(settings.storage_path)
    assert len(archive.history()) == 2
    assert {row["team_id"] for row in archive.probability_history({"ARG", "ESP"})} == {
        "ARG",
        "ESP",
    }


def test_observational_raw_byte_changes_do_not_invalidate_predictions(tmp_path) -> None:
    settings = Settings(
        storage_path=tmp_path / "storage",
        scenario_path=ROOT / "data" / "scenario.yaml",
        teams_path=ROOT / "data" / "teams.csv",
        sources_path=ROOT / "data" / "sources.yaml",
    )
    collector = MutableObservationalCollector()
    orchestrator = UpdateOrchestrator(
        settings=settings,
        collectors=[collector],
        bracket_spec=BracketExportSpec(960, 540, 20),
    )
    command = UpdateCommand(
        iterations=15,
        seed=2030,
        modes=(ModelMode.FOOTBALL_ONLY,),
        workers=1,
    )
    first = orchestrator.run(command)
    collector.payload = b"dynamic-html-byte-change"
    second = orchestrator.run(command)
    assert second.idempotent_replay
    assert second.snapshot_id == first.snapshot_id
    event = json.loads(Path(second.update_event_path).read_text(encoding="utf-8"))
    assert event["sources"][0]["source_url"] == "https://example.com/static"
    assert event["sources"][0]["quality"] == "B"
    manifest = PredictionArchive(settings.storage_path).load(first.snapshot_id)
    assert manifest is not None
    assert manifest["sources"][0]["model_input"] is False
