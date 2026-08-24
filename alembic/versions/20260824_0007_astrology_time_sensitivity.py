"""Add the astrology_time_sensitivity cache for unknown-time subjects.

Revision ID: 20260824_0007
Revises: 20260820_0006
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision = "20260824_0007"
down_revision = "20260820_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    existing = set(inspect(op.get_bind()).get_table_names())
    if "astrology_time_sensitivity" not in existing:
        op.create_table(
            "astrology_time_sensitivity",
            sa.Column("subject_type", sa.String(length=60), nullable=False),
            sa.Column("subject_id", sa.String(length=64), nullable=False),
            sa.Column("input_hash", sa.String(length=64), nullable=False),
            sa.Column("birth_date", sa.Date(), nullable=False),
            sa.Column("timezone", sa.String(length=80), nullable=False),
            sa.Column("latitude", sa.Float(), nullable=True),
            sa.Column("longitude", sa.Float(), nullable=True),
            sa.Column("step_minutes", sa.Integer(), nullable=False),
            sa.Column("ephemeris_version", sa.String(length=80), nullable=False),
            sa.Column("result", sa.JSON(), nullable=False),
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id", name="pk_astrology_time_sensitivity"),
            sa.UniqueConstraint(
                "input_hash", name="uq_astrology_time_sensitivity_input_hash"
            ),
        )
        op.create_index(
            "ix_astrology_time_sensitivity_subject_id",
            "astrology_time_sensitivity",
            ["subject_id"],
        )


def downgrade() -> None:
    existing = set(inspect(op.get_bind()).get_table_names())
    if "astrology_time_sensitivity" in existing:
        op.drop_index(
            "ix_astrology_time_sensitivity_subject_id",
            table_name="astrology_time_sensitivity",
        )
        op.drop_table("astrology_time_sensitivity")
