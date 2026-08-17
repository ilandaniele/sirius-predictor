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
        "prediction_snapshots",
        "simulation_paths",
        "backtest_runs",
    } <= tables
    with engine.connect() as connection:
        grades = connection.execute(text("SELECT code FROM data_qualities ORDER BY code")).scalars()
        assert set(grades) == {"A", "B", "C", "D", "X"}
    engine.dispose()


def test_birth_data_check_constraint_is_postgresql_boolean_safe() -> None:
    ddl = str(CreateTable(BirthData.__table__).compile(dialect=postgresql.dialect()))
    assert "time_known IS FALSE" in ddl
    assert "time_known = 0" not in ddl
