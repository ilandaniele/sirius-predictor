"""Initial professional provenance schema.

Revision ID: 20260817_0001
Revises:
"""

from __future__ import annotations

from alembic import op
from db import models  # noqa: F401
from db.base import Base

revision = "20260817_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    Base.metadata.create_all(bind=op.get_bind())
    qualities = Base.metadata.tables["data_qualities"]
    op.bulk_insert(
        qualities,
        [
            {
                "code": "A",
                "label": "Fuente primaria oficial",
                "precedence": 5,
                "requires_manual_review": False,
            },
            {
                "code": "B",
                "label": "Archivo confiable",
                "precedence": 4,
                "requires_manual_review": False,
            },
            {
                "code": "C",
                "label": "Fuente secundaria",
                "precedence": 3,
                "requires_manual_review": True,
            },
            {
                "code": "D",
                "label": "Pista no verificada",
                "precedence": 2,
                "requires_manual_review": True,
            },
            {
                "code": "X",
                "label": "Supuesto/proyección",
                "precedence": 1,
                "requires_manual_review": True,
            },
        ],
    )


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind())
