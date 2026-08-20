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
    engine.dispose()


def test_birth_data_check_constraint_is_postgresql_boolean_safe() -> None:
    ddl = str(CreateTable(BirthData.__table__).compile(dialect=postgresql.dialect()))
    assert "time_known IS FALSE" in ddl
    assert "time_known = 0" not in ddl


def test_chart_cache_migration_backfills_an_existing_schema(tmp_path: Path) -> None:
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

    command.upgrade(config, "head")
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
