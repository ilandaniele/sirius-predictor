from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from alembic import command
from db.models import BirthData

pytestmark = pytest.mark.integration


def test_initial_migration_creates_complete_schema(tmp_path: Path, monkeypatch) -> None:
    # The integration workflow already migrates PostgreSQL before pytest. This
    # isolated check intentionally exercises a fresh SQLite database.
    monkeypatch.delenv("SIRIUS_DATABASE_URL", raising=False)
    database_path = tmp_path / "schema.db"
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path.as_posix()}")
    command.upgrade(config, "head")
    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    tables = set(inspect(engine).get_table_names())
    assert {
        "teams",
        "source_claims",
        "birth_data",
        "astrology_charts",
        "sirius_review_candidates",
        "sirius_review_decisions",
        "prediction_snapshots",
        "simulation_paths",
        "backtest_runs",
    } <= tables
    with engine.connect() as connection:
        grades = connection.execute(text("SELECT code FROM data_qualities ORDER BY code")).scalars()
        assert set(grades) == {"A", "B", "C", "D", "X"}
    chart_columns = {
        column["name"]: column for column in inspect(engine).get_columns("astrology_charts")
    }
    assert chart_columns["input_hash"]["nullable"] is False
    chart_unique_columns = {
        tuple(constraint["column_names"])
        for constraint in inspect(engine).get_unique_constraints("astrology_charts")
    }
    assert ("input_hash",) in chart_unique_columns
    claim_columns = {
        column["name"]: column for column in inspect(engine).get_columns("source_claims")
    }
    assert claim_columns["fingerprint"]["nullable"] is False
    assert claim_columns["quality_code"]["nullable"] is False
    assert "source_url" in claim_columns
    prediction_columns = {
        column["name"] for column in inspect(engine).get_columns("prediction_snapshots")
    }
    assert {"snapshot_key", "mode", "format_size"} <= prediction_columns
    run_columns = {column["name"] for column in inspect(engine).get_columns("simulation_runs")}
    assert "run_id" in run_columns
    tournament_columns = {
        column["name"]: column for column in inspect(engine).get_columns("tournaments")
    }
    assert tournament_columns["status"]["type"].length == 100
    engine.dispose()


def test_birth_data_check_constraint_is_postgresql_boolean_safe() -> None:
    ddl = str(CreateTable(BirthData.__table__).compile(dialect=postgresql.dialect()))
    assert "time_known IS FALSE" in ddl
    assert "time_known = 0" not in ddl


def test_chart_cache_migration_backfills_an_existing_schema(tmp_path: Path, monkeypatch) -> None:
    # The CI integration job exports PostgreSQL for the application migration.
    # This test deliberately targets its own legacy SQLite database.
    monkeypatch.delenv("SIRIUS_DATABASE_URL", raising=False)
    database_path = tmp_path / "legacy-schema.db"
    database_url = f"sqlite:///{database_path.as_posix()}"
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", database_url)
    command.stamp(config, "20260820_0002")
    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE astrology_charts ("
                "id VARCHAR NOT NULL PRIMARY KEY, "
                "subject_type VARCHAR(60) NOT NULL"
                ")"
            )
        )
        connection.execute(
            text(
                "INSERT INTO astrology_charts (id, subject_type) VALUES ('legacy-chart', 'Fixture')"
            )
        )
    engine.dispose()

    command.upgrade(config, "20260820_0003")
    migrated = create_engine(database_url)
    with migrated.connect() as connection:
        input_hash = connection.execute(
            text("SELECT input_hash FROM astrology_charts WHERE id = 'legacy-chart'")
        ).scalar_one()
    assert len(input_hash) == 64
    columns = {
        column["name"]: column for column in inspect(migrated).get_columns("astrology_charts")
    }
    assert columns["input_hash"]["nullable"] is False
    migrated.dispose()


