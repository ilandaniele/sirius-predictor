"""Allow descriptive status values for the 48- and 64-team scenarios.

Revision ID: 20260820_0006
Revises: 20260820_0005
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision = "20260820_0006"
down_revision = "20260820_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if "tournaments" not in inspect(op.get_bind()).get_table_names():
        return
    with op.batch_alter_table("tournaments") as batch_op:
        batch_op.alter_column(
            "status",
            existing_type=sa.String(length=40),
            type_=sa.String(length=100),
            existing_nullable=False,
        )


def downgrade() -> None:
    if "tournaments" not in inspect(op.get_bind()).get_table_names():
        return
    with op.batch_alter_table("tournaments") as batch_op:
        batch_op.alter_column(
            "status",
            existing_type=sa.String(length=100),
            type_=sa.String(length=40),
            existing_nullable=False,
        )
