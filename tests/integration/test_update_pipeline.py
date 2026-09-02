import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from collectors.common.base import Collector, CollectorOutcome, CollectorSpec
from collectors.common.pipeline import UpdateReport
from db.base import Base
from db.models import AstrologyChart, PredictionSnapshot, SimulationRun, SourceClaim
from engine.config import load_scenario
from packages.common.config import Settings
from packages.common.provenance import DataGrade, SourceClaimInput
from packages.common.types import ModelMode
from packages.montecarlo import run_parallel
from packages.reports import BracketExportSpec
from services.api.update_pipeline import (
    PredictionArchive,
    UpdateCommand,
    UpdateOrchestrator,
    _attach_review_snapshot,
    _input_hash,
    _source_manifest,
)

pytestmark = pytest.mark.integration

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


class OfficialFixtureCollector(StaticCollector):
    spec = CollectorSpec(
        source_id="official-fixture-source",
        url="https://example.com/fixture",
        grade=DataGrade.A,
        official=True,
        allowed_hosts=("example.com",),
        terms_url="https://example.com/terms",
        robots_policy="test fixture",
        priority=1,
    )

    def parse(self, payload: bytes, consulted_at: datetime) -> list[SourceClaimInput]:
        del payload
        return [
            SourceClaimInput(
                entity_type="Fixture",
                entity_key="final-2030",
                field_name="kickoff",
                value={
                    "chart_request": {
                        "moment": "2030-07-21T18:00:00+02:00",
                        "time_known": True,
                        "house_system": "P",
                        "location": None,
                        "bodies": ["Sun", "Moon"],
                        "orbs": {},
                        "label": "Final Mundial 2030",
                    }
                },
                source_id=self.spec.source_id,
                source_url=self.spec.url,
                consulted_at=consulted_at,
                grade=DataGrade.A,
                confidence=1.0,
                official=True,
            )
        ]