def test_source_claim_migration_backfills_provenance_snapshot(tmp_path: Path, monkeypatch) -> None:
    # Keep the isolated Alembic Config authoritative over the CI database URL.
    monkeypatch.delenv("SIRIUS_DATABASE_URL", raising=False)
    database_path = tmp_path / "legacy-claims.db"
    database_url = f"sqlite:///{database_path.as_posix()}"
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", database_url)
    command.stamp(config, "20260820_0003")
    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(
            text("CREATE TABLE data_qualities (code VARCHAR(1) NOT NULL PRIMARY KEY)")
        )
        connection.execute(text("INSERT INTO data_qualities (code) VALUES ('A')"))
        connection.execute(
            text(
                "CREATE TABLE sources ("
                "id VARCHAR NOT NULL PRIMARY KEY, url TEXT, quality_code VARCHAR(1) NOT NULL"
                ")"
            )
        )
        connection.execute(
            text(
                "INSERT INTO sources (id, url, quality_code) "
                "VALUES ('source-1', 'https://example.com/source', 'A')"
            )
        )
        connection.execute(
            text(
                "CREATE TABLE source_claims ("
                "id VARCHAR NOT NULL PRIMARY KEY, source_id VARCHAR NOT NULL"
                ")"
            )
        )
        connection.execute(
            text("INSERT INTO source_claims (id, source_id) VALUES ('claim-1', 'source-1')")
        )
    engine.dispose()

    command.upgrade(config, "20260820_0004")
    migrated = create_engine(database_url)
    with migrated.connect() as connection:
        row = connection.execute(
            text(
                "SELECT fingerprint, source_url, quality_code "
                "FROM source_claims WHERE id = 'claim-1'"
            )
        ).one()
    assert len(row.fingerprint) == 64
    assert row.source_url == "https://example.com/source"
    assert row.quality_code == "A"
    migrated.dispose()


def test_prediction_persistence_migration_preserves_legacy_rows(
    tmp_path: Path, monkeypatch
) -> None:
    # Do not let the integration service URL redirect this legacy-schema test.
    monkeypatch.delenv("SIRIUS_DATABASE_URL", raising=False)
    database_path = tmp_path / "legacy-predictions.db"
    database_url = f"sqlite:///{database_path.as_posix()}"
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", database_url)
    command.stamp(config, "20260820_0004")
    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(
            text("CREATE TABLE prediction_snapshots (id VARCHAR NOT NULL PRIMARY KEY)")
        )
        connection.execute(text("INSERT INTO prediction_snapshots (id) VALUES ('legacy')"))
        connection.execute(
            text(
                "CREATE TABLE simulation_runs ("
                "run_id TEXT NOT NULL PRIMARY KEY, created_at TEXT NOT NULL, "
                "manifest_json TEXT NOT NULL, summary_json TEXT NOT NULL"
                ")"
            )
        )
        connection.execute(
            text(
                "INSERT INTO simulation_runs "
                "(run_id, created_at, manifest_json, summary_json) VALUES "
                "('legacy-run', '2026-08-17T00:00:00Z', '{}', '{}')"
            )
        )
        connection.execute(text("CREATE TABLE simulation_paths (id VARCHAR NOT NULL PRIMARY KEY)"))
        connection.execute(text("INSERT INTO simulation_paths (id) VALUES ('legacy-path')"))
    engine.dispose()

    command.upgrade(config, "head")
    migrated = create_engine(database_url)
    prediction_columns = {
        column["name"] for column in inspect(migrated).get_columns("prediction_snapshots")
    }
    run_columns = {column["name"] for column in inspect(migrated).get_columns("simulation_runs")}
    assert {"snapshot_key", "mode", "format_size"} <= prediction_columns
    assert {
        "run_id",
        "prediction_snapshot_id",
        "mode",
        "seed",
        "iterations",
        "status",
        "started_at",
        "finished_at",
        "result",
        "id",
        "created_at",
    } <= run_columns
    assert {"simulation_runs_legacy_v0", "simulation_paths_legacy_v0"} <= set(
        inspect(migrated).get_table_names()
    )
    with migrated.connect() as connection:
        assert (
            connection.execute(
                text("SELECT id FROM prediction_snapshots WHERE id = 'legacy'")
            ).scalar_one()
            == "legacy"
        )
        assert (
            connection.execute(
                text("SELECT run_id FROM simulation_runs_legacy_v0 WHERE run_id = 'legacy-run'")
            ).scalar_one()
            == "legacy-run"
        )
        assert (
            connection.execute(
                text("SELECT id FROM simulation_paths_legacy_v0 WHERE id = 'legacy-path'")
            ).scalar_one()
            == "legacy-path"
        )
    migrated.dispose()
