"""Add idempotency keys for relational prediction persistence.

Revision ID: 20260820_0005
Revises: 20260820_0004
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision = "20260820_0005"
down_revision = "20260820_0004"
branch_labels = None
depends_on = None


def _create_simulation_runs() -> None:
    op.create_table(
        "simulation_runs",
        sa.Column("run_id", sa.String(length=64), nullable=True),
        sa.Column("prediction_snapshot_id", sa.String(), nullable=False),
        sa.Column("mode", sa.String(length=40), nullable=False),
        sa.Column("seed", sa.Integer(), nullable=False),
        sa.Column("iterations", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["prediction_snapshot_id"],
            ["prediction_snapshots.id"],
            name="fk_simulation_runs_prediction_snapshot_id_prediction_snapshots",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_simulation_runs"),
        sa.UniqueConstraint("run_id", name="uq_simulation_runs_run_id"),
    )


def _create_simulation_paths() -> None:
    op.create_table(
        "simulation_paths",
        sa.Column("simulation_run_id", sa.String(), nullable=False),
        sa.Column("family_rank", sa.Integer(), nullable=False),
        sa.Column("density", sa.Float(), nullable=False),
        sa.Column("champion_team_id", sa.String(), nullable=False),
        sa.Column("bracket", sa.JSON(), nullable=False),
        sa.Column("asset_manifest", sa.JSON(), nullable=False),
        sa.Column("id", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(
            ["champion_team_id"],
            ["teams.id"],
            name="fk_simulation_paths_champion_team_id_teams",
        ),
        sa.ForeignKeyConstraint(
            ["simulation_run_id"],
            ["simulation_runs.id"],
            name="fk_simulation_paths_simulation_run_id_simulation_runs",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_simulation_paths"),
        sa.UniqueConstraint(
            "simulation_run_id",
            "family_rank",
            name="uq_simulation_paths_simulation_run_id",
        ),
    )


def upgrade() -> None:
    inspector = inspect(op.get_bind())
    prediction_columns = {
        column["name"] for column in inspector.get_columns("prediction_snapshots")
    }
    if "snapshot_key" not in prediction_columns:
        with op.batch_alter_table("prediction_snapshots") as batch_op:
            batch_op.add_column(sa.Column("snapshot_key", sa.String(length=64), nullable=True))
            batch_op.add_column(sa.Column("mode", sa.String(length=40), nullable=True))
            batch_op.add_column(sa.Column("format_size", sa.Integer(), nullable=True))
            batch_op.create_unique_constraint(
                "uq_prediction_snapshots_snapshot_key",
                ["snapshot_key", "mode"],
            )
            batch_op.create_check_constraint(
                "valid_prediction_format_size",
                "format_size IS NULL OR format_size IN (48,64)",
            )

    inspector = inspect(op.get_bind())
    tables = set(inspector.get_table_names())
    run_columns = {column["name"] for column in inspector.get_columns("simulation_runs")}
    current_core = {
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
    }
    if not current_core <= run_columns:
        if "simulation_runs_legacy_v0" in tables:
            raise RuntimeError("legacy simulation run archive already exists")
        paths_exist = "simulation_paths" in tables
        if paths_exist:
            if "simulation_paths_legacy_v0" in tables:
                raise RuntimeError("legacy simulation path archive already exists")
            op.rename_table("simulation_paths", "simulation_paths_legacy_v0")
        op.rename_table("simulation_runs", "simulation_runs_legacy_v0")
        _create_simulation_runs()
        if paths_exist:
            _create_simulation_paths()
    elif "run_id" not in run_columns:
        with op.batch_alter_table("simulation_runs") as batch_op:
            batch_op.add_column(sa.Column("run_id", sa.String(length=64), nullable=True))
            batch_op.create_unique_constraint("uq_simulation_runs_run_id", ["run_id"])


def downgrade() -> None:
    inspector = inspect(op.get_bind())
    tables = set(inspector.get_table_names())
    if "simulation_runs_legacy_v0" in tables:
        if "simulation_paths_legacy_v0" in tables:
            op.drop_table("simulation_paths")
        op.drop_table("simulation_runs")
        op.rename_table("simulation_runs_legacy_v0", "simulation_runs")
        if "simulation_paths_legacy_v0" in tables:
            op.rename_table("simulation_paths_legacy_v0", "simulation_paths")
    else:
        run_columns = {column["name"] for column in inspector.get_columns("simulation_runs")}
        if "run_id" in run_columns:
            with op.batch_alter_table("simulation_runs") as batch_op:
                batch_op.drop_constraint("uq_simulation_runs_run_id", type_="unique")
                batch_op.drop_column("run_id")

    inspector = inspect(op.get_bind())
    prediction_columns = {
        column["name"] for column in inspector.get_columns("prediction_snapshots")
    }
    if "snapshot_key" in prediction_columns:
        with op.batch_alter_table("prediction_snapshots") as batch_op:
            batch_op.drop_constraint(
                "ck_prediction_snapshots_valid_prediction_format_size",
                type_="check",
            )
            batch_op.drop_constraint(
                "uq_prediction_snapshots_snapshot_key",
                type_="unique",
            )
            batch_op.drop_column("format_size")
            batch_op.drop_column("mode")
            batch_op.drop_column("snapshot_key")
