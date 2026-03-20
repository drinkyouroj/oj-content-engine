"""add vertical column to voice_exemplars

Revision ID: 002
Revises: 001
Create Date: 2026-03-20
"""
from __future__ import annotations

from alembic import op

revision: str = "002"
down_revision: str = "001"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE voice_exemplars ADD COLUMN vertical VARCHAR(50) DEFAULT 'general'")


def downgrade() -> None:
    op.execute("ALTER TABLE voice_exemplars DROP COLUMN vertical")
