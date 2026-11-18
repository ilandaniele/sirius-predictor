"""Add a content-addressed key to immutable astrology charts.

Revision ID: 20260820_0003
Revises: 20260820_0002
"""

from __future__ import annotations

import hashlib

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision = "20260820_0003"
down_revision = "20260820_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("astrology_charts")}
    if "input_hash" in columns:
        return

    op.add_column(
        "astrology_charts",
        sa.Column("input_hash", sa.String(length=64), nullable=True),
    )
    rows = bind.execute(sa.text("SELECT id FROM astrology_charts")).mappings()
    for row in rows:
        legacy_hash = hashlib.sha256(f"legacy-astrology-chart:{row['id']}".encode()).hexdigest()
        bind.execute(
            sa.text("UPDATE astrology_charts SET input_hash = :value WHERE id = :id"),
            {"value": legacy_hash, "id": row["id"]},
        )
    with op.batch_alter_table("astrology_charts") as batch_op:
        batch_op.alter_column("input_hash", existing_type=sa.String(length=64), nullable=False)
        batch_op.create_unique_constraint(
            "uq_astrology_charts_input_hash",
            ["input_hash"],
        )


def downgrade() -> None:
    inspector = inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("astrology_charts")}
    if "input_hash" not in columns:
        return
    unique_names = {
        constraint["name"] for constraint in inspector.get_unique_constraints("astrology_charts")
    }
    with op.batch_alter_table("astrology_charts") as batch_op:
        if "uq_astrology_charts_input_hash" in unique_names:
            batch_op.drop_constraint("uq_astrology_charts_input_hash", type_="unique")
        batch_op.drop_column("input_hash")
