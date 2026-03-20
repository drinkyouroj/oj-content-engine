"""add generation_metadata to content_drafts and vertical to topics

Revision ID: 003
Revises: 002
Create Date: 2026-03-20
"""
from __future__ import annotations

from alembic import op

revision: str = "003"
down_revision: str = "002"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE content_drafts ADD COLUMN generation_metadata JSONB DEFAULT '{}'")
    op.execute("ALTER TABLE topics ADD COLUMN vertical VARCHAR(50)")


def downgrade() -> None:
    op.execute("ALTER TABLE content_drafts DROP COLUMN generation_metadata")
    op.execute("ALTER TABLE topics DROP COLUMN vertical")
