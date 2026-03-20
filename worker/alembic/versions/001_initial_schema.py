"""initial schema — 7 tables

Revision ID: 001
Revises:
Create Date: 2026-03-19
"""
from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "001"
down_revision: str | None = None
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    """Create all 5 Postgres ENUMs and 7 tables in dependency order."""

    # Enums
    op.execute("CREATE TYPE signal_source AS ENUM ('rss', 'reddit', 'hn', 'twitter')")
    op.execute("CREATE TYPE scoring_status AS ENUM ('pending', 'scored', 'failed')")
    op.execute("CREATE TYPE topic_status AS ENUM ('queued', 'review', 'generating', 'generated', 'snoozed', 'archived', 'killed')")
    op.execute("CREATE TYPE platform AS ENUM ('substack', 'twitter', 'linkedin', 'instagram')")
    op.execute("CREATE TYPE draft_status AS ENUM ('draft', 'review', 'approved', 'published', 'killed')")

    # Independent tables (no FKs)
    op.execute("""
        CREATE TABLE voice_exemplars (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            content TEXT NOT NULL,
            platform platform NOT NULL,
            active BOOLEAN NOT NULL DEFAULT true,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)

    op.execute("""
        CREATE TABLE scoring_adjustments (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            keyword TEXT NOT NULL,
            dimension TEXT NOT NULL,
            adjustment INTEGER NOT NULL,
            created_by TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT ck_adjustment_range CHECK (adjustment >= -20 AND adjustment <= 20)
        )
    """)

    op.execute("""
        CREATE TABLE system_alerts (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            source TEXT NOT NULL,
            alert_type TEXT NOT NULL,
            consecutive_failures INTEGER NOT NULL DEFAULT 0,
            last_failure_at TIMESTAMPTZ,
            resolved_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)

    # FK chain: signals -> scored_signals -> topics -> content_drafts
    op.execute("""
        CREATE TABLE signals (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            source signal_source NOT NULL,
            url TEXT NOT NULL,
            title TEXT NOT NULL,
            body_preview TEXT,
            discovered_at TIMESTAMPTZ NOT NULL,
            source_metrics JSONB,
            dedup_hash TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_signals_dedup_hash UNIQUE (dedup_hash)
        )
    """)

    op.execute("""
        CREATE TABLE scored_signals (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            signal_id UUID NOT NULL REFERENCES signals(id) ON DELETE CASCADE,
            score_breakdown JSONB NOT NULL,
            composite_score NUMERIC(5,2) NOT NULL,
            status scoring_status NOT NULL DEFAULT 'pending',
            pass1_completed_at TIMESTAMPTZ,
            pass2_completed_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)

    op.execute("""
        CREATE TABLE topics (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            scored_signal_id UUID NOT NULL REFERENCES scored_signals(id) ON DELETE CASCADE,
            status topic_status NOT NULL,
            thesis TEXT,
            thesis_provided BOOLEAN NOT NULL DEFAULT false,
            queued_at TIMESTAMPTZ,
            reviewed_by TEXT,
            review_decision TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)

    op.execute("""
        CREATE TABLE content_drafts (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            topic_id UUID NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
            platform platform NOT NULL,
            content TEXT NOT NULL,
            status draft_status NOT NULL DEFAULT 'draft',
            notion_page_id TEXT,
            model_used TEXT,
            token_cost NUMERIC(8,4),
            image_url TEXT,
            generated_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)


def downgrade() -> None:
    """Drop all tables and enums in reverse dependency order."""

    op.execute("DROP TABLE IF EXISTS content_drafts CASCADE")
    op.execute("DROP TABLE IF EXISTS topics CASCADE")
    op.execute("DROP TABLE IF EXISTS scored_signals CASCADE")
    op.execute("DROP TABLE IF EXISTS signals CASCADE")
    op.execute("DROP TABLE IF EXISTS system_alerts CASCADE")
    op.execute("DROP TABLE IF EXISTS scoring_adjustments CASCADE")
    op.execute("DROP TABLE IF EXISTS voice_exemplars CASCADE")

    op.execute("DROP TYPE IF EXISTS draft_status")
    op.execute("DROP TYPE IF EXISTS platform")
    op.execute("DROP TYPE IF EXISTS topic_status")
    op.execute("DROP TYPE IF EXISTS scoring_status")
    op.execute("DROP TYPE IF EXISTS signal_source")
