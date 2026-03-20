"""add MANUAL source, signal_id FK on topics, nullable scored_signal_id

Revision ID: 004
Revises: 003
Create Date: 2026-03-20
"""
from __future__ import annotations

from alembic import op

revision: str = "004"
down_revision: str = "003"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    # Add 'manual' to signal_source enum
    op.execute("ALTER TYPE signal_source ADD VALUE IF NOT EXISTS 'manual'")

    # Add nullable signal_id column with FK to signals
    op.execute(
        "ALTER TABLE topics ADD COLUMN signal_id UUID "
        "REFERENCES signals(id) ON DELETE CASCADE"
    )

    # Make scored_signal_id nullable
    op.execute(
        "ALTER TABLE topics ALTER COLUMN scored_signal_id DROP NOT NULL"
    )

    # Backfill signal_id from scored_signals
    op.execute(
        "UPDATE topics t SET signal_id = ss.signal_id "
        "FROM scored_signals ss WHERE t.scored_signal_id = ss.id"
    )


def downgrade() -> None:
    # Restore NOT NULL on scored_signal_id (set orphans to a dummy if needed)
    op.execute(
        "ALTER TABLE topics ALTER COLUMN scored_signal_id SET NOT NULL"
    )

    # Drop signal_id column
    op.execute("ALTER TABLE topics DROP COLUMN signal_id")

    # Note: cannot remove a value from a Postgres enum without recreating it.
    # 'manual' value is left in signal_source enum on downgrade.
