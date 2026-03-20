"""initial schema — 7 tables

Revision ID: 001
Revises:
Create Date: 2026-03-19
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = "001"
down_revision: str | None = None
branch_labels: str | None = None
depends_on: str | None = None

# ---------------------------------------------------------------------------
# Enum definitions — created before tables, dropped after tables
# ---------------------------------------------------------------------------
signal_source_enum = sa.Enum(
    "rss", "reddit", "hn", "twitter", name="signal_source"
)
scoring_status_enum = sa.Enum(
    "pending", "scored", "failed", name="scoring_status"
)
topic_status_enum = sa.Enum(
    "queued", "review", "generating", "generated", "snoozed", "archived", "killed",
    name="topic_status",
)
platform_enum = sa.Enum(
    "substack", "twitter", "linkedin", "instagram", name="platform"
)
draft_status_enum = sa.Enum(
    "draft", "review", "approved", "published", "killed", name="draft_status"
)


def upgrade() -> None:
    """Create all 5 Postgres ENUMs and 7 tables in dependency order."""

    # --- Enums ---------------------------------------------------------------
    signal_source_enum.create(op.get_bind(), checkfirst=True)
    scoring_status_enum.create(op.get_bind(), checkfirst=True)
    topic_status_enum.create(op.get_bind(), checkfirst=True)
    platform_enum.create(op.get_bind(), checkfirst=True)
    draft_status_enum.create(op.get_bind(), checkfirst=True)

    # --- Independent tables (no FKs) ----------------------------------------

    op.create_table(
        "voice_exemplars",
        sa.Column("id", sa.Uuid, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column(
            "platform",
            sa.Enum("substack", "twitter", "linkedin", "instagram", name="platform", create_type=False),
            nullable=False,
        ),
        sa.Column("active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    op.create_table(
        "scoring_adjustments",
        sa.Column("id", sa.Uuid, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("keyword", sa.Text, nullable=False),
        sa.Column("dimension", sa.Text, nullable=False),
        sa.Column("adjustment", sa.Integer, nullable=False),
        sa.Column("created_by", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("adjustment >= -20 AND adjustment <= 20", name="ck_adjustment_range"),
    )

    op.create_table(
        "system_alerts",
        sa.Column("id", sa.Uuid, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("source", sa.Text, nullable=False),
        sa.Column("alert_type", sa.Text, nullable=False),
        sa.Column("consecutive_failures", sa.Integer, nullable=False, server_default="0"),
        sa.Column("last_failure_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    # --- FK chain: signals -> scored_signals -> topics -> content_drafts -----

    op.create_table(
        "signals",
        sa.Column("id", sa.Uuid, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "source",
            sa.Enum("rss", "reddit", "hn", "twitter", name="signal_source", create_type=False),
            nullable=False,
        ),
        sa.Column("url", sa.Text, nullable=False),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("body_preview", sa.Text, nullable=True),
        sa.Column("discovered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_metrics", JSONB, nullable=True),
        sa.Column("dedup_hash", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("dedup_hash", name="uq_signals_dedup_hash"),
    )

    op.create_table(
        "scored_signals",
        sa.Column("id", sa.Uuid, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "signal_id", sa.Uuid,
            sa.ForeignKey("signals.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("score_breakdown", JSONB, nullable=False),
        sa.Column("composite_score", sa.Numeric(5, 2), nullable=False),
        sa.Column(
            "status",
            sa.Enum("pending", "scored", "failed", name="scoring_status", create_type=False),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("pass1_completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("pass2_completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    op.create_table(
        "topics",
        sa.Column("id", sa.Uuid, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "scored_signal_id", sa.Uuid,
            sa.ForeignKey("scored_signals.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "queued", "review", "generating", "generated", "snoozed", "archived", "killed",
                name="topic_status", create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("thesis", sa.Text, nullable=True),
        sa.Column("thesis_provided", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("queued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_by", sa.Text, nullable=True),
        sa.Column("review_decision", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    op.create_table(
        "content_drafts",
        sa.Column("id", sa.Uuid, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "topic_id", sa.Uuid,
            sa.ForeignKey("topics.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "platform",
            sa.Enum("substack", "twitter", "linkedin", "instagram", name="platform", create_type=False),
            nullable=False,
        ),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column(
            "status",
            sa.Enum("draft", "review", "approved", "published", "killed", name="draft_status", create_type=False),
            nullable=False,
            server_default="draft",
        ),
        sa.Column("notion_page_id", sa.Text, nullable=True),
        sa.Column("model_used", sa.Text, nullable=True),
        sa.Column("token_cost", sa.Numeric(8, 4), nullable=True),
        sa.Column("image_url", sa.Text, nullable=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )


def downgrade() -> None:
    """Drop all tables and enums in reverse dependency order."""

    # --- Tables (reverse of creation order) ----------------------------------
    op.drop_table("content_drafts")
    op.drop_table("topics")
    op.drop_table("scored_signals")
    op.drop_table("signals")
    op.drop_table("system_alerts")
    op.drop_table("scoring_adjustments")
    op.drop_table("voice_exemplars")

    # --- Enums ---------------------------------------------------------------
    draft_status_enum.drop(op.get_bind(), checkfirst=True)
    platform_enum.drop(op.get_bind(), checkfirst=True)
    topic_status_enum.drop(op.get_bind(), checkfirst=True)
    scoring_status_enum.drop(op.get_bind(), checkfirst=True)
    signal_source_enum.drop(op.get_bind(), checkfirst=True)
