"""Snapshot provenance on append-only source claims.

Revision ID: 20260820_0004
Revises: 20260820_0003
"""

from __future__ import annotations

import hashlib

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision = "20260820_0004"
down_revision = "20260820_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("source_claims")}
    if "fingerprint" in columns:
        return

    op.add_column(
        "source_claims",
        sa.Column("fingerprint", sa.String(length=64), nullable=True),
    )
    op.add_column("source_claims", sa.Column("source_url", sa.Text(), nullable=True))
    op.add_column(
        "source_claims",
        sa.Column("quality_code", sa.String(length=1), nullable=True),
    )
    rows = bind.execute(
        sa.text(
            "SELECT source_claims.id, sources.url, sources.quality_code "
            "FROM source_claims JOIN sources ON sources.id = source_claims.source_id"
        )
    ).mappings()
    for row in rows:
        fingerprint = hashlib.sha256(f"legacy-source-claim:{row['id']}".encode()).hexdigest()
        bind.execute(
            sa.text(
                "UPDATE source_claims SET fingerprint = :fingerprint, "
                "source_url = :source_url, quality_code = :quality_code WHERE id = :id"
            ),
            {
                "fingerprint": fingerprint,
                "source_url": row["url"],
                "quality_code": row["quality_code"],
                "id": row["id"],
            },
        )
    with op.batch_alter_table("source_claims") as batch_op:
        batch_op.alter_column("fingerprint", existing_type=sa.String(length=64), nullable=False)
        batch_op.alter_column("quality_code", existing_type=sa.String(length=1), nullable=False)
        batch_op.create_unique_constraint("uq_source_claims_fingerprint", ["fingerprint"])
        batch_op.create_foreign_key(
            "fk_source_claims_quality_code_data_qualities",
            "data_qualities",
            ["quality_code"],
            ["code"],
        )


def downgrade() -> None:
    inspector = inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("source_claims")}
    if "fingerprint" not in columns:
        return
    with op.batch_alter_table("source_claims") as batch_op:
        batch_op.drop_constraint(
            "fk_source_claims_quality_code_data_qualities",
            type_="foreignkey",
        )
        batch_op.drop_constraint("uq_source_claims_fingerprint", type_="unique")
        batch_op.drop_column("quality_code")
        batch_op.drop_column("source_url")
        batch_op.drop_column("fingerprint")
