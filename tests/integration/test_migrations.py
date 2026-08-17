from pathlib import Path

from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from alembic import command


def test_initial_migration_creates_complete_schema(tmp_path: Path) -> None:
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
