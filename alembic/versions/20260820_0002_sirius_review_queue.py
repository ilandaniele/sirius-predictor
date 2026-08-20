"""Add the append-only Sirius archive review queue.

Revision ID: 20260820_0002
Revises: 20260817_0001
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision = "20260820_0002"
down_revision = "20260817_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The initial migration predates explicit per-revision table creation and calls
    # metadata.create_all(). The guards keep a fresh install and an existing install
    # equally safe until that legacy migration can be squashed in a major release.
    existing = set(inspect(op.get_bind()).get_table_names())
    if "sirius_review_candidates" not in existing:
        op.create_table(
            "sirius_review_candidates",
            sa.Column("fingerprint", sa.String(length=64), nullable=False),
            sa.Column("post_id", sa.String(length=160), nullable=False),
            sa.Column("claim_index", sa.Integer(), nullable=False),
            sa.Column("claim_text", sa.Text(), nullable=False),
            sa.Column("title", sa.Text(), nullable=False),
            sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("source_id", sa.String(length=100), nullable=False),
            sa.Column("source_url", sa.Text(), nullable=False),
            sa.Column("consulted_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("quality_code", sa.String(length=1), nullable=False),
            sa.Column("content_sha256", sa.String(length=64), nullable=False),
            sa.Column("technique_mentions", sa.JSON(), nullable=False),
            sa.Column("inferred", sa.Boolean(), nullable=False),
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.CheckConstraint(
                "claim_index >= 0", name="ck_sirius_review_candidates_non_negative_claim_index"
            ),
            sa.ForeignKeyConstraint(
                ["quality_code"],
                ["data_qualities.code"],
                name="fk_sirius_review_candidates_quality_code_data_qualities",
            ),
            sa.PrimaryKeyConstraint("id", name="pk_sirius_review_candidates"),
            sa.UniqueConstraint("fingerprint", name="uq_sirius_review_candidates_fingerprint"),
            sa.UniqueConstraint(
                "post_id",
                "content_sha256",
                "claim_index",
                name="uq_sirius_review_candidates_post_id",
            ),
        )
        op.create_index(
            "ix_sirius_review_candidates_post_id",
            "sirius_review_candidates",
            ["post_id"],
        )
    if "sirius_review_decisions" not in existing:
        op.create_table(
            "sirius_review_decisions",
            sa.Column("candidate_id", sa.String(), nullable=False),
            sa.Column("action", sa.String(length=16), nullable=False),
            sa.Column("reviewer", sa.String(length=160), nullable=False),
            sa.Column("reason", sa.Text(), nullable=False),
            sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("supersedes_decision_id", sa.String(), nullable=True),
            sa.Column("observation", sa.JSON(), nullable=True),
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.CheckConstraint(
                "action IN ('approved','rejected')",
                name="ck_sirius_review_decisions_valid_review_action",
            ),
            sa.ForeignKeyConstraint(
                ["candidate_id"],
                ["sirius_review_candidates.id"],
                name="fk_sirius_review_decisions_candidate_id_sirius_review_candidates",
            ),
            sa.ForeignKeyConstraint(
                ["supersedes_decision_id"],
                ["sirius_review_decisions.id"],
                name="fk_sirius_review_decisions_supersedes_decision_id_sirius_review_decisions",
            ),
            sa.PrimaryKeyConstraint("id", name="pk_sirius_review_decisions"),
        )
        op.create_index(
            "ix_sirius_review_decisions_candidate_id",
            "sirius_review_decisions",
            ["candidate_id"],
        )


def downgrade() -> None:
    existing = set(inspect(op.get_bind()).get_table_names())
    if "sirius_review_decisions" in existing:
        op.drop_index(
            "ix_sirius_review_decisions_candidate_id",
            table_name="sirius_review_decisions",
        )
        op.drop_table("sirius_review_decisions")
    if "sirius_review_candidates" in existing:
        op.drop_index(
            "ix_sirius_review_candidates_post_id",
            table_name="sirius_review_candidates",
        )
        op.drop_table("sirius_review_candidates")