def test_full_update_is_idempotent_and_never_overwrites_prediction(tmp_path) -> None:
    database_url = f"sqlite:///{(tmp_path / 'full-update.db').as_posix()}"
    database_engine = create_engine(database_url)
    Base.metadata.create_all(database_engine)
    database_engine.dispose()
    settings = Settings(
        storage_path=tmp_path / "storage",
        database_url=database_url,
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
    database_url = f"sqlite:///{(tmp_path / 'observational.db').as_posix()}"
    database_engine = create_engine(database_url)
    Base.metadata.create_all(database_engine)
    database_engine.dispose()
    settings = Settings(
        storage_path=tmp_path / "storage",
        database_url=database_url,
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
    assert PredictionArchive(settings.storage_path).latest_update_event() == event
    assert second.summary.endswith("predicción sin cambios")
    manifest = PredictionArchive(settings.storage_path).load(first.snapshot_id)
    assert manifest is not None
    assert manifest["sources"][0]["model_input"] is False


def test_reviewed_snapshot_invalidates_inputs_while_raw_archive_stays_observational() -> None:
    scenario = load_scenario(ROOT / "data" / "scenario.yaml")
    command = UpdateCommand(
        iterations=100,
        seed=2030,
        modes=(ModelMode.HYBRID,),
    )
    sources = [
        {
            "source_id": "sirius_blog",
            "effective_sha256": "raw-html-does-not-enter-model",
            "model_input": False,
        }
    ]
    _attach_review_snapshot(
        sources,
        {
            "snapshot_id": "a" * 64,
            "path": "storage/sirius-review/snapshots/a.yaml",
            "reviewed_observations": 0,
        },
    )
    empty_review_hash = _input_hash(command, scenario, sources)
    _attach_review_snapshot(
        sources,
        {
            "snapshot_id": "b" * 64,
            "path": "storage/sirius-review/snapshots/b.yaml",
            "reviewed_observations": 1,
        },
    )
    assert _input_hash(command, scenario, sources) != empty_review_hash


def test_failed_fetch_retains_the_previous_immutable_snapshot_path() -> None:
    previous_path = "storage/source_snapshots/sirius_blog/previous.bin"
    previous = {
        "sources": [
            {
                "source_id": "sirius_blog",
                "effective_sha256": "a" * 64,
                "snapshot_path": previous_path,
                "model_input": False,
            }
        ]
    }
    report = UpdateReport(
        outcomes=[
            CollectorOutcome(
                source_id="sirius_blog",
                source_url="https://astrologiadeportivaa.blogspot.com/",
                quality=DataGrade.B,
                consulted_at=datetime(2026, 8, 20, tzinfo=UTC),
                status="error",
                error="test failure",
            )
        ]
    )
    source = _source_manifest(report, previous)[0]
    assert source["retained_previous"] is True
    assert source["snapshot_path"] == previous_path


def test_accepted_observational_claim_is_not_mislabeled_as_model_input() -> None:
    claim = SourceClaimInput(
        entity_type="RankingSnapshot",
        entity_key="ARG",
        field_name="rank",
        value=2,
        source_id="fifa_ranking",
        source_url="https://api.fifa.com/api/v3/fifarankings/rankings/example",
        consulted_at=datetime(2026, 8, 20, tzinfo=UTC),
        grade=DataGrade.A,
        confidence=1.0,
        official=True,
    )
    report = UpdateReport(
        outcomes=[
            CollectorOutcome(
                source_id="fifa_ranking",
                source_url="https://api.fifa.com/api/v3/fifarankings/rankings/example",
                quality=DataGrade.A,
                consulted_at=claim.consulted_at,
                status="success",
                payload_sha256="f" * 64,
                claims=[claim],
            )
        ],
        accepted=[claim],
    )
    source = _source_manifest(report, None)[0]
    assert source["model_input"] is False


def test_update_pipeline_recalculates_only_accepted_complete_charts(tmp_path) -> None:
    database_path = tmp_path / "charts.db"
    database_url = f"sqlite:///{database_path.as_posix()}"
    engine = create_engine(database_url)
    Base.metadata.create_all(engine)
    settings = Settings(
        storage_path=tmp_path / "storage",
        database_url=database_url,
        scenario_path=ROOT / "data" / "scenario.yaml",
        teams_path=ROOT / "data" / "teams.csv",
        sources_path=ROOT / "data" / "sources.yaml",
    )
    orchestrator = UpdateOrchestrator(
        settings=settings,
        collectors=[OfficialFixtureCollector()],
    )
    first = orchestrator.run(
        UpdateCommand(
            iterations=15,
            seed=2030,
            modes=(ModelMode.FOOTBALL_ONLY,),
            workers=1,
        )
    )
    second = orchestrator.run(
        UpdateCommand(
            iterations=15,
            seed=2031,
            modes=(ModelMode.FOOTBALL_ONLY,),
            workers=1,
        )
    )

    first_manifest = PredictionArchive(settings.storage_path).load(first.snapshot_id)
    second_manifest = PredictionArchive(settings.storage_path).load(second.snapshot_id)
    assert first_manifest is not None
    assert second_manifest is not None
    assert first_manifest["affected_charts"] == ["Fixture:final-2030"]
    assert first_manifest["chart_recalculation"]["recalculated_count"] == 1
    assert first_manifest["chart_recalculation"]["cache_hit_count"] == 0
    # sources.yaml grows over time as new fact-checked sources are added (natal data,
    # blogs, etc.); +1 accounts for OfficialFixtureCollector, which isn't cataloged there.
    catalog_size = len(yaml.safe_load((ROOT / "data" / "sources.yaml").read_text("utf-8")))
    assert first_manifest["claim_persistence"] == {
        "observed": 1,
        "inserted": 1,
        "duplicates": 0,
        "eligible": 1,
        "pending": 0,
        "sources_created": catalog_size + 1,
        "sources_updated": 0,
    }
    assert second_manifest["chart_recalculation"]["recalculated_count"] == 0
    assert second_manifest["chart_recalculation"]["cache_hit_count"] == 1
    assert second_manifest["claim_persistence"]["inserted"] == 0
    assert second_manifest["claim_persistence"]["duplicates"] == 1
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(AstrologyChart)) == 1
        assert session.scalar(select(func.count()).select_from(SourceClaim)) == 1
        assert session.scalar(select(func.count()).select_from(PredictionSnapshot)) == 2
        assert session.scalar(select(func.count()).select_from(SimulationRun)) == 2
    engine.dispose()
